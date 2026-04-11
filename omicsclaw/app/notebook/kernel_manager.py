"""Per-notebook IPython kernel lifecycle and execution.

Wraps `jupyter_client.AsyncKernelManager` so that each open notebook in the
frontend gets its own real Python kernel process, with stable state across
cell executions and isolated tracebacks.

Design notes
------------

* **One kernel per notebook_id.** Lazily started on first execute. Stable
  identity is the `notebook_id`, not the file path.
* **Lock per kernel.** A single IPython kernel can only run one cell at a
  time anyway, but the SSE event stream needs serialized iopub reads or
  concurrent executions would interleave parent_header.msg_id filtering.
* **Idle tracking is timestamp-only.** A background reaper shuts down local
  kernels after a period of inactivity.
* **No server-side execution timeout.** Bioinformatics workflows can run for
  hours. The frontend Interrupt button is the user's bail switch.
"""

from __future__ import annotations

import asyncio
import logging
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from jupyter_client.manager import AsyncKernelManager

from .event_adapter import (
    adapt_iopub_message,
    adapt_shell_reply,
    has_matching_parent,
    is_idle_status_for,
)
from .live_session import (
    LiveSessionBinding,
    install_live_session_support,
    is_live_session_running,
    resolve_live_session,
)

log = logging.getLogger(__name__)

try:
    IDLE_KERNEL_TTL_SECONDS = max(
        60.0,
        float(os.environ.get("OMICSCLAW_NOTEBOOK_IDLE_TTL_SECONDS", "900")),
    )
except ValueError:
    IDLE_KERNEL_TTL_SECONDS = 900.0

IDLE_REAPER_INTERVAL_SECONDS = 60.0


@dataclass
class KernelHandle:
    """Bookkeeping for a single live IPython kernel."""

    notebook_id: str
    km: AsyncKernelManager
    client: Any
    cwd: Optional[str]
    last_activity: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    generation: int = 0

    def touch(self) -> None:
        self.last_activity = time.time()


