export type TodayFundTask = {
  fund_code: string;
  fund_name: string;
  bucket_code: string;
  record_type: "scheduled" | "probe" | "manual";
  planned_amount: number;
  daily_limit: number | null;
  limit_label: string;
  selected?: boolean;
  frequency?: string;
  pool_id?: number | null;
  purchase_limit?: number | null;
  already_submitted?: boolean;
  record_status?: string | null;
};

export type TodayBucketGroup = {
  bucket_code: string;
  bucket_name: string;
  record_type?: string;
  funds?: TodayFundTask[];
  total_amount?: number;
  hint?: string;
  message?: string;
};

export type TodayView = {
  date: string;
  date_label: string;
  weekday: string;
  is_trading_day: boolean;
  is_today?: boolean;
  is_backfill?: boolean;
  has_tasks: boolean;
  bucket_groups: TodayBucketGroup[];
  skipped_buckets: TodayBucketGroup[];
  total_amount: number;
  fee_summary?: {
    total_planned: number;
    total_purchase_fee: number;
    total_net_invested: number;
  } | null;
  next_event?: {
    date_label: string;
    bucket_name: string;
    days_until: number;
  } | null;
};

export type InvestmentRecord = {
  id: number;
  date: string;
  fund_code: string;
  fund_name: string;
  bucket_code: string;
  record_type: string;
  planned_amount: number;
  submitted_amount: number;
  status: "pending" | "confirmed" | "failed" | "partial";
  confirmed_amount?: number | null;
  confirmed_shares?: number | null;
  confirmed_nav?: number | null;
  confirmed_date?: string | null;
  frequency: string;
  notes?: string | null;
};

export type HistoryDay = {
  date: string;
  label: string;
  record_type: string;
  fund_count: number;
  amount: number;
  status: string;
  records: InvestmentRecord[];
};

export type MonthHistory = {
  month: string;
  summary: {
    total_submitted: number;
    total_confirmed: number;
    total_failed: number;
  };
  days: HistoryDay[];
};

export type FundPoolItem = {
  id: number;
  bucket_code: string;
  fund_code: string;
  fund_name: string;
  daily_limit: number;
  frequency: string;
  buy_type: "scheduled" | "probe";
  status: "active" | "paused";
  sort_order: number;
};

export const STATUS_LABEL: Record<string, string> = {
  pending: "⏳ 待确认",
  confirmed: "✅ 已确认",
  failed: "❌ 失败",
  partial: "⚠️ 部分成功",
};

export const BUCKET_COLORS: Record<string, string> = {
  growth: "#3ABFF8",
  dividend: "#F87272",
  gold: "#FBBD23",
  bond_long: "#B083F0",
  bond_short: "#67E8F9",
};
