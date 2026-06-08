# DCA-Dashboard 产品规格与实施指南

> 给 Cursor 实施用的完整 spec
> 配套：《纳指100+红利低波 组合定投实操手册》《定时检查执行清单》
> 版本：v1.1 / 2026-06（MySQL 版）

---

## 0. 给 Cursor 的总体说明

**项目目标**：把投资手册的执行流程系统化，提供 Web 仪表盘自动获取数据、计算系数、跟踪持仓、辅助再平衡。

**实施原则**：
1. **MVP 优先**：先做能跑通的最小版本，再加细节
2. **数据获取容错**：任何外部数据源都可能失败，必须有 fallback 和缓存
3. **业务逻辑沉淀在后端**：所有系数计算、再平衡逻辑写成纯函数，便于单元测试
4. **前端只展示，不计算**：前端不重复实现业务逻辑

**项目代号**：`dca-dashboard`

---

## 1. 技术栈选型

| 层 | 技术 | 版本 | 理由 |
|---|---|---|---|
| 后端语言 | Python | 3.11+ | 数据生态成熟 |
| Web 框架 | FastAPI | 0.110+ | 自动 OpenAPI 文档, 异步 |
| ORM | SQLAlchemy 2.0 | 最新 | 类型安全 |
| 数据库 | **MySQL** | **8.0+** | 远程访问/多端、生态成熟 |
| DB 驱动 | PyMySQL + cryptography | 最新 | 纯 Python, 无需编译 |
| 连接池 | SQLAlchemy 自带 QueuePool | - | pool_size=10, max_overflow=20 |
| 任务调度 | APScheduler | 3.10+ | 进程内, 无需 Redis |
| 数据源-A股/基金/指数 | akshare | 最新 | 开源, 覆盖全 |
| 数据源-美股/汇率 | yfinance | 最新 | 稳定 |
| HTTP 客户端 | httpx | 最新 | 异步 |
| 前端框架 | React 18 + Vite | 最新 | Cursor 熟悉 |
| UI 库 | shadcn/ui + TailwindCSS | 最新 | 现代化, 易改 |
| 图表 | Recharts | 2.x | React 原生 |
| 表单 | react-hook-form + zod | 最新 | 类型安全 |
| 状态管理 | TanStack Query (React Query) | v5 | 服务端状态首选 |
| 路由 | React Router | v6 | 标准 |
| 部署 | Docker Compose | - | 一键启动 |

**不用 baostock**：覆盖范围不够，akshare 是它的超集（且开源活跃）。

---

## 2. 数据源对照表（核心！）

每个数据源都要实现**主源 + 备用源 + 本地缓存**三级容错。

| 业务数据 | 主数据源 | 备用源 | 缓存策略 | 更新频率 |
|---|---|---|---|---|
| 纳指100 价格/历史 | yfinance (`^NDX`) | akshare `index_us_stock_sina` | 1小时 | 日终 |
| 纳指100 PE-TTM | yfinance (Ticker info) | 手动录入 | 1天 | 周度 |
| 纳指100 历史PE（算分位）| 本地累计存储 | - | 永久 | 累计 |
| H30269 价格指数 | akshare `index_zh_a_hist(symbol="H30269")` | 中证官网爬虫 | 4小时 | 日终 |
| H30269 全收益指数 | akshare `index_value_hist_funddb` 或自行计算 | 中证factsheet | 1天 | 月度 |
| H30269 股息率 | csindex.com.cn factsheet PDF 解析 | 手动录入 | 1天 | 月度 |
| USD/CNY 汇率 | yfinance (`CNY=X`) | akshare `currency_boc_sina` | 1小时 | 日终 |
| 场内ETF 实时价+IOPV | akshare `fund_etf_spot_em` | akshare `fund_etf_hist_em` | 5分钟 | 盘中 |
| ETF 溢价率 | 由IOPV和现价计算 | - | 5分钟 | 盘中 |
| 场外基金净值 | akshare `fund_open_fund_info_em` | 天天基金API | 1天 | 日终(15点后) |
| 基金限购状态 | akshare `fund_purchase_em` | - | 1天 | 日终 |
| 各基金费率 | 本地配置（手动维护） | - | 永久 | 半年 |

**关键约定**：
- 所有数据源拉取必须包含 `try/except` + 日志记录 + 默认值/上次缓存值返回
- 时间戳统一用 UTC 存储，前端展示按北京时间
- 历史 PE 数据 yfinance 不直接给 → 用价格 ÷ 当年 EPS 估算并入库

---

## 3. 数据库 Schema

SQLAlchemy 2.0 ORM 风格。所有表都有 `created_at` / `updated_at`。

**MySQL 通用约定**（所有表统一）：
- 引擎: **InnoDB**（事务、外键、行级锁）
- 字符集: **utf8mb4**, collation: **utf8mb4_0900_ai_ci**
- 主键: `BIGINT UNSIGNED AUTO_INCREMENT`（除 UserConfig 用固定 id=1）
- 金额字段: **`DECIMAL(18,4)`**，禁止用 FLOAT/DOUBLE（精度问题）
- 比例/系数字段: **`DECIMAL(8,6)`**（最多6位小数, 如 0.500000）
- 时间字段: **`DATETIME(3)`**（毫秒精度），不用 TIMESTAMP（2038问题+时区陷阱）
- 时区: 所有时间入库 UTC，在 MySQL 连接串设 `time_zone='+00:00'`
- 枚举字段（如 `txn_type`）: 用 `VARCHAR(32) + CHECK` 而非 ENUM 类型（ENUM 改值需 ALTER TABLE）
- JSON 字段: MySQL 8.0 原生 JSON 类型可用，用于灵活字段
- 索引: 凡是 WHERE/JOIN/ORDER BY 涉及的列都建索引

### 3.1 资产与配置

> 下面用 SQLAlchemy 2.0 风格示例，所有字段类型都已选好 MySQL 对应列类型。

```python
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import DECIMAL, String, Integer, BigInteger, Boolean, DateTime, Date, JSON, ForeignKey, Index
from decimal import Decimal
from datetime import datetime, date

# 用户配置 (单用户, 单行)
class UserConfig(Base):
    __tablename__ = "user_config"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    risk_profile: Mapped[str] = mapped_column(String(16))  # 'aggressive' | 'balanced' | 'defensive'
    target_nasdaq_pct: Mapped[Decimal] = mapped_column(DECIMAL(8, 6))     # 0.500000
    target_dividend_pct: Mapped[Decimal] = mapped_column(DECIMAL(8, 6))
    target_bond_pct: Mapped[Decimal] = mapped_column(DECIMAL(8, 6))
    monthly_budget: Mapped[Decimal] = mapped_column(DECIMAL(18, 4))       # 月预算
    rebalance_threshold_passive: Mapped[Decimal] = mapped_column(DECIMAL(8, 6), default=Decimal("0.05"))
    rebalance_threshold_active: Mapped[Decimal] = mapped_column(DECIMAL(8, 6), default=Decimal("0.10"))
    max_total_pct_of_family: Mapped[Decimal] = mapped_column(DECIMAL(8, 6), default=Decimal("0.30"))
    family_total_assets: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 4), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(3), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(3), default=datetime.utcnow, onupdate=datetime.utcnow)

# 资产分类
class AssetCategory(Base):
    __tablename__ = "asset_category"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)  # 'NASDAQ' | 'DIVIDEND' | 'BOND' | 'SP500'
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

# 基金/标的池
class Fund(Base):
    __tablename__ = "fund"
    __table_args__ = (
        Index("ix_fund_category", "category_id"),
        Index("ix_fund_active", "is_active"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)  # '161130'
    name: Mapped[str] = mapped_column(String(128))
    category_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("asset_category.id"))
    fund_type: Mapped[str] = mapped_column(String(16))  # 'otc_link' | 'etf' | 'bond_etf'
    market: Mapped[str | None] = mapped_column(String(4), nullable=True)  # 'SH' | 'SZ' | NULL
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1-5
    annual_fee_rate: Mapped[Decimal] = mapped_column(DECIMAL(8, 6))   # 0.008500
    purchase_fee_rate: Mapped[Decimal] = mapped_column(DECIMAL(8, 6))
    redemption_fee_2y: Mapped[Decimal] = mapped_column(DECIMAL(8, 6), default=Decimal(0))
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(3), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(3), default=datetime.utcnow, onupdate=datetime.utcnow)
```

