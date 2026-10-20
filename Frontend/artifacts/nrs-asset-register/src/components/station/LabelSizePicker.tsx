import { LABEL_SIZES, type LabelSize } from "@/lib/labels";

/** The station's label-size selector — one control for both of the
 *  station's modes, so a label printed from *Capture* comes out the size the
 *  printer on the desk is loaded with, like every other label there. */
export default function LabelSizePicker({ value, onChange, testid }: {
  value: LabelSize; onChange: (v: LabelSize) => void; testid?: string;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as LabelSize)}
      title={LABEL_SIZES.find((s) => s.value === value)?.hint}
      aria-label="Label size"
      data-testid={testid}
      className="px-2 py-1.5 text-[11px] border border-border rounded-xl bg-background"
    >
      {LABEL_SIZES.map((s) => (
        <option key={s.value} value={s.value}>{s.label} — {s.hint.split(" — ")[0]}</option>
      ))}
    </select>
  );
}
