import { useEffect, useState } from "react";
import { api, getRole } from "../api";

export default function DataPage() {
  const [status, setStatus] = useState<any>(null);

  async function load() {
    const res = await api("/api/v1/data/status");
    setStatus(res.data);
  }

  useEffect(() => {
    load();
  }, []);

  async function refresh() {
    if (getRole() === "admin") {
      await api("/api/v1/data/refresh", { method: "POST" });
    }
    load();
  }

  return (
    <>
      <button onClick={refresh}>刷新数据源</button>
      <div className="card" style={{ marginTop: 16 }}>
        <h3>10 年回填进度</h3>
        <p>
          {status?.backfill?.status} · {status?.backfill?.progress_pct}% · {status?.backfill?.message}
        </p>
      </div>
      <table style={{ marginTop: 16 }}>
        <thead>
          <tr>
            <th>数据源</th>
            <th>最后更新</th>
            <th>状态</th>
            <th>备注</th>
          </tr>
        </thead>
        <tbody>
          {(status?.sources || []).map((s: any) => (
            <tr key={s.data_key}>
              <td>{s.name}</td>
              <td>{s.last_updated || "—"}</td>
              <td>{s.status}</td>
              <td>{s.message || (s.from_cache ? "缓存" : "")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
