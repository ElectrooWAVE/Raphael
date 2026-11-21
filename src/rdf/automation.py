"""Scheduled automation jobs using APScheduler (Stage 4)."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from .config import STORAGE_DIR
from .db import get_db, init_db, now_iso
from .inventory import start_batch_forecast_job
from .reporting import export_inventory_excel

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    BackgroundScheduler = None  # type: ignore[assignment]
    CronTrigger = None  # type: ignore[assignment]
    APSCHEDULER_AVAILABLE = False

_SCHEDULER: Any = None


def _get_scheduler() -> Any:
    global _SCHEDULER
    if not APSCHEDULER_AVAILABLE:
        return None
    if _SCHEDULER is None:
        _SCHEDULER = BackgroundScheduler(daemon=True)
        _SCHEDULER.start()
    return _SCHEDULER


def _log_execution(schedule_id: str, status: str, message: str) -> None:
    ts = now_iso()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO automation_logs (schedule_id, status, message, created_at) VALUES (?, ?, ?, ?)",
            (schedule_id, status, message, ts),
        )
        conn.execute(
            "UPDATE automation_schedules SET last_run_at = ?, last_status = ? WHERE id = ?",
            (ts, status, schedule_id),
        )


def execute_schedule(schedule_id: str) -> dict[str, Any]:
    """Execute a scheduled job immediately and record an automation log entry."""
    init_db()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM automation_schedules WHERE id = ?", (schedule_id,)).fetchone()
    if not row:
        raise KeyError(f"Schedule '{schedule_id}' not found.")

    sched = dict(row)
    job_type = sched["job_type"]
    dataset_id = sched["dataset_id"]

    if job_type == "batch_forecast_refresh":
        job = start_batch_forecast_job(dataset_id=dataset_id, horizon=28)
        msg = f"Started batch Chronos-2 job {job['job_id']} ({job['total_series']} series)."
        _log_execution(schedule_id, "triggered", msg)
        return {"schedule_id": schedule_id, "status": "triggered", "message": msg, "job": job}

    if job_type == "export_report":
        reports_dir = STORAGE_DIR / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        xlsx_bytes = export_inventory_excel(dataset_id=dataset_id)
        out_path = reports_dir / f"inventory_report_{dataset_id}_{schedule_id[:8]}.xlsx"
        out_path.write_bytes(xlsx_bytes)
        msg = f"Saved Excel report to {out_path.name} ({len(xlsx_bytes)} bytes)."
        _log_execution(schedule_id, "completed", msg)
        return {"schedule_id": schedule_id, "status": "completed", "message": msg, "file": str(out_path)}

    raise ValueError(f"Unsupported job_type '{job_type}'.")


def list_schedules() -> dict[str, Any]:
    """List saved schedules and recent automation logs."""
    init_db()
    with get_db() as conn:
        schedules = [
            dict(r)
            for r in conn.execute("SELECT * FROM automation_schedules ORDER BY created_at DESC").fetchall()
        ]
        logs = [
            dict(r)
            for r in conn.execute("SELECT * FROM automation_logs ORDER BY id DESC LIMIT 20").fetchall()
        ]
    return {
        "apscheduler_available": APSCHEDULER_AVAILABLE,
        "schedules": schedules,
        "logs": logs,
    }


def create_schedule(
    *,
    name: str,
    job_type: str = "batch_forecast_refresh",
    cron_expr: str = "0 6 * * *",
    dataset_id: str = "retail-demand-m5",
) -> dict[str, Any]:
    """Create a cron-based automation schedule."""
    init_db()
    if job_type not in ("batch_forecast_refresh", "export_report"):
        raise ValueError("job_type must be 'batch_forecast_refresh' or 'export_report'.")

    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError("cron_expr must be a 5-field cron expression (e.g. '0 6 * * *').")

    sid = f"sched-{uuid.uuid4().hex[:8]}"
    created = now_iso()

    if APSCHEDULER_AVAILABLE:
        sched = _get_scheduler()
        trigger = CronTrigger.from_crontab(cron_expr.strip())
        sched.add_job(execute_schedule, trigger=trigger, args=[sid], id=sid, replace_existing=True)

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO automation_schedules (id, name, job_type, cron_expr, dataset_id, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (sid, name.strip(), job_type, cron_expr.strip(), dataset_id, created),
        )
    return {
        "id": sid,
        "name": name.strip(),
        "job_type": job_type,
        "cron_expr": cron_expr.strip(),
        "dataset_id": dataset_id,
        "enabled": 1,
        "created_at": created,
    }


def delete_schedule(schedule_id: str) -> bool:
    """Delete an automation schedule and remove it from APScheduler if registered."""
    init_db()
    if APSCHEDULER_AVAILABLE and _SCHEDULER is not None:
        try:
            _SCHEDULER.remove_job(schedule_id)
        except Exception:
            pass
    with get_db() as conn:
        cur = conn.execute("DELETE FROM automation_schedules WHERE id = ?", (schedule_id,))
    return cur.rowcount > 0
