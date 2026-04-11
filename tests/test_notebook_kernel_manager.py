"""Unit regressions for `NotebookKernelManager`'s lifecycle hot-spots.

These tests hit the manager directly — not via the FastAPI router — so
we can exercise the get_or_start / dead-kernel / idle-reaper / execute
lock paths without spawning a real IPython kernel. A lightweight
``_FakeKm`` stand-in satisfies the ``AsyncKernelManager`` surface the
manager actually uses (``is_alive`` / ``interrupt_kernel`` /
``shutdown_kernel``) and a matching ``_FakeClient`` satisfies
``stop_channels``.

The scenarios cover the four things most likely to break quietly in
production: kernel identity, dead-kernel replacement, idle cleanup, and
concurrent-execute serialization via the per-handle asyncio lock. See
the issue review that triggered this file for the motivation.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

pytest.importorskip("jupyter_client")

from omicsclaw.app.notebook import kernel_manager as km_module
from omicsclaw.app.notebook.kernel_manager import KernelHandle, NotebookKernelManager


# ---------------------------------------------------------------------------
# Minimal fakes
# ---------------------------------------------------------------------------


class _FakeKm:
    """AsyncKernelManager stand-in.

    Only implements the subset `NotebookKernelManager` actually calls:
    ``is_alive`` (async), ``interrupt_kernel`` (async), and
    ``shutdown_kernel`` (async). State changes go through ``kill()`` and
    ``restore()`` so individual tests can flip a kernel between alive
    and dead without racing an asyncio task.
    """

    def __init__(self) -> None:
        self._alive = True
        self.shutdown_calls = 0
        self.interrupt_calls = 0

    def kill(self) -> None:
        self._alive = False

    async def is_alive(self) -> bool:
        return self._alive

    async def interrupt_kernel(self) -> None:
        self.interrupt_calls += 1

    async def shutdown_kernel(self, now: bool = False) -> None:
        self._alive = False
        self.shutdown_calls += 1


class _FakeClient:
    """IPython client stand-in — only ``stop_channels`` is called."""

    def __init__(self) -> None:
        self.stopped = False

    def stop_channels(self) -> None:
        self.stopped = True


def _make_fake_handle(
    notebook_id: str,
    cwd: str | None = None,
) -> KernelHandle:
    return KernelHandle(
        notebook_id=notebook_id,
        km=_FakeKm(),
        client=_FakeClient(),
        cwd=cwd,
    )


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch) -> NotebookKernelManager:
    """A manager instance whose ``_start_kernel`` produces fake handles.

    Also stubs out the reaper bootstrap so tests don't race against a
    background task they didn't create; each test that needs the reaper
    starts it explicitly.
    """
    mgr = NotebookKernelManager()

    async def fake_start(self: NotebookKernelManager, notebook_id: str, cwd: str | None):  # noqa: ARG001
        return _make_fake_handle(notebook_id, cwd)

    monkeypatch.setattr(NotebookKernelManager, "_start_kernel", fake_start, raising=True)
    # Pin the reaper off — individual tests call `_idle_reaper` / pop
    # the registry themselves to keep timing deterministic.
    monkeypatch.setattr(
        NotebookKernelManager, "_ensure_reaper", lambda self: None, raising=True
    )
    # Defang `resolve_live_session` so no live-session logic interferes
    # with the local-kernel path we're exercising.
    monkeypatch.setattr(km_module, "resolve_live_session", lambda _fp: None)
    return mgr


# ---------------------------------------------------------------------------
# get_or_start identity + dead-kernel replacement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_or_start_returns_same_handle_when_kernel_is_alive(
    manager: NotebookKernelManager,
) -> None:
    first = await manager.get_or_start("nbk_abc")
    second = await manager.get_or_start("nbk_abc")
    assert first is second, "alive kernels must be reused, not re-created"


@pytest.mark.asyncio
async def test_get_or_start_replaces_a_dead_kernel(
    manager: NotebookKernelManager,
) -> None:
    first = await manager.get_or_start("nbk_abc")
    assert isinstance(first.km, _FakeKm)
    first.km.kill()

    replacement = await manager.get_or_start("nbk_abc")
    assert replacement is not first, (
        "dead kernels must be replaced on the next get_or_start()"
    )
    # The old fake was shut down during the dead-kernel cleanup.
    assert first.km.shutdown_calls == 1
    # And the registry only holds the replacement now.
    assert manager.get_handle("nbk_abc") is replacement


# ---------------------------------------------------------------------------
# stop() + shutdown_all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_coordinated_shutdown_removes_registry_entry(
    manager: NotebookKernelManager,
) -> None:
    handle = await manager.get_or_start("nbk_abc")
    assert manager.get_handle("nbk_abc") is handle

    stopped = await manager.stop("nbk_abc")
    assert stopped is True
    assert manager.get_handle("nbk_abc") is None
    assert handle.km.shutdown_calls == 1


@pytest.mark.asyncio
async def test_stop_returns_false_for_missing_notebook(
    manager: NotebookKernelManager,
) -> None:
    assert await manager.stop("nbk_missing") is False


# ---------------------------------------------------------------------------
# interrupt()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_interrupt_forwards_sigint_to_the_live_handle(
    manager: NotebookKernelManager,
) -> None:
    """The most load-bearing assertion in the whole feature: clicking
    the Stop button in the UI has to eventually turn into
    ``handle.km.interrupt_kernel()`` being called on the exact kernel
    that is currently executing work for that notebook."""
    handle = await manager.get_or_start("nbk_abc")
    assert isinstance(handle.km, _FakeKm)

    ok = await manager.interrupt("nbk_abc")

    assert ok is True
    assert handle.km.interrupt_calls == 1
    # Interrupt must NOT tear down the kernel — the cell is expected to
    # recover cleanly and accept further work.
    assert manager.get_handle("nbk_abc") is handle
    assert handle.km.shutdown_calls == 0


@pytest.mark.asyncio
async def test_interrupt_returns_false_for_missing_notebook(
    manager: NotebookKernelManager,
) -> None:
    """No kernel for that id → router turns this into HTTP 404 so the
    UI can surface "nothing to interrupt" rather than silently no-op."""
    assert await manager.interrupt("nbk_missing") is False


@pytest.mark.asyncio
async def test_interrupt_returns_false_when_kernel_interrupt_raises(
    manager: NotebookKernelManager,
) -> None:
    """If the underlying kernel raises while processing SIGINT, the
    manager must surface that as False (not swallow into success) so
    the router can translate it into a real HTTP error the user sees."""
    handle = await manager.get_or_start("nbk_abc")
    assert isinstance(handle.km, _FakeKm)

    async def boom() -> None:
        raise RuntimeError("kernel is unhappy")

    handle.km.interrupt_kernel = boom  # type: ignore[method-assign]

    ok = await manager.interrupt("nbk_abc")
    assert ok is False
    # The handle must not be evicted on a failed interrupt — the kernel
    # is still there, the interrupt just didn't land.
    assert manager.get_handle("nbk_abc") is handle


# ---------------------------------------------------------------------------
# Idle reaper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idle_reaper_evicts_stale_handles(
    manager: NotebookKernelManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A handle that has been idle past the TTL should be shut down and
    removed from the registry the next time the reaper runs."""
    handle = await manager.get_or_start("nbk_abc")
    handle.last_activity = time.time() - (km_module.IDLE_KERNEL_TTL_SECONDS + 10)

    # Run the reaper loop just long enough to execute exactly one sweep,
    # then cancel. Using a tiny interval keeps the test fast without
    # depending on wall-clock behavior.
    monkeypatch.setattr(km_module, "IDLE_REAPER_INTERVAL_SECONDS", 0.01)

    reaper = asyncio.create_task(manager._idle_reaper())
    # Yield control a few times to let the reaper observe the stale
    # handle and finish its cleanup pass.
    for _ in range(20):
        await asyncio.sleep(0.01)
        if manager.get_handle("nbk_abc") is None:
            break
    reaper.cancel()
    # The reaper swallows CancelledError by design — await just to let
    # the task unwind cleanly before we make our assertions.
    try:
        await reaper
    except asyncio.CancelledError:
        pass

    assert manager.get_handle("nbk_abc") is None, (
        "idle reaper must evict stale handles"
    )
    assert handle.km.shutdown_calls == 1


