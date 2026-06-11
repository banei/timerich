import { fmtMoney } from "../../../utils/formatNumber";
import { AMOUNT_PRESETS } from "./fundConfigUtils";

type Props = {
  value: number;
  onChange: (amount: number) => void;
  disabled?: boolean;
  compact?: boolean;
};

export default function AmountQuickPicker({ value, onChange, disabled, compact }: Props) {
  return (
    <div className={`exec-v2-amount-picker ${compact ? "exec-v2-amount-picker-compact" : ""}`}>
      <input
        type="number"
        min={0}
        step={1}
        className="exec-v2-amount-input font-num"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Math.max(0, Number(e.target.value) || 0))}
      />
      <div className="exec-v2-amount-presets">
        {AMOUNT_PRESETS.map((n) => (
          <button
            key={n}
            type="button"
            className={`exec-v2-preset-btn ${value === n ? "active" : ""}`}
            disabled={disabled}
            title={n === 0 ? "暂停定投" : fmtMoney(n)}
            onClick={() => onChange(n)}
          >
            {n === 0 ? "暂停" : n}
          </button>
        ))}
      </div>
    </div>
  );
}
