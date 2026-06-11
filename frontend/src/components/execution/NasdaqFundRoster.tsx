import type { GrowthLimitRow } from "../../types/execution";
import { fmtMoney } from "../../utils/formatNumber";

type RosterRow = GrowthLimitRow & {
  tier?: number;
  ladder_order?: number;
  note?: string;
  buyable?: boolean;
  is_custom?: boolean;
};

type Props = {
  roster: RosterRow[];
};

function fmtLimit(n: number | null | undefined) {
  if (n == null) return "—";
  if (n <= 0) return "暂停";
  return fmtMoney(n);
}

export default function NasdaqFundRoster({ roster }: Props) {
  if (!roster.length) return null;

  const buyable = roster.filter((r) => r.buyable);
  const paused = roster.filter((r) => !r.buyable);

  return (
    <details className="daily-schedule ndx-roster" open>
      <summary>
        纳指100候选名单（{buyable.length} 只可买 · {paused.length} 只暂停）
      </summary>
      <p className="text-muted daily-hint">
        按轮询阶梯排序；含内置名单与用户自定义基金，可在下方调整日限购或添加新基金。
      </p>
      <div className="ndx-roster-table data-table">
        <table>
          <thead>
            <tr>
              <th>阶梯</th>
              <th>代码</th>
              <th>基金</th>
              <th className="num">日限购</th>
              <th>状态</th>
              <th>备注</th>
            </tr>
          </thead>
          <tbody>
            {roster.map((row) => (
              <tr key={row.fund_code} className={row.buyable ? "" : "dca-row-off"}>
                <td className="font-num">{row.tier}</td>
                <td className="font-num">{row.fund_code}</td>
                <td>
                  {row.fund_name}
                  {row.is_custom && <span className="badge custom-fund-badge">自定义</span>}
                </td>
                <td className="num font-num">{fmtLimit(row.daily_limit as number | null)}</td>
                <td>{row.status === "paused" ? "暂停" : row.status === "limited" ? "限大额" : "开放"}</td>
                <td className="text-muted">{row.note || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
