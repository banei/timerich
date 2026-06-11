import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../../api";
import type { TodayFundTask, TodayView } from "../../../types/execution-v2";
import { BUCKET_COLORS } from "../../../types/execution-v2";
import { fmtMoney } from "../../../utils/formatNumber";
import AmountQuickPicker from "./AmountQuickPicker";
import { FREQUENCY_OPTIONS, frequencyLabel, isDefaultSelected } from "./fundConfigUtils";
import { saveFundPoolItem } from "./FundConfigRow";

type Props = {
  today: TodayView;
  viewDate: string;
  onViewDateChange: (date: string) => void;
  onReload: () => void;
};

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function FundTaskRow({
  task,
  checked,
  amount,
  frequency,
  readOnly,
  onToggle,
  onAmountChange,
  onFrequencyChange,
}: {
  task: TodayFundTask;
  checked: boolean;
  amount: number;
  frequency: string;
  readOnly?: boolean;
  onToggle: () => void;
  onAmountChange: (n: number) => void;
  onFrequencyChange: (freq: string) => void;
}) {
  const off = readOnly || !checked || amount <= 0;

  if (readOnly) {
    return (
      <div className="exec-v2-fund-row exec-v2-fund-row-edit exec-v2-fund-submitted">
        <span className="exec-v2-submitted-badge">已录入</span>
        <span className="font-num exec-v2-code">{task.fund_code}</span>
        <span className="exec-v2-name">{task.fund_name}</span>
        <span className="font-num exec-v2-amt">{fmtMoney(task.planned_amount)}</span>
        <span className="text-muted exec-v2-limit">{task.limit_label}</span>
      </div>
    );
  }

  return (
    <div className={`exec-v2-fund-row exec-v2-fund-row-edit ${off ? "exec-v2-fund-off" : ""}`}>
      <label className="exec-v2-fund-check">
        <input type="checkbox" checked={checked && amount > 0} onChange={onToggle} disabled={amount <= 0} />
      </label>
      <div className="exec-v2-fund-main">
        <div className="exec-v2-fund-title">
          <span className="font-num exec-v2-code">{task.fund_code}</span>
          <span className="exec-v2-name">{task.fund_name}</span>
          <span className="text-muted exec-v2-limit">{task.limit_label}</span>
        </div>
        <div className="exec-v2-fund-edit-row">
          <AmountQuickPicker compact value={amount} onChange={onAmountChange} />
          <select
            className="exec-v2-freq-select"
            value={frequency}
            onChange={(e) => onFrequencyChange(e.target.value)}
            title={frequencyLabel(frequency)}
          >
            {FREQUENCY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <span className="font-num exec-v2-amt">{fmtMoney(amount)}</span>
    </div>
  );
}

function BucketTaskGroup({
  group,
  amounts,
  frequencies,
  selected,
  onToggle,
  onAmountChange,
  onFrequencyChange,
}: {
  group: {
    bucket_code: string;
    bucket_name: string;
    record_type?: string;
    funds?: TodayFundTask[];
    total_amount?: number;
    hint?: string;
    message?: string;
  };
  amounts: Record<string, number>;
  frequencies: Record<string, string>;
  selected: Set<string>;
  onToggle: (code: string) => void;
  onAmountChange: (code: string, n: number, task: TodayFundTask) => void;
  onFrequencyChange: (code: string, freq: string, task: TodayFundTask) => void;
}) {
  if (group.message) {
    return (
      <div className="exec-v2-bucket exec-v2-bucket-skip">
        <span className="bucket-dot" style={{ background: BUCKET_COLORS[group.bucket_code] || "#888" }} />
        <span>{group.bucket_name}</span>
        <span className="text-muted">{group.message}</span>
      </div>
    );
  }

  const isProbe = group.record_type === "probe";
  const isSubmitted = group.record_type === "submitted";
  const funds = group.funds || [];
  const color = isSubmitted ? "#94a8cc" : BUCKET_COLORS[group.bucket_code] || "#3ABFF8";
  const total = isSubmitted
    ? funds.reduce((s, f) => s + f.planned_amount, 0)
    : funds.reduce((s, f) => s + (selected.has(f.fund_code) ? amounts[f.fund_code] ?? f.planned_amount : 0), 0);

  return (
    <div className={`exec-v2-bucket ${isProbe ? "exec-v2-bucket-probe" : ""} ${isSubmitted ? "exec-v2-bucket-submitted" : ""}`}>
      <div className="exec-v2-bucket-head">
        <span className="bucket-dot" style={{ background: color }} />
        <strong>
          {isProbe ? "⚗ 试探性买入" : group.bucket_name}
          {funds.length > 0 && (
            <span className="text-muted">
              {" "}
              · {funds.length}只 · 合计 {fmtMoney(total)}
            </span>
          )}
        </strong>
        {group.hint && <p className="text-muted daily-hint">{group.hint}</p>}
      </div>
      <div className="exec-v2-fund-list">
        {funds.map((f) => (
          <FundTaskRow
            key={f.fund_code}
            task={f}
            readOnly={isSubmitted}
            checked={selected.has(f.fund_code)}
            amount={amounts[f.fund_code] ?? f.planned_amount}
            frequency={frequencies[f.fund_code] ?? f.frequency ?? "daily"}
            onToggle={() => onToggle(f.fund_code)}
            onAmountChange={(n) => onAmountChange(f.fund_code, n, f)}
            onFrequencyChange={(freq) => onFrequencyChange(f.fund_code, freq, f)}
          />
        ))}
      </div>
    </div>
  );
}

export default function TodaySection({ today, viewDate, onViewDateChange, onReload }: Props) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const persistRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isBackfill = today.is_backfill ?? viewDate < todayIso();
  const isToday = today.is_today ?? viewDate === todayIso();

  const actionableGroups = useMemo(
    () => today.bucket_groups.filter((g) => g.record_type !== "submitted"),
    [today.bucket_groups],
  );

  const allTasks = useMemo(() => {
    const tasks: TodayFundTask[] = [];
    for (const g of actionableGroups) {
      if (g.funds) tasks.push(...g.funds);
    }
    return tasks;
  }, [actionableGroups]);

  const [amounts, setAmounts] = useState<Record<string, number>>({});
  const [frequencies, setFrequencies] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const selectionSeedRef = useRef("");

  function defaultSelectedCodes(
    tasks: TodayFundTask[],
    amt: Record<string, number>,
    freq: Record<string, string>,
    anchorDate: string,
  ): Set<string> {
    return new Set(
      tasks
        .filter((t) => {
          const amount = amt[t.fund_code] ?? 0;
          const f = freq[t.fund_code] ?? t.frequency ?? "daily";
          if (t.already_submitted || amount <= 0) return false;
          return isDefaultSelected(f, anchorDate);
        })
        .map((t) => t.fund_code),
    );
  }

  useEffect(() => {
    // 等所选日期的接口数据返回后再初始化，避免用新日期配旧列表
    if (today.date !== viewDate) return;

    const amt: Record<string, number> = {};
    const freq: Record<string, string> = {};
    for (const t of allTasks) {
      amt[t.fund_code] = t.daily_limit ?? t.planned_amount;
      freq[t.fund_code] = t.frequency ?? "daily";
    }
    const seed = `${viewDate}|${allTasks
      .map((t) => t.fund_code)
      .sort()
      .join(",")}`;
    if (selectionSeedRef.current !== seed) {
      selectionSeedRef.current = seed;
      setAmounts(amt);
      setFrequencies(freq);
      setSelected(defaultSelectedCodes(allTasks, amt, freq, viewDate));
    }
  }, [allTasks, viewDate, today.date]);

  const totalSelected = useMemo(
    () => allTasks.filter((t) => selected.has(t.fund_code)).reduce((s, t) => s + (amounts[t.fund_code] ?? 0), 0),
    [allTasks, selected, amounts],
  );

  const selectableCodes = useMemo(
    () => allTasks.filter((t) => (amounts[t.fund_code] ?? t.planned_amount) > 0).map((t) => t.fund_code),
    [allTasks, amounts],
  );

  const selectedCount = useMemo(
    () => selectableCodes.filter((code) => selected.has(code)).length,
    [selectableCodes, selected],
  );

  function selectAll() {
    setSelected(new Set(selectableCodes));
  }

  function deselectAll() {
    setSelected(new Set());
  }

  function toggle(code: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  async function persistTask(task: TodayFundTask, patch: { daily_limit?: number; frequency?: string; status?: string }) {
    if (persistRef.current) clearTimeout(persistRef.current);
    persistRef.current = setTimeout(async () => {
      await saveFundPoolItem({
        fund_code: task.fund_code,
        fund_name: task.fund_name,
        bucket_code: task.bucket_code,
        daily_limit: patch.daily_limit,
        frequency: patch.frequency,
        status: patch.status,
        buy_type: task.record_type === "probe" ? "probe" : "scheduled",
      });
    }, 400);
  }

  function onAmountChange(code: string, n: number, task: TodayFundTask) {
    setAmounts((prev) => ({ ...prev, [code]: n }));
    if (n <= 0) {
      setSelected((prev) => {
        const next = new Set(prev);
        next.delete(code);
        return next;
      });
    }
    persistTask(task, { daily_limit: n, status: n <= 0 ? "paused" : "active" });
  }

  function onFrequencyChange(code: string, freq: string, task: TodayFundTask) {
    setFrequencies((prev) => ({ ...prev, [code]: freq }));
    persistTask(task, { frequency: freq });
    setSelected((prev) => {
      const next = new Set(prev);
      const n = amounts[code] ?? 0;
      if (n > 0 && isDefaultSelected(freq, viewDate)) next.add(code);
      else next.delete(code);
      return next;
    });
  }

  async function submit() {
    setBusy(true);
    setMsg("");
    const tasks = allTasks
      .filter((t) => selected.has(t.fund_code) && (amounts[t.fund_code] ?? 0) > 0)
      .map((t) => ({
        fund_code: t.fund_code,
        fund_name: t.fund_name,
        bucket_code: t.bucket_code,
        record_type: t.record_type,
        amount: amounts[t.fund_code] ?? t.planned_amount,
        frequency: frequencies[t.fund_code] ?? t.frequency ?? "daily",
      }));
    const skip_codes = allTasks
      .filter((t) => !selected.has(t.fund_code) || (amounts[t.fund_code] ?? 0) <= 0)
      .map((t) => t.fund_code);
    const res = await api("/api/v1/execution/submit", {
      method: "POST",
      body: JSON.stringify({ tasks, skip_codes, date: viewDate }),
    });
    setBusy(false);
    if (res.error) {
      setMsg(res.error);
      return;
    }
    setMsg(isBackfill ? `已补录 ${viewDate}，请在「待确认」中跟踪结果` : "已提交，请在「待确认」中跟踪结果");
    onReload();
  }

  async function skipToday() {
    setBusy(true);
    await api("/api/v1/execution/skip-today", { method: "POST" });
    setBusy(false);
    onReload();
  }

  const showEmpty = !today.has_tasks && actionableGroups.every((g) => !g.funds?.length);
  const submittedGroups = today.bucket_groups.filter((g) => g.record_type === "submitted");

  const selectToolbar =
    selectableCodes.length > 0 ? (
      <div className="exec-v2-select-toolbar">
        <button type="button" className="secondary exec-v2-mini-btn" onClick={selectAll} disabled={selectedCount >= selectableCodes.length}>
          全选
        </button>
        <button type="button" className="secondary exec-v2-mini-btn" onClick={deselectAll} disabled={selectedCount === 0}>
          全取消
        </button>
        <span className="text-muted exec-v2-select-count">
          已选 {selectedCount}/{selectableCodes.length} 只
        </span>
      </div>
    ) : null;

  const headerBlock = (
    <header className="exec-v2-header exec-v2-date-header">
      <div>
        <h2>{isBackfill ? "补录定投" : "今日定投"}</h2>
        <span className="text-muted">
          {today.date_label} {today.weekday}
          {!today.is_trading_day && isBackfill && " · 非交易日（可手动补录）"}
        </span>
      </div>
      <div className="exec-v2-date-picker">
        <label htmlFor="exec-view-date">执行日期</label>
        <input
          id="exec-view-date"
          type="date"
          className="exec-v2-date-input"
          value={viewDate}
          max={todayIso()}
          onChange={(e) => onViewDateChange(e.target.value)}
        />
        {!isToday && (
          <button type="button" className="secondary exec-v2-mini-btn" onClick={() => onViewDateChange(todayIso())}>
            回到今天
          </button>
        )}
      </div>
    </header>
  );

  if (showEmpty && isToday && !today.is_trading_day) {
    const nxt = today.next_event;
    return (
      <section className="card exec-v2-section exec-v2-empty">
        {headerBlock}
        <h3>今日无需操作</h3>
        {nxt ? (
          <>
            <p>
              下次定投：<strong>{nxt.date_label}</strong> · {nxt.bucket_name}
            </p>
            <p className="text-muted">距下次定投：{nxt.days_until} 天</p>
          </>
        ) : (
          <p className="text-muted">今日非交易日。可选择历史日期补录漏掉的定投。</p>
        )}
      </section>
    );
  }

  if (showEmpty && isBackfill) {
    return (
      <section className="card exec-v2-section exec-v2-empty">
        {headerBlock}
        <p className="text-muted">该日无待补录基金（可能均已录入，或当日无频率命中）。可调整基金频率后重试，或选其他日期。</p>
        {submittedGroups.map((g) => (
          <BucketTaskGroup
            key={`submitted-${g.bucket_code}`}
            group={g}
            amounts={amounts}
            frequencies={frequencies}
            selected={selected}
            onToggle={toggle}
            onAmountChange={onAmountChange}
            onFrequencyChange={onFrequencyChange}
          />
        ))}
      </section>
    );
  }

  return (
    <section className="card exec-v2-section">
      {headerBlock}

      {isBackfill && (
        <p className="exec-v2-backfill-hint">
          补录模式：勾选基金并提交后，记录将写入 <strong>{viewDate}</strong>，可在「待确认」中确认成交。
        </p>
      )}

      {selectToolbar}

      {today.bucket_groups.map((g) => (
        <BucketTaskGroup
          key={`${g.bucket_code}-${g.record_type || "skip"}-${g.message || g.bucket_name}`}
          group={g}
          amounts={amounts}
          frequencies={frequencies}
          selected={selected}
          onToggle={toggle}
          onAmountChange={onAmountChange}
          onFrequencyChange={onFrequencyChange}
        />
      ))}

      {today.skipped_buckets.map((g) => (
        <BucketTaskGroup
          key={`skip-${g.bucket_code}`}
          group={g}
          amounts={amounts}
          frequencies={frequencies}
          selected={selected}
          onToggle={toggle}
          onAmountChange={onAmountChange}
          onFrequencyChange={onFrequencyChange}
        />
      ))}

      {today.fee_summary && totalSelected > 0 && (
        <p className="exec-v2-fee text-muted">
          申购费 {fmtMoney(today.fee_summary.total_purchase_fee)} · 净投入{" "}
          {fmtMoney(today.fee_summary.total_net_invested)}
        </p>
      )}

      <div className="exec-v2-submit-bar">
        <button type="button" disabled={busy || totalSelected <= 0} onClick={submit}>
          {busy ? "提交中…" : isBackfill ? `补录提交 ${fmtMoney(totalSelected)}` : `全部提交 ${fmtMoney(totalSelected)}`}
        </button>
        {isToday && (
          <button type="button" className="secondary" disabled={busy} onClick={skipToday}>
            今日跳过
          </button>
        )}
        {msg && <span className={msg.includes("已") ? "save-hint" : "text-down"}>{msg}</span>}
      </div>
    </section>
  );
}
