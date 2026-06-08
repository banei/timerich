import asyncio
from datetime import date, datetime

from loguru import logger

from app.config import get_settings
from app.database import SessionLocal
from app.models import BackfillStatus, DataFetchLog
from app.services.market_data import MarketDataService
from app.services.notify import send_notification


class DataGuardian:
    """守护进程：确保每日刷新完成，并触发历史回填。"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_daily_date: date | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        asyncio.create_task(self._run_backfill())
        logger.info("DataGuardian 已启动")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("DataGuardian 已停止")

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except Exception as exc:
                logger.exception("DataGuardian tick 异常: {}", exc)
            await asyncio.sleep(60)

    async def _tick(self) -> None:
        now = datetime.now()
        if now.hour == self.settings.daily_refresh_hour and now.minute >= self.settings.daily_refresh_minute:
            if self._last_daily_date != now.date():
                ok = await self.run_daily_refresh(force=False)
                self._last_daily_date = now.date()
                if not ok:
                    await send_notification("日终刷新未完成", "将在窗口内重试")
                    await self.run_daily_refresh(force=True)

        if now.hour in {23, 0, 1, 2, 3, 4, 5, 6}:
            await self._ensure_daily_success()

    async def _ensure_daily_success(self) -> None:
        db = SessionLocal()
        try:
            today_key = f"daily_refresh:{date.today().isoformat()}"
            log = (
                db.query(DataFetchLog)
                .filter(DataFetchLog.data_key == today_key, DataFetchLog.status == "success")
                .first()
            )
            if log:
                return
            await self.run_daily_refresh(force=False)
        finally:
            db.close()

    async def run_daily_refresh(self, force: bool = False) -> bool:
        db = SessionLocal()
        try:
            svc = MarketDataService(db)
            results = svc.daily_refresh(force=force)
            ok = all(v for k, v in results.items() if k != "fund_navs") and results.get("fund_navs", 0) >= 0
            db.add(
                DataFetchLog(
                    data_key=f"daily_refresh:{date.today().isoformat()}",
                    status="success" if ok else "failed",
                    message=str(results),
                )
            )
            db.commit()
            if ok:
                await send_notification("日终刷新完成", str(results))
            return ok
        except Exception as exc:
            logger.error("日终刷新失败: {}", exc)
            db.add(
                DataFetchLog(
                    data_key=f"daily_refresh:{date.today().isoformat()}",
                    status="failed",
                    message=str(exc),
                )
            )
            db.commit()
            await send_notification("日终刷新失败", str(exc))
            return False
        finally:
            db.close()

    async def _run_backfill(self) -> None:
        await asyncio.sleep(5)
        db = SessionLocal()
        status = None
        try:
            task_key = "backfill_10y"
            status = db.query(BackfillStatus).filter(BackfillStatus.task_key == task_key).first()
            if status and status.status == "completed":
                return
            if status is None:
                status = BackfillStatus(task_key=task_key, status="running", progress_pct=0)
                db.add(status)
                db.commit()

            svc = MarketDataService(db)
            years = self.settings.backfill_years
            ndx_count = await asyncio.to_thread(svc.backfill_index, "NDX", years)
            status.progress_pct = 50
            status.message = f"NDX 回填 {ndx_count} 条"
            db.commit()

            h_count = await asyncio.to_thread(svc.backfill_index, "H30269", years)
            status.progress_pct = 100
            status.status = "completed"
            status.message = f"回填完成 NDX={ndx_count}, H30269={h_count}"
            db.commit()
            logger.info("10年历史回填完成: NDX={}, H30269={}", ndx_count, h_count)
        except Exception as exc:
            logger.error("回填任务失败: {}", exc)
            if status is not None:
                status.status = "failed"
                status.message = str(exc)
                db.commit()
        finally:
            db.close()


guardian = DataGuardian()
