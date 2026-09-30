"""The GPU, memory and CPU pool that concurrent trials share, and GPU detection.

A trial asks for all of its resources at once and gets all of them or waits
for all of them, so no trial holds one resource while waiting for another and
the pool cannot deadlock. Waiters are served in arrival order, with backfill:
when the head of the queue cannot start, a later request may start only if it
fits in what is free *after* setting aside what the head needs, so backfill
never delays the head.

One pool per process. Two processes on one machine do not see each other's
leases.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import shutil
import subprocess
from collections import deque
from dataclasses import dataclass, field
from typing import AsyncIterator, Literal, Mapping, Sequence

__all__ = [
    "Admission",
    "GpuDetection",
    "Lease",
    "QueueTimeout",
    "ResourcePool",
    "ResourceRequest",
    "detect_gpus",
    "parse_gpu_setting",
    "parse_size_gb",
    "pool_memory_gb",
]

GpuMode = Literal["none", "preferred", "required"]

NVIDIA_SMI_QUERY = "nvidia-smi --query-gpu=index --format=csv,noheader"


class QueueTimeout(TimeoutError):
    """A request waited in the queue longer than it was allowed to."""


@dataclass(frozen=True, slots=True)
class ResourceRequest:
    """What one trial needs: GPU mode, memory in GB, CPUs."""

    gpu: GpuMode
    memory_gb: float
    cpus: int


@dataclass(frozen=True, slots=True)
class Admission:
    """The pool's decision about a request before it queues.

    ``use_gpu`` says whether it will take a GPU slot. ``degraded`` is
    ``"no_gpu"`` when a GPU was preferred and the pool has none. ``refused``
    is the reason it can never run here, or ``""``.
    """

    request: ResourceRequest
    use_gpu: bool
    degraded: str = ""
    refused: str = ""

    @property
    def admitted(self) -> bool:
        return not self.refused


@dataclass(frozen=True, slots=True)
class Lease:
    """What a running trial holds. ``gpu`` is the device id, or ``None``."""

    gpu: str | None
    memory_gb: float
    cpus: int


@dataclass
class _Waiter:
    admission: Admission
    future: asyncio.Future = field(repr=False)


class ResourcePool:
    """GPU slots, memory and CPUs, granted atomically in arrival order with backfill.

    :param gpu_ids: Device ids trials may be given (``CUDA_VISIBLE_DEVICES`` values).
    :param slots_per_gpu: Concurrent trials per device.
    :param memory_gb: Memory the pool may hand out in total.
    :param cpus: CPUs the pool may hand out in total.
    :param gpu_detail: How the GPU list was obtained, repeated in refusals.
    :raises ValueError: A non-positive memory, CPU or slot count.
    """

    def __init__(
        self,
        *,
        gpu_ids: Sequence[str],
        slots_per_gpu: int = 1,
        memory_gb: float,
        cpus: int,
        gpu_detail: str = "",
    ) -> None:
        if slots_per_gpu < 1:
            raise ValueError(f"slots_per_gpu must be at least 1; got {slots_per_gpu}")
        if memory_gb <= 0:
            raise ValueError(f"memory_gb must be positive; got {memory_gb}")
        if cpus < 1:
            raise ValueError(f"cpus must be at least 1; got {cpus}")
        self.gpu_ids: tuple[str, ...] = tuple(dict.fromkeys(str(g) for g in gpu_ids))
        self.slots_per_gpu = slots_per_gpu
        self.memory_gb = float(memory_gb)
        self.cpus = int(cpus)
        self.gpu_detail = gpu_detail
        self._gpu_used: dict[str, int] = {gpu: 0 for gpu in self.gpu_ids}
        self._memory_free = self.memory_gb
        self._cpus_free = self.cpus
        self._queue: deque[_Waiter] = deque()

    # ---- decisions ---------------------------------------------------------

    def admit(self, request: ResourceRequest) -> Admission:
        """Decide device and feasibility; never refuses a request for wanting a GPU it may skip."""
        if request.memory_gb > self.memory_gb:
            return Admission(
                request, False,
                refused=f"requests {request.memory_gb:g} GB of memory; the pool has {self.memory_gb:g} GB in total",
            )
        if request.cpus > self.cpus:
            return Admission(
                request, False,
                refused=f"requests {request.cpus} CPUs; the pool has {self.cpus} in total",
            )
        if request.gpu == "none":
            return Admission(request, False)
        if self.gpu_ids:
            return Admission(request, True)
        if request.gpu == "preferred":
            return Admission(request, False, degraded="no_gpu")
        detail = f" ({self.gpu_detail})" if self.gpu_detail else ""
        return Admission(request, False, refused=f"method requires a GPU; none detected{detail}")

    @contextlib.asynccontextmanager
    async def acquire(
        self,
        admission: Admission,
        *,
        max_wait_s: float | None = None,
    ) -> AsyncIterator[Lease]:
        """Hold the admitted resources for the block.

        :raises ValueError: The admission was refused.
        :raises QueueTimeout: The request waited more than *max_wait_s*.
        """
        if not admission.admitted:
            raise ValueError(f"a refused request cannot be acquired: {admission.refused}")
        lease = await self._wait(admission, max_wait_s)
        try:
            yield lease
        finally:
            self._release(lease)

    # ---- state ---------------------------------------------------------------

    def snapshot(self) -> dict:
        """Free and used amounts, and the queue length."""
        return {
            "gpu_used": dict(self._gpu_used),
            "memory_free_gb": self._memory_free,
            "cpus_free": self._cpus_free,
            "queued": len(self._queue),
        }

    @property
    def gpu_slots_free(self) -> int:
        return sum(self.slots_per_gpu - used for used in self._gpu_used.values())

    # ---- internals -------------------------------------------------------------

    async def _wait(self, admission: Admission, max_wait_s: float | None) -> Lease:
        loop = asyncio.get_running_loop()
        waiter = _Waiter(admission, loop.create_future())
        self._queue.append(waiter)
        self._dispatch()
        try:
            if max_wait_s is None:
                return await asyncio.shield(waiter.future)
            try:
                async with asyncio.timeout(max_wait_s):
                    return await asyncio.shield(waiter.future)
            except TimeoutError:
                if waiter.future.done() and not waiter.future.cancelled():
                    return waiter.future.result()
                raise QueueTimeout(f"queued longer than {max_wait_s:g} s") from None
        except BaseException:
            if waiter.future.done() and not waiter.future.cancelled():
                if waiter not in self._queue:
                    self._release(waiter.future.result())
            else:
                waiter.future.cancel()
            with contextlib.suppress(ValueError):
                self._queue.remove(waiter)
            self._dispatch()
            raise

    def _needs(self, admission: Admission) -> tuple[int, float, int]:
        return (1 if admission.use_gpu else 0, admission.request.memory_gb, admission.request.cpus)

    def _fits(self, needs: tuple[int, float, int], free: tuple[int, float, int]) -> bool:
        return all(need <= have + 1e-9 for need, have in zip(needs, free))

    def _free(self) -> tuple[int, float, int]:
        return (self.gpu_slots_free, self._memory_free, self._cpus_free)

    def _dispatch(self) -> None:
        while self._queue and self._queue[0].future.done():
            self._queue.popleft()
        while self._queue:
            head = self._queue[0]
            if not self._fits(self._needs(head.admission), self._free()):
                break
            self._queue.popleft()
            self._grant(head)
        if not self._queue:
            return
        head_needs = self._needs(self._queue[0].admission)
        for waiter in list(self._queue)[1:]:
            if waiter.future.done():
                continue
            free = self._free()
            spare = tuple(max(0.0, have - need) for have, need in zip(free, head_needs))
            if self._fits(self._needs(waiter.admission), spare):  # type: ignore[arg-type]
                self._queue.remove(waiter)
                self._grant(waiter)

    def _grant(self, waiter: _Waiter) -> None:
        request = waiter.admission.request
        gpu: str | None = None
        if waiter.admission.use_gpu:
            gpu = min(
                (g for g in self.gpu_ids if self._gpu_used[g] < self.slots_per_gpu),
                key=lambda g: (self._gpu_used[g], self.gpu_ids.index(g)),
            )
            self._gpu_used[gpu] += 1
        self._memory_free -= request.memory_gb
        self._cpus_free -= request.cpus
        waiter.future.set_result(Lease(gpu=gpu, memory_gb=request.memory_gb, cpus=request.cpus))

    def _release(self, lease: Lease) -> None:
        if lease.gpu is not None:
            self._gpu_used[lease.gpu] -= 1
        self._memory_free += lease.memory_gb
        self._cpus_free += lease.cpus
        self._dispatch()


# ---- sizes and memory ------------------------------------------------------------

_SIZE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kmgt]?)b?\s*$", re.IGNORECASE)
_UNIT_GB = {"": 1 / 1024**3, "k": 1 / 1024**2, "m": 1 / 1024, "g": 1.0, "t": 1024.0}


def parse_size_gb(text: str) -> float:
    """A Docker size (``"64g"``, ``"512m"``, a byte count) in GiB.

    :raises ValueError: The text is not a size.
    """
    match = _SIZE.match(text or "")
    if match is None:
        raise ValueError(f"{text!r} is not a size such as 64g or 512m")
    return float(match.group(1)) * _UNIT_GB[match.group(2).lower()]


def pool_memory_gb(
    *,
    base_gb: float,
    tmpfs_gb: float = 0.0,
    shm_gb: float = 0.0,
    reserved_gb: float,
    configured_gb: float = 0.0,
) -> float:
    """``base - tmpfs - shm - reserved``, or the configured value if smaller.

    :raises ValueError: The result is not positive.
    """
    available = base_gb - tmpfs_gb - shm_gb - reserved_gb
    if configured_gb > 0:
        available = min(configured_gb, available)
    if available <= 0:
        raise ValueError(
            f"the ensemble pool would have {available:g} GB of memory "
            f"(base {base_gb:g} - tmpfs {tmpfs_gb:g} - shm {shm_gb:g} - reserved {reserved_gb:g})"
        )
    return available


# ---- GPU detection ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GpuDetection:
    """The GPUs trials may use, how that was decided, and any warning to log."""

    ids: tuple[str, ...]
    source: Literal["detected", "configured", "none"]
    detail: str = ""
    warning: str = ""

    def describe(self) -> str:
        if self.source == "configured":
            return f"{len(self.ids)} (configured)"
        if self.ids:
            return f"{len(self.ids)} (detected)"
        return f"0 (none detected: {self.detail})" if self.detail else "0 (none)"


def parse_gpu_setting(setting: str) -> tuple[str, ...] | None:
    """``None`` for auto-detection (``""``), ``()`` for ``none``, else the listed ids.

    :raises ValueError: A list entry is empty.
    """
    value = (setting or "").strip()
    if not value:
        return None
    if value.lower() == "none":
        return ()
    ids = tuple(part.strip() for part in value.split(","))
    if any(not part for part in ids):
        raise ValueError(f"{setting!r} is not a comma-separated list of GPU ids")
    return ids


def _parse_indices(output: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in output.splitlines() if line.strip().isdigit())


def _visible(ids: tuple[str, ...], env: Mapping[str, str]) -> tuple[str, ...]:
    if "CUDA_VISIBLE_DEVICES" not in env:
        return ids
    allowed = {part.strip() for part in env["CUDA_VISIBLE_DEVICES"].split(",") if part.strip()}
    return tuple(gpu for gpu in ids if gpu in allowed)


async def detect_gpus(
    setting: str,
    *,
    environment=None,
    cwd: str = "/",
    sandbox_gpus: str = "",
    env: Mapping[str, str] | None = None,
    timeout_s: float = 30.0,
) -> GpuDetection:
    """Resolve ``ensemble_gpus``: configured ids, ``none``, or detect with ``nvidia-smi``.

    Detection runs on this machine, or inside the sandbox when *environment*
    (a ``BashEnvironment``) is given. A sandbox started without ``--gpus``
    cannot see a GPU, so none is detected and a warning is returned. On this
    machine, a ``CUDA_VISIBLE_DEVICES`` in *env* (default ``os.environ``)
    narrows what is detected.
    Never raises for a missing or failing ``nvidia-smi``: that is zero GPUs.
    """
    configured = parse_gpu_setting(setting)
    if configured is not None:
        if not configured:
            return GpuDetection((), "none", detail="ensemble_gpus is none")
        return GpuDetection(configured, "configured")

    if environment is not None:
        if not sandbox_gpus:
            return GpuDetection(
                (),
                "detected",
                detail="the sandbox was started without GPUs",
                warning="the sandbox does not pass GPUs through (set --sandbox-gpus); ensemble trials run on CPU",
            )
        try:
            outcome = await environment.run_bash(NVIDIA_SMI_QUERY, cwd, timeout_s)
        except Exception as exc:  # detection failure is zero GPUs, reported
            return GpuDetection((), "detected", detail=f"nvidia-smi in the sandbox failed: {exc}")
        if outcome.exit_code != 0:
            return GpuDetection(
                (), "detected", detail=f"nvidia-smi in the sandbox exited {outcome.exit_code}"
            )
        ids = _parse_indices(outcome.output)
        return GpuDetection(ids, "detected", detail="" if ids else "nvidia-smi listed no GPU")

    source = os.environ if env is None else env
    if shutil.which("nvidia-smi", path=source.get("PATH")) is None:
        return GpuDetection((), "detected", detail="nvidia-smi is not on PATH")
    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            NVIDIA_SMI_QUERY.split(),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=dict(source),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return GpuDetection((), "detected", detail=f"nvidia-smi failed: {exc}")
    if completed.returncode != 0:
        return GpuDetection((), "detected", detail=f"nvidia-smi exited {completed.returncode}")
    ids = _visible(_parse_indices(completed.stdout), source)
    return GpuDetection(ids, "detected", detail="" if ids else "nvidia-smi listed no visible GPU")
