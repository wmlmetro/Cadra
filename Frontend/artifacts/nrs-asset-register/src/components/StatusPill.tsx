import type { ApprovalStatus } from "@/types";
import { cn } from "@/lib/utils";

type Config = { bg: string; text: string; dot: string };

const statusConfig: Record<ApprovalStatus, Config> = {
  "Cleared": {
    bg: "bg-green-50 dark:bg-green-950/30 border-green-200/70 dark:border-green-800/30",
    text: "text-green-700 dark:text-green-400",
    dot: "bg-green-500",
  },
  "Review — data quality": {
    bg: "bg-amber-50 dark:bg-amber-950/30 border-amber-200/70 dark:border-amber-800/30",
    text: "text-amber-700 dark:text-amber-400",
    dot: "bg-amber-500",
  },
  // Orange, not amber and not red. It has to read as a different finding from
  // "data quality" at a glance down a column — the two sit side by side in the
  // register, and both begin with the word "Review" — and red is kept for the
  // one alarm on this screen, a missing asset (`LifecyclePill`).
  "Review — no SAP code": {
    bg: "bg-orange-50 dark:bg-orange-950/30 border-orange-300/70 dark:border-orange-800/40",
    text: "text-orange-800 dark:text-orange-300",
    dot: "bg-orange-500",
  },
  // Not a verdict — the absence of one. Muted on purpose: an asset that is
  // missing or disposed has no data-quality status, and a colour here would
  // claim one. `AssetStatusPills` draws the lifecycle pill instead wherever
  // the state is known; this is what is left when it is not.
  "Not in service": {
    bg: "bg-muted border-border",
    text: "text-muted-foreground",
    dot: "bg-muted-foreground/50",
  },
};

/** A status this build has never seen still renders. The lookup was an
 *  unguarded index, so one unmapped value — a persisted query cache written by
 *  an older build is enough — read `undefined` and threw on `cfg.bg`: a white
 *  screen on the register. `ConditionBadge` already falls back this way. */
const UNKNOWN_STATUS: Config = {
  bg: "bg-muted border-border",
  text: "text-muted-foreground",
  dot: "bg-muted-foreground/50",
};

interface StatusPillProps {
  status: ApprovalStatus;
  showDot?: boolean;
  className?: string;
}

export default function StatusPill({ status, showDot = false, className }: StatusPillProps) {
  const cfg = statusConfig[status] ?? UNKNOWN_STATUS;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg text-[11px] font-semibold border",
        cfg.bg,
        cfg.text,
        className
      )}
      data-testid="status-pill"
      data-status={status}
    >
      {showDot && <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", cfg.dot)} />}
      {status}
    </span>
  );
}
