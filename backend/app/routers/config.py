from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import BackfillStatus, Fund, User, UserConfig
from app.schemas.common import (
    ApiResponse,
    BucketConfigItem,
    BucketConfigOut,
    UserConfigOut,
    UserConfigUpdate,
)
from app.services.bucket_config import (
    bucket_config_to_json,
    buckets_from_update_items,
    parse_bucket_config,
    sync_legacy_targets,
    validate_bucket_targets,
)
from app.services.market_data import MarketDataService

router = APIRouter(prefix="/config", tags=["config"])
data_router = APIRouter(prefix="/data", tags=["data"])


def _serialize_config(config: UserConfig) -> UserConfigOut:
    buckets = parse_bucket_config(
        config.bucket_config,
        target_nasdaq=float(config.target_nasdaq_pct),
        target_dividend=float(config.target_dividend_pct),
        target_bond=float(config.target_bond_pct),
    )
    return UserConfigOut(
        risk_profile=config.risk_profile,
        target_nasdaq_pct=config.target_nasdaq_pct,
        target_dividend_pct=config.target_dividend_pct,
        target_bond_pct=config.target_bond_pct,
        bucket_config=BucketConfigOut(
            buckets=[
                BucketConfigItem(
                    code=b.code,
                    name=b.name,
                    target_pct=Decimal(str(b.target_pct)),
                    color=b.color,
                )
                for b in buckets
            ]
        ),
        monthly_budget=config.monthly_budget,
        rebalance_threshold_passive=config.rebalance_threshold_passive,
        rebalance_threshold_active=config.rebalance_threshold_active,
        max_total_pct_of_family=config.max_total_pct_of_family,
        family_total_assets=config.family_total_assets,
        notes=config.notes,
    )


@router.get("", response_model=ApiResponse[UserConfigOut])
def get_config(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    config = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
    if config is None:
        raise HTTPException(status_code=404, detail="配置不存在")
    return ApiResponse(data=_serialize_config(config))


@router.put("", response_model=ApiResponse[UserConfigOut])
def update_config(
    body: UserConfigUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    config = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
    if config is None:
        raise HTTPException(status_code=404, detail="配置不存在")

    data = body.model_dump(exclude_unset=True)
    if "bucket_config" in data and data["bucket_config"] is not None:
        buckets = buckets_from_update_items(data["bucket_config"]["buckets"])
        if not validate_bucket_targets(buckets):
            total = sum(b.target_pct for b in buckets)
            raise HTTPException(
                status_code=400,
                detail=f"五桶目标比例合计应为 100%，当前为 {total * 100:.1f}%",
            )
        config.bucket_config = bucket_config_to_json(buckets)
        legacy = sync_legacy_targets(buckets)
        config.target_nasdaq_pct = legacy["target_nasdaq_pct"]
        config.target_dividend_pct = legacy["target_dividend_pct"]
        config.target_bond_pct = legacy["target_bond_pct"]
        data.pop("bucket_config", None)
        data.pop("target_nasdaq_pct", None)
        data.pop("target_dividend_pct", None)
        data.pop("target_bond_pct", None)

    for field, value in data.items():
        setattr(config, field, value)

    db.commit()
    db.refresh(config)
    return ApiResponse(data=_serialize_config(config))


@data_router.get("/status", response_model=ApiResponse)
def data_status(db: Annotated[Session, Depends(get_db)], _: Annotated[User, Depends(get_current_user)]):
    svc = MarketDataService(db)
    backfill = db.query(BackfillStatus).filter(BackfillStatus.task_key == "backfill_10y").first()
    return ApiResponse(
        data={
            "sources": svc.list_data_status(),
            "backfill": {
                "status": backfill.status if backfill else "pending",
                "progress_pct": backfill.progress_pct if backfill else 0,
                "message": backfill.message if backfill else None,
            },
        }
    )


@data_router.post("/refresh", response_model=ApiResponse)
def refresh_data(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_admin)],
):
    svc = MarketDataService(db)
    return ApiResponse(data=svc.daily_refresh(force=True))


@data_router.get("/funds/limits", response_model=ApiResponse)
def fund_purchase_limits(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    live: bool = False,
    growth_only: bool = True,
):
    """纳指/成长档基金日限购。live=true 时实时拉取天天基金并入库。"""
    from app.services.growth_limits import all_growth_fund_codes
    from app.services.market_data import MarketDataService

    svc = MarketDataService(db)
    codes = all_growth_fund_codes() if growth_only else None
    if live:
        data = svc.fetch_fund_purchase_limits(codes, force=True)
    else:
        data = svc.list_fund_purchase_limits(codes)
    return ApiResponse(data=data)


@data_router.get("/funds", response_model=ApiResponse)
def list_funds(db: Annotated[Session, Depends(get_db)], _: Annotated[User, Depends(get_current_user)]):
    funds = db.query(Fund).filter(Fund.is_active.is_(True)).order_by(Fund.priority.desc()).all()
    return ApiResponse(
        data=[
            {
                "id": f.id,
                "code": f.code,
                "name": f.name,
                "fund_type": f.fund_type,
                "priority": f.priority,
                "purchase_fee_rate": str(f.purchase_fee_rate),
                "annual_fee_rate": str(f.annual_fee_rate),
                "redemption_fee_2y": str(f.redemption_fee_2y),
            }
            for f in funds
        ]
    )
