import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import HistorySection from "../components/execution/v2/HistorySection";
import DcaFundPanel from "../components/execution/v2/DcaFundPanel";
import PendingSection from "../components/execution/v2/PendingSection";
import TodaySection from "../components/execution/v2/TodaySection";
import type { InvestmentRecord, TodayView } from "../types/execution-v2";

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

export default function ExecutionPage() {
  const [viewDate, setViewDate] = useState(todayIso);
  const [today, setToday] = useState<TodayView | null>(null);
  const [pending, setPending] = useState<InvestmentRecord[]>([]);

  const load = useCallback(async () => {
    const [todayRes, pendingRes] = await Promise.all([
      api<TodayView>(`/api/v1/execution/today?date=${viewDate}`),
      api<InvestmentRecord[]>("/api/v1/execution/pending"),
    ]);
    if (todayRes.data) setToday(todayRes.data);
    if (pendingRes.data) setPending(pendingRes.data);
  }, [viewDate]);

  useEffect(() => {
    load();
  }, [load]);

  if (!today) {
    return (
      <div className="exec-v2-page">
        <DcaFundPanel today={null} onReload={load} />
        <div className="card">加载定投任务…</div>
      </div>
    );
  }

  return (
    <div className="exec-v2-page">
      <DcaFundPanel today={today} onReload={load} />
      <TodaySection
        today={today}
        viewDate={viewDate}
        onViewDateChange={setViewDate}
        onReload={load}
      />
      <PendingSection records={pending} onReload={load} />
      <HistorySection month={viewDate.slice(0, 7)} />
    </div>
  );
}
