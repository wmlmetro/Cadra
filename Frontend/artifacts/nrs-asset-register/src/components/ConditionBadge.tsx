import type { Asset } from "@/types";
import { cn } from "@/lib/utils";

const conditionConfig: Record<Asset["condition"], { bg: string; text: string; dot: string }> = {
  "Good":   { bg: "bg-green-50 dark:bg-green-950/30 border-green-200/70 dark:border-green-800/30",  text: "text-green-700 dark:text-green-400",  dot: "bg-green-500"  },
  "Fair":   { bg: "bg-blue-50 dark:bg-blue-950/30 border-blue-200/70 dark:border-blue-800/30",      text: "text-blue-700 dark:text-blue-400",    dot: "bg-blue-500"   },
  "Poor":   { bg: "bg-amber-50 dark:bg-amber-950/30 border-amber-200/70 dark:border-amber-800/30",  text: "text-amber-700 dark:text-amber-400",  dot: "bg-amber-500"  },
  "Faulty": { bg: "bg-red-50 dark:bg-red-950/30 border-red-200/70 dark:border-red-800/30",          text: "text-red-700 dark:text-red-400",      dot: "bg-red-500"    },
};

export default function ConditionBadge({ condition, showDot }: { condition: Asset["condition"]; showDot?: boolean }) {
  const cfg = conditionConfig[condition];
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg text-[11px] font-semibold border", cfg.bg, cfg.text)}>
      {showDot && <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", cfg.dot)} />}
      {condition}
    </span>
  );
}
