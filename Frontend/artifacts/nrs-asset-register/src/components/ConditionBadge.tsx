import { cn } from "@/lib/utils";
import { useEnumLabel } from "@/hooks/useEnums";

/**
 * Styling per `nrs.asset.condition` key — the model's keys, not display words.
 *
 * This map used to be keyed on a four-member display union ("Good", "Fair",
 * "Poor", "Decommissioned") that the adapter translated into. The model has
 * five values, and the missing one was `new`, which the adapter folded into
 * "Good". So a brand-new asset was drawn in the same green as one that had been
 * in service for six years, and 282 of them across the live tenants (204
 * jaizbankplc, 54 nrs19, 24 cadra19) had no way of being seen as new at all.
 * `new` gets its own emerald here for that reason: it is a distinct state the
 * register stopped showing, and the whole point of this change is that it is
 * visible again.
 */
const conditionConfig: Record<string, { bg: string; text: string; dot: string }> = {
  "new":    { bg: "bg-emerald-50 dark:bg-emerald-950/30 border-emerald-300/70 dark:border-emerald-700/40", text: "text-emerald-700 dark:text-emerald-300", dot: "bg-emerald-500" },
  "good":   { bg: "bg-green-50 dark:bg-green-950/30 border-green-200/70 dark:border-green-800/30",  text: "text-green-700 dark:text-green-400",  dot: "bg-green-500"  },
  "fair":   { bg: "bg-blue-50 dark:bg-blue-950/30 border-blue-200/70 dark:border-blue-800/30",      text: "text-blue-700 dark:text-blue-400",    dot: "bg-blue-500"   },
  "poor":   { bg: "bg-amber-50 dark:bg-amber-950/30 border-amber-200/70 dark:border-amber-800/30",  text: "text-amber-700 dark:text-amber-400",  dot: "bg-amber-500"  },
  "decommissioned": { bg: "bg-red-50 dark:bg-red-950/30 border-red-200/70 dark:border-red-800/30",  text: "text-red-700 dark:text-red-400",      dot: "bg-red-500"    },
};

/** A key this build has never seen still renders. The lookup was an unguarded
 *  index before, so the first value the model gains would have read `undefined`
 *  off this map and thrown on `cfg.bg` — a white screen on the register,
 *  triggered by a one-line Python change in a module nobody deployed with the
 *  front end. Muted is the honest answer for a state we have no opinion about. */
const UNKNOWN_CONDITION = {
  bg: "bg-muted border-border",
  text: "text-muted-foreground",
  dot: "bg-muted-foreground/50",
};

export default function ConditionBadge({ condition, showDot }: { condition: string; showDot?: boolean }) {
  // The label is the model's own, read live from /api/v1/meta/enums, so a
  // value added to the Selection is spelled the way the model spells it
  // without a front-end release. `enumLabel` falls through to the raw key for
  // anything the set does not carry, which is better than a blank badge.
  const labelOf = useEnumLabel("condition");
  const cfg = conditionConfig[condition] ?? UNKNOWN_CONDITION;
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg text-[11px] font-semibold border", cfg.bg, cfg.text)}>
      {showDot && <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", cfg.dot)} />}
      {labelOf(condition)}
    </span>
  );
}