@pytest.mark.asyncio
async def test_idle_reaper_leaves_busy_handles_alone(
    manager: NotebookKernelManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A locked handle is actively executing — the reaper must never
    evict it, regardless of how old its last_activity is."""
    handle = await manager.get_or_start("nbk_abc")
    handle.last_activity = time.time() - (km_module.IDLE_KERNEL_TTL_SECONDS + 10)

    monkeypatch.setattr(km_module, "IDLE_REAPER_INTERVAL_SECONDS", 0.01)

    async with handle.lock:
        reaper = asyncio.create_task(manager._idle_reaper())
        # Give the reaper a few sweeps with the lock held.
        for _ in range(5):
            await asyncio.sleep(0.01)
        reaper.cancel()
        try:
            await reaper
        except asyncio.CancelledError:
            pass
        assert manager.get_handle("nbk_abc") is handle


# ---------------------------------------------------------------------------
# Per-handle lock serializes execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_lock_serializes_concurrent_work(
    manager: NotebookKernelManager,
) -> None:
    """``handle.lock`` is the single-writer gate that keeps two cells
    from interleaving iopub reads on the same kernel. This test pins
    down that contract at the asyncio-Lock level so a refactor can't
    accidentally downgrade it (e.g. to an RLock or drop it entirely)."""
    handle = await manager.get_or_start("nbk_abc")

    order: list[str] = []

    async def worker(name: str, hold: float) -> None:
        async with handle.lock:
            order.append(f"{name}-enter")
            await asyncio.sleep(hold)
            order.append(f"{name}-exit")

    # Kick off three concurrent workers. Because they all contend for
    # the same lock, we must observe each enter/exit pair atomically —
    # never ``A-enter, B-enter``.
    await asyncio.gather(
        worker("a", 0.02),
        worker("b", 0.02),
        worker("c", 0.02),
    )

    for i in range(0, len(order), 2):
        enter = order[i]
        exit_ = order[i + 1]
        assert enter.endswith("-enter") and exit_.endswith("-exit")
        assert enter.split("-")[0] == exit_.split("-")[0], (
            f"interleaved execution observed at index {i}: {order!r}"
        )


# ---------------------------------------------------------------------------
# live → local switch
# ---------------------------------------------------------------------------


class _FakeLiveBinding:
    """Stand-in for LiveSessionBinding — we only need the manager to
    see "a binding exists", the body of its fields is never touched by
    the test scenarios below."""

    def __init__(self) -> None:
        self.session = _FakeLiveSession()
        self.state = _FakeLiveState()
        self.cwd = "/tmp/live"


class _FakeLiveSession:
    class _Km:
        def is_alive(self) -> bool:
            return True

    def __init__(self) -> None:
        self.km = self._Km()


class _FakeLiveState:
    def __init__(self) -> None:
        self.last_activity = time.time()
        self.status = "idle"

    def touch(self) -> None:
        self.last_activity = time.time()


@pytest.mark.asyncio
async def test_live_binding_cleans_up_an_existing_local_kernel(
    manager: NotebookKernelManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a live pipeline session becomes available for a notebook
    that already has a local kernel running, the manager must shut down
    the local one before routing work to the live one — otherwise the
    user would have two kernels talking to the same notebook state."""
    handle = await manager.get_or_start("nbk_abc")
    assert manager.get_handle("nbk_abc") is handle

    fake_live = _FakeLiveBinding()
    monkeypatch.setattr(km_module, "resolve_live_session", lambda _fp: fake_live)
    monkeypatch.setattr(km_module, "is_live_session_running", lambda _live: True)

    status = await manager.status("nbk_abc", file_path="/tmp/live/analysis.ipynb")

    assert status["source"] == "live"
    assert manager.get_handle("nbk_abc") is None, (
        "local kernel must be torn down when a live session takes over"
    )
    assert handle.km.shutdown_calls == 1