### 3.2 市场数据 (时序)

```python
# 注意: 下面只列出关键字段类型差异, 其他通用字段(created_at等)与3.1相同

class FundQuote(Base):
    """场外基金净值, 场内ETF收盘价均存这里"""
    __tablename__ = "fund_quote"
    __table_args__ = (
        Index("ix_fund_quote_unique", "fund_id", "date", unique=True),  # 防重复入库
        Index("ix_fund_quote_date", "date"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fund_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fund.id"))
    date: Mapped[date] = mapped_column(Date)
    nav: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 4), nullable=True)
    iopv: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 4), nullable=True)
    premium_rate: Mapped[Decimal | None] = mapped_column(DECIMAL(8, 6), nullable=True)
    purchase_limit: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 2), nullable=True)  # 0=暂停
    source: Mapped[str] = mapped_column(String(32))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(3), default=datetime.utcnow)

class IndexQuote(Base):
    """指数行情: 纳指100/H30269/汇率"""
    __tablename__ = "index_quote"
    __table_args__ = (
        Index("ix_index_quote_unique", "symbol", "date", unique=True),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32))  # 'NDX' | 'H30269' | 'H30269.TR' | 'USDCNY'
    date: Mapped[date] = mapped_column(Date)
    close: Mapped[Decimal] = mapped_column(DECIMAL(18, 4))
    pe_ttm: Mapped[Decimal | None] = mapped_column(DECIMAL(10, 4), nullable=True)
    dividend_yield: Mapped[Decimal | None] = mapped_column(DECIMAL(8, 6), nullable=True)
    source: Mapped[str] = mapped_column(String(32))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(3), default=datetime.utcnow)

class PEHistory(Base):
    """纳指100 PE历史(用于算分位)"""
    __tablename__ = "pe_history"
    __table_args__ = (
        Index("ix_pe_history_date", "date", unique=True),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date)
    pe_ttm: Mapped[Decimal] = mapped_column(DECIMAL(10, 4))
    rolling_10y_percentile: Mapped[Decimal | None] = mapped_column(DECIMAL(8, 6), nullable=True)
```

### 3.3 持仓与交易

```python
class Transaction(Base):
    """每一笔买入/卖出"""
    __tablename__ = "transaction"
    __table_args__ = (
        Index("ix_txn_date", "date"),
        Index("ix_txn_fund", "fund_id"),
        Index("ix_txn_type", "txn_type"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date)
    fund_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fund.id"))
    txn_type: Mapped[str] = mapped_column(String(32))  # 'buy'|'sell'|'dividend'|'rebalance_buy'|'rebalance_sell'
    amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 4))
    nav: Mapped[Decimal] = mapped_column(DECIMAL(18, 4))
    shares: Mapped[Decimal] = mapped_column(DECIMAL(18, 6))  # 份额精度更高
    coefficient: Mapped[Decimal | None] = mapped_column(DECIMAL(8, 6), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(3), default=datetime.utcnow)

class Holding(Base):
    """当前持仓(由Transaction聚合计算, 这里做缓存表)"""
    __tablename__ = "holding"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}
    
    fund_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fund.id"), primary_key=True)
    total_shares: Mapped[Decimal] = mapped_column(DECIMAL(18, 6), default=Decimal(0))
    total_invested: Mapped[Decimal] = mapped_column(DECIMAL(18, 4), default=Decimal(0))
    current_value: Mapped[Decimal] = mapped_column(DECIMAL(18, 4), default=Decimal(0))
    last_updated: Mapped[datetime] = mapped_column(DateTime(3), default=datetime.utcnow, onupdate=datetime.utcnow)
```

### 3.4 信号与执行

```python
class MonthlyCoefficient(Base):
    """每月生效的系数, 月底计算后写入"""
    __tablename__ = "monthly_coefficient"
    __table_args__ = (
        Index("ix_monthly_coef_month", "month", unique=True),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    month: Mapped[str] = mapped_column(String(7))  # 'YYYY-MM'
    nasdaq_pe_percentile: Mapped[Decimal] = mapped_column(DECIMAL(8, 6))
    nasdaq_coefficient: Mapped[Decimal] = mapped_column(DECIMAL(8, 6))
    dividend_yield: Mapped[Decimal] = mapped_column(DECIMAL(8, 6))
    dividend_coefficient: Mapped[Decimal] = mapped_column(DECIMAL(8, 6))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(3), default=datetime.utcnow)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

class MonthlyExecution(Base):
    """每月10日执行的勾选清单"""
    __tablename__ = "monthly_execution"
    __table_args__ = (
        Index("ix_monthly_exec_month", "month", unique=True),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    month: Mapped[str] = mapped_column(String(7))  # 'YYYY-MM'
    step_check_signals: Mapped[bool] = mapped_column(Boolean, default=False)
    step_calc_amounts: Mapped[bool] = mapped_column(Boolean, default=False)
    step_execute_nasdaq: Mapped[bool] = mapped_column(Boolean, default=False)
    step_check_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    step_execute_dividend: Mapped[bool] = mapped_column(Boolean, default=False)
    step_execute_bond: Mapped[bool] = mapped_column(Boolean, default=False)
    step_record: Mapped[bool] = mapped_column(Boolean, default=False)
    planned_nasdaq_amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 4))
    planned_dividend_amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 4))
    planned_bond_amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 4))
    actual_nasdaq_amount: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 4), nullable=True)
    actual_dividend_amount: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 4), nullable=True)
    actual_bond_amount: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 4), nullable=True)
    execution_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 各基金实际执行金额
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(3), nullable=True)

class RebalanceLog(Base):
    """每次再平衡记录"""
    __tablename__ = "rebalance_log"
    __table_args__ = (
        Index("ix_rebalance_date", "date"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date)
    type: Mapped[str] = mapped_column(String(32))  # 'annual'|'quarterly_triggered'|'manual'
    before_nasdaq_pct: Mapped[Decimal] = mapped_column(DECIMAL(8, 6))
    before_dividend_pct: Mapped[Decimal] = mapped_column(DECIMAL(8, 6))
    before_bond_pct: Mapped[Decimal] = mapped_column(DECIMAL(8, 6))
    after_nasdaq_pct: Mapped[Decimal | None] = mapped_column(DECIMAL(8, 6), nullable=True)
    after_dividend_pct: Mapped[Decimal | None] = mapped_column(DECIMAL(8, 6), nullable=True)
    after_bond_pct: Mapped[Decimal | None] = mapped_column(DECIMAL(8, 6), nullable=True)
    action_taken: Mapped[str] = mapped_column(String(32))  # 'none'|'passive_via_new_investment'|'active_sell_buy'
    orders_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 具体订单
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(3), default=datetime.utcnow)
```

---

## 4. 业务逻辑模块（纯函数, 易测试）

放在 `backend/services/` 下，每个模块独立可单元测试。

### 4.1 估值系数 `services/coefficients.py`

