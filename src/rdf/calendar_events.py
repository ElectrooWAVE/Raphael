"""Calendar events reference loader and user-managed promotions (Stage 2)."""
from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Any, Sequence

import pandas as pd

from .config import DATA_DIR
from .db import get_db, init_db, now_iso


@lru_cache(maxsize=1)
def load_calendar_events() -> list[dict[str, str]]:
    """Load M5 calendar events from data/calendar_events_reference.csv."""
    path = DATA_DIR / "calendar_events_reference.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path)
    events: list[dict[str, str]] = []
    for rec in df.to_dict(orient="records"):
        dt = str(rec.get("date", "")).strip()
        n1 = "" if pd.isna(rec.get("event_name_1")) else str(rec.get("event_name_1")).strip()
        t1 = "" if pd.isna(rec.get("event_type_1")) else str(rec.get("event_type_1")).strip()
        n2 = "" if pd.isna(rec.get("event_name_2")) else str(rec.get("event_name_2")).strip()
        t2 = "" if pd.isna(rec.get("event_type_2")) else str(rec.get("event_type_2")).strip()
        if not dt or not n1:
            continue
        label = f"{n1} ({t1})" if t1 else n1
        if n2:
            label += f" + {n2} ({t2})" if t2 else f" + {n2}"
        events.append({
            "date": dt,
            "event_name_1": n1,
            "event_type_1": t1,
            "event_name_2": n2,
            "event_type_2": t2,
            "label": label,
            "source": "calendar",
        })
    return events


def list_promotions(dataset_id: str = "retail-demand-m5") -> list[dict[str, Any]]:
    """List saved user promotions for a dataset."""
    init_db()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM promotions WHERE dataset_id = ? ORDER BY start_date ASC, created_at DESC",
            (dataset_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def create_promotion(
    *,
    name: str,
    start_date: str,
    end_date: str,
    series_id: str | None = None,
    dataset_id: str = "retail-demand-m5",
    promo_type: str = "promotion",
    uplift_pct: float = 0.0,
    notes: str = "",
) -> dict[str, Any]:
    """Create a user-defined promotion window."""
    init_db()
    s_dt = pd.Timestamp(start_date).strftime("%Y-%m-%d")
    e_dt = pd.Timestamp(end_date).strftime("%Y-%m-%d")
    if e_dt < s_dt:
        raise ValueError("end_date must be on or after start_date.")

    pid = str(uuid.uuid4())
    created = now_iso()
    sid = series_id.strip() if series_id and series_id.strip() and series_id.strip() != "ALL" else None
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO promotions (
                id, dataset_id, series_id, name, start_date, end_date,
                promo_type, uplift_pct, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (pid, dataset_id, sid, name.strip(), s_dt, e_dt, promo_type.strip() or "promotion", float(uplift_pct), notes.strip(), created),
        )
    return {
        "id": pid,
        "dataset_id": dataset_id,
        "series_id": sid,
        "name": name.strip(),
        "start_date": s_dt,
        "end_date": e_dt,
        "promo_type": promo_type.strip() or "promotion",
        "uplift_pct": float(uplift_pct),
        "notes": notes.strip(),
        "created_at": created,
    }


def delete_promotion(promo_id: str) -> bool:
    """Delete a promotion by ID."""
    init_db()
    with get_db() as conn:
        cur = conn.execute("DELETE FROM promotions WHERE id = ?", (promo_id,))
    return cur.rowcount > 0


def get_events_for_window(
    start_date: str | None = None,
    end_date: str | None = None,
    series_id: str | None = None,
    dataset_id: str = "retail-demand-m5",
) -> dict[str, Any]:
    """Return reference calendar events and matching user promotions in [start_date, end_date]."""
    cal = load_calendar_events()
    if start_date:
        cal = [e for e in cal if e["date"] >= start_date]
    if end_date:
        cal = [e for e in cal if e["date"] <= end_date]

    promos = list_promotions(dataset_id)
    matched_promos: list[dict[str, Any]] = []
    for p in promos:
        if p["series_id"] is not None and series_id and p["series_id"] != series_id:
            continue
        if start_date and p["end_date"] < start_date:
            continue
        if end_date and p["start_date"] > end_date:
            continue
        matched_promos.append(p)

    return {
        "calendar_events": cal,
        "promotions": matched_promos,
    }


def build_known_future_covariates(
    history_dates: Sequence[Any],
    forecast_dates: Sequence[Any],
    series_id: str | None = None,
    dataset_id: str = "retail-demand-m5",
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    """Build known-future calendar & promotion covariate DataFrames aligned to history and forecast dates.

    Returns (hist_cov_df, fut_cov_df, promo_uplift_by_date).
    """
    cal_by_date = {e["date"]: e for e in load_calendar_events()}
    promos = list_promotions(dataset_id)

    def _rows_for(dates: Sequence[Any]) -> tuple[pd.DataFrame, dict[str, float]]:
        recs: list[dict[str, Any]] = []
        uplift_map: dict[str, float] = {}
        for d in dates:
            ds = pd.Timestamp(d).strftime("%Y-%m-%d")
            ev = cal_by_date.get(ds)
            is_ev = 1.0 if ev else 0.0
            t1 = ev["event_type_1"] if ev else ""
            t2 = ev["event_type_2"] if ev else ""
            is_promo = 0.0
            uplift_pct = 0.0
            for p in promos:
                if p["series_id"] is not None and series_id and p["series_id"] != series_id:
                    continue
                if p["start_date"] <= ds <= p["end_date"]:
                    is_promo = 1.0
                    uplift_pct += float(p.get("uplift_pct") or 0.0)
            if uplift_pct != 0.0:
                uplift_map[ds] = uplift_pct
            recs.append({
                "timestamp": pd.Timestamp(ds),
                "is_event": is_ev,
                "is_cultural": 1.0 if ("Cultural" in (t1, t2)) else 0.0,
                "is_national": 1.0 if ("National" in (t1, t2)) else 0.0,
                "is_religious": 1.0 if ("Religious" in (t1, t2)) else 0.0,
                "is_sporting": 1.0 if ("Sporting" in (t1, t2)) else 0.0,
                "is_promo": is_promo,
            })
        return pd.DataFrame(recs), uplift_map

    hist_cov, _ = _rows_for(history_dates)
    fut_cov, fut_uplifts = _rows_for(forecast_dates)
    return hist_cov, fut_cov, fut_uplifts
