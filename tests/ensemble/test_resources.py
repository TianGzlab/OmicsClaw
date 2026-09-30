"""The resource pool: atomic grants, backfill that never delays the head, admission.

Two properties carry the design. Grants are atomic, so a trial never holds a
GPU while waiting for memory and the pool cannot deadlock. Backfill lets a
small CPU-only trial use memory and CPUs the queue head cannot use yet, but
only out of what is left after the head's needs are set aside — otherwise a
stream of small trials could starve a large one forever. Admission never
refuses a request for *wanting* a GPU: a ``preferred`` method runs on CPU and
says so (``degraded``), only a ``required`` one fails, and that failure is a
trial result rather than a tool error.
"""

from __future__ import annotations

import asyncio

import pytest

from omicsclaw.ensemble.resources import (
    QueueTimeout,
    ResourcePool,
    ResourceRequest,
    parse_size_gb,
    pool_memory_gb,
)


def _run(coro, timeout=5.0):
    async def guarded():
        return await asyncio.wait_for(coro, timeout)

    return asyncio.run(guarded())


def _pool(gpus=("0", "1"), memory=100.0, cpus=16, slots=1):
    return ResourcePool(gpu_ids=gpus, slots_per_gpu=slots, memory_gb=memory, cpus=cpus)


class _Holder:
    """Acquires on request and holds until released."""

    def __init__(self, pool, request, *, max_wait_s=None):
        self.pool = pool
        self.admission = pool.admit(request)
        self.max_wait_s = max_wait_s
        self.lease = None
        self.error = None
        self.granted = asyncio.Event()
        self.release = asyncio.Event()
        self.task = asyncio.ensure_future(self._hold())

    async def _hold(self):
        try:
            async with self.pool.acquire(self.admission, max_wait_s=self.max_wait_s) as lease:
                self.lease = lease
                self.granted.set()
                await self.release.wait()
        except Exception as exc:
            self.error = exc
            self.granted.set()


async def _settle():
    for _ in range(5):
        await asyncio.sleep(0)


# ---- admission --------------------------------------------------------------------


@pytest.mark.parametrize(
    "gpu, has_gpu, use_gpu, degraded, refused",
    [
        ("none", True, False, "", False),
        ("none", False, False, "", False),
        ("preferred", True, True, "", False),
        ("preferred", False, False, "no_gpu", False),
        ("required", True, True, "", False),
        ("required", False, False, "", True),
    ],
)
def test_the_admission_table(gpu, has_gpu, use_gpu, degraded, refused):
    pool = _pool(gpus=("0",) if has_gpu else (), )
    admission = pool.admit(ResourceRequest(gpu, 4, 2))
    assert admission.use_gpu is use_gpu
    assert admission.degraded == degraded
    assert bool(admission.refused) is refused
    if refused:
        assert "requires a GPU" in admission.refused


def test_a_refusal_names_the_detection_result():
    pool = ResourcePool(gpu_ids=(), memory_gb=10, cpus=2, gpu_detail="nvidia-smi is not on PATH")
    assert "nvidia-smi is not on PATH" in pool.admit(ResourceRequest("required", 1, 1)).refused


def test_requests_beyond_the_totals_are_refused_at_admission():
    pool = _pool(memory=64, cpus=8)
    assert "64 GB in total" in pool.admit(ResourceRequest("none", 65, 1)).refused
    assert "8 in total" in pool.admit(ResourceRequest("none", 1, 9)).refused


def test_a_refused_admission_cannot_be_acquired():
    pool = _pool(gpus=())

    async def main():
        async with pool.acquire(pool.admit(ResourceRequest("required", 1, 1))):
            pass

    with pytest.raises(ValueError, match="refused"):
        _run(main())


# ---- grants -----------------------------------------------------------------------------


def test_grants_are_atomic_and_gpu_ids_are_not_shared():
    async def main():
        pool = _pool(gpus=("0", "1"), memory=100, cpus=16)
        a = _Holder(pool, ResourceRequest("preferred", 10, 2))
        b = _Holder(pool, ResourceRequest("preferred", 10, 2))
        c = _Holder(pool, ResourceRequest("preferred", 10, 2))
        await _settle()
        assert a.granted.is_set() and b.granted.is_set() and not c.granted.is_set()
        assert {a.lease.gpu, b.lease.gpu} == {"0", "1"}
        assert pool.snapshot()["memory_free_gb"] == 80
        a.release.set()
        await c.granted.wait()
        assert c.lease.gpu == a.lease.gpu
        b.release.set()
        c.release.set()
        await asyncio.gather(a.task, b.task, c.task)
        assert pool.snapshot() == {"gpu_used": {"0": 0, "1": 0}, "memory_free_gb": 100, "cpus_free": 16, "queued": 0}

    _run(main())