```python
def calculate_nasdaq_coefficient(pe_percentile: float) -> tuple[float, str]:
    """
    输入: 纳指100 PE-TTM 在近10年的分位 (0.0-1.0)
    输出: (系数, 说明)
    """
    if pe_percentile < 0.30: return (1.5, "低估")
    if pe_percentile < 0.70: return (1.0, "合理")
    if pe_percentile < 0.90: return (0.7, "偏高")
    return (0.5, "高估")

def calculate_dividend_coefficient(dividend_yield: float) -> tuple[float, str]:
    """
    输入: H30269 当前股息率 (e.g. 0.047 = 4.7%)
    输出: (系数, 说明)
    """
    if dividend_yield >= 0.06: return (1.5, "高股息")
    if dividend_yield >= 0.05: return (1.0, "正常")
    if dividend_yield >= 0.04: return (0.7, "偏高")
    return (0.3, "暂停大额")
```

### 4.2 仓位计算 `services/allocation.py`

```python
def calculate_monthly_amounts(
    budget: float,
    target: dict,  # {'nasdaq': 0.5, 'dividend': 0.3, 'bond': 0.2}
    coefficients: dict,  # {'nasdaq': 0.5, 'dividend': 1.0}
) -> dict:
    """
    计算本月各档应投金额, 含未投部分的转移逻辑
    """
    nasdaq_planned = budget * target['nasdaq']
    nasdaq_actual = nasdaq_planned * coefficients['nasdaq']
    nasdaq_spillover = nasdaq_planned - nasdaq_actual  # 系数<1时溢出
    
    dividend_planned = budget * target['dividend']
    dividend_actual = dividend_planned * coefficients['dividend']
    dividend_spillover = dividend_planned - dividend_actual
    
    bond_planned = budget * target['bond']
    
    # 溢出资金优先去红利低波,再去债券 (除非红利也系数<1)
    if coefficients['dividend'] >= 1.0:
        dividend_actual += nasdaq_spillover
    else:
        bond_planned += nasdaq_spillover + dividend_spillover
    
    return {
        'nasdaq': nasdaq_actual,
        'dividend': dividend_actual,
        'bond': bond_planned,
        'total': nasdaq_actual + dividend_actual + bond_planned,
    }
```

### 4.3 再平衡 `services/rebalance.py`

```python
def evaluate_rebalance(
    current_values: dict,  # {'nasdaq': 245000, 'dividend': 440000, 'bond': 257500}
    target: dict,  # {'nasdaq': 0.35, 'dividend': 0.40, 'bond': 0.25}
    threshold_passive: float = 0.05,
    threshold_active: float = 0.10,
) -> dict:
    """
    返回:
    {
      'total': 942500,
      'current_pct': {...},
      'deviations': {...},
      'max_deviation': 0.10,
      'recommendation': 'active_rebalance' | 'passive_via_new_investment' | 'no_action',
      'orders': [{'fund_category': 'dividend', 'action': 'sell', 'amount': 40000}, ...]
    }
    """
    pass  # 完整实现见 spec 附录 A

def generate_sell_orders(
    excess_per_category: dict,
    holdings: list[Holding],
    funds: list[Fund],
) -> list[dict]:
    """
    决定卖哪只基金的份额, 按节税顺序:
    1. 优先卖持有>1年的份额
    2. 同类基金中优先卖费率高的
    3. 同费率中优先卖累计收益低的
    """
    pass
```

### 4.4 估值分位计算 `services/percentile.py`

```python
def calculate_percentile(
    current_value: float,
    historical_values: list[float],
    lookback_years: int = 10,
) -> float:
    """
    返回 current_value 在 historical_values 中的分位 (0.0-1.0)
    用于纳指 PE 分位计算
    """
    import numpy as np
    arr = np.array(historical_values)
    return float(np.mean(arr <= current_value))
```

### 4.5 回测引擎 `services/backtest.py`

```python
def backtest_dca(
    start_date: date,
    end_date: date,
    monthly_amount: float,
    target_allocation: dict,
    use_coefficients: bool = True,
    use_rebalance: bool = True,
    rebalance_freq: str = 'annual',
) -> dict:
    """
    回测 2016-2026 的组合表现
    返回月度时间序列 + 关键指标
    
    返回:
    {
      'time_series': [
        {'date': '2016-01-31', 'total_value': 1200, 'invested': 1200, 
         'nasdaq_value': 600, 'dividend_value': 360, 'bond_value': 240},
        ...
      ],
      'final_value': 415000,
      'total_invested': 125000,
      'profit': 290000,
      'irr': 0.14,
      'max_drawdown': -0.22,
      'max_drawdown_date': '2022-10-15',
      'sharpe_ratio': 0.85,
    }
    """
    pass
```

---

## 5. API 接口设计

REST 风格，前缀 `/api/v1/`。所有响应包含 `{"data": ..., "error": null, "meta": {...}}`。

### 5.1 仪表盘相关

```
GET  /api/v1/dashboard/summary
     返回: 当前总览(总资产/配比/今日变动/本月系数)

GET  /api/v1/dashboard/signals
     返回: 当前估值信号(纳指PE分位/红利股息率/系数)
     
GET  /api/v1/dashboard/allocation
     返回: 当前实际配比 vs 目标配比

POST /api/v1/dashboard/refresh
     手动触发数据刷新, 返回任务ID
     
GET  /api/v1/dashboard/refresh/{task_id}
     查询刷新进度
```

### 5.2 数据查询

```
GET  /api/v1/data/funds                 # 基金池列表
GET  /api/v1/data/funds/{code}/quote    # 单只基金最新报价
GET  /api/v1/data/funds/{code}/history?days=365  # 历史净值
GET  /api/v1/data/index/{symbol}/quote  # NDX / H30269 / USDCNY
GET  /api/v1/data/index/NDX/percentile  # 纳指当前PE分位
GET  /api/v1/data/etf/premium           # 所有场内ETF溢价率
GET  /api/v1/data/funds/limits          # 限购状态列表
```

### 5.3 持仓与交易

```
GET  /api/v1/transactions               # 交易历史
POST /api/v1/transactions               # 录入新交易
PUT  /api/v1/transactions/{id}
DELETE /api/v1/transactions/{id}
POST /api/v1/transactions/batch-import  # CSV批量导入

GET  /api/v1/holdings                   # 当前持仓汇总
GET  /api/v1/holdings/by-category       # 按类别汇总
```

### 5.4 月度执行

```
GET  /api/v1/execution/current-month    # 本月清单(自动生成)
PUT  /api/v1/execution/{month}/step/{step_name}  # 勾选某一步
POST /api/v1/execution/{month}/complete # 标记当月完成
GET  /api/v1/execution/history          # 历史完成情况
```

### 5.5 再平衡

```
POST /api/v1/rebalance/evaluate         # 评估当前是否需要再平衡
     输入: 可选指定日期 (默认当前)
     输出: 评估结果 + 建议操作

POST /api/v1/rebalance/execute          # 提交再平衡操作
     输入: 卖买订单列表
     输出: 写入 Transaction 表
     
GET  /api/v1/rebalance/history          # 历史再平衡记录
```

### 5.6 回测

```
POST /api/v1/backtest/run
     输入: 起止日期, 月预算, 配比, 是否启用系数/再平衡
     输出: 完整时间序列 + 指标
     
GET  /api/v1/backtest/scenarios         # 预设场景列表
     预设: '50/30/20+系数+再平衡', '简单等额', '纯纳指', '纯红利' 等
```

### 5.7 配置

```
GET  /api/v1/config                     # 用户配置
PUT  /api/v1/config                     # 更新配置
GET  /api/v1/config/funds-pool          # 基金池
PUT  /api/v1/config/funds-pool/{id}     # 修改基金优先级/费率
```

---

## 6. 定时任务设计 (APScheduler)

后端启动时注册以下 cron 任务，配置在 `backend/scheduler.py`。

