from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from loguru import logger
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import DataFetchLog, Fund, FundQuote, IndexQuote
from app.services.fund_purchase import fetch_em_purchase_for_codes


@dataclass
class QuoteResult:
    value: Decimal
    source: str
    from_cache: bool = False
    pe_ttm: Decimal | None = None
    dividend_yield: Decimal | None = None


class MarketDataService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def _log_fetch(
        self,
        data_key: str,
        status: str,
        source: str | None = None,
        message: str | None = None,
        ttl_minutes: int | None = None,
    ) -> None:
        next_fetch = None
        if ttl_minutes and status in {"success", "skipped"}:
            next_fetch = datetime.utcnow() + timedelta(minutes=ttl_minutes)
        self.db.add(
            DataFetchLog(
                data_key=data_key,
                status=status,
                source=source,
                message=message,
                next_fetch_after=next_fetch,
            )
        )
        self.db.commit()

    def _should_skip(self, data_key: str, force: bool = False) -> bool:
        if force:
            return False
        row = (
            self.db.query(DataFetchLog)
            .filter(DataFetchLog.data_key == data_key)
            .order_by(DataFetchLog.fetched_at.desc())
            .first()
        )
        if row is None or row.next_fetch_after is None:
            return False
        return row.next_fetch_after > datetime.utcnow() and row.status in {"success", "skipped"}

    def upsert_index_quote(
        self,
        symbol: str,
        quote_date: date,
        close: Decimal,
        source: str,
        pe_ttm: Decimal | None = None,
        dividend_yield: Decimal | None = None,
    ) -> None:
        stmt = mysql_insert(IndexQuote).values(
            symbol=symbol,
            date=quote_date,
            close=close,
            pe_ttm=pe_ttm,
            dividend_yield=dividend_yield,
            source=source,
            fetched_at=datetime.utcnow(),
        )
        stmt = stmt.on_duplicate_key_update(
            close=stmt.inserted.close,
            pe_ttm=stmt.inserted.pe_ttm,
            dividend_yield=stmt.inserted.dividend_yield,
            source=stmt.inserted.source,
            fetched_at=stmt.inserted.fetched_at,
        )
        self.db.execute(stmt)
        self.db.commit()

    def upsert_fund_quote(
        self,
        fund_id: int,
        quote_date: date,
        nav: Decimal | None,
        source: str,
        iopv: Decimal | None = None,
        premium_rate: Decimal | None = None,
        purchase_limit: Decimal | None = None,
    ) -> None:
        values: dict = {
            "fund_id": fund_id,
            "date": quote_date,
            "nav": nav,
            "iopv": iopv,
            "premium_rate": premium_rate,
            "purchase_limit": purchase_limit,
            "source": source,
            "fetched_at": datetime.utcnow(),
        }
        stmt = mysql_insert(FundQuote).values(**values)
        update_map = {
            "source": stmt.inserted.source,
            "fetched_at": stmt.inserted.fetched_at,
        }
        if nav is not None:
            update_map["nav"] = stmt.inserted.nav
        if iopv is not None:
            update_map["iopv"] = stmt.inserted.iopv
        if premium_rate is not None:
            update_map["premium_rate"] = stmt.inserted.premium_rate
        if purchase_limit is not None:
            update_map["purchase_limit"] = stmt.inserted.purchase_limit
        stmt = stmt.on_duplicate_key_update(**update_map)
        self.db.execute(stmt)
        self.db.commit()

    def set_fund_purchase_limit(
        self,
        fund_id: int,
        quote_date: date,
        purchase_limit: Decimal | None,
        source: str = "akshare",
    ) -> None:
        row = (
            self.db.query(FundQuote)
            .filter(FundQuote.fund_id == fund_id, FundQuote.date == quote_date)
            .first()
        )
        if row:
            row.purchase_limit = purchase_limit
            row.source = source
            row.fetched_at = datetime.utcnow()
        else:
            prev = (
                self.db.query(FundQuote)
                .filter(FundQuote.fund_id == fund_id)
                .order_by(FundQuote.date.desc())
                .first()
            )
            self.db.add(
                FundQuote(
                    fund_id=fund_id,
                    date=quote_date,
                    nav=prev.nav if prev else None,
                    purchase_limit=purchase_limit,
                    source=source,
                    fetched_at=datetime.utcnow(),
                )
            )
        self.db.commit()

    def get_latest_index(self, symbol: str) -> IndexQuote | None:
        return (
            self.db.query(IndexQuote)
            .filter(IndexQuote.symbol == symbol)
            .order_by(IndexQuote.date.desc())
            .first()
        )

    def fetch_ndx(self, force: bool = False) -> QuoteResult | None:
        data_key = f"index:NDX:{date.today().isoformat()}"
        if self._should_skip(data_key, force):
            cached = self.get_latest_index("NDX")
            if cached:
                self._log_fetch(data_key, "skipped", cached.source, "TTL 内跳过抓取", self.settings.cache_ttl_daily)
                return QuoteResult(cached.close, cached.source, True, cached.pe_ttm)
            return None

        try:
            import yfinance as yf

            ticker = yf.Ticker("^NDX")
            hist = ticker.history(period="5d")
            if hist.empty:
                raise ValueError("yfinance 无数据")
            close = Decimal(str(round(hist["Close"].iloc[-1], 4)))
            pe = None
            info = ticker.info or {}
            if info.get("trailingPE"):
                pe = Decimal(str(round(info["trailingPE"], 4)))
            self.upsert_index_quote("NDX", date.today(), close, "yfinance", pe_ttm=pe)
            self._log_fetch(data_key, "success", "yfinance", ttl_minutes=self.settings.cache_ttl_daily)
            return QuoteResult(close, "yfinance", False, pe)
        except Exception as exc:
            logger.warning("NDX yfinance 失败: {}", exc)
            try:
                import akshare as ak

                df = ak.index_us_stock_sina(symbol=".NDX")
                close = Decimal(str(round(float(df.iloc[-1]["close"]), 4)))
                self.upsert_index_quote("NDX", date.today(), close, "akshare")
                self._log_fetch(data_key, "success", "akshare", ttl_minutes=self.settings.cache_ttl_daily)
                return QuoteResult(close, "akshare")
            except Exception as exc2:
                logger.error("NDX 全部源失败: {}", exc2)
                self._log_fetch(data_key, "failed", None, str(exc2))
                cached = self.get_latest_index("NDX")
                if cached:
                    return QuoteResult(cached.close, cached.source, True, cached.pe_ttm)
                return None

    def fetch_usdcny(self, force: bool = False) -> QuoteResult | None:
        data_key = f"index:USDCNY:{date.today().isoformat()}"
        if self._should_skip(data_key, force):
            cached = self.get_latest_index("USDCNY")
            if cached:
                return QuoteResult(cached.close, cached.source, True)
            return None
        try:
            import yfinance as yf

            hist = yf.Ticker("CNY=X").history(period="5d")
            close = Decimal(str(round(hist["Close"].iloc[-1], 4)))
            self.upsert_index_quote("USDCNY", date.today(), close, "yfinance")
            self._log_fetch(data_key, "success", "yfinance", ttl_minutes=self.settings.cache_ttl_daily)
            return QuoteResult(close, "yfinance")
        except Exception as exc:
            logger.error("USDCNY 抓取失败: {}", exc)
            cached = self.get_latest_index("USDCNY")
            if cached:
                return QuoteResult(cached.close, cached.source, True)
            return None

    def fetch_h30269(self, force: bool = False) -> QuoteResult | None:
        data_key = f"index:H30269:{date.today().isoformat()}"
        if self._should_skip(data_key, force):
            cached = self.get_latest_index("H30269")
            if cached:
                return QuoteResult(cached.close, cached.source, True, dividend_yield=cached.dividend_yield)
            return None
        try:
            import akshare as ak

            df = ak.index_zh_a_hist(symbol="H30269", period="daily")
            close = Decimal(str(round(float(df.iloc[-1]["收盘"]), 4)))
            self.upsert_index_quote("H30269", date.today(), close, "akshare")
            self._log_fetch(data_key, "success", "akshare", ttl_minutes=self.settings.cache_ttl_daily)
            return QuoteResult(close, "akshare")
        except Exception as exc:
            logger.error("H30269 抓取失败: {}", exc)
            cached = self.get_latest_index("H30269")
            if cached:
                return QuoteResult(cached.close, cached.source, True)
            return None

    def fetch_fund_navs(self, force: bool = False) -> int:
        count = 0
        funds = self.db.query(Fund).filter(Fund.is_active.is_(True), Fund.fund_type == "otc_link").all()
        for fund in funds:
            data_key = f"fund:{fund.code}:{date.today().isoformat()}"
            if self._should_skip(data_key, force):
                continue
            try:
                import akshare as ak

                df = ak.fund_open_fund_info_em(symbol=fund.code, indicator="单位净值走势")
                nav = Decimal(str(round(float(df.iloc[-1]["净值"]), 4)))
                quote_date = date.fromisoformat(str(df.iloc[-1]["净值日期"])[:10])
                self.upsert_fund_quote(fund.id, quote_date, nav, "akshare")
                self._log_fetch(data_key, "success", "akshare", ttl_minutes=self.settings.cache_ttl_daily)
                count += 1
            except Exception as exc:
                logger.warning("基金 {} 净值失败: {}", fund.code, exc)
                self._log_fetch(data_key, "failed", None, str(exc))
        return count

    def fetch_fund_purchase_limits(
        self,
        fund_codes: list[str] | None = None,
        force: bool = False,
    ) -> list[dict]:
        """从天天基金拉取申购状态与日累计限购，写入 fund_quote.purchase_limit。"""
        data_key = f"fund:purchase_limits:{date.today().isoformat()}"
        if self._should_skip(data_key, force):
            return self.list_fund_purchase_limits(fund_codes)

        funds_q = self.db.query(Fund).filter(Fund.is_active.is_(True))
        if fund_codes:
            funds_q = funds_q.filter(Fund.code.in_(fund_codes))
        funds = funds_q.all()
        code_to_fund = {f.code: f for f in funds}
        target_codes = fund_codes or list(code_to_fund.keys())

        try:
            rows = fetch_em_purchase_for_codes(target_codes)
            today = date.today()
            saved = 0
            for info in rows:
                fund = code_to_fund.get(info.fund_code)
                if fund is None:
                    continue
                limit_val: Decimal | None
                if info.status == "paused":
                    limit_val = Decimal("0")
                elif info.daily_limit is not None:
                    limit_val = Decimal(str(round(info.daily_limit, 2)))
                else:
                    limit_val = None
                self.set_fund_purchase_limit(fund.id, today, limit_val, source=info.source)
                saved += 1
            self._log_fetch(
                data_key,
                "success",
                "akshare",
                f"更新 {saved} 只基金限购",
                self.settings.cache_ttl_daily,
            )
            return self.list_fund_purchase_limits(fund_codes)
        except Exception as exc:
            logger.error("基金限购抓取失败: {}", exc)
            self._log_fetch(data_key, "failed", None, str(exc))
            return self.list_fund_purchase_limits(fund_codes)

    def list_fund_purchase_limits(self, fund_codes: list[str] | None = None) -> list[dict]:
        funds_q = self.db.query(Fund).filter(Fund.is_active.is_(True))
        if fund_codes:
            funds_q = funds_q.filter(Fund.code.in_(fund_codes))
        funds = funds_q.all()
        result: list[dict] = []
        for fund in funds:
            quote = (
                self.db.query(FundQuote)
                .filter(FundQuote.fund_id == fund.id)
                .order_by(FundQuote.date.desc())
                .first()
            )
            limit = float(quote.purchase_limit) if quote and quote.purchase_limit is not None else None
            status = "unknown"
            if limit is not None:
                status = "paused" if limit <= 0 else "limited"
            result.append(
                {
                    "fund_code": fund.code,
                    "fund_name": fund.name,
                    "daily_limit": limit,
                    "status": status,
                    "quote_date": quote.date.isoformat() if quote else None,
                    "fetched_at": quote.fetched_at.isoformat() if quote and quote.fetched_at else None,
                    "source": quote.source if quote else None,
                }
            )
        return result

    def daily_refresh(self, force: bool = False) -> dict[str, int | bool]:
        from app.services.growth_limits import all_growth_fund_codes

        results = {
            "ndx": self.fetch_ndx(force=force) is not None,
            "usdcny": self.fetch_usdcny(force=force) is not None,
            "h30269": self.fetch_h30269(force=force) is not None,
            "fund_navs": self.fetch_fund_navs(force=force),
            "fund_purchase_limits": len(
                self.fetch_fund_purchase_limits(all_growth_fund_codes(), force=force)
            ),
        }
        return results

    def backfill_index(self, symbol: str, years: int) -> int:
        start = date.today() - timedelta(days=365 * years)
        count = 0
        try:
            if symbol == "NDX":
                import yfinance as yf

                hist = yf.Ticker("^NDX").history(start=start.isoformat())
                for idx, row in hist.iterrows():
                    d = idx.date()
                    existing = (
                        self.db.query(IndexQuote)
                        .filter(IndexQuote.symbol == "NDX", IndexQuote.date == d)
                        .first()
                    )
                    if existing:
                        continue
                    self.upsert_index_quote("NDX", d, Decimal(str(round(row["Close"], 4))), "yfinance_backfill")
                    count += 1
            elif symbol == "H30269":
                import akshare as ak

                df = ak.index_zh_a_hist(symbol="H30269", period="daily", start_date=start.strftime("%Y%m%d"))
                for _, row in df.iterrows():
                    d = date.fromisoformat(str(row["日期"])[:10])
                    existing = (
                        self.db.query(IndexQuote)
                        .filter(IndexQuote.symbol == "H30269", IndexQuote.date == d)
                        .first()
                    )
                    if existing:
                        continue
                    self.upsert_index_quote("H30269", d, Decimal(str(round(float(row["收盘"]), 4))), "akshare_backfill")
                    count += 1
        except Exception as exc:
            logger.error("回填 {} 失败: {}", symbol, exc)
        return count

    def list_data_status(self) -> list[dict]:
        items = [
            ("NDX 价格", "index:NDX"),
            ("USD/CNY", "index:USDCNY"),
            ("H30269 价格", "index:H30269"),
            ("基金净值", "fund:*"),
            ("基金限购", "fund:purchase_limits"),
        ]
        result = []
        for name, prefix in items:
            if prefix.startswith("index:"):
                sym = prefix.split(":")[1]
                row = self.get_latest_index(sym)
                log = (
                    self.db.query(DataFetchLog)
                    .filter(DataFetchLog.data_key.like(f"{prefix}%"))
                    .order_by(DataFetchLog.fetched_at.desc())
                    .first()
                )
                result.append(
                    {
                        "name": name,
                        "data_key": prefix,
                        "last_updated": (row.fetched_at.isoformat() if row else None),
                        "status": log.status if log else "unknown",
                        "from_cache": log.status == "skipped" if log else False,
                        "message": log.message if log else None,
                    }
                )
            elif prefix == "fund:purchase_limits":
                log = (
                    self.db.query(DataFetchLog)
                    .filter(DataFetchLog.data_key.like("fund:purchase_limits:%"))
                    .order_by(DataFetchLog.fetched_at.desc())
                    .first()
                )
                result.append(
                    {
                        "name": name,
                        "data_key": prefix,
                        "last_updated": log.fetched_at.isoformat() if log else None,
                        "status": log.status if log else "unknown",
                        "from_cache": log.status == "skipped" if log else False,
                        "message": log.message if log else None,
                    }
                )
            else:
                log = (
                    self.db.query(DataFetchLog)
                    .filter(DataFetchLog.data_key.like("fund:%"))
                    .filter(~DataFetchLog.data_key.like("fund:purchase_limits:%"))
                    .order_by(DataFetchLog.fetched_at.desc())
                    .first()
                )
                result.append(
                    {
                        "name": name,
                        "data_key": prefix,
                        "last_updated": log.fetched_at.isoformat() if log else None,
                        "status": log.status if log else "unknown",
                        "from_cache": False,
                        "message": log.message if log else None,
                    }
                )
        return result
