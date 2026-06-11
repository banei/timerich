import { useEffect, useState } from "react";
import { api } from "../../../api";
import type { MonthHistory } from "../../../types/execution-v2";
import { STATUS_LABEL } from "../../../types/execution-v2";
import { fmtMoney } from "../../../utils/formatNumber";

type Props = {
  month?: string;
};

export default function HistorySection({ month }: Props) {
  const [history, setHistory] = useState<MonthHistory | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const m = month || new Date().toISOString().slice(0, 7);

  useEffect(() => {
    api<MonthHistory>(`/api/v1/execution/history?month=${m}&status=${statusFilter}`).then((r) => {
      if (r.data) setHistory(r.data);
    });
  }, [m, statusFilter]);

  function exportCsv() {
    if (!history) return;
    const lines = ["日期,基金,类型,金额,状态"];
    for (const day of history.days) {
      for (const rec of day.records) {
        lines.push(
          [rec.date, rec.fund_code, rec.record_type, rec.submitted_amount, rec.status].join(","),
        );
      }
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `execution-${m}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="card exec-v2-section">
      <details className="exec-v2-history">
        <summary className="exec-v2-summary">本月记录 {m}</summary>
        {history && (
          <>
            <div className="exec-v2-history-summary">
              <span>
                累计提交 <strong className="font-num">{fmtMoney(history.summary.total_submitted)}</strong>
              </span>
              <span>
                已确认 <strong className="font-num text-up">{fmtMoney(history.summary.total_confirmed)}</strong>
              </span>
              <span>
                失败 <strong className="font-num text-down">{fmtMoney(history.summary.total_failed)}</strong>
              </span>
            </div>
            <div className="exec-v2-filter-row">
              <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="all">全部状态</option>
                <option value="pending">待确认</option>
                <option value="confirmed">已确认</option>
                <option value="failed">失败</option>
                <option value="partial">部分成功</option>
              </select>
              <button type="button" className="secondary" onClick={exportCsv}>
                导出本月记录
              </button>
            </div>
            <table className="exec-v2-table">
              <thead>
                <tr>
                  <th>日期</th>
                  <th>基金</th>
                  <th>类型</th>
                  <th>金额</th>
                  <th>结果</th>
                </tr>
              </thead>
              <tbody>
                {history.days.map((day) => (
                  <tr key={day.date}>
                    <td className="font-num">{day.date.slice(5)}</td>
                    <td>{day.label}</td>
                    <td>{day.record_type === "probe" ? "试探" : "定投"}</td>
                    <td className="font-num">{fmtMoney(day.amount)}</td>
                    <td>{STATUS_LABEL[day.status] || day.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </details>
    </section>
  );
}
