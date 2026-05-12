"""POST /connections/test — tunnel + version + extras probe.

App calls this immediately after opening the SSH tunnel to confirm:
- the backend is reachable
- versions are compatible
- optional extras (gpu, disk free) for the Settings UI
"""

from __future__ import annotations

import shutil

from fastapi import APIRouter

from omicsclaw.remote.schemas import ConnectionTestResponse
from omicsclaw.remote.storage import utc_now_iso
from omicsclaw.version import __version__

router = APIRouter(tags=["remote"])


def _detect_gpu() -> dict[str, object]:
    try:
        import torch  # type: ignore[import-not-found]
    except ImportError:
        return {"available": False, "reason": "torch not installed"}
    if not torch.cuda.is_available():
        return {"available": False, "reason": "cuda not available"}
    devices = []
    for idx in range(torch.cuda.device_count()):
        devices.append({"index": idx, "name": torch.cuda.get_device_name(idx)})
    return {"available": True, "device_count": len(devices), "devices": devices}


def _disk_free_bytes(path: str = "/") -> int:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return -1


@router.post("/connections/test", response_model=ConnectionTestResponse)
async def connections_test() -> ConnectionTestResponse:
    return ConnectionTestResponse(
        ok=True,
        version=__version__,
        server_time=utc_now_iso(),
        extras={
            "gpu": _detect_gpu(),
            "disk_free_bytes": _disk_free_bytes(),
        },
    )