def test_slots_per_gpu_allows_sharing_a_device():
    async def main():
        pool = _pool(gpus=("0",), slots=2)
        a = _Holder(pool, ResourceRequest("preferred", 1, 1))
        b = _Holder(pool, ResourceRequest("preferred", 1, 1))
        await _settle()
        assert a.lease.gpu == b.lease.gpu == "0"
        a.release.set(); b.release.set()
        await asyncio.gather(a.task, b.task)

    _run(main())


def test_a_cpu_trial_backfills_while_the_head_waits_for_a_gpu():
    async def main():
        pool = _pool(gpus=("0",), memory=100, cpus=16)
        gpu_holder = _Holder(pool, ResourceRequest("preferred", 10, 2))
        await _settle()
        head = _Holder(pool, ResourceRequest("preferred", 30, 4))
        small = _Holder(pool, ResourceRequest("none", 20, 4))
        await _settle()
        assert not head.granted.is_set()
        assert small.granted.is_set(), "a CPU trial fits beside the head's reservation"
        gpu_holder.release.set()
        await head.granted.wait()
        for holder in (head, small):
            holder.release.set()
        await asyncio.gather(gpu_holder.task, head.task, small.task)

    _run(main())


def test_backfill_never_takes_memory_the_head_needs():
    async def main():
        pool = _pool(gpus=("0",), memory=100, cpus=16)
        gpu_holder = _Holder(pool, ResourceRequest("preferred", 10, 2))
        await _settle()
        head = _Holder(pool, ResourceRequest("preferred", 60, 4))
        hungry = _Holder(pool, ResourceRequest("none", 45, 2))
        await _settle()
        assert not hungry.granted.is_set(), "90 free - 60 for the head leaves 30, not 45"
        gpu_holder.release.set()
        await head.granted.wait()
        await _settle()
        assert not hungry.granted.is_set()
        head.release.set()
        await hungry.granted.wait()
        hungry.release.set()
        await asyncio.gather(gpu_holder.task, head.task, hungry.task)

    _run(main())


def test_a_head_short_of_memory_is_not_overtaken_by_memory_eaters():
    async def main():
        pool = _pool(gpus=(), memory=100, cpus=16)
        big = _Holder(pool, ResourceRequest("none", 70, 2))
        await _settle()
        head = _Holder(pool, ResourceRequest("none", 50, 2))
        eater = _Holder(pool, ResourceRequest("none", 20, 2))
        await _settle()
        assert not head.granted.is_set() and not eater.granted.is_set()
        big.release.set()
        await head.granted.wait()
        await eater.granted.wait()
        head.release.set(); eater.release.set()
        await asyncio.gather(big.task, head.task, eater.task)

    _run(main())


def test_cancelling_a_waiter_leaks_nothing():
    async def main():
        pool = _pool(gpus=("0",))
        holder = _Holder(pool, ResourceRequest("preferred", 10, 2))
        await _settle()
        waiter = _Holder(pool, ResourceRequest("preferred", 10, 2))
        await _settle()
        waiter.task.cancel()
        await asyncio.gather(waiter.task, return_exceptions=True)
        assert pool.snapshot()["queued"] == 0
        holder.release.set()
        await holder.task
        assert pool.snapshot()["gpu_used"] == {"0": 0}
        assert pool.snapshot()["memory_free_gb"] == 100

    _run(main())


def test_waiting_longer_than_allowed_is_a_queue_timeout():
    async def main():
        pool = _pool(gpus=("0",))
        holder = _Holder(pool, ResourceRequest("preferred", 10, 2))
        await _settle()
        late = _Holder(pool, ResourceRequest("preferred", 10, 2), max_wait_s=0.05)
        await late.granted.wait()
        assert isinstance(late.error, QueueTimeout)
        assert "queued longer than 0.05 s" in str(late.error)
        assert pool.snapshot()["queued"] == 0
        holder.release.set()
        await holder.task

    _run(main())


# ---- sizes and pool memory ----------------------------------------------------------------


def test_sizes_parse_like_docker():
    assert parse_size_gb("64g") == 64
    assert parse_size_gb("512m") == 0.5
    assert parse_size_gb("1t") == 1024
    assert parse_size_gb("1557G") == 1557
    with pytest.raises(ValueError):
        parse_size_gb("lots")


def test_pool_memory_on_this_machine_and_in_the_sandbox():
    assert pool_memory_gb(base_gb=1557, reserved_gb=64) == 1493
    assert pool_memory_gb(base_gb=1557, tmpfs_gb=64, shm_gb=128, reserved_gb=64) == 1301


def test_an_explicit_pool_memory_is_capped_by_the_formula():
    assert pool_memory_gb(base_gb=1557, reserved_gb=64, configured_gb=200) == 200
    assert pool_memory_gb(base_gb=1557, tmpfs_gb=64, shm_gb=128, reserved_gb=64, configured_gb=5000) == 1301


def test_a_pool_without_memory_is_an_error():
    with pytest.raises(ValueError, match="-"):
        pool_memory_gb(base_gb=100, tmpfs_gb=64, shm_gb=128, reserved_gb=64)
