from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, hash_password, require_admin, verify_password
from app.config import get_settings
from app.database import get_db
from app.models import User, UserConfig
from app.schemas.common import ApiResponse, LoginRequest, TokenData, UserCreateRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/login", response_model=ApiResponse[TokenData])
def login(body: LoginRequest, db: Annotated[Session, Depends(get_db)]):
    user = db.query(User).filter(User.username == body.username).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    if user.locked_until and user.locked_until > datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="账户已锁定，请稍后再试")

    if not verify_password(body.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.login_max_attempts:
            from datetime import timedelta

            user.locked_until = datetime.utcnow() + timedelta(minutes=settings.login_lockout_minutes)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    user.failed_login_count = 0
    user.locked_until = None
    db.commit()

    token = create_access_token(user.id, user.username, user.role)
    return ApiResponse(
        data=TokenData(
            access_token=token,
            username=user.username,
            role=user.role,
        )
    )


@router.get("/me", response_model=ApiResponse[UserOut])
def me(user: Annotated[User, Depends(get_current_user)]):
    return ApiResponse(data=UserOut.model_validate(user))


users_router = APIRouter(prefix="/users", tags=["users"])


@users_router.get("", response_model=ApiResponse[list[UserOut]])
def list_users(
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    users = db.query(User).order_by(User.id).all()
    return ApiResponse(data=[UserOut.model_validate(u) for u in users])


@users_router.post("", response_model=ApiResponse[UserOut])
def create_user(
    body: UserCreateRequest,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role if body.role in {"admin", "user"} else "user",
    )
    db.add(user)
    db.flush()
    db.add(
        UserConfig(
            user_id=user.id,
            target_nasdaq_pct=Decimal("0.35"),
            target_dividend_pct=Decimal("0.40"),
            target_bond_pct=Decimal("0.25"),
            monthly_budget=Decimal("5000"),
        )
    )
    db.commit()
    db.refresh(user)
    return ApiResponse(data=UserOut.model_validate(user))


@users_router.post("/{user_id}/toggle", response_model=ApiResponse[UserOut])
def toggle_user(
    user_id: int,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="不能禁用自己")
    user.is_active = not user.is_active
    db.commit()
    db.refresh(user)
    return ApiResponse(data=UserOut.model_validate(user))
