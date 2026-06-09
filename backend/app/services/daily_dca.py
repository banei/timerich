"""日定投批量确认与组合记忆（以最后一次确认的组合为准）。"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import MonthlyExecution

MEMORY_KEY = "daily_dca_memory"
DAYS_KEY = "daily_dca_days"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def empty_memory() -> dict[str, Any]:
    return {
        "active": False,
        "fund_codes": [],
        "funds": [],
        "last_action_date": None,
        "confirmed_at": None,
    }


def _memory_from_detail(detail: dict | None) -> dict[str, Any] | None:
    if not detail or not isinstance(detail, dict):
        return None
    mem = detail.get(MEMORY_KEY)
    if isinstance(mem, dict) and (mem.get("fund_codes") or mem.get("active")):
        return mem
    return None


def get_daily_dca_memory(db: Session, user_id: int, month: str | None = None) -> dict[str, Any]:
    """读取用户定投组合记忆：优先当月，再按月份倒序。"""
    if month:
        row = (
            db.query(MonthlyExecution)
            .filter(MonthlyExecution.user_id == user_id, MonthlyExecution.month == month)
            .first()
        )
        mem = _memory_from_detail(row.execution_detail if row else None)
        if mem:
            return deepcopy(mem)

    rows = (
        db.query(MonthlyExecution)
        .filter(MonthlyExecution.user_id == user_id)
        .order_by(MonthlyExecution.month.desc())
        .all()
    )
    for row in rows:
        mem = _memory_from_detail(row.execution_detail)
        if mem:
            return deepcopy(mem)
    return empty_memory()


def get_today_dca_record(detail: dict | None, action_date: str) -> dict[str, Any] | None:
    if not detail or not isinstance(detail, dict):
        return None
    days = detail.get(DAYS_KEY)
    if not isinstance(days, dict):
        return None
    rec = days.get(action_date)
    return rec if isinstance(rec, dict) else None


def copy_memory_to_execution_detail(detail: dict | None, memory: dict[str, Any]) -> dict[str, Any]:
    out = dict(detail or {})
    out[MEMORY_KEY] = memory
    return out


def save_daily_dca_memory(row: MonthlyExecution, memory: dict[str, Any]) -> None:
    detail = dict(row.execution_detail or {})
    detail[MEMORY_KEY] = memory
    row.execution_detail = detail


def save_today_dca_record(row: MonthlyExecution, action_date: str, record: dict[str, Any]) -> None:
    detail = dict(row.execution_detail or {})
    days = dict(detail.get(DAYS_KEY) or {})
    days[action_date] = record
    detail[DAYS_KEY] = days
    row.execution_detail = detail


def memory_fund_codes(memory: dict[str, Any]) -> list[str]:
    codes = memory.get("fund_codes")
    if isinstance(codes, list) and codes:
        return [str(c) for c in codes]
    funds = memory.get("funds")
    if isinstance(funds, list):
        return [str(f["fund_code"]) for f in funds if isinstance(f, dict) and f.get("fund_code")]
    return []


def build_dca_batch(
    *,
    proposed_funds: list[dict[str, Any]],
    memory: dict[str, Any],
    today_record: dict[str, Any] | None,
    action_date: str,
    fund_catalog: dict[str, str] | None,
) -> dict[str, Any]:
    """生成前端批量确认区：勾选、状态、记忆提示。"""
    catalog = fund_catalog or {}
    mem_codes = memory_fund_codes(memory)
    mem_active = bool(memory.get("active")) and bool(mem_codes)

    base: dict[str, Any] = {
        "action_date": action_date,
        "status": "idle",
        "items": [],
        "total_selected": 0.0,
        "memory_active": mem_active,
        "memory_fund_codes": mem_codes,
        "memory_funds": [
            {
                "fund_code": c,
                "fund_name": catalog.get(c, c),
            }
            for c in mem_codes
        ],
        "memory_last_action_date": memory.get("last_action_date"),
        "memory_confirmed_at": memory.get("confirmed_at"),
    }

    if not proposed_funds and not today_record:
        return base

    if today_record and today_record.get("status") in ("confirmed", "cancelled"):
        items = today_record.get("funds") or []
        if not isinstance(items, list):
            items = []
        total = sum(float(i.get("planned_amount") or 0) for i in items if i.get("selected", True))
        base.update(
            {
                "status": today_record["status"],
                "items": items,
                "total_selected": total,
                "confirmed_at": today_record.get("confirmed_at"),
                "cancelled_at": today_record.get("cancelled_at"),
                "stop_memory": today_record.get("stop_memory", False),
            }
        )
        return base

    mem_set = set(mem_codes)
    items: list[dict[str, Any]] = []
    for f in proposed_funds:
        code = str(f.get("fund_code", ""))
        if mem_active and mem_set:
            selected = code in mem_set
        else:
            selected = True
        items.append({**f, "selected": selected})

    if mem_active and mem_set and not any(i.get("selected") for i in items):
        for i in items:
            i["selected"] = True

    total = sum(float(i.get("planned_amount") or 0) for i in items if i.get("selected"))
    base.update({"status": "pending", "items": items, "total_selected": total})
    return base


def confirm_daily_dca(
    row: MonthlyExecution,
    *,
    action_date: str,
    funds: list[dict[str, Any]],
    fund_catalog: dict[str, str] | None = None,
) -> dict[str, Any]:
    catalog = fund_catalog or {}
    selected = [f for f in funds if f.get("selected", True)]
    if not selected:
        raise ValueError("请至少勾选一只基金，或使用「取消今日」/「停止定投」")

    ordered_codes = [str(f["fund_code"]) for f in selected]
    normalized = []
    for f in selected:
        code = str(f["fund_code"])
        entry: dict[str, Any] = {
            "fund_code": code,
            "fund_name": f.get("fund_name") or catalog.get(code, code),
            "planned_amount": float(f.get("planned_amount") or 0),
            "selected": True,
        }
        for key in (
            "net_invested_amount",
            "purchase_fee_amount",
            "purchase_fee_rate",
            "nav",
            "nav_date",
            "nav_source",
            "estimated_shares",
        ):
            if f.get(key) is not None:
                entry[key] = f.get(key)
        normalized.append(entry)

    now = utc_now_iso()
    record = {
        "status": "confirmed",
        "funds": normalized,
        "confirmed_at": now,
    }
    save_today_dca_record(row, action_date, record)

    memory = {
        "active": True,
        "fund_codes": ordered_codes,
        "funds": normalized,
        "last_action_date": action_date,
        "confirmed_at": now,
    }
    save_daily_dca_memory(row, memory)
    return {"record": record, "memory": memory}


def cancel_daily_dca(
    row: MonthlyExecution,
    *,
    action_date: str,
    stop_memory: bool = False,
    proposed_funds: list[dict[str, Any]] | None = None,
    fund_catalog: dict[str, str] | None = None,
) -> dict[str, Any]:
    catalog = fund_catalog or {}
    now = utc_now_iso()
    funds_snapshot = []
    for f in proposed_funds or []:
        code = str(f.get("fund_code", ""))
        funds_snapshot.append(
            {
                "fund_code": code,
                "fund_name": f.get("fund_name") or catalog.get(code, code),
                "planned_amount": float(f.get("planned_amount") or 0),
                "selected": False,
            }
        )

    record = {
        "status": "cancelled",
        "funds": funds_snapshot,
        "cancelled_at": now,
        "stop_memory": stop_memory,
    }
    save_today_dca_record(row, action_date, record)

    memory = get_daily_dca_memory_from_row(row)
    if stop_memory:
        memory = empty_memory()
        save_daily_dca_memory(row, memory)
    return {"record": record, "memory": memory}


def stop_daily_dca_memory(row: MonthlyExecution) -> dict[str, Any]:
    memory = empty_memory()
    save_daily_dca_memory(row, memory)
    return memory


def get_daily_dca_memory_from_row(row: MonthlyExecution) -> dict[str, Any]:
    mem = _memory_from_detail(row.execution_detail)
    return deepcopy(mem) if mem else empty_memory()
