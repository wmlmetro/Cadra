import type { AssetDepreciation, DepreciationMethod, DepreciationState } from "@/types";
import { cn } from "@/lib/utils";
import { Info, AlertTriangle } from "lucide-react";
import DepreciationTimeline from "@/components/DepreciationTimeline";

const METHOD_LABEL: Record<DepreciationMethod, string> = {
  none: "Not depreciated",
  straight_line: "Straight line",
  declining_balance: "Declining balance",
  erp_managed: "ERP-managed",
};

const STATE_LABEL: Record<DepreciationState, string> = {
  not_applicable: "Not depreciated",
  not_started: "Not started",
  depreciating: "Depreciating",
  fully_depreciated: "Fully depreciated",
  disposed: "Disposed",
  erp_managed: "ERP-managed",
};

const STATE_CLASS: Record<DepreciationState, string> = {
  not_applicable: "bg-muted text-muted-foreground",
  not_started: "bg-muted text-muted-foreground",
  depreciating: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  fully_depreciated: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  disposed: "bg-muted text-muted-foreground",
  erp_managed: "bg-sky-500/10 text-sky-600 dark:text-sky-400",
};

function money(v: number | undefined, currency?: string) {
  if (typeof v !== "number") return "—";
  const formatted = v.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return currency ? `${currency} ${formatted}` : formatted;
}

function Row({ label, value }: { label: string; value?: React.ReactNode }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="flex flex-col sm:flex-row sm:gap-4 py-2.5 border-b border-border last:border-0">
      <dt className="text-xs font-medium text-muted-foreground w-44 shrink-0">{label}</dt>
      <dd className="text-xs text-foreground mt-0.5 sm:mt-0">{value}</dd>
    </div>
  );
}

export default function DepreciationCard({
  assetId,
  depreciation: d,
  currency,
}: {
  assetId: string;
  depreciation: AssetDepreciation;
  currency?: string;
}) {
  const isErp = d.method === "erp_managed";
  const isComputed = d.method === "straight_line" || d.method === "declining_balance";

  // Proportion of the depreciable amount written off so far. Only meaningful
  // when there is actually something to depreciate.
  const depreciable =
    typeof d.depreciableCost === "number" && typeof d.salvageValue === "number"
      ? d.depreciableCost - d.salvageValue
      : undefined;
  const pct =
    depreciable && depreciable > 0 && typeof d.accumulatedDepreciation === "number"
      ? Math.min(100, Math.max(0, (d.accumulatedDepreciation / depreciable) * 100))
      : undefined;

  return (
    <section>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Depreciation
        </h3>
        <span
          className={cn(
            "text-[10px] font-medium px-2 py-0.5 rounded-full",
            STATE_CLASS[d.state] ?? "bg-muted text-muted-foreground",
          )}
        >
          {STATE_LABEL[d.state] ?? d.state}
        </span>
      </div>

      <div className="bg-card border border-card-border rounded-xl px-5 py-1">
        {/* Cadra never calculates for ERP-managed assets — NRS spec §6.2. */}
        {isErp && (
          <div className="flex gap-2 items-start text-[11px] text-sky-700 dark:text-sky-300 bg-sky-500/10 rounded-lg px-3 py-2 my-3">
            <Info className="h-3.5 w-3.5 shrink-0 mt-px" />
            <span>
              Book value for this asset is supplied by an external ERP. Cadra stores
              it for reporting and does not calculate it.
            </span>
          </div>
        )}

        {/* An inferred start date makes every figure below an estimate. */}
        {d.startDateIsEstimated && isComputed && (
          <div className="flex gap-2 items-start text-[11px] text-amber-700 dark:text-amber-300 bg-amber-500/10 rounded-lg px-3 py-2 my-3">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-px" />
            <span>
              No acquisition or purchase date on record, so depreciation was started
              from the date this record was created. These figures are an estimate
              until a real date is captured.
            </span>
          </div>
        )}

        {pct !== undefined && (
          <div className="py-3">
            <div className="flex justify-between text-[11px] text-muted-foreground mb-1.5">
              <span>Written off</span>
              <span>{pct.toFixed(1)}%</span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
              <div
                className="h-full rounded-full bg-emerald-500 transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        )}

        <dl>
          <Row label="Method" value={METHOD_LABEL[d.method] ?? d.method} />
          <Row
            label="Useful Life"
            value={d.usefulLifeMonths ? `${d.usefulLifeMonths} months` : undefined}
          />
          <Row
            label="Declining Rate"
            value={d.decliningRate ? `${d.decliningRate}% / yr` : undefined}
          />
          <Row label="Depreciable Cost" value={money(d.depreciableCost, currency)} />
          <Row label="Salvage Value" value={money(d.salvageValue, currency)} />
          <Row
            label="Accumulated Depreciation"
            value={money(d.accumulatedDepreciation, currency)}
          />
          <Row
            label="Net Book Value"
            value={
              <span className="font-semibold">{money(d.currentBookValue, currency)}</span>
            }
          />
          <Row label="Depreciation Start" value={d.startDate} />
          <Row label="Fully Depreciated On" value={d.endDate} />
          <Row
            label="Policy"
            value={d.usesCategoryPolicy ? "Inherited from category" : "Set on this asset"}
          />
        </dl>

        <DepreciationTimeline assetId={assetId} depreciation={d} currency={currency} />
      </div>
    </section>
  );
}
