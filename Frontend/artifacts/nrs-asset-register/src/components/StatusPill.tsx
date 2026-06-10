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
  "Review — allottee not in nominal roll": {
    bg: "bg-orange-50 dark:bg-orange-950/30 border-orange-200/70 dark:border-orange-800/30",
    text: "text-orange-700 dark:text-orange-400",
    dot: "bg-orange-500",
  },
  "Review — VIN not verifiable": {
    bg: "bg-yellow-50 dark:bg-yellow-950/30 border-yellow-200/70 dark:border-yellow-800/30",
    text: "text-yellow-700 dark:text-yellow-400",
    dot: "bg-yellow-500",
  },
  "Review — possible duplicate": {
    bg: "bg-purple-50 dark:bg-purple-950/30 border-purple-200/70 dark:border-purple-800/30",
    text: "text-purple-700 dark:text-purple-400",
    dot: "bg-purple-500",
  },
};

interface StatusPillProps {
  status: ApprovalStatus;
  showDot?: boolean;
  className?: string;
}

export default function StatusPill({ status, showDot = false, className }: StatusPillProps) {
  const cfg = statusConfig[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg text-[11px] font-semibold border",
        cfg.bg,
        cfg.text,
        className
      )}
    >
      {showDot && <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", cfg.dot)} />}
      {status}
    </span>
  );
}
