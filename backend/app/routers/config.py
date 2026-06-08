from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import BackfillStatus, Fund, User, UserConfig
from app.schemas.common import ApiResponse, UserConfigOut, UserConfigUpdate
from app.services.market_data import MarketDataService

router = APIRouter(prefix="/config", tags=["config"])
data_router = APIRouter(prefix="/data", tags=["data"])


@router.get("", response_model=ApiResponse[UserConfigOut])
def get_config(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    config = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
    if config is None:
        raise HTTPException(status_code=404, detail="配置不存在")
    return ApiResponse(data=UserConfigOut.model_validate(config))


@router.put("", response_model=ApiResponse[UserConfigOut])
def update_config(
    body: UserConfigUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    config = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
    if config is None:
        raise HTTPException(status_code=404, detail="配置不存在")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(config, field, value)
    db.commit()
    db.refresh(config)
    return ApiResponse(data=UserConfigOut.model_validate(config))


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
            }
            for f in funds
        ]
    )
