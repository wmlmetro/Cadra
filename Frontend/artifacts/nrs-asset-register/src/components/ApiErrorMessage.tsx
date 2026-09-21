/**
 * What goes INSIDE a red error panel, for every write in the app.
 *
 * There is no shared panel — each form, settings screen and dialog draws its
 * own box, in two layouts — and until handoff 31 each also wrote its own
 * `{err.code}: {err.message}` inside it. That was enough while every refusal
 * was one sentence. It stopped being enough the day a body field the API does
 * not accept became a `400 invalid_request` (handoff 31 §B): the server's
 * sentence for that is "This route does not accept: `nrs_asset_id`. Nothing
 * was written." — a route and a backticked key, to somebody who pressed Save
 * on a form. The readable part is in `error.details`:
 *
 *   rejected_fields  the keys refused
 *   hint             where ONE of them does belong, when the server knows
 *                    (today: `stage_id` on a request → the transition route)
 *   writable         what the route accepts. For an integration repairing
 *                    itself; not shown — a person cannot act on an allow-list.
 *
 * So this prints the fields in words, and says the one thing that matters
 * about this refusal and is NOT true of the warning it replaced: NOTHING was
 * saved, including the fields that were fine. The old answer was a 200 that
 * kept the rest; a person who remembers it would otherwise assume the rest
 * went through.
 *
 * INLINE ONLY — no toast. `lib/apiWarnings.tsx` raises a toast because a
 * warning rides on a SUCCESS, and every form navigates away on success, so
 * the message has to outlive the page. A refusal is the opposite case: the
 * form stays exactly where it is, with what was typed still in it, and the
 * panel sits beside the button that was pressed. A toast as well would be the
 * same sentence twice, one of them in a corner, and the one in the corner
 * would outlive the fix.
 */
import type { CadraApiError } from "@/lib/api";
import { fieldWords } from "@/lib/apiWarnings";

/** `details.rejected_fields` of a refused write; `[]` for any other error. */
export function refusedFields(err: CadraApiError | null | undefined): string[] {
  const d = err?.details;
  if (!d || typeof d !== "object") return [];
  const v = (d as { rejected_fields?: unknown }).rejected_fields;
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string" && x !== "") : [];
}

function refusalHint(err: CadraApiError): string | null {
  const h = (err.details as { hint?: unknown } | null | undefined)?.hint;
  return typeof h === "string" && h ? h : null;
}

const tone = "text-red-700 dark:text-red-400";

/**
 * `stacked` is the page-level layout (code on its own line, 13px, message
 * under it); the default is the one-paragraph layout the dialogs use. Both
 * were already in the app; this keeps each panel looking as it did for every
 * error that is not a refused field.
 */
export function ApiErrorMessage({ err, stacked = false }: { err: CadraApiError; stacked?: boolean }) {
  const refused = refusedFields(err);
  if (refused.length === 0) {
    return stacked ? (
      <div>
        <p className={`text-[13px] font-semibold ${tone}`}>{err.code}</p>
        <p className={`text-[12px] ${tone} mt-0.5`}>{err.message}</p>
      </div>
    ) : (
      <p className={`text-[12px] ${tone}`}>
        <span className="font-semibold">{err.code}:</span> {err.message}
      </p>
    );
  }
  const hint = refusalHint(err);
  return (
    <div className={`text-[12px] ${tone}`} data-testid="refused-fields" role="alert">
      <p className={stacked ? "text-[13px] font-semibold" : "font-semibold"}>
        {refused.length === 1
          ? "This field was not accepted, so nothing was saved:"
          : "These fields were not accepted, so nothing was saved:"}
      </p>
      <ul className="mt-1 list-disc pl-4 space-y-0.5" data-testid="refused-fields-list">
        {refused.map(k => (
          <li key={k} data-field={k}>
            {fieldWords(k)} <span className="font-mono text-[10px] opacity-70">({k})</span>
          </li>
        ))}
      </ul>
      {hint && <p className="mt-1.5" data-testid="refused-fields-hint">{hint}</p>}
      {/* Not "it is still in the form": true of the forms and the dialogs,
          false of the depreciation switches, which are put back on an error. */}
      <p className="mt-1.5 opacity-80">The rest of what you entered was not saved either.</p>
    </div>
  );
}
