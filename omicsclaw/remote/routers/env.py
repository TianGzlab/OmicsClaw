"""GET /env/doctor — JSON shape of ``omicsclaw.diagnostics.build_doctor_report``.

Reuses the existing ``oc doctor`` machinery so the App's Env tab and the CLI
agree byte-for-byte on what counts as a healthy environment.
"""

from __future__ import annotations

from fastapi import APIRouter

from omicsclaw.diagnostics import build_doctor_report
from omicsclaw.remote.schemas import EnvDoctorCheck, EnvDoctorReport
from omicsclaw.remote.storage import resolve_workspace

router = APIRouter(tags=["remote"])


def build_env_doctor_report_payload(*, workspace_dir: str = "") -> EnvDoctorReport:
    resolved_workspace = str(workspace_dir or "").strip()
    if not resolved_workspace:
        try:
            resolved_workspace = str(resolve_workspace())
        except RuntimeError:
            resolved_workspace = ""

    # ``omicsclaw_dir`` mirrors what server.py exposes via /health.
    try:
        from omicsclaw.app.server import _omicsclaw_project_dir
        omicsclaw_dir = str(_omicsclaw_project_dir())
    except Exception:
        omicsclaw_dir = ""

    report = build_doctor_report(
        omicsclaw_dir=omicsclaw_dir,
        workspace_dir=resolved_workspace,
    )
    return EnvDoctorReport(
        generated_at=report.generated_at,
        workspace_dir=report.workspace_dir,
        omicsclaw_dir=report.omicsclaw_dir,
        overall_status=report.overall_status,
        failure_count=report.failure_count,
        warning_count=report.warning_count,
        checks=[
            EnvDoctorCheck(
                name=check.name,
                status=check.status,
                summary=check.summary,
                details=list(check.details),
            )
            for check in report.checks
        ],
    )


@router.get("/env/doctor", response_model=EnvDoctorReport)
async def env_doctor() -> EnvDoctorReport:
    return build_env_doctor_report_payload()
