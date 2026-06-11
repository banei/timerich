import { useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import type { DailyDcaBatch, DailyDcaBatchItem } from "../../types/execution";
import { fmtAmount, fmtMoney } from "../../utils/formatNumber";

type Props = {
  month: string;
  batch: DailyDcaBatch;
  onReload: () => void;
  onRefreshNav?: () => void;
};

function fmtNav(n: number) {
  return fmtAmount(n);
}

function fmtShares(n: number) {
  return n.toLocaleString("zh-CN", { minimumFractionDigits: 4, maximumFractionDigits: 4 });
}

export default function DailyDcaBatchPanel({ month, batch, onReload, onRefreshNav }: Props) {
  const [items, setItems] = useState<DailyDcaBatchItem[]>(batch.items);
  const [busy, setBusy] = useState(false);
  const [navBusy, setNavBusy] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    setItems(batch.items);
    setMsg("");
  }, [batch]);

  const totalSelected = useMemo(
    () =>
      items.reduce((sum, i) => (i.selected ? sum + (i.planned_amount || 0) : sum), 0),
    [items],
  );

  const totalShares = useMemo(() => {
    const rows = items.filter((i) => i.selected && i.estimated_shares != null);
    if (rows.length === 0) return null;
    return rows.reduce((sum, i) => sum + (i.estimated_shares || 0), 0);
  }, [items]);

  const readonly = batch.status === "confirmed" || batch.status === "cancelled";
  const hasItems = items.length > 0;
  const missingNav = batch.share_summary?.funds_missing_nav ?? 0;

  function toggle(code: string, checked: boolean) {
    setItems((prev) => prev.map((i) => (i.fund_code === code ? { ...i, selected: checked } : i)));
  }

  function payloadFunds() {
    return items.map((i) => ({
      fund_code: i.fund_code,
      fund_name: i.fund_name,
      planned_amount: i.planned_amount,
      selected: Boolean(i.selected),
    }));
  }

  function shareLine(row: DailyDcaBatchItem) {
    if (row.estimated_shares == null) return "净值待查";
    return fmtShares(row.estimated_shares);
  }

  function navLine(row: DailyDcaBatchItem) {
    if (row.nav == null) return "—";
    const dateHint = row.nav_date ? ` (${row.nav_date})` : "";
    const stale = row.nav_stale ? " · 偏旧" : "";
    return `${fmtNav(row.nav)}${dateHint}${stale}`;
  }

  async function refreshNav() {
    if (!onRefreshNav) return;
    setNavBusy(true);
    setMsg("");
    await onRefreshNav();
    setNavBusy(false);
  }

  async function confirmPurchase() {
    const selected = items.filter((i) => i.selected);
    if (selected.length === 0) {
      setMsg("请至少勾选一只基金");
      return;
    }
    const shareHint =
      totalShares != null
        ? `，预估合计 ${fmtShares(totalShares)} 份（按最新净值估算，以基金公司确认为准）`
        : "（部分基金暂无净值，确认后仍将记录金额）";
    if (!window.confirm(`确认今日批量购买 ${selected.length} 只基金，合计 ${fmtMoney(totalSelected)}${shareHint}？`)) {
      return;
    }
    setBusy(true);
    setMsg("");
    const res = await api(`/api/v1/execution/${month}/daily-dca/confirm`, {
      method: "PUT",
      body: JSON.stringify({ action_date: batch.action_date, funds: payloadFunds() }),
    });
    setBusy(false);
    if (res.error) {
      setMsg(res.error);
      return;
    }
    onReload();
  }

  async function cancelToday(stopMemory: boolean) {
    const tip = stopMemory
      ? "取消今日定投并停止沿用上日组合？明日将恢复系统默认阶梯。"
      : "确认取消今日定投？上日组合记忆仍会保留。";
    if (!window.confirm(tip)) return;
    setBusy(true);
    setMsg("");
    const res = await api(`/api/v1/execution/${month}/daily-dca/cancel`, {
      method: "PUT",
      body: JSON.stringify({
        action_date: batch.action_date,
        stop_memory: stopMemory,
        funds: payloadFunds(),
      }),
    });
    setBusy(false);
    if (res.error) {
      setMsg(res.error);
      return;
    }
    onReload();
  }

  async function stopMemory() {
    if (!window.confirm("停止定投记忆？明日将不再自动沿用上日基金组合。")) return;
    setBusy(true);
    setMsg("");
    const res = await api(`/api/v1/execution/${month}/daily-dca/stop`, { method: "PUT" });
    setBusy(false);
    if (res.error) {
      setMsg(res.error);
      return;
    }
    onReload();
  }

  if (batch.status === "idle" && !hasItems) {
    return null;
  }

  return (
    <div className="dca-batch-panel">
      <div className="dca-batch-header">
        <div className="dca-batch-title-row">
          <h4 className="section-title">今日批量购买确认</h4>
          {onRefreshNav && !readonly && hasItems && (
            <button type="button" className="secondary dca-refresh-nav" disabled={navBusy} onClick={refreshNav}>
              {navBusy ? "拉取净值…" : "刷新净值"}
            </button>
          )}
        </div>
        {missingNav > 0 && batch.status === "pending" && (
          <p className="dca-nav-warn text-warn">
            {missingNav} 只基金暂无净值，可点「刷新净值」从天天基金拉取；份额为估算值，以基金公司 T+1 确认为准。
          </p>
        )}
        {batch.memory_active && batch.memory_funds.length > 0 && (
          <p className="dca-memory-hint text-muted">
            沿用上日组合：
            {batch.memory_funds.map((f) => (
              <span key={f.fund_code} className="limit-chip">
                {f.fund_code} {f.fund_name}
              </span>
            ))}
            {!readonly && (
              <button type="button" className="secondary dca-stop-btn" disabled={busy} onClick={stopMemory}>
                停止定投
              </button>
            )}
          </p>
        )}
        {!batch.memory_active && batch.status === "pending" && (
          <p className="dca-memory-hint text-muted">首次确认后将记住所选组合，次日自动沿用。</p>
        )}
      </div>

      {batch.status === "confirmed" && (
        <p className="dca-status-banner dca-status-ok">
          今日已确认购买计划（{batch.confirmed_at ? new Date(batch.confirmed_at).toLocaleString("zh-CN") : ""}
          {totalShares != null ? ` · 预估 ${fmtShares(totalShares)} 份` : ""}）
        </p>
      )}
      {batch.status === "cancelled" && (
        <p className="dca-status-banner dca-status-cancel">
          今日已取消定投
          {batch.stop_memory ? "，且已停止组合记忆" : "，组合记忆仍保留"}
        </p>
      )}

      {hasItems && (
        <div className="dca-fund-table data-table">
          <table>
            <thead>
              <tr>
                <th className="dca-col-check">{readonly ? "" : "选"}</th>
                <th>代码</th>
                <th>基金</th>
                <th className="num">计划金额</th>
                <th className="num">净投入</th>
                <th className="num">净值</th>
                <th className="num">预估份额</th>
                <th>备注</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.fund_code} className={row.selected ? "" : "dca-row-off"}>
                  <td>
                    {!readonly && (
                      <input
                        type="checkbox"
                        checked={Boolean(row.selected)}
                        onChange={(e) => toggle(row.fund_code, e.target.checked)}
                      />
                    )}
                    {readonly && row.selected && <span className="dca-check-mark">✓</span>}
                  </td>
                  <td className="font-num">{row.fund_code}</td>
                  <td>{row.fund_name}</td>
                  <td className="num font-num">{fmtMoney(row.planned_amount)}</td>
                  <td className="num font-num">
                    {row.net_invested_amount != null ? fmtMoney(row.net_invested_amount) : "—"}
                  </td>
                  <td className="num font-num text-muted">{navLine(row)}</td>
                  <td className="num font-num">{shareLine(row)}</td>
                  <td className="text-muted">{row.notes || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {hasItems && (
        <div className="dca-batch-footer">
          <span className="dca-total text-muted">
            已选合计 <strong className="font-num">{fmtMoney(totalSelected)}</strong>
            {totalShares != null && (
              <>
                {" · "}
                预估份额 <strong className="font-num">{fmtShares(totalShares)}</strong>
              </>
            )}
          </span>
          {!readonly && (
            <div className="dca-batch-actions">
              <button type="button" disabled={busy} onClick={confirmPurchase}>
                {busy ? "处理中…" : "确认购买"}
              </button>
              <button type="button" className="secondary" disabled={busy} onClick={() => cancelToday(false)}>
                取消今日
              </button>
              <button type="button" className="secondary" disabled={busy} onClick={() => cancelToday(true)}>
                取消并停止定投
              </button>
            </div>
          )}
          {msg && <span className="text-down">{msg}</span>}
        </div>
      )}
    </div>
  );
}
