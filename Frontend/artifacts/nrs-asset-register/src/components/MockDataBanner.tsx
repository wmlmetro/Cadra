import { Info } from "lucide-react";

interface Props {
  reason?: string;
}

/**
 * Persistent stripe at the top of pages that have no backing API endpoint.
 * Reused by Fleet, Staff Bus, and Identity (clearance) pages until those
 * resources ship in the Cadra v1 API.
 */
export default function MockDataBanner({ reason }: Props) {
  return (
    <div className="px-5 py-2 bg-amber-50 dark:bg-amber-950/30 border-b border-amber-200/70 dark:border-amber-800/30 flex items-center gap-2">
      <Info size={12} className="text-amber-700 dark:text-amber-400 shrink-0" />
      <p className="text-[11px] text-amber-800 dark:text-amber-300">
        <span className="font-semibold">Showing mock data</span>
        {reason ? <> — {reason}</> : <> — backend endpoint not yet available.</>}
      </p>
    </div>
  );
}
