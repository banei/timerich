from decimal import Decimal
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    data: T | None = None
    error: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class TokenData(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=4, max_length=128)
    role: str = "user"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    is_active: bool
    created_at: Any


class UserConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    risk_profile: str
    target_nasdaq_pct: Decimal
    target_dividend_pct: Decimal
    target_bond_pct: Decimal
    monthly_budget: Decimal
    rebalance_threshold_passive: Decimal
    rebalance_threshold_active: Decimal
    max_total_pct_of_family: Decimal
    family_total_assets: Decimal | None
    notes: str | None


class UserConfigUpdate(BaseModel):
    risk_profile: str | None = None
    target_nasdaq_pct: Decimal | None = None
    target_dividend_pct: Decimal | None = None
    target_bond_pct: Decimal | None = None
    monthly_budget: Decimal | None = None
    rebalance_threshold_passive: Decimal | None = None
    rebalance_threshold_active: Decimal | None = None
    max_total_pct_of_family: Decimal | None = None
    family_total_assets: Decimal | None = None
    notes: str | None = None


class TransactionCreate(BaseModel):
    date: str
    fund_id: int
    txn_type: str
    amount: Decimal
    nav: Decimal
    shares: Decimal | None = None
    coefficient: Decimal | None = None
    notes: str | None = None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: Any
    fund_id: int
    txn_type: str
    amount: Decimal
    nav: Decimal
    shares: Decimal
    coefficient: Decimal | None
    notes: str | None


class HoldingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fund_id: int
    fund_code: str | None = None
    fund_name: str | None = None
    total_shares: Decimal
    total_invested: Decimal
    current_value: Decimal


class ExecutionStepUpdate(BaseModel):
    step_name: str
    completed: bool


class DataSourceStatus(BaseModel):
    name: str
    data_key: str
    last_updated: str | None
    status: str
    from_cache: bool = False
    message: str | None = None