| 任务名 | Cron | 内容 | 失败处理 |
|---|---|---|---|
| `update_index_quotes` | `0 16 * * 1-5` (A股收盘后) | 拉 H30269/USDCNY | 记录失败, 不重试 |
| `update_us_index` | `0 6 * * 2-6` (美股收盘后) | 拉 NDX 价格+PE | 同上 |
| `update_fund_navs` | `0 21 * * 1-5` (基金净值公布后) | 拉所有场外基金净值 | 同上 |
| `update_etf_prices` | `*/15 9-15 * * 1-5` (A股交易时段) | 拉场内ETF实时+IOPV | 同上 |
| `update_purchase_limits` | `0 9 * * 1-5` | 拉限购状态 | 同上 |
| `calculate_monthly_coefficient` | `0 23 28-31 * *` (月末) | 计算下月系数并写入 | 必须重试 |
| `generate_monthly_execution` | `0 0 1 * *` (每月1日) | 生成本月执行单 | 必须重试 |
| `cleanup_logs` | `0 3 1 * *` (每月1日) | 清理>2年的日志 | - |

**手动触发接口**：所有任务通过 `POST /api/v1/admin/jobs/{job_name}/run` 手动触发。

---

## 7. 前端页面设计

### 7.1 整体布局

```
┌─────────────────────────────────────────────────┐
│ 侧边栏          │ 顶栏: 标题 / 刷新 / 设置        │
│                │ ─────────────────────────────  │
│ □ 仪表盘        │                                │
│ □ 持仓          │  当前页面内容                   │
│ □ 月度执行      │                                │
│ □ 再平衡        │                                │
│ □ 回测          │                                │
│ □ 数据管理      │                                │
│ □ 设置          │                                │
│                │                                │
└─────────────────────────────────────────────────┘
```

### 7.2 页面 1：仪表盘 `/dashboard`

**布局**（自上而下）：

```
┌─ 顶部 KPI 卡片(4列) ────────────────────────────┐
│ [总资产]   [本月浮盈]   [累计浮盈率]  [距家庭资产上限] │
│ ¥942,500   +¥12,300     +25.4%       已用 21%      │
└────────────────────────────────────────────────┘

┌─ 估值信号(2列) ─────────────────────────────────┐
│ 纳指100                  │ 红利低波              │
│ PE-TTM 分位: 94%         │ 股息率: 4.7%          │
│ ━━━━━━━━━━━━━━━ [仪表盘] │ ━━━━━━━━━━━━━━━ [仪表盘] │
│ 系数: 0.5 (高估)         │ 系数: 1.0 (正常)      │
└────────────────────────────────────────────────┘

┌─ 当前配比 vs 目标 (饼图+柱状图) ─────────────────┐
│ [Pie图: 当前]   [Pie图: 目标]   [偏离条形图]      │
│ 纳指 26% (-9%)  红利 47% (+7%)  债券 27% (+2%)   │
│ 提示: 纳指偏离-9%, 建议下月新投入向纳指倾斜       │
└────────────────────────────────────────────────┘

┌─ 资产历史走势 (折线图) ──────────────────────────┐
│ [按月]/[按季]/[按年]   [全部] / [近1年] / [近3年] │
│   折线: 累计投入 / 当前市值                       │
└────────────────────────────────────────────────┘

┌─ 本月待办 ──────────────────────────────────────┐
│ 月度执行 6/7 已完成 [继续 →]                     │
│ 下次定投日: 2026-07-10 (32天后)                  │
└────────────────────────────────────────────────┘
```

**组件**：
- KPI 卡：`<KPICard title amount delta />`
- 仪表盘：`<GaugeChart value max thresholds />` (用 Recharts 自制或 react-gauge-chart)
- 饼图：`<PieChart />` Recharts
- 偏离条形：`<DeviationBar current target />`
- 折线：`<LineChart />` Recharts

### 7.3 页面 2：持仓 `/holdings`

```
[Tab: 按基金 | 按类别 | 交易历史]

按基金视图(默认):
┌──────────────────────────────────────────────────────────┐
│ 代码    名称              市值    占比   累计盈亏  操作   │
│ 161130  易方达纳指100联接 8.5万   9%    +24%     [详情]  │
│ 018043  天弘纳斯达克100   6.2万   6.5%  +18%     [详情]  │
│ 563020  易方达红利低波ETF 20万    21%   +12%     [详情]  │
│ 007466  华泰柏瑞红利低波  18万    19%   +9%      [详情]  │
│ 511010  国债ETF           24万    25%   +5%      [详情]  │
└──────────────────────────────────────────────────────────┘
[新增交易] [批量导入CSV] [导出]
```

**新增交易表单**（模态框）：
```
日期 [date picker]
基金 [select from pool]
类型 [买入 / 卖出 / 分红 / 再平衡买 / 再平衡卖]
金额 [number]
净值 [number, 自动填充当日]
份额 [number, 自动计算]
当时系数 [number, 默认本月]
备注 [textarea]
[取消] [确认]
```

### 7.4 页面 3：月度执行 `/execution`

```
┌─ 2026年7月 定投执行清单 ────────────────────────┐
│ 执行日: 2026-07-10 (周五)                       │
│                                                │
│ 系数 (本月生效): 纳指 0.5 | 红利 1.0           │
│ 本月预算: ¥5,000                                │
│                                                │
│ 计划金额:                                       │
│   纳指档: ¥875 (预算×35%×0.5)                   │
│   红利档: ¥2,875 (含纳指溢出 ¥875)              │
│   债券档: ¥1,250                                │
│                                                │
│ ─────────────────────────────────────────────  │
│                                                │
│ □ Step 1: 检查信号 (5分钟)                      │
│ □ Step 2: 确认本月金额分配                       │
│ □ Step 3: 执行纳指档 (溢出阶梯)                  │
│    [展开] 实际执行情况:                          │
│       基金   计划   实际                         │
│       161130 875    ___                         │
│ □ Step 4: 检查场内ETF溢价                       │
│ □ Step 5: 执行红利档                            │
│ □ Step 6: 执行债券档                            │
│ □ Step 7: 记录到表格                            │
│                                                │
│ 进度: 0/7  [完成本月]                           │
└────────────────────────────────────────────────┘

[历史月度记录 →]
```

### 7.5 页面 4：再平衡 `/rebalance`

```
┌─ 评估当前再平衡需求 ────────────────────────────┐
│ 评估日期: [date picker, default=today]          │
│ [评估]                                          │
│                                                │
│ 评估结果:                                       │
│   当前总资产: ¥942,500                          │
│   纳指: 实际 25%  目标 35%  偏离 -10% ⚠️       │
│   红利: 实际 47%  目标 40%  偏离 +7%           │
│   债券: 实际 27%  目标 25%  偏离 +2%           │
│                                                │
│ 建议操作: 主动再平衡 (有项偏离>10%)              │
│                                                │
│ 建议订单:                                       │
│   卖出 红利低波 ¥40,000 (优先卖563020)         │
│   卖出 国债ETF  ¥10,000                        │
│   买入 纳指联接 ¥50,000 (按溢出阶梯)           │
│                                                │
│ 节税提示: 优先卖持有>1年的份额                   │
│                                                │
│ [生成具体订单列表] [提交执行]                    │
└────────────────────────────────────────────────┘
```

### 7.6 页面 5：回测 `/backtest`

