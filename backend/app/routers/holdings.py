from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Fund, MonthlyExecution, Transaction, User, UserConfig
from app.schemas.common import ApiResponse, ExecutionStepUpdate, TransactionCreate, TransactionOut
from app.services.allocation import calculate_monthly_amounts
from app.services.holdings import holdings_with_funds, recalculate_holdings

router = APIRouter(tags=["holdings"])


@router.get("/holdings", response_model=ApiResponse)
def get_holdings(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return ApiResponse(data=holdings_with_funds(db, user.id))


@router.get("/transactions", response_model=ApiResponse[list[TransactionOut]])
def list_transactions(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    rows = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(200)
        .all()
    )
    return ApiResponse(data=[TransactionOut.model_validate(r) for r in rows])


@router.post("/transactions", response_model=ApiResponse[TransactionOut])
def create_transaction(
    body: TransactionCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    fund = db.get(Fund, body.fund_id)
    if fund is None:
        raise HTTPException(status_code=404, detail="基金不存在")

    shares = body.shares
    if shares is None and body.nav > 0:
        shares = body.amount / body.nav

    txn = Transaction(
        user_id=user.id,
        date=date.fromisoformat(body.date),
        fund_id=body.fund_id,
        txn_type=body.txn_type,
        amount=body.amount,
        nav=body.nav,
        shares=shares or Decimal(0),
        coefficient=body.coefficient,
        notes=body.notes,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    recalculate_holdings(db, user.id)
    return ApiResponse(data=TransactionOut.model_validate(txn))


@router.delete("/transactions/{txn_id}", response_model=ApiResponse)
def delete_transaction(
    txn_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    txn = db.get(Transaction, txn_id)
    if txn is None or txn.user_id != user.id:
        raise HTTPException(status_code=404, detail="交易不存在")
    db.delete(txn)
    db.commit()
    recalculate_holdings(db, user.id)
    return ApiResponse(data={"deleted": txn_id})


execution_router = APIRouter(prefix="/execution", tags=["execution"])

STEP_MAP = {
    "check_signals": "step_check_signals",
    "calc_amounts": "step_calc_amounts",
    "execute_nasdaq": "step_execute_nasdaq",
    "check_premium": "step_check_premium",
    "execute_dividend": "step_execute_dividend",
    "execute_bond": "step_execute_bond",
    "record": "step_record",
}


def _get_or_create_execution(db: Session, user: User) -> MonthlyExecution:
    month = date.today().strftime("%Y-%m")
    row = (
        db.query(MonthlyExecution)
        .filter(MonthlyExecution.user_id == user.id, MonthlyExecution.month == month)
        .first()
    )
    if row:
        return row

    config = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
    amounts = {"nasdaq": 0, "dividend": 0, "bond": 0}
    if config:
        amounts = calculate_monthly_amounts(
            float(config.monthly_budget),
            {
                "nasdaq": float(config.target_nasdaq_pct),
                "dividend": float(config.target_dividend_pct),
                "bond": float(config.target_bond_pct),
            },
            {"nasdaq": 1.0, "dividend": 1.0},
        )

    row = MonthlyExecution(
        user_id=user.id,
        month=month,
        planned_nasdaq_amount=Decimal(str(amounts["nasdaq"])),
        planned_dividend_amount=Decimal(str(amounts["dividend"])),
        planned_bond_amount=Decimal(str(amounts["bond"])),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@execution_router.get("/current-month", response_model=ApiResponse)
def current_month(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    row = _get_or_create_execution(db, user)
    steps = {
        "check_signals": row.step_check_signals,
        "calc_amounts": row.step_calc_amounts,
        "execute_nasdaq": row.step_execute_nasdaq,
        "check_premium": row.step_check_premium,
        "execute_dividend": row.step_execute_dividend,
        "execute_bond": row.step_execute_bond,
        "record": row.step_record,
    }
    done = sum(1 for v in steps.values() if v)
    return ApiResponse(
        data={
            "month": row.month,
            "steps": steps,
            "progress": f"{done}/7",
            "planned": {
                "nasdaq": str(row.planned_nasdaq_amount),
                "dividend": str(row.planned_dividend_amount),
                "bond": str(row.planned_bond_amount),
            },
        }
    )


@execution_router.put("/{month}/step/{step_name}", response_model=ApiResponse)
def update_step(
    month: str,
    step_name: str,
    body: ExecutionStepUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    field = STEP_MAP.get(step_name)
    if field is None:
        raise HTTPException(status_code=400, detail="未知步骤")
    row = (
        db.query(MonthlyExecution)
        .filter(MonthlyExecution.user_id == user.id, MonthlyExecution.month == month)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="月度执行单不存在")
    setattr(row, field, body.completed)
    db.commit()
    return ApiResponse(data={"step": step_name, "completed": body.completed})


@execution_router.post("/{month}/complete", response_model=ApiResponse)
def complete_month(
    month: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    from datetime import datetime

    row = (
        db.query(MonthlyExecution)
        .filter(MonthlyExecution.user_id == user.id, MonthlyExecution.month == month)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="月度执行单不存在")
    row.completed_at = datetime.utcnow()
    db.commit()
    return ApiResponse(data={"completed_at": row.completed_at.isoformat()})
