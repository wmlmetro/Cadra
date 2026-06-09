import type { ApprovalStatus } from "@/types";
import { cn } from "@/lib/utils";

const statusConfig: Record<ApprovalStatus, { bg: string; text: string; dot: string }> = {
  "Cleared": { bg: "bg-green-50 dark:bg-green-900/20", text: "text-green-800 dark:text-green-300", dot: "bg-green-500" },
  "Review — data quality": { bg: "bg-amber-50 dark:bg-amber-900/20", text: "text-amber-800 dark:text-amber-300", dot: "bg-amber-500" },
  "Review — allottee not in nominal roll": { bg: "bg-orange-50 dark:bg-orange-900/20", text: "text-orange-800 dark:text-orange-300", dot: "bg-orange-500" },
  "Review — VIN not verifiable": { bg: "bg-amber-50 dark:bg-amber-900/20", text: "text-amber-800 dark:text-amber-300", dot: "bg-amber-500" },
  "Review — possible duplicate": { bg: "bg-purple-50 dark:bg-purple-900/20", text: "text-purple-800 dark:text-purple-300", dot: "bg-purple-500" },
};

interface StatusPillProps {
  status: ApprovalStatus;
  showDot?: boolean;
  className?: string;
}

export default function StatusPill({ status, showDot = false, className }: StatusPillProps) {
  const config = statusConfig[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border",
        config.bg,
        config.text,
        "border-current/10",
        className
      )}
    >
      {showDot && <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", config.dot)} />}
      {status}
    </span>
  );
}
