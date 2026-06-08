from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger

from app.config import get_settings
from app.database import SessionLocal
from app.services.market_data import MarketDataService


def _daily_job() -> None:
    db = SessionLocal()
    try:
        svc = MarketDataService(db)
        svc.daily_refresh(force=False)
        logger.info("APScheduler 日终任务完成")
    except Exception as exc:
        logger.error("APScheduler 日终任务失败: {}", exc)
    finally:
        db.close()


def create_scheduler() -> BackgroundScheduler:
    settings = get_settings()
    scheduler = BackgroundScheduler(timezone=settings.tz)
    scheduler.add_job(
        _daily_job,
        "cron",
        hour=settings.daily_refresh_hour,
        minute=settings.daily_refresh_minute,
        id="daily_refresh",
        replace_existing=True,
    )
    return scheduler