```
┌─ 回测参数 ──────────────────────────────────────┐
│ 起始日期 [2016-01]   结束日期 [2026-05]         │
│ 月投金额 [1000]                                 │
│ 配比:                                           │
│   纳指 [35]%   红利 [40]%   债券 [25]%         │
│ 选项:                                           │
│   ☑ 启用估值系数                                │
│   ☑ 启用年度再平衡                              │
│                                                │
│ [运行回测]  [对比场景: 简单等额 ▼]              │
└────────────────────────────────────────────────┘

┌─ 关键指标 ─────────────────────────────────────┐
│  最终市值  累计投入  IRR    最大回撤   夏普     │
│  ¥41.5万   ¥12.5万   14%    -22%      0.85    │
└────────────────────────────────────────────────┘

┌─ 资产价值演变 (折线图, 多曲线对比) ──────────────┐
│  [当前策略] vs [简单等额] vs [纯纳指] vs [纯红利] │
└────────────────────────────────────────────────┘

┌─ 回撤曲线 ─────────────────────────────────────┐
│  [水下曲线图]                                   │
└────────────────────────────────────────────────┘

┌─ 月度配比演变 (堆叠面积图) ─────────────────────┐
│  纳指/红利/债券 三色堆叠                         │
└────────────────────────────────────────────────┘
```

### 7.7 页面 6：数据管理 `/data`

```
[Tab: 数据状态 | 基金池 | 手动录入]

数据状态:
┌────────────────────────────────────────────────┐
│ 数据源       最后更新           状态   [刷新]    │
│ NDX 价格    2026-06-09 06:30   ✓     [刷新]    │
│ NDX PE      2026-06-09 06:30   ✓     [刷新]    │
│ H30269 价格 2026-06-09 16:00   ✓     [刷新]    │
│ H30269 股息 2026-06-01 09:00   ⚠     [刷新]    │
│ USD/CNY     2026-06-09 17:00   ✓     [刷新]    │
│ 基金净值    2026-06-09 21:30   ✓     [刷新]    │
│ ETF 实时    2026-06-09 14:45   ✓     [刷新]    │
│ 限购状态    2026-06-09 09:00   ✓     [刷新]    │
└────────────────────────────────────────────────┘

基金池: 表格 + 编辑 + 启用/禁用
手动录入: 当 API 失败时手动录入指数/股息率数据
```

### 7.8 页面 7：设置 `/settings`

```
账户配置:
  风险档位: ○ 进攻 ○ 平衡 ● 防御
  目标配比: 纳指 [20]%  红利 [50]%  债券 [30]%
  月预算: ¥[5000]
  
再平衡阈值:
  被动阈值: [5]%
  主动阈值: [10]%

家庭资产上限:
  总占比上限: [30]%
  当前占比: 21% (基于家庭总资产 ¥4,500,000)
  家庭总资产: ¥[4,500,000] (用于占比计算)

[保存]
```

---

## 8. 项目目录结构

```
dca-dashboard/
├── docker-compose.yml
├── README.md
├── .env.example
├── .env                        # 含 MySQL 密码 (gitignore)
├── .gitignore
│
├── mysql-init/                 # MySQL 首次启动初始化脚本
│   └── 01-seed.sql
├── mysql-data/                 # MySQL 数据卷 (gitignore)
├── mysql-logs/                 # MySQL 日志 (gitignore)
│
├── scripts/
│   ├── backup.sh               # 每日 mysqldump 备份
│   └── restore.sh
│
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── alembic/                # DB migrations
│   ├── app/
│   │   ├── main.py             # FastAPI入口
│   │   ├── config.py           # 配置加载
│   │   ├── database.py         # DB连接
│   │   ├── scheduler.py        # APScheduler配置
│   │   ├── models/             # SQLAlchemy models
│   │   │   ├── user_config.py
│   │   │   ├── fund.py
│   │   │   ├── transaction.py
│   │   │   └── ...
│   │   ├── schemas/            # Pydantic schemas (req/resp)
│   │   │   └── ...
│   │   ├── routers/            # FastAPI routes
│   │   │   ├── dashboard.py
│   │   │   ├── data.py
│   │   │   ├── transactions.py
│   │   │   ├── execution.py
│   │   │   ├── rebalance.py
│   │   │   ├── backtest.py
│   │   │   └── config.py
│   │   ├── services/           # 业务逻辑(纯函数为主)
│   │   │   ├── coefficients.py
│   │   │   ├── allocation.py
│   │   │   ├── rebalance.py
│   │   │   ├── percentile.py
│   │   │   ├── backtest.py
│   │   │   └── holdings.py
│   │   ├── adapters/           # 数据源适配器
│   │   │   ├── base.py
│   │   │   ├── yfinance_adapter.py
│   │   │   ├── akshare_adapter.py
│   │   │   ├── csindex_adapter.py
│   │   │   └── cache.py
│   │   ├── jobs/               # 定时任务
│   │   │   ├── update_quotes.py
│   │   │   ├── calculate_coefficients.py
│   │   │   └── generate_monthly.py
│   │   └── utils/
│   │       ├── logger.py
│   │       └── date_utils.py
│   └── tests/
│       ├── test_coefficients.py
│       ├── test_allocation.py
│       ├── test_rebalance.py
│       └── test_backtest.py
│
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── Dockerfile
    ├── tailwind.config.js
    ├── index.html
    ├── src/
    │   ├── main.tsx
    │   ├── App.tsx
    │   ├── router.tsx
    │   ├── api/                 # API client
    │   │   ├── client.ts        # axios/fetch wrapper
    │   │   ├── dashboard.ts
    │   │   ├── transactions.ts
    │   │   └── ...
    │   ├── components/
    │   │   ├── ui/              # shadcn组件
    │   │   ├── charts/
    │   │   │   ├── GaugeChart.tsx
    │   │   │   ├── AllocationPie.tsx
    │   │   │   └── PortfolioLine.tsx
    │   │   ├── layout/
    │   │   │   ├── Sidebar.tsx
    │   │   │   └── Topbar.tsx
    │   │   └── shared/
    │   │       ├── KPICard.tsx
    │   │       └── DataStatus.tsx
    │   ├── pages/
    │   │   ├── Dashboard.tsx
    │   │   ├── Holdings.tsx
    │   │   ├── Execution.tsx
    │   │   ├── Rebalance.tsx
    │   │   ├── Backtest.tsx
    │   │   ├── DataManagement.tsx
    │   │   └── Settings.tsx
    │   ├── hooks/
    │   │   ├── useDashboard.ts
    │   │   └── ...
    │   ├── types/
    │   │   └── api.ts           # 与后端共享的类型(从OpenAPI生成)
    │   └── lib/
    │       └── format.ts
    └── public/
```

---

## 9. 部署方案 (Docker Compose)

`docker-compose.yml`:
```yaml
version: '3.9'

services:
  mysql:
    image: mysql:8.0
    container_name: dca-mysql
    restart: unless-stopped
    ports:
      - "3306:3306"   # 仅本地访问可改为 "127.0.0.1:3306:3306"
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: dca_dashboard
      MYSQL_USER: dca_app
      MYSQL_PASSWORD: ${MYSQL_APP_PASSWORD}
      TZ: Asia/Shanghai
    command:
      - --character-set-server=utf8mb4
      - --collation-server=utf8mb4_0900_ai_ci
      - --default-time-zone=+00:00       # 数据库内部时区固定 UTC
      - --max-connections=200
      - --innodb-buffer-pool-size=256M   # 单用户场景, 不用太大
      - --slow-query-log=1
      - --slow-query-log-file=/var/log/mysql/slow.log
      - --long-query-time=2
    volumes:
      - ./mysql-data:/var/lib/mysql
      - ./mysql-logs:/var/log/mysql
      - ./mysql-init:/docker-entrypoint-initdb.d  # 首次启动执行的脚本
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-u", "root", "-p${MYSQL_ROOT_PASSWORD}"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s

  backend:
    build: ./backend
    container_name: dca-backend
    restart: unless-stopped
    ports:
      - "8000:8000"
    depends_on:
      mysql:
        condition: service_healthy
    volumes:
      - ./logs:/app/logs
    environment:
      - DATABASE_URL=mysql+pymysql://dca_app:${MYSQL_APP_PASSWORD}@mysql:3306/dca_dashboard?charset=utf8mb4
      - TZ=Asia/Shanghai
      - LOG_LEVEL=INFO
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 20s

  frontend:
    build: ./frontend
    container_name: dca-frontend
    restart: unless-stopped
    ports:
      - "3000:80"
    depends_on:
      - backend
```