class NotebookKernelManager:
    """Process-wide registry of `notebook_id → KernelHandle`."""

    def __init__(self) -> None:
        self._kernels: dict[str, KernelHandle] = {}
        self._registry_lock = asyncio.Lock()
        self._reaper_task: Optional[asyncio.Task[None]] = None
        install_live_session_support()

    def get_handle(self, notebook_id: str) -> Optional[KernelHandle]:
        return self._kernels.get(notebook_id)

    async def get_or_start(
        self,
        notebook_id: str,
        cwd: Optional[str] = None,
    ) -> KernelHandle:
        self._ensure_reaper()
        stale: Optional[KernelHandle] = None
        async with self._registry_lock:
            handle = self._kernels.get(notebook_id)
            if handle is not None:
                if await _async_kernel_alive(handle.km):
                    return handle
                self._kernels.pop(notebook_id, None)
                stale = handle
        if stale is not None:
            await self._coordinated_shutdown(stale)
        async with self._registry_lock:
            handle = self._kernels.get(notebook_id)
            if handle is not None:
                return handle
            handle = await self._start_kernel(notebook_id, cwd)
            self._kernels[notebook_id] = handle
            return handle

    async def start(
        self,
        notebook_id: str,
        cwd: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> dict[str, Any]:
        self._ensure_reaper()
        live = await self._resolve_live_binding(
            notebook_id,
            file_path,
            cleanup_local=True,
        )
        if live is not None:
            await self._restart_live_session(live)
            return await self._status_live_session(notebook_id, live)

        async with self._registry_lock:
            existing = self._kernels.pop(notebook_id, None)
        if existing is not None:
            await self._coordinated_shutdown(existing)
        handle = await self._start_kernel(notebook_id, cwd)
        async with self._registry_lock:
            self._kernels[notebook_id] = handle
        return {
            "notebook_id": handle.notebook_id,
            "running": True,
            "cwd": handle.cwd,
            "last_activity": handle.last_activity,
            "kernel_status": "idle",
            "source": "local",
        }

    async def stop(
        self,
        notebook_id: str,
        file_path: Optional[str] = None,
    ) -> bool:
        live = await self._resolve_live_binding(notebook_id, file_path)
        if live is not None:
            return False

        async with self._registry_lock:
            handle = self._kernels.pop(notebook_id, None)
        if handle is None:
            return False
        await self._coordinated_shutdown(handle)
        return True

    async def interrupt(
        self,
        notebook_id: str,
        file_path: Optional[str] = None,
    ) -> bool:
        live = await self._resolve_live_binding(notebook_id, file_path)
        if live is not None:
            try:
                await asyncio.to_thread(live.session.km.interrupt_kernel)
            except Exception as exc:
                log.warning("[notebook] live interrupt failed for %s: %s", notebook_id, exc)
                return False
            live.state.touch()
            return True

        handle = self._kernels.get(notebook_id)
        if handle is None:
            return False
        try:
            await handle.km.interrupt_kernel()
        except Exception as exc:
            log.warning("[notebook] interrupt failed for %s: %s", notebook_id, exc)
            return False
        handle.touch()
        return True

    async def status(
        self,
        notebook_id: str,
        file_path: Optional[str] = None,
    ) -> dict[str, Any]:
        live = await self._resolve_live_binding(
            notebook_id,
            file_path,
            cleanup_local=True,
        )
        if live is not None:
            return await self._status_live_session(notebook_id, live)

        handle = self._kernels.get(notebook_id)
        if handle is None:
            return {
                "notebook_id": notebook_id,
                "running": False,
                "kernel_status": "missing",
            }
        try:
            alive = await handle.km.is_alive()
        except Exception:
            alive = False
        kernel_status = "busy" if alive and handle.lock.locked() else "idle"
        if not alive:
            kernel_status = "dead"
        return {
            "notebook_id": notebook_id,
            "running": alive,
            "cwd": handle.cwd,
            "last_activity": handle.last_activity,
            "kernel_status": kernel_status,
            "source": "local",
        }

    async def shutdown_all(self) -> None:
        if self._reaper_task is not None:
            self._reaper_task.cancel()
            self._reaper_task = None

        async with self._registry_lock:
            handles = list(self._kernels.values())
            self._kernels.clear()
        for handle in handles:
            try:
                await self._coordinated_shutdown(handle)
            except Exception as exc:
                log.warning(
                    "[notebook] shutdown failed for %s: %s",
                    handle.notebook_id,
                    exc,
                )

    async def execute_stream(
        self,
        notebook_id: str,
        cell_id: str,
        code: str,
        cwd: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        self._ensure_reaper()
        live = await self._resolve_live_binding(
            notebook_id,
            file_path,
            cleanup_local=True,
        )
        if live is not None:
            async for event in self._execute_live_stream(live, cell_id, code):
                yield event
            return

        handle = await self.get_or_start(notebook_id, cwd=cwd)
        handle.touch()
        expected_generation = handle.generation

        saw_reply = False
        try:
            async with handle.lock:
                if handle.generation != expected_generation:
                    yield _make_error_event(
                        cell_id, "KernelRestarted",
                        "Kernel was restarted before execution began",
                    )
                    yield _make_reply_event(cell_id, "aborted")
                    saw_reply = True
                    return

                client = handle.client
                msg_id = client.execute(code, store_history=True, silent=False)
                shell_task = asyncio.create_task(
                    _wait_for_shell_reply(client, msg_id)
                )

                try:
                    saw_idle = False
                    while not saw_idle:
                        if handle.generation != expected_generation:
                            yield _make_error_event(
                                cell_id, "KernelRestarted",
                                "Kernel was restarted mid-execution",
                            )
                            break

                        try:
                            msg = await client.get_iopub_msg(timeout=1.0)
                        except queue.Empty:
                            if not await _async_kernel_alive(handle.km):
                                yield _make_error_event(
                                    cell_id,
                                    "DeadKernel",
                                    "Kernel died before execution completed",
                                )
                                break
                            continue
                        except Exception as exc:
                            log.exception(
                                "[notebook] iopub read failed for %s",
                                notebook_id,
                            )
                            yield _make_error_event(
                                cell_id,
                                type(exc).__name__,
                                str(exc),
                            )
                            break

                        if not has_matching_parent(msg, msg_id):
                            continue

                        event = adapt_iopub_message(msg, cell_id)
                        if event is not None:
                            yield event

                        if is_idle_status_for(msg, msg_id):
                            saw_idle = True

                    try:
                        reply_msg = await asyncio.wait_for(shell_task, timeout=5.0)
                    except asyncio.TimeoutError:
                        log.warning(
                            "[notebook] timed out waiting for execute_reply on %s",
                            notebook_id,
                        )
                    except Exception as exc:
                        log.warning(
                            "[notebook] shell reply raised for %s: %s",
                            notebook_id,
                            exc,
                        )
                    else:
                        reply_event = adapt_shell_reply(reply_msg, cell_id)
                        if reply_event is not None:
                            yield reply_event
                            saw_reply = True
                finally:
                    handle.touch()
                    if not shell_task.done():
                        shell_task.cancel()
                        try:
                            await shell_task
                        except (asyncio.CancelledError, Exception):
                            pass
        finally:
            if not saw_reply:
                yield _make_reply_event(cell_id, "error")

    async def inspect(
        self,
        notebook_id: str,
        file_path: Optional[str] = None,
    ) -> dict[str, Any]:
        live = await self._resolve_live_binding(
            notebook_id,
            file_path,
            cleanup_local=True,
        )
        if live is not None:
            return await self._inspect_live_session(live, notebook_id)

        handle = self._kernels.get(notebook_id)
        if handle is None:
            return _make_missing_inspect_payload()
        if not await _async_kernel_alive(handle.km):
            return _make_missing_inspect_payload(kernel_status="dead")
        handle.touch()
        async with handle.lock:
            if not await _async_kernel_alive(handle.km):
                return _make_missing_inspect_payload(kernel_status="dead")
            client = handle.client
            try:
                msg_id = client.execute(
                    _INSPECT_SCRIPT,
                    store_history=False,
                    silent=False,
                )
            except Exception as exc:
                log.warning(
                    "[notebook] inspect execute failed for %s: %s",
                    notebook_id,
                    exc,
                )
                alive = await _async_kernel_alive(handle.km)
                return _make_missing_inspect_payload(
                    kernel_status="idle" if alive else "dead"
                )

            shell_task = asyncio.create_task(
                _wait_for_shell_reply(
                    client,
                    msg_id,
                    timeout=2.0,
                    kernel_manager=handle.km,
                )
            )
            collected = []
            try:
                while True:
                    try:
                        msg = await client.get_iopub_msg(timeout=1.0)
                    except queue.Empty:
                        if not await _async_kernel_alive(handle.km):
                            break
                        continue
                    except Exception as exc:
                        log.warning(
                            "[notebook] iopub read failed during inspect for %s: %s",
                            notebook_id,
                            exc,
                        )
                        break

                    if msg.get("parent_header", {}).get("msg_id") != msg_id:
                        continue

                    if msg.get("msg_type") == "stream":
                        text = msg.get("content", {}).get("text", "")
                        if isinstance(text, list):
                            text = "".join(text)
                        collected.append(text)
                    elif (
                        msg.get("msg_type") == "status"
                        and msg.get("content", {}).get("execution_state") == "idle"
                    ):
                        break
            finally:
                if not shell_task.done():
                    shell_task.cancel()
                try:
                    await shell_task
                except (asyncio.CancelledError, DeadKernelError, TimeoutError, Exception):
                    pass

            joined = "".join(collected)
            alive = await _async_kernel_alive(handle.km)
            return _make_inspect_payload(
                _parse_inspect_payload(joined),
                kernel_status="idle" if alive else "dead",
            )

    async def run_stdout_script(
        self,
        notebook_id: str,
        script: str,
        file_path: Optional[str] = None,
    ) -> tuple[str, str]:
        """Run ``script`` silently in the kernel and return ``(stdout, kernel_status)``.

        Intended for on-demand inspection endpoints (``var_detail``,
        ``adata_slot``) where the generated snippet emits a JSON payload
        bracketed by sentinel markers. The caller is responsible for
        parsing the returned stdout; this method only cares about
        collecting stream output that matches the silently-issued
        ``execute`` request.
        """
        live = await self._resolve_live_binding(
            notebook_id,
            file_path,
            cleanup_local=True,
        )
        if live is not None:
            return await self._run_stdout_script_live(live, script)

        handle = self._kernels.get(notebook_id)
        if handle is None:
            return "", "missing"
        if not await _async_kernel_alive(handle.km):
            return "", "dead"
        handle.touch()
        async with handle.lock:
            if not await _async_kernel_alive(handle.km):
                return "", "dead"
            client = handle.client
            try:
                msg_id = client.execute(
                    script,
                    store_history=False,
                    silent=False,
                )
            except Exception as exc:
                log.warning(
                    "[notebook] run_stdout_script execute failed for %s: %s",
                    notebook_id,
                    exc,
                )
                alive = await _async_kernel_alive(handle.km)
                return "", "idle" if alive else "dead"

            shell_task = asyncio.create_task(
                _wait_for_shell_reply(
                    client,
                    msg_id,
                    timeout=5.0,
                    kernel_manager=handle.km,
                )
            )
            collected: list[str] = []
            try:
                while True:
                    try:
                        msg = await client.get_iopub_msg(timeout=1.0)
                    except queue.Empty:
                        if not await _async_kernel_alive(handle.km):
                            break
                        continue
                    except Exception as exc:
                        log.warning(
                            "[notebook] run_stdout_script iopub read failed for %s: %s",
                            notebook_id,
                            exc,
                        )
                        break

                    if msg.get("parent_header", {}).get("msg_id") != msg_id:
                        continue

                    if msg.get("msg_type") == "stream":
                        text = msg.get("content", {}).get("text", "")
                        if isinstance(text, list):
                            text = "".join(text)
                        collected.append(text)
                    elif (
                        msg.get("msg_type") == "status"
                        and msg.get("content", {}).get("execution_state") == "idle"
                    ):
                        break
            finally:
                if not shell_task.done():
                    shell_task.cancel()
                try:
                    await shell_task
                except (asyncio.CancelledError, DeadKernelError, TimeoutError, Exception):
                    pass

            joined = "".join(collected)
            alive = await _async_kernel_alive(handle.km)
            return joined, "idle" if alive else "dead"

    async def _run_stdout_script_live(
        self,
        live: LiveSessionBinding,
        script: str,
    ) -> tuple[str, str]:
        def run() -> tuple[str, str]:
            if not _sync_kernel_alive(live.session.km):
                live.state.status = "dead"
                return "", "dead"

            with live.state.lock:
                live.state.touch()
                client = live.session.kc
                try:
                    msg_id = client.execute(
                        script,
                        store_history=False,
                        silent=False,
                        allow_stdin=False,
                        stop_on_error=False,
                    )
                except Exception as exc:
                    log.warning(
                        "[notebook] live run_stdout_script execute failed: %s",
                        exc,
                    )
                    alive = _sync_kernel_alive(live.session.km)
                    return "", "idle" if alive else "dead"

                collected: list[str] = []
                while True:
                    try:
                        msg = client.get_iopub_msg(timeout=1)
                    except queue.Empty:
                        if not _sync_kernel_alive(live.session.km):
                            break
                        continue
                    except Exception as exc:
                        log.warning(
                            "[notebook] live run_stdout_script iopub read failed: %s",
                            exc,
                        )
                        break

                    if msg.get("parent_header", {}).get("msg_id") != msg_id:
                        continue

                    if msg.get("msg_type") == "stream":
                        text = msg.get("content", {}).get("text", "")
                        if isinstance(text, list):
                            text = "".join(text)
                        collected.append(text)
                    elif (
                        msg.get("msg_type") == "status"
                        and msg.get("content", {}).get("execution_state") == "idle"
                    ):
                        break

                try:
                    _wait_for_sync_shell_reply(client, msg_id, timeout=5.0)
                except Exception:
                    pass

                live.state.touch()
                alive = _sync_kernel_alive(live.session.km)
                return "".join(collected), "idle" if alive else "dead"

        return await asyncio.to_thread(run)

    async def complete(
        self,
        notebook_id: str,
        code: str,
        cursor_pos: int,
        file_path: Optional[str] = None,
    ) -> dict[str, Any]:
        live = await self._resolve_live_binding(
            notebook_id,
            file_path,
            cleanup_local=True,
        )
        if live is not None:
            return await self._complete_live_session(live, code, cursor_pos)

        handle = self._kernels.get(notebook_id)
        if handle is None:
            return _make_missing_complete_payload(cursor_pos)
        if not await _async_kernel_alive(handle.km):
            return _make_missing_complete_payload(cursor_pos)
        handle.touch()
        async with handle.lock:
            if not await _async_kernel_alive(handle.km):
                return _make_missing_complete_payload(cursor_pos)
            client = handle.client
            try:
                msg_id = client.complete(code, cursor_pos)
                reply = await _wait_for_shell_reply(
                    client,
                    msg_id,
                    timeout=5.0,
                    kernel_manager=handle.km,
                )
            except (DeadKernelError, TimeoutError):
                return _make_missing_complete_payload(cursor_pos)
            except Exception as exc:
                if not await _async_kernel_alive(handle.km):
                    return _make_missing_complete_payload(cursor_pos)
                log.warning(
                    "[notebook] completion failed for %s: %s",
                    notebook_id,
                    exc,
                )
                raise
            content = reply.get("content", {}) or {}
            return {
                "matches": list(content.get("matches", [])),
                "cursor_start": int(content.get("cursor_start", cursor_pos)),
                "cursor_end": int(content.get("cursor_end", cursor_pos)),
                "status": content.get("status", "ok"),
            }

    def _ensure_reaper(self) -> None:
        if self._reaper_task is not None and not self._reaper_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._reaper_task = loop.create_task(self._idle_reaper())

    async def _idle_reaper(self) -> None:
        try:
            while True:
                await asyncio.sleep(IDLE_REAPER_INTERVAL_SECONDS)
                cutoff = time.time() - IDLE_KERNEL_TTL_SECONDS
                stale: list[KernelHandle] = []
                async with self._registry_lock:
                    for notebook_id, handle in list(self._kernels.items()):
                        if handle.lock.locked():
                            continue
                        if handle.last_activity >= cutoff:
                            continue
                        self._kernels.pop(notebook_id, None)
                        stale.append(handle)
                for handle in stale:
                    try:
                        await self._coordinated_shutdown(handle)
                    except Exception as exc:
                        log.warning(
                            "[notebook] idle shutdown failed for %s: %s",
                            handle.notebook_id,
                            exc,
                        )
        except asyncio.CancelledError:
            return

    async def _resolve_live_binding(
        self,
        notebook_id: str,
        file_path: Optional[str],
        *,
        cleanup_local: bool = False,
    ) -> Optional[LiveSessionBinding]:
        live = resolve_live_session(file_path)
        if live is None or not is_live_session_running(live):
            return None

        if cleanup_local:
            async with self._registry_lock:
                local = self._kernels.pop(notebook_id, None)
            if local is not None:
                await self._coordinated_shutdown(local)

        return live

    async def _status_live_session(
        self,
        notebook_id: str,
        live: LiveSessionBinding,
    ) -> dict[str, Any]:
        def snapshot() -> tuple[bool, str]:
            alive = False
            try:
                alive = bool(live.session.km.is_alive())
            except Exception:
                alive = False
            if not alive:
                live.state.status = "dead"
            elif live.state.status != "busy":
                live.state.status = "idle"
            return alive, live.state.status

        alive, kernel_status = await asyncio.to_thread(snapshot)
        live.state.touch()
        return {
            "notebook_id": notebook_id,
            "running": alive,
            "cwd": live.cwd,
            "last_activity": live.state.last_activity,
            "kernel_status": kernel_status,
            "source": "live",
        }

    async def _restart_live_session(self, live: LiveSessionBinding) -> None:
        def restart() -> None:
            try:
                live.session.km.interrupt_kernel()
            except Exception:
                pass
            live.session.restart_kernel()
            live.state.touch()

        await asyncio.to_thread(restart)

    async def _execute_live_stream(
        self,
        live: LiveSessionBinding,
        cell_id: str,
        code: str,
    ) -> AsyncIterator[dict[str, Any]]:
        loop = asyncio.get_running_loop()
        outbox: asyncio.Queue[dict[str, Any] | object] = asyncio.Queue()
        done = object()

        def emit(event: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(outbox.put_nowait, event)

        def finish() -> None:
            loop.call_soon_threadsafe(outbox.put_nowait, done)

        def worker() -> None:
            saw_reply = False
            with live.state.lock:
                live.state.status = "busy"
                live.state.touch()
                try:
                    client = live.session.kc
                    msg_id = client.execute(
                        code,
                        store_history=True,
                        silent=False,
                        allow_stdin=False,
                        stop_on_error=False,
                    )

                    saw_idle = False
                    while not saw_idle:
                        try:
                            msg = client.get_iopub_msg(timeout=1)
                        except queue.Empty:
                            continue
                        except Exception as exc:
                            emit(_make_error_event(cell_id, type(exc).__name__, str(exc)))
                            break

                        if not has_matching_parent(msg, msg_id):
                            continue

                        event = adapt_iopub_message(msg, cell_id)
                        if event is not None:
                            emit(event)

                        if is_idle_status_for(msg, msg_id):
                            saw_idle = True

                    try:
                        reply_msg = _wait_for_sync_shell_reply(client, msg_id, timeout=5.0)
                    except TimeoutError:
                        log.warning("[notebook] timed out waiting for live execute_reply")
                    except Exception as exc:
                        log.warning("[notebook] live shell reply failed: %s", exc)
                    else:
                        reply_event = adapt_shell_reply(reply_msg, cell_id)
                        if reply_event is not None:
                            emit(reply_event)
                            saw_reply = True
                except Exception as exc:
                    emit(_make_error_event(cell_id, type(exc).__name__, str(exc)))
                finally:
                    live.state.status = "idle" if _sync_kernel_alive(live.session.km) else "dead"
                    live.state.touch()
                    if not saw_reply:
                        emit(_make_reply_event(cell_id, "error"))
                    finish()

        thread = threading.Thread(target=worker, name="omicsclaw-live-notebook", daemon=True)
        thread.start()

        while True:
            item = await outbox.get()
            if item is done:
                break
            yield item  # type: ignore[misc]

    async def _inspect_live_session(
        self,
        live: LiveSessionBinding,
        notebook_id: str,
    ) -> dict[str, Any]:
        def inspect() -> dict[str, Any]:
            if not _sync_kernel_alive(live.session.km):
                live.state.status = "dead"
                return _make_missing_inspect_payload(kernel_status="dead")

            with live.state.lock:
                live.state.touch()
                client = live.session.kc
                msg_id = client.execute(
                    _INSPECT_SCRIPT,
                    store_history=False,
                    silent=False,
                    allow_stdin=False,
                    stop_on_error=False,
                )
                collected: list[str] = []
                while True:
                    try:
                        msg = client.get_iopub_msg(timeout=1)
                    except queue.Empty:
                        continue
                    except Exception as exc:
                        log.warning(
                            "[notebook] live inspect iopub failed for %s: %s",
                            notebook_id,
                            exc,
                        )
                        break

                    if msg.get("parent_header", {}).get("msg_id") != msg_id:
                        continue

                    if msg.get("msg_type") == "stream":
                        text = msg.get("content", {}).get("text", "")
                        if isinstance(text, list):
                            text = "".join(text)
                        collected.append(text)
                    elif (
                        msg.get("msg_type") == "status"
                        and msg.get("content", {}).get("execution_state") == "idle"
                    ):
                        break

                try:
                    _wait_for_sync_shell_reply(client, msg_id, timeout=2.0)
                except Exception:
                    pass

                live.state.touch()
                live.state.status = "busy" if live.state.status == "busy" else "idle"
                joined = "".join(collected)
                return _make_inspect_payload(
                    _parse_inspect_payload(joined),
                    kernel_status="busy" if live.state.status == "busy" else "idle",
                )

        return await asyncio.to_thread(inspect)

    async def _complete_live_session(
        self,
        live: LiveSessionBinding,
        code: str,
        cursor_pos: int,
    ) -> dict[str, Any]:
        def complete() -> dict[str, Any]:
            if not _sync_kernel_alive(live.session.km):
                live.state.status = "dead"
                return {
                    "matches": [],
                    "cursor_start": int(cursor_pos),
                    "cursor_end": int(cursor_pos),
                    "status": "aborted",
                }

            with live.state.lock:
                live.state.touch()
                client = live.session.kc
                msg_id = client.complete(code, cursor_pos)
                reply = _wait_for_sync_shell_reply(client, msg_id, timeout=5.0)
                content = reply.get("content", {}) or {}
                live.state.touch()
                return {
                    "matches": list(content.get("matches", [])),
                    "cursor_start": int(content.get("cursor_start", cursor_pos)),
                    "cursor_end": int(content.get("cursor_end", cursor_pos)),
                    "status": content.get("status", "ok"),
                }

        return await asyncio.to_thread(complete)

    async def _start_kernel(
        self, notebook_id: str, cwd: Optional[str]
    ) -> KernelHandle:
        log.info(
            "[notebook] starting kernel for %s (cwd=%s)", notebook_id, cwd
        )
        km = AsyncKernelManager()
        await km.start_kernel(cwd=cwd) if cwd else await km.start_kernel()

        client = km.client()
        client.start_channels()
        try:
            await client.wait_for_ready(timeout=30)
        except RuntimeError as exc:
            log.error(
                "[notebook] kernel for %s failed to become ready: %s",
                notebook_id,
                exc,
            )
            client.stop_channels()
            await km.shutdown_kernel(now=True)
            raise

        try:
            client.execute(
                _BOOTSTRAP_SCRIPT,
                store_history=False,
                silent=True,
            )
        except Exception as exc:
            log.warning(
                "[notebook] bootstrap script failed for %s: %s",
                notebook_id,
                exc,
            )

        return KernelHandle(
            notebook_id=notebook_id,
            km=km,
            client=client,
            cwd=cwd,
            generation=int(time.time() * 1000),
        )

    async def _coordinated_shutdown(self, handle: KernelHandle) -> None:
        handle.generation += 1
        try:
            await handle.km.interrupt_kernel()
        except Exception:
            pass
        for _ in range(20):
            if not handle.lock.locked():
                break
            await asyncio.sleep(0.1)
        try:
            handle.client.stop_channels()
        except Exception:
            pass
        try:
            await handle.km.shutdown_kernel(now=True)
        except Exception as exc:
            log.warning(
                "[notebook] kernel shutdown error for %s: %s",
                handle.notebook_id,
                exc,
            )


class DeadKernelError(RuntimeError):
    """Raised when a local kernel dies while a shell reply is still pending."""


async def _wait_for_shell_reply(
    client: Any,
    msg_id: str,
    *,
    timeout: float | None = None,
    kernel_manager: Any | None = None,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout if timeout is not None else None
    while True:
        wait_timeout = 1.0
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("timed out waiting for shell reply")
            wait_timeout = min(wait_timeout, remaining)
        try:
            msg = await client.get_shell_msg(timeout=wait_timeout)
        except (queue.Empty, asyncio.TimeoutError):
            if kernel_manager is not None and not await _async_kernel_alive(kernel_manager):
                raise DeadKernelError("kernel is not alive")
            continue
        except Exception:
            if kernel_manager is not None and not await _async_kernel_alive(kernel_manager):
                raise DeadKernelError("kernel is not alive")
            raise
        if msg.get("parent_header", {}).get("msg_id") == msg_id:
            return msg


async def _async_kernel_alive(kernel_manager: Any) -> bool:
    try:
        return bool(await kernel_manager.is_alive())
    except Exception:
        return False


def _wait_for_sync_shell_reply(client: Any, msg_id: str, *, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("timed out waiting for shell reply")
        try:
            msg = client.get_shell_msg(timeout=min(1.0, remaining))
        except queue.Empty:
            continue
        if msg.get("parent_header", {}).get("msg_id") == msg_id:
            return msg


def _sync_kernel_alive(kernel_manager: Any) -> bool:
    try:
        return bool(kernel_manager.is_alive())
    except Exception:
        return False


def _make_error_event(cell_id: str, ename: str, evalue: str) -> dict[str, Any]:
    return {
        "type": "error",
        "data": {
            "cell_id": cell_id,
            "ename": ename,
            "evalue": evalue,
            "traceback": [],
        },
    }


def _make_reply_event(cell_id: str, status: str) -> dict[str, Any]:
    return {
        "type": "execute_reply",
        "data": {
            "cell_id": cell_id,
            "status": status,
            "execution_count": None,
        },
    }


def _make_missing_inspect_payload(
    *,
    kernel_status: str = "missing",
) -> dict[str, Any]:
    return _make_inspect_payload(
        {"vars": [], "memory_mb": None},
        kernel_status=kernel_status,
    )


def _make_missing_complete_payload(cursor_pos: int) -> dict[str, Any]:
    return {
        "matches": [],
        "cursor_start": int(cursor_pos),
        "cursor_end": int(cursor_pos),
        "status": "aborted",
    }


def _make_inspect_payload(
    payload: dict[str, Any],
    *,
    kernel_status: str,
) -> dict[str, Any]:
    vars_payload = payload.get("vars", [])
    if not isinstance(vars_payload, list):
        vars_payload = []
    memory_mb = payload.get("memory_mb")
    if not isinstance(memory_mb, (int, float)):
        memory_mb = None
    return {
        "vars": vars_payload,
        "memory_mb": memory_mb,
        "kernel_status": kernel_status,
        "kernel_available": kernel_status != "missing",
    }


_BOOTSTRAP_SCRIPT = r"""
import os as _oc_os
import sys as _oc_sys
import importlib.util as _oc_importlib_util
import warnings as _oc_warnings

try:
    get_ipython().run_line_magic("matplotlib", "inline")  # type: ignore[name-defined]
except Exception:
    pass

_oc_dir = _oc_os.environ.get("OMICSCLAW_DIR")
if not _oc_dir:
    try:
        import omicsclaw as _oc_pkg
        _oc_dir = _oc_os.path.dirname(_oc_os.path.dirname(_oc_pkg.__file__))
    except Exception:
        _oc_dir = ""
if _oc_dir and _oc_dir not in _oc_sys.path:
    _oc_sys.path.insert(0, _oc_dir)

try:
    _oc_warnings.filterwarnings("ignore")
except Exception:
    pass

def load_skill(name):
    from omicsclaw.core.registry import OmicsRegistry
    reg = OmicsRegistry()
    reg.load_all()
    info = reg.skills.get(name)
    if not info:
        raise ValueError(
            f"Skill {name!r} not found. Use a valid skill name from `oc list`."
        )
    script = info.get("script", "")
    if not script or not _oc_os.path.exists(script):
        raise FileNotFoundError(f"Script not found for {name}: {script}")
    mod_name = name.replace("-", "_")
    spec = _oc_importlib_util.spec_from_file_location(mod_name, script)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load skill module for {name}: {script}")
    mod = _oc_importlib_util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

del _oc_os, _oc_sys, _oc_importlib_util, _oc_warnings, _oc_dir
"""


_INSPECT_BEGIN = "__OMICSCLAW_INSPECT_BEGIN__"
_INSPECT_END = "__OMICSCLAW_INSPECT_END__"

_INSPECT_SCRIPT = f'''
def __omicsclaw_inspect():
    import json as _json
    import sys as _sys
    _ns = globals()
    _IGNORE = {{
        "In", "Out", "exit", "quit", "get_ipython",
        "__omicsclaw_inspect",
    }}
    _vars = []
    for _name, _val in list(_ns.items()):
        if _name.startswith("_"):
            continue
        if _name in _IGNORE:
            continue
        if callable(_val):
            continue
        if type(_val).__name__ == "module":
            continue
        _summary = {{"name": _name, "type": type(_val).__name__, "preview": ""}}
        try:
            import numpy as _np
            if isinstance(_val, _np.ndarray):
                _summary["preview"] = "ndarray shape=" + str(_val.shape) + " dtype=" + str(_val.dtype)
                _vars.append(_summary)
                continue
        except Exception:
            pass
        try:
            import pandas as _pd
            if isinstance(_val, _pd.DataFrame):
                _summary["preview"] = "DataFrame shape=" + str(tuple(_val.shape))
                _summary["shape"] = list(_val.shape)
                _vars.append(_summary)
                continue
            if isinstance(_val, _pd.Series):
                _summary["preview"] = "Series len=" + str(len(_val)) + " dtype=" + str(_val.dtype)
                _vars.append(_summary)
                continue
        except Exception:
            pass
        try:
            if type(_val).__name__ == "AnnData":
                _shape = getattr(_val, "shape", None)
                _summary["preview"] = "AnnData shape=" + str(_shape)
                _summary["shape"] = list(_shape) if _shape is not None else None
                _vars.append(_summary)
                continue
        except Exception:
            pass
        try:
            _r = repr(_val).replace("\\n", " ")
            _summary["preview"] = _r[:160]
        except Exception:
            _summary["preview"] = "<unavailable>"
        _vars.append(_summary)
    _vars.sort(key=lambda v: v["name"].lower())
    _mem = None
    try:
        import os as _os
        import psutil as _psutil  # type: ignore
        _mem = round(_psutil.Process(_os.getpid()).memory_info().rss / (1024 * 1024), 1)
    except Exception:
        _mem = None
    _payload = {{"vars": _vars[:200], "memory_mb": _mem}}
    print("{_INSPECT_BEGIN}" + _json.dumps(_payload) + "{_INSPECT_END}")
__omicsclaw_inspect()
del __omicsclaw_inspect
'''


def _parse_inspect_payload(stdout: str) -> dict[str, Any]:
    try:
        start = stdout.index(_INSPECT_BEGIN) + len(_INSPECT_BEGIN)
        end = stdout.index(_INSPECT_END, start)
        import json

        return json.loads(stdout[start:end])
    except (ValueError, Exception):
        return {"vars": [], "memory_mb": None}


_singleton: Optional[NotebookKernelManager] = None


def get_kernel_manager() -> NotebookKernelManager:
    global _singleton
    if _singleton is None:
        _singleton = NotebookKernelManager()
    return _singleton
