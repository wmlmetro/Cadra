/**
 * The panel a page draws in place of itself when the session does not hold
 * the scope the page is for.
 *
 * Generalised from the Users page's admin-only refusal in handoff 46, when
 * Access changes stopped requiring `admin` and began requiring what its
 * server route requires, `identity:read`. The server refuses the same read
 * whether or not this panel is drawn; the panel only says so before a
 * request is made, in words rather than a 403.
 */
import { AlertCircle } from "lucide-react";

export function ScopeRefusal({ scope, detail, testId = "scope-refusal" }: {
  scope: string;
  /** A second sentence about who does hold it. */
  detail?: string;
  testId?: string;
}) {
  return (
    <div className="p-8 max-w-xl mx-auto" data-testid={testId} data-scope={scope}>
      <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3">
        <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-[13px] font-semibold text-red-700 dark:text-red-400">This page needs the {scope} scope</p>
          <p className="text-[12px] text-red-700 dark:text-red-400 mt-0.5">
            Your session does not hold it.{detail ? ` ${detail}` : ""}
          </p>
        </div>
      </div>
    </div>
  );
}