**`.env` 文件**（与 docker-compose.yml 同目录, 加到 .gitignore）：
```
MYSQL_ROOT_PASSWORD=<强密码,至少16位>
MYSQL_APP_PASSWORD=<强密码,至少16位>
```

**首次启动**：
```bash
# 1. 准备环境变量
cp .env.example .env
# 编辑 .env, 填入强密码

# 2. 启动
docker compose up -d

# 3. 等待 mysql 健康检查通过(约30秒)
docker compose logs -f mysql

# 4. 在 backend 容器内执行 alembic 迁移
docker compose exec backend alembic upgrade head

# 5. 初始化基金池数据(见附录C)
docker compose exec backend python -m app.scripts.seed_fund_pool

# 6. 访问
# Web: http://your-server:3000
# API: http://your-server:8000/docs
```

**反向代理建议**（生产）：
- 用 Nginx/Caddy 做 HTTPS（强烈建议，因为公网暴露 MySQL 端口风险大）
- MySQL 端口建议**只绑定 127.0.0.1**，不要暴露到公网；如需远程访问，走 SSH 隧道
- 加 Basic Auth 或简单的密码登录（单用户场景）
- **配置自动备份**（见 9.1）

### 9.1 MySQL 备份策略（必做！）

`scripts/backup.sh`:
```bash
#!/bin/bash
# 每日凌晨2点用 cron 调用
BACKUP_DIR="/path/to/backups"
DATE=$(date +%Y%m%d_%H%M%S)
docker compose exec -T mysql mysqldump \
  -u root -p${MYSQL_ROOT_PASSWORD} \
  --single-transaction \
  --routines \
  --triggers \
  dca_dashboard | gzip > ${BACKUP_DIR}/dca_${DATE}.sql.gz

# 保留最近30天
find ${BACKUP_DIR} -name "dca_*.sql.gz" -mtime +30 -delete
```

加到 crontab：`0 2 * * * /path/to/scripts/backup.sh >> /var/log/dca-backup.log 2>&1`

**强烈建议**：备份文件同步到云盘（rclone+OneDrive/百度网盘）或异地服务器。

### 9.2 MySQL 远程访问设置

如果需要从你的 Mac/PC 直接连 MySQL 看数据（推荐用 SSH 隧道而非直接开放端口）：

```bash
# 本机执行, 建立到服务器的 SSH 隧道
ssh -L 13306:127.0.0.1:3306 your-user@your-server

# 然后在本机 DBeaver/TablePlus 连接:
# Host: 127.0.0.1
# Port: 13306
# User: dca_app (或 root)
# Database: dca_dashboard
```


---

## 10. 关键依赖列表

`backend/pyproject.toml`:
```toml
[project]
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "pymysql>=1.1",              # MySQL 驱动(纯Python, 无需编译)
    "cryptography>=42",          # pymysql 配合 caching_sha2_password 需要
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "apscheduler>=3.10",
    "httpx>=0.27",
    "akshare>=1.13",
    "yfinance>=0.2.40",
    "pandas>=2.2",
    "numpy>=1.26",
    "python-dateutil>=2.8",
    "loguru>=0.7",
    "pdfplumber>=0.11",          # 解析中证factsheet PDF
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio", "pytest-cov", "ruff", "mypy"]
```

> **为什么选 PyMySQL 而非 mysqlclient？** PyMySQL 是纯 Python 实现，Docker 镜像不需要额外装编译工具；性能差距对单用户场景完全可忽略。如果未来真的有性能瓶颈，再切换到 `asyncmy`（异步驱动，可配合 FastAPI 异步路由）。

`frontend/package.json` 关键依赖:
```json
{
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.23.0",
    "@tanstack/react-query": "^5.40.0",
    "axios": "^1.7.0",
    "recharts": "^2.12.0",
    "tailwindcss": "^3.4.0",
    "lucide-react": "^0.400.0",
    "react-hook-form": "^7.51.0",
    "zod": "^3.23.0",
    "@hookform/resolvers": "^3.6.0",
    "date-fns": "^3.6.0",
    "clsx": "^2.1.0"
  }
}
```

UI 组件用 shadcn/ui，按需添加：`npx shadcn-ui@latest add button card table dialog form input select`

---

## 11. 实施步骤建议（给 Cursor 用）

按这个顺序做，每个阶段都能 deploy 一个可用版本：

### Phase 1 - 数据底座 (1-2天)
1. 初始化项目结构 + docker-compose（含 MySQL 8.0 服务）
2. 配置 `.env`、写好 SQLAlchemy 连接（pymysql driver, charset=utf8mb4, isolation_level=READ_COMMITTED）
3. 实现所有 SQLAlchemy 模型 + Alembic 初始化（`alembic init` 后改 `env.py` 用 MySQL URL）
4. **生成首个 migration: `alembic revision --autogenerate -m "init"`**, 验证表结构
5. 实现 akshare/yfinance/csindex 适配器(主要数据源)
6. 编写单元测试覆盖适配器（用 pytest-mock 隔离外部 HTTP）
7. 用 `app/scripts/seed_fund_pool.py` 预填充基金池基础数据

**MySQL 连接配置示例（`app/database.py`）**：
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL")  # mysql+pymysql://...

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,           # 自动重连断开的连接
    pool_recycle=3600,            # 1小时回收, 避免 MySQL wait_timeout 断连
    isolation_level="READ COMMITTED",
    echo=False,                   # 开发期可以 True 看 SQL
    connect_args={
        "connect_timeout": 10,
        "init_command": "SET time_zone='+00:00'",  # 强制 UTC
    },
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass
```

### Phase 2 - 后端核心 (2-3天)
6. 实现业务逻辑 services (coefficients/allocation/rebalance)
7. 实现 FastAPI 路由 (dashboard/data/config 几个先)
8. 实现 APScheduler 定时任务
9. 单元测试覆盖率 >70%

### Phase 3 - 前端骨架 (1-2天)
10. Vite + React 初始化, shadcn 配置
11. 路由 + 布局 + 侧边栏
12. API client + React Query 配置
13. 数据状态页(最简单, 先把后端连起来)

### Phase 4 - 仪表盘 (1-2天)
14. KPI 卡片 + 估值仪表盘
15. 配比饼图 + 偏离条
16. 资产历史折线图

### Phase 5 - 持仓与执行 (2天)
17. 持仓页 + 交易录入
18. 月度执行清单页
19. CSV 导入导出

### Phase 6 - 高级功能 (2-3天)
20. 再平衡计算器 + 提交
21. 回测引擎 + 可视化
22. 设置页

### Phase 7 - 打磨 (1天)
23. 错误处理 + 加载状态
24. 移动端适配
25. README + 部署文档

**总计预估**：10-15 个工作日

---

## 12. 关键测试用例（验收标准）

### 12.1 业务逻辑单元测试

```python
# test_coefficients.py
def test_nasdaq_coefficient():
    assert calculate_nasdaq_coefficient(0.20) == (1.5, "低估")
    assert calculate_nasdaq_coefficient(0.50) == (1.0, "合理")
    assert calculate_nasdaq_coefficient(0.85) == (0.7, "偏高")
    assert calculate_nasdaq_coefficient(0.95) == (0.5, "高估")

def test_dividend_coefficient():
    assert calculate_dividend_coefficient(0.065) == (1.5, "高股息")
    assert calculate_dividend_coefficient(0.055) == (1.0, "正常")
    assert calculate_dividend_coefficient(0.045) == (0.7, "偏高")
    assert calculate_dividend_coefficient(0.035) == (0.3, "暂停大额")

