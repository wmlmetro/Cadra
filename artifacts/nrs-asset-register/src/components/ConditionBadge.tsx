import type { Asset } from "@/types";
import { cn } from "@/lib/utils";

const conditionConfig: Record<Asset["condition"], { bg: string; text: string }> = {
  "Good":   { bg: "bg-green-50 dark:bg-green-900/20",  text: "text-green-700 dark:text-green-300" },
  "Fair":   { bg: "bg-blue-50 dark:bg-blue-900/20",    text: "text-blue-700 dark:text-blue-300" },
  "Poor":   { bg: "bg-amber-50 dark:bg-amber-900/20",  text: "text-amber-700 dark:text-amber-300" },
  "Faulty": { bg: "bg-red-50 dark:bg-red-900/20",      text: "text-red-700 dark:text-red-300" },
};

export default function ConditionBadge({ condition }: { condition: Asset["condition"] }) {
  const config = conditionConfig[condition];
  return (
    <span className={cn("inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium", config.bg, config.text)}>
      {condition}
    </span>
  );
}
