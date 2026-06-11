import { useState } from "react";
import { api } from "../../../api";
import type { InvestmentRecord } from "../../../types/execution-v2";
import { STATUS_LABEL } from "../../../types/execution-v2";
import { fmtAmount, fmtMoney } from "../../../utils/formatNumber";

type Props = {
  records: InvestmentRecord[];
  onReload: () => void;
};

function shortDate(iso: string) {
  const d = iso.slice(5).replace("-", "-");
  return d.startsWith("0") ? d.slice(1) : d;
}

function PendingRecordRow({ row, onUpdated }: { row: InvestmentRecord; onUpdated: () => void }) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState(row.status === "pending" ? "confirmed" : row.status);
  const [amount, setAmount] = useState(String(row.submitted_amount));
  const [shares, setShares] = useState(row.confirmed_shares != null ? String(row.confirmed_shares) : "");
  const [nav, setNav] = useState(row.confirmed_nav != null ? String(row.confirmed_nav) : "");
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    const res = await api(`/api/v1/execution/records/${row.id}/confirm`, {
      method: "PATCH",
      body: JSON.stringify({
        status,
        confirmed_amount: Number(amount),
        confirmed_shares: shares ? Number(shares) : undefined,
        confirmed_nav: nav ? Number(nav) : undefined,
        confirmed_date: new Date().toISOString().slice(0, 10),
      }),
    });
    setBusy(false);
    if (!res.error) {
      setOpen(false);
      onUpdated();
    }
  }

  return (
    <>
      <tr className={row.status === "pending" ? "exec-v2-pending-row" : ""}>
        <td className="font-num">{shortDate(row.date)}</td>
        <td className="exec-v2-pending-fund">
          <span className="font-num">{row.fund_code}</span>{" "}
          <span className="exec-v2-name">{row.fund_name}</span>
        </td>
        <td className="font-num">{fmtMoney(row.submitted_amount)}</td>
        <td>
          {STATUS_LABEL[row.status] || row.status}
          {row.status === "confirmed" && row.confirmed_shares != null && (
            <span className="text-muted"> 份额+{fmtAmount(row.confirmed_shares)}</span>
          )}
        </td>
        <td>
          {row.status === "pending" && (
            <button type="button" className="secondary exec-v2-mini-btn" onClick={() => setOpen(!open)}>
              更新
            </button>
          )}
        </td>
      </tr>
      {open && (
        <tr className="exec-v2-confirm-form-row">
          <td colSpan={5}>
            <div className="exec-v2-confirm-form">
              <select value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="confirmed">✅ 已确认</option>
                <option value="failed">❌ 失败</option>
                <option value="partial">⚠️ 部分成功</option>
              </select>
              <input type="number" step="0.01" placeholder="成交金额" value={amount} onChange={(e) => setAmount(e.target.value)} />
              <input type="number" step="0.0001" placeholder="份额" value={shares} onChange={(e) => setShares(e.target.value)} />
              <input type="number" step="0.0001" placeholder="净值" value={nav} onChange={(e) => setNav(e.target.value)} />
              <button type="button" disabled={busy} onClick={save}>
                保存
              </button>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function PendingSection({ records, onReload }: Props) {
  const pending = records.filter((r) => r.status === "pending");
  const [open, setOpen] = useState(pending.length > 0);
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);

  async function syncDefaultAmounts() {
    setSyncing(true);
    setSyncMsg(null);
    const res = await api<{ updated: unknown[]; count: number }>("/api/v1/execution/sync-default-amounts", {
      method: "POST",
    });
    setSyncing(false);
    if (res.error) {
      setSyncMsg("同步失败");
      return;
    }
    const n = res.data?.count ?? 0;
    setSyncMsg(n > 0 ? `已同步 ${n} 只基金默认定投金额` : "无历史记录可同步");
    onReload();
  }

  if (pending.length === 0) {
    return (
      <section className="card exec-v2-section exec-v2-pending-section">
        <div className="exec-v2-summary exec-v2-summary-with-actions">
          <span>待确认</span>
          <button
            type="button"
            className="secondary exec-v2-mini-btn exec-v2-sync-btn"
            disabled={syncing}
            title="按每只基金最近一次定投结果更新默认定投金额；购买失败则设为 0"
            onClick={() => void syncDefaultAmounts()}
          >
            {syncing ? "同步中…" : "↻ 同步默认金额"}
          </button>
        </div>
        {syncMsg && <p className="exec-v2-sync-msg">{syncMsg}</p>}
        <p className="exec-v2-empty-hint text-muted">暂无待确认记录，已确认或失败的记录见下方「本月记录」。</p>
      </section>
    );
  }

  return (
    <section className="card exec-v2-section">
      <details open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
        <summary className="exec-v2-summary exec-v2-summary-with-actions">
          <span>
            待确认 {pending.length > 0 && <span className="badge">{pending.length}笔</span>}
          </span>
          <button
            type="button"
            className="secondary exec-v2-mini-btn exec-v2-sync-btn"
            disabled={syncing}
            title="按每只基金最近一次定投结果更新默认定投金额；购买失败则设为 0"
            onClick={(e) => {
              e.preventDefault();
              void syncDefaultAmounts();
            }}
          >
            {syncing ? "同步中…" : "↻ 同步默认金额"}
          </button>
        </summary>
        {syncMsg && <p className="exec-v2-sync-msg">{syncMsg}</p>}
        <table className="exec-v2-table">
          <thead>
            <tr>
              <th>日期</th>
              <th>基金</th>
              <th>金额</th>
              <th>状态</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {pending.map((r) => (
              <PendingRecordRow key={r.id} row={r} onUpdated={onReload} />
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}