# test_allocation.py
def test_monthly_allocation_normal():
    result = calculate_monthly_amounts(
        budget=5000,
        target={'nasdaq': 0.35, 'dividend': 0.40, 'bond': 0.25},
        coefficients={'nasdaq': 1.0, 'dividend': 1.0},
    )
    assert result == {'nasdaq': 1750, 'dividend': 2000, 'bond': 1250, 'total': 5000}

def test_monthly_allocation_with_spillover():
    """纳指系数0.5时, 溢出资金应进红利档"""
    result = calculate_monthly_amounts(
        budget=5000,
        target={'nasdaq': 0.35, 'dividend': 0.40, 'bond': 0.25},
        coefficients={'nasdaq': 0.5, 'dividend': 1.0},
    )
    # 纳指原 1750 -> 实际 875, 溢出 875 进红利
    assert result['nasdaq'] == 875
    assert result['dividend'] == 2875
    assert result['bond'] == 1250

# test_rebalance.py
def test_rebalance_no_action():
    """所有偏离都≤5%, 不操作"""
    result = evaluate_rebalance(
        current_values={'nasdaq': 35, 'dividend': 40, 'bond': 25},
        target={'nasdaq': 0.35, 'dividend': 0.40, 'bond': 0.25},
    )
    assert result['recommendation'] == 'no_action'

def test_rebalance_active():
    """有项偏离>10%, 主动再平衡"""
    result = evaluate_rebalance(
        current_values={'nasdaq': 25, 'dividend': 50, 'bond': 25},
        target={'nasdaq': 0.35, 'dividend': 0.40, 'bond': 0.25},
    )
    assert result['recommendation'] == 'active_rebalance'

# test_backtest.py (集成测试)
def test_backtest_2016_2026():
    """回测应该接近手册给出的指标"""
    result = backtest_dca(
        start_date=date(2016, 1, 1),
        end_date=date(2026, 5, 31),
        monthly_amount=1000,
        target_allocation={'nasdaq': 0.50, 'dividend': 0.30, 'bond': 0.20},
        use_coefficients=False,
        use_rebalance=True,
    )
    # IRR 应在 12-16% 之间
    assert 0.12 <= result['irr'] <= 0.16
    # 最大回撤在 -18% 到 -25% 之间
    assert -0.25 <= result['max_drawdown'] <= -0.18
```

### 12.2 数据源容错测试

```python
def test_data_source_fallback():
    """主源失败时应自动切到备用源"""
    with mock_yfinance_failure():
        result = get_ndx_price()
        assert result.source == 'akshare_fallback'
        assert result.price > 0

def test_data_source_all_failed():
    """所有源都失败时应返回最近缓存"""
    with mock_all_failures():
        result = get_ndx_price()
        assert result.from_cache == True
```

### 12.3 端到端验收

- [ ] 启动 Docker compose 后能在 5 分钟内访问页面
- [ ] 首次启动后能自动拉取所有数据并入库
- [ ] 仪表盘所有数字与手动计算一致
- [ ] 录入一笔交易后持仓和配比即时更新
- [ ] 月底自动生成下月系数
- [ ] 回测结果可对比手册中的校对数据(±2%)
- [ ] 数据源失败时页面不崩溃,显示"使用缓存数据"提示

---

## 附录 A：再平衡详细算法

```python
def evaluate_rebalance(current_values, target, threshold_passive=0.05, threshold_active=0.10):
    total = sum(current_values.values())
    current_pct = {k: v/total for k, v in current_values.items()}
    deviations = {k: current_pct[k] - target[k] for k in target}
    max_dev = max(abs(d) for d in deviations.values())
    
    if max_dev <= threshold_passive:
        return {
            'total': total,
            'current_pct': current_pct,
            'deviations': deviations,
            'max_deviation': max_dev,
            'recommendation': 'no_action',
            'orders': [],
        }
    
    if max_dev <= threshold_active:
        return {
            'total': total,
            'current_pct': current_pct,
            'deviations': deviations,
            'max_deviation': max_dev,
            'recommendation': 'passive_via_new_investment',
            'orders': [],  # 不卖出, 靠下月新投入调整
        }
    
    # 主动再平衡: 计算每类需要变动的金额
    target_values = {k: total * v for k, v in target.items()}
    deltas = {k: target_values[k] - current_values[k] for k in target}
    
    orders = []
    for category, delta in deltas.items():
        if delta < 0:
            orders.append({'category': category, 'action': 'sell', 'amount': abs(delta)})
        elif delta > 0:
            orders.append({'category': category, 'action': 'buy', 'amount': delta})
    
    return {
        'total': total,
        'current_pct': current_pct,
        'deviations': deviations,
        'max_deviation': max_dev,
        'recommendation': 'active_rebalance',
        'orders': orders,
    }
```

---

## 附录 B：纳指 PE 分位计算策略

yfinance 不直接提供历史 PE 序列。两种实现：

**方案 A（推荐, 自建累计）**：
- 每日拉取当日 NDX 价格 + Trailing EPS
- 计算当日 PE = price / EPS
- 累计入库, 至少积累 5 年后开始有意义
- 启动时用历史价格 × 静态估算 EPS 作为初始值（精度低但够用）

**方案 B（外部 API）**：
- multpl.com 有 NDX PE 历史数据，可一次性爬取建库
- 作为方案 A 的初始数据填充

**计算分位**：
```python
def calculate_pe_percentile(current_pe, history_pe_list):
    """history_pe_list: 近10年(约2500个交易日)的PE序列"""
    import numpy as np
    arr = np.array(history_pe_list)
    return float(np.sum(arr <= current_pe) / len(arr))
```

---

## 附录 C：基金池初始化 SQL (MySQL)

> 推荐做法：把这份脚本放到 `mysql-init/01-seed.sql`，配合 `docker-entrypoint-initdb.d` 在首次启动时自动执行。
> 或者用 `app/scripts/seed_fund_pool.py` 通过 SQLAlchemy 写入（推荐，便于幂等）。

```sql
-- 切换到目标库
USE dca_dashboard;

-- 资产类别 (使用 INSERT IGNORE 保证幂等)
INSERT IGNORE INTO asset_category (id, code, name) VALUES
  (1, 'NASDAQ',   '纳指100'),
  (2, 'SP500',    '标普500'),
  (3, 'DIVIDEND', '红利低波'),
  (4, 'BOND',     '债券');

-- 基金池
INSERT IGNORE INTO fund (code, name, category_id, fund_type, priority, annual_fee_rate, purchase_fee_rate, is_active) VALUES
  ('161130', '易方达纳斯达克100联接A', 1, 'otc_link', 5, 0.008500, 0.001200, 1),
  ('018043', '天弘纳斯达克100A',        1, 'otc_link', 5, 0.007500, 0.001200, 1),
  ('270042', '广发纳指100联接A',         1, 'otc_link', 4, 0.009500, 0.001200, 1),
  ('000834', '大成纳斯达克100联接A',     1, 'otc_link', 4, 0.010000, 0.001200, 1),
  ('160213', '国泰纳斯达克100联接A',     1, 'otc_link', 4, 0.010000, 0.001200, 1),
  ('018959', '华夏纳斯达克100联接A',     1, 'otc_link', 3, 0.008500, 0.001200, 1),
  ('040046', '华安纳斯达克100联接A',     1, 'otc_link', 3, 0.010000, 0.001200, 1),
  ('019547', '嘉实纳斯达克100联接A',     1, 'otc_link', 3, 0.007500, 0.001200, 1),
  ('017437', '摩根纳斯达克100A',         1, 'otc_link', 2, 0.008000, 0.001200, 1),
  ('019870', '招商纳斯达克100联接A',     1, 'otc_link', 2, 0.007500, 0.001200, 1),
  ('050025', '博时标普500ETF联接A',     2, 'otc_link', 5, 0.008000, 0.001000, 1),
  ('118002', '易方达标普500人民币A',     2, 'otc_link', 5, 0.008000, 0.001000, 1),
  ('096001', '大成标普500等权重A',       2, 'otc_link', 4, 0.009000, 0.001000, 1),
  ('007466', '华泰柏瑞红利低波联接A',    3, 'otc_link', 5, 0.006000, 0.000800, 1),
  ('563020', '易方达红利低波ETF',        3, 'etf',      5, 0.002000, 0.000000, 1),
  ('512890', '华泰柏瑞红利低波ETF',      3, 'etf',      4, 0.006000, 0.000000, 1),
  ('511010', '国债ETF',                  4, 'bond_etf', 5, 0.001500, 0.000000, 1),
  ('110007', '易方达稳健收益',           4, 'otc_link', 4, 0.008000, 0.000800, 1);

