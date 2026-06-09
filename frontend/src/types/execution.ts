export type BucketSignal = {
  code: string;
  name: string;
  color: string;
  signal_type: string;
  signal_value: number;
  signal_display: string;
  coefficient: number;
  coefficient_label: string;
};

export type DerivationLine = {
  bucket: string;
  label: string;
  base_amount: number;
  coefficient: number;
  after_coefficient: number;
  spillover_in: number;
  spillover_out: number;
  final_amount: number;
  editable: boolean;
  notes: string;
};

export type FeeSummary = {
  total_planned: number;
  total_purchase_fee: number;
  total_net_invested: number;
};

export type FundAllocation = {
  fund_code: string;
  fund_name: string;
  planned_amount: number;
  tier?: number | null;
  notes?: string;
  daily_limit?: number | null;
  purchase_status?: string;
  purchase_fee_rate?: number;
  annual_fee_rate?: number;
  purchase_fee_amount?: number;
  net_invested_amount?: number;
};

export type GrowthLimitRow = {
  fund_code: string;
  fund_name: string;
  daily_limit: number | null;
  status: string;
};

export type BucketExecution = {
  bucket: string;
  name: string;
  color: string;
  total_amount: number;
  funds: FundAllocation[];
  execution_notes: string[];
  fee_summary?: FeeSummary | null;
  action_date?: string | null;
  weekday?: string | null;
  date_label?: string | null;
};

export type DailyBucketPlan = {
  bucket: string;
  name: string;
  color: string;
  mode: "daily" | "monthly";
  monthly_planned: number;
  monthly_invested: number;
  monthly_remaining: number;
  days_remaining: number;
  today_target: number;
  today_invested: number;
  funds: FundAllocation[];
  execution_notes: string[];
  action_date?: string | null;
  weekday?: string | null;
  date_label?: string | null;
  fee_summary?: FeeSummary | null;
};

export type DateInfo = {
  date: string;
  weekday: string;
  date_label: string;
};

export type ActionStep = {
  key: string;
  title: string;
  hint: string;
  recurrence: "daily" | "monthly";
  date: string;
  weekday: string;
  date_label: string;
};

export type DailyScheduleRow = {
  date: string;
  weekday?: string;
  date_label?: string;
  target_amount: number;
  is_today: boolean;
};

export type DailyDcaShareSummary = {
  total_estimated_shares: number | null;
  funds_with_nav: number;
  funds_missing_nav: number;
};

export type DailyDcaBatchItem = FundAllocation & {
  selected?: boolean;
  nav?: number | null;
  nav_date?: string | null;
  nav_source?: string | null;
  nav_stale?: boolean;
  estimated_shares?: number | null;
};

export type DailyDcaMemoryFund = {
  fund_code: string;
  fund_name: string;
};

export type DailyDcaBatch = {
  action_date: string;
  status: "idle" | "pending" | "confirmed" | "cancelled";
  items: DailyDcaBatchItem[];
  total_selected: number;
  memory_active: boolean;
  memory_fund_codes: string[];
  memory_funds: DailyDcaMemoryFund[];
  memory_last_action_date?: string | null;
  memory_confirmed_at?: string | null;
  confirmed_at?: string | null;
  cancelled_at?: string | null;
  stop_memory?: boolean;
  share_summary?: DailyDcaShareSummary;
};

export type DailyExecutionContext = {
  date: string;
  date_label?: string;
  weekday?: string;
  month: string;
  is_trading_day: boolean;
  next_trading_date?: string | null;
  next_trading_date_label?: string | null;
  month_end_date?: string | null;
  month_end_date_label?: string | null;
  trading_days_in_month: number;
  trading_days_remaining: number;
  trading_days_elapsed: number;
  growth: DailyBucketPlan;
  other_buckets: DailyBucketPlan[];
  schedule: DailyScheduleRow[];
  growth_limits: GrowthLimitRow[];
  dca_batch?: DailyDcaBatch;
};

export type BudgetReconciliationStep = {
  key: string;
  label: string;
  amount: number;
  delta_from_budget?: number;
};

export type BudgetSpilloverMove = {
  from_bucket: string;
  from_label: string;
  to_bucket: string;
  to_label: string;
  amount: number;
};

export type BudgetOverrideAdjustment = {
  bucket: string;
  label: string;
  from_amount: number;
  to_amount: number;
  delta: number;
};

export type BudgetReconciliation = {
  budget: number;
  total_planned: number;
  delta: number;
  aligned: boolean;
  target_sum_pct: number;
  base_allocated: number;
  after_signals_total: number;
  has_manual_overrides: boolean;
  override_adjustments: BudgetOverrideAdjustment[];
  spillover_moves: BudgetSpilloverMove[];
  summary_lines: string[];
  steps: BudgetReconciliationStep[];
};

export type ExecutionPlan = {
  month: string;
  budget: number;
  signals: BucketSignal[];
  derivations: DerivationLine[];
  bucket_executions: BucketExecution[];
  total_planned: number;
  daily?: DailyExecutionContext;
  action_steps?: ActionStep[];
  month_start?: DateInfo;
  month_end?: DateInfo;
  fee_summary?: FeeSummary;
  daily_fee_summary?: FeeSummary;
  budget_reconciliation?: BudgetReconciliation;
};
