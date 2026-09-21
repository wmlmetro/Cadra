import { cn } from "@/lib/utils";
import { useEnumLabel } from "@/hooks/useEnums";

/**
 * Styling per `nrs.asset.state` key — the model's keys, not display words.
 *
 * The only PAGE-SIDE file that holds these keys side by side (`lib/enums.ts`
 * holds the seed the model is checked against), and it holds them for colour
 * alone. The words come from the model (below). It is waived by name in
 * `tests/test_frontend_enums.py` (`STYLING_WAIVERS`), which allows a styling
 * map on the condition that it carries a fallback. A second copy elsewhere is
 * MEANT to fail the build — but know the guard's reach before leaning on it:
 * it matches double-quoted keys within 240 characters, so an unquoted-key
 * object or single quotes would slip past. Don't.
 *
 * It exists because nothing drew the lifecycle at all. "Mark missing" and
 * "Condemn" move an asset off `active`, and the only thing on the page that
 * read `state` was one raw-text row; the pill beside the name was derived from
 * `is_verified` and said "Cleared" in green over a missing asset. Red for
 * missing because it is the one state that is an alarm; a strong slate for
 * disposed because it is final and not an alarm; the rest follow the
 * condition badge's palette.
 */
const stateConfig: Record<string, { bg: string; text: string; dot: string }> = {
  "active":      { bg: "bg-green-50 dark:bg-green-950/30 border-green-200/70 dark:border-green-800/30", text: "text-green-700 dark:text-green-400", dot: "bg-green-500" },
  "in_repair":   { bg: "bg-amber-50 dark:bg-amber-950/30 border-amber-200/70 dark:border-amber-800/30", text: "text-amber-700 dark:text-amber-400", dot: "bg-amber-500" },
  "transferred": { bg: "bg-blue-50 dark:bg-blue-950/30 border-blue-200/70 dark:border-blue-800/30",     text: "text-blue-700 dark:text-blue-400",   dot: "bg-blue-500"  },
  "missing":     { bg: "bg-red-50 dark:bg-red-950/30 border-red-200/70 dark:border-red-800/30",         text: "text-red-700 dark:text-red-400",     dot: "bg-red-500"   },
  "disposed":    { bg: "bg-slate-200 dark:bg-slate-800 border-slate-400/70 dark:border-slate-600/60",   text: "text-slate-800 dark:text-slate-200", dot: "bg-slate-600 dark:bg-slate-400" },
};

/** A key this build has never seen still renders. The model gaining a sixth
 *  state is a one-line Python change in a module nobody deploys with the front
 *  end, and an unguarded index here would turn it into a white screen on every
 *  page that lists an asset. Muted is the honest answer for a state we have no
 *  opinion about — and the label below still spells it the model's way. */
const UNKNOWN_STATE = {
  bg: "bg-muted border-border",
  text: "text-muted-foreground",
  dot: "bg-muted-foreground/50",
};

export default function LifecyclePill({ state, showDot, className }: { state: string; showDot?: boolean; className?: string }) {
  // The label is the model's own, read live from /api/v1/meta/enums. The set
  // is published as `asset_state`, not `state` — a bare `state` would collide
  // with the other models in the schema that have a field of that name.
  // `enumLabel` falls through to the raw key for anything the set does not
  // carry, which is better than a blank pill.
  const labelOf = useEnumLabel("asset_state");
  const cfg = stateConfig[state] ?? UNKNOWN_STATE;
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg text-[11px] font-semibold border", cfg.bg, cfg.text, className)}
      data-testid="lifecycle-pill"
      data-state={state}
    >
      {showDot && <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", cfg.dot)} />}
      {labelOf(state)}
    </span>
  );
}