-- 默认用户配置 (平衡型为默认, 可后续在 settings 页修改)
INSERT IGNORE INTO user_config (id, risk_profile, target_nasdaq_pct, target_dividend_pct, target_bond_pct, monthly_budget) VALUES
  (1, 'balanced', 0.350000, 0.400000, 0.250000, 5000.0000);
```

---

## 附录 D：MySQL 特别注意事项

### D.1 字符集陷阱（必看）

MySQL 8.0 默认 `utf8mb4`，但务必确认每一层都是：

```bash
# 1. 容器启动参数
--character-set-server=utf8mb4
--collation-server=utf8mb4_0900_ai_ci

# 2. 连接串
?charset=utf8mb4

# 3. 建表显式声明
CREATE TABLE ... DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

# 4. 验证
SHOW VARIABLES LIKE 'character%';
SHOW VARIABLES LIKE 'collation%';
```

如果哪一层错了，会出现：
- 中文存入变 `???`
- emoji 直接报错（旧 `utf8` 实际是 utf8mb3，3字节不够）
- 排序结果错乱

### D.2 时区陷阱（必看）

MySQL 有三处时区设置，必须都对齐：

```sql
-- 检查
SELECT @@global.time_zone, @@session.time_zone, NOW(), UTC_TIMESTAMP();

-- 应该看到:
-- global.time_zone = '+00:00'  (由 --default-time-zone 设置)
-- session.time_zone = '+00:00' (由连接初始化命令设置)
-- NOW() 和 UTC_TIMESTAMP() 一致
```

**约定**：
- DB 内全部存 UTC
- Python `datetime.utcnow()` 写入
- 读出后在应用层 `astimezone(ZoneInfo("Asia/Shanghai"))` 再展示
- 前端 JS Date 自动按浏览器时区显示（北京时间）

### D.3 Decimal 精度

```python
# ❌ 错误: 用 float 存金额
amount = 100.1 + 200.2  # 300.29999999999995

# ✅ 正确: 用 Decimal
from decimal import Decimal
amount = Decimal("100.1") + Decimal("200.2")  # Decimal('300.3')

# SQLAlchemy 中, DECIMAL 列读出来就是 Decimal 类型, 不会自动转 float
# JSON 序列化时要单独处理:
from decimal import Decimal
import json

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)  # 或 str(obj) 保留精度
        return super().default(obj)
```

FastAPI 中可在 Pydantic schema 用 `Decimal` 类型，配合 `json_encoders` 配置序列化为字符串。

### D.4 连接池与重连

MySQL 默认 `wait_timeout=28800`（8小时）。SQLAlchemy 连接池如果有空闲连接超过这个时间，下次使用会抛 `MySQL server has gone away`。

**解决**（已在 9.x 节连接配置中体现）：
- `pool_pre_ping=True`：每次取连接时 ping 一下
- `pool_recycle=3600`：1小时主动回收

### D.5 大批量插入优化

回测引擎和初始历史数据填充时会大量插入。

```python
# ❌ 慢: 一条一条 insert
for row in 10000_rows:
    session.add(PEHistory(date=row.date, pe_ttm=row.pe))
    session.commit()

# ✅ 快: 批量
session.bulk_insert_mappings(PEHistory, [
    {"date": r.date, "pe_ttm": r.pe} for r in 10000_rows
])
session.commit()

# 更快: 用 pandas + to_sql
df.to_sql("pe_history", engine, if_exists="append", index=False, method="multi", chunksize=1000)
```

### D.6 索引选择

定时任务里的关键查询：

```python
# 取最新的纳指 PE
SELECT pe_ttm FROM pe_history ORDER BY date DESC LIMIT 1
# → 已建索引 ix_pe_history_date

# 取近10年 PE 用于分位计算
SELECT pe_ttm FROM pe_history WHERE date >= '2016-06-09'
# → 同上, range scan

# 取本月所有交易
SELECT * FROM transaction WHERE date >= '2026-06-01' AND date < '2026-07-01'
# → 已建索引 ix_txn_date

# 按基金查交易历史
SELECT * FROM transaction WHERE fund_id = 1 ORDER BY date DESC
# → 已建索引 ix_txn_fund
```

启动后用 `EXPLAIN` 验证关键查询是否走索引。

### D.7 SQLite vs MySQL 迁移注意

如果之前已经用 SQLite 跑过：

```bash
# 用 pgloader 或自己写脚本迁移
# 简单情况: 用 SQLAlchemy 把 SQLite 数据读出, 写入 MySQL

# 注意:
# 1. SQLite BOOLEAN 实际是 INTEGER 0/1, MySQL 是 TINYINT, 需类型转换
# 2. SQLite 日期字段是字符串, MySQL 是 DATE/DATETIME, 需 parse
# 3. SQLite 自增 ID 可以保留, 但要重置 MySQL AUTO_INCREMENT 起始值
```

---

## 附录 E：Cursor 实施时的提示

1. **先跑通 happy path**：不要一开始就做完美的错误处理。先让一条数据链路跑通，再补 fallback。

2. **每个 service 函数都要有 docstring + 单元测试**：业务逻辑是这个系统的核心价值，必须测试覆盖。

3. **API 响应格式严格统一**：所有响应 `{"data": ..., "error": null, "meta": {...}}`，前端拦截器统一处理。

4. **不要把业务逻辑写到前端**：所有计算（系数/再平衡/回测）必须在后端完成，前端只负责展示和交互。

5. **数据源失败的提示要清晰**：用户最不想看到的就是"数据加载中..."然后什么都没有。永远显示上次缓存数据 + 时间戳 + 失败提示。

6. **数据库迁移用 Alembic**：不要直接改 schema，所有变更通过 migration。生产环境跑迁移前**先备份 MySQL**。

7. **环境变量管理**：用 pydantic-settings，所有配置走 `.env` 文件，不要硬编码。MySQL 密码绝对不要进 git。

8. **日志用 loguru**：所有外部请求、定时任务执行、关键决策都打日志，便于排查。MySQL 慢查询也要看（slow.log）。

9. **金额一律用 Decimal**：见 D.3。本项目涉及钱，**不能用 float**，没有"暂时"。

10. **时区**：见 D.2。所有 datetime 入库 UTC，展示用 Asia/Shanghai。这是常见 bug 源。

11. **MySQL 备份**：见 9.1。**未做备份的系统等于没做**。开发第一周内必须把备份脚本跑起来。

12. **测试用独立的 MySQL 数据库**：`pytest` 时连 `dca_dashboard_test`，每次跑前 truncate 所有表。不要污染主库。

---

*spec 编写完成（v1.1 - MySQL 版）。Cursor 实施时如有疑问，回头补充。*
