"""定投执行页 v2 API。"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.common import ApiResponse
from app.services.dca_amounts import get_last_investment_by_fund, sync_pool_defaults_from_records
from app.services.fund_pool import (
    delete_fund_pool_item,
    fund_pool_to_dict,
    list_fund_pool,
    lookup_fund_by_code,
    seed_default_fund_pool,
    upsert_fund_pool_item,
)
from app.services.investment_execution import (
    confirm_record,
    get_today_view,
    list_pending,
    month_history,
    record_to_dict,
    submit_today,
)

router = APIRouter(prefix="/execution", tags=["execution-v2"])


class SubmitTaskItem(BaseModel):
    fund_code: str
    fund_name: str | None = None
    bucket_code: str = "growth"
    record_type: str = "scheduled"
    amount: float
    frequency: str = "daily"


class SubmitTodayBody(BaseModel):
    tasks: list[SubmitTaskItem] = Field(default_factory=list)
    skip_codes: list[str] = Field(default_factory=list)
    date: str | None = None


class ConfirmRecordBody(BaseModel):
    status: str
    confirmed_amount: float | None = None
    confirmed_shares: float | None = None
    confirmed_nav: float | None = None
    confirmed_date: str | None = None


class BatchConfirmBody(BaseModel):
    records: list[dict] = Field(default_factory=list)


class FundPoolItemBody(BaseModel):
    bucket_code: str = "growth"
    fund_code: str
    fund_name: str | None = None
    daily_limit: float = 10.0
    frequency: str = "daily"
    buy_type: str = "scheduled"
    status: str = "active"
    sort_order: int = 0


def _parse_view_date(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD") from exc
    if parsed > date.today():
        raise HTTPException(status_code=400, detail="不能选择未来日期")
    return parsed


@router.get("/today", response_model=ApiResponse)
def execution_today(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    view_date: str | None = Query(None, alias="date"),
):
    as_of = _parse_view_date(view_date)
    return ApiResponse(data=get_today_view(db, user, as_of=as_of))


@router.post("/submit", response_model=ApiResponse)
def execution_submit(
    body: SubmitTodayBody,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    rows = submit_today(
        db,
        user,
        tasks=[t.model_dump() for t in body.tasks],
        skip_codes=body.skip_codes,
        as_of=_parse_view_date(body.date),
    )
    return ApiResponse(data={"records": [record_to_dict(r) for r in rows], "date": _parse_view_date(body.date).isoformat()})


@router.post("/skip-today", response_model=ApiResponse)
def execution_skip_today(
    user: Annotated[User, Depends(get_current_user)],
):
    return ApiResponse(data={"skipped": True, "date": date.today().isoformat()})


@router.get("/pending", response_model=ApiResponse)
def execution_pending(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return ApiResponse(data=list_pending(db, user.id))


@router.post("/sync-default-amounts", response_model=ApiResponse)
def execution_sync_default_amounts(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    seed_default_fund_pool(db, user.id)
    updated = sync_pool_defaults_from_records(db, user.id)
    return ApiResponse(data={"updated": updated, "count": len(updated)})


@router.patch("/records/{record_id}/confirm", response_model=ApiResponse)
def execution_confirm_one(
    record_id: int,
    body: ConfirmRecordBody,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        row = confirm_record(
            db,
            user,
            record_id,
            status=body.status,
            confirmed_amount=body.confirmed_amount,
            confirmed_shares=body.confirmed_shares,
            confirmed_nav=body.confirmed_nav,
            confirmed_date=body.confirmed_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data=record_to_dict(row))


@router.patch("/records/batch-confirm", response_model=ApiResponse)
def execution_batch_confirm(
    body: BatchConfirmBody,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    updated = []
    for item in body.records:
        rid = int(item["id"])
        try:
            row = confirm_record(
                db,
                user,
                rid,
                status=str(item["status"]),
                confirmed_amount=item.get("confirmed_amount"),
                confirmed_shares=item.get("confirmed_shares"),
                confirmed_nav=item.get("confirmed_nav"),
                confirmed_date=item.get("confirmed_date"),
            )
            updated.append(record_to_dict(row))
        except ValueError:
            continue
    return ApiResponse(data={"records": updated})


@router.get("/history", response_model=ApiResponse)
def execution_history(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    month: str | None = Query(None, description="YYYY-MM"),
    status: str = Query("all"),
):
    m = month or date.today().strftime("%Y-%m")
    return ApiResponse(data=month_history(db, user.id, m, status=status))


@router.get("/fund-lookup", response_model=ApiResponse)
def get_fund_lookup(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    code: str = Query(..., min_length=6, max_length=6, pattern=r"^\d{6}$"),
):
    return ApiResponse(data=lookup_fund_by_code(db, code))


@router.get("/fund-pool", response_model=ApiResponse)
def get_fund_pool(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    bucket: str | None = Query(None),
):
    seed_default_fund_pool(db, user.id)
    rows = list_fund_pool(db, user.id, bucket_code=bucket)
    last_by_fund = get_last_investment_by_fund(db, user.id)
    return ApiResponse(data=fund_pool_to_dict(rows, last_by_fund=last_by_fund))


@router.put("/fund-pool", response_model=ApiResponse)
def put_fund_pool_item(
    body: FundPoolItemBody,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    row = upsert_fund_pool_item(db, user.id, body.model_dump())
    last_by_fund = get_last_investment_by_fund(db, user.id)
    return ApiResponse(data=fund_pool_to_dict([row], last_by_fund=last_by_fund)[0])


@router.delete("/fund-pool/{item_id}", response_model=ApiResponse)
def delete_fund_pool(
    item_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if not delete_fund_pool_item(db, user.id, item_id):
        raise HTTPException(status_code=404, detail="配置不存在")
    return ApiResponse(data={"deleted": item_id})
