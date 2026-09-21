/**
 * What the API said it did NOT do, put where the user can read it.
 *
 * `lib/api.ts` calls this for every write (`sendMutation`). It is a separate
 * file only because the message has markup in it and `api.ts` is not a `.tsx`.
 *
 * The rule it serves is architecture rule 3 — *never let an integration
 * guess* — turned on ourselves: this app IS an integration, and until handoff
 * 30 it was the one guessing. A field the server refused came back as a 200, a
 * key in `data._warnings.rejected_fields`, and nothing on any screen.
 */
import { ToastAction } from "@/components/ui/toast";
import { toast } from "@/hooks/use-toast";
import type { CadraWarnings } from "./api";

/** The test id the e2e suite waits for. One warning, one of these. */
export const API_WARNING_TESTID = "rejected-fields-warning";

export interface ApiWarningSummary {
  /** Keys the route's allow-list refused. The rest of the write went ahead. */
  rejected: string[];
  /** Keys a replayed callback carried and the server threw away. */
  discarded: string[];
  /** The server's own sentence about where those keys DO belong, if it has one. */
  hints: string[];
  /** Anything else under `_warnings`, as `key: value`. Never dropped: a block
   *  this build has not heard of is still something the server wanted said. */
  other: string[];
}

const strings = (v: unknown): string[] =>
  Array.isArray(v) ? v.filter((x): x is string => typeof x === "string" && x !== "") : [];

function readBlock(w: unknown, into: ApiWarningSummary) {
  if (!w || typeof w !== "object" || Array.isArray(w)) return;
  const block = w as CadraWarnings;
  for (const [key, value] of Object.entries(block)) {
    if (key === "rejected_fields") into.rejected.push(...strings(value));
    else if (key === "discarded_fields") into.discarded.push(...strings(value));
    else if (key === "hint") { if (typeof value === "string" && value) into.hints.push(value); }
    else if (key === "truncated") {
      // Its own sentence is the readable part; `cap` and `total` are in it.
      const reason = (value as { reason?: unknown } | null)?.reason;
      into.other.push(typeof reason === "string" && reason ? reason : `truncated: ${JSON.stringify(value)}`);
    }
    else if (value !== null && value !== undefined && value !== "") {
      into.other.push(`${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`);
    }
  }
}

/**
 * Both places the server writes the block — inside `data` (the handler's) and
 * at the top of the envelope (`ok()`'s) — folded into one summary. Returns
 * null when there is nothing to say, which is nearly always.
 */
export function collectApiWarnings(envelope: unknown): ApiWarningSummary | null {
  const out: ApiWarningSummary = { rejected: [], discarded: [], hints: [], other: [] };
  if (envelope && typeof envelope === "object") {
    const env = envelope as { data?: unknown; _warnings?: unknown };
    readBlock(env._warnings, out);
    if (env.data && typeof env.data === "object" && !Array.isArray(env.data)) {
      readBlock((env.data as { _warnings?: unknown })._warnings, out);
    }
  }
  const uniq = (xs: string[]) => Array.from(new Set(xs));
  out.rejected = uniq(out.rejected);
  out.discarded = uniq(out.discarded);
  out.hints = uniq(out.hints);
  out.other = uniq(out.other);
  return out.rejected.length || out.discarded.length || out.hints.length || out.other.length ? out : null;
}

/**
 * `building_id` → "Building". The key is the API's and means nothing to the
 * person who pressed Save; it is still printed beside the words, because it is
 * what they will be asked for when they report it. No lookup table: the set of
 * keys a route might refuse is the server's and open, and a table here would
 * be a copy of every allow-list in the API that nothing keeps in step.
 */
export function fieldWords(key: string): string {
  const words = key.replace(/_ids?$/, "").replace(/_+/g, " ").trim();
  if (!words) return key;
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function FieldList({ keys, testid }: { keys: string[]; testid: string }) {
  return (
    <ul className="mt-1 list-disc pl-4 space-y-0.5" data-testid={testid}>
      {keys.map(k => (
        <li key={k} data-field={k}>
          {fieldWords(k)} <span className="font-mono text-[10px] opacity-70">({k})</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Shown until somebody dismisses it (`duration: Infinity`). Radix closes a
 * toast after five seconds by default, and five seconds is how long it takes
 * to notice one, not to read a list of fields — and every form in this app
 * navigates away on success, so the message has to outlive the page that
 * caused it. It does: the `<Toaster />` is mounted once, in `App.tsx`, above
 * the router.
 *
 * Dismissed by a BUTTON with words on it. The toast's own close control is an
 * icon that stays invisible until it is hovered, and this app is shown to the
 * client on a tablet, where nothing is ever hovered.
 *
 * A screen reader gets it without looking for it: Radix announces a
 * foreground toast through an assertive live region, and the list sits in the
 * labelled "Notifications" region (F8 moves focus there).
 */
export function showApiWarnings(
  w: ApiWarningSummary | null,
  ctx: { method: string; path: string },
) {
  if (!w) return;
  toast({
    duration: Infinity,
    "data-testid": API_WARNING_TESTID,
    "data-request": `${ctx.method} ${ctx.path}`,
    className:
      "items-start border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800/60 dark:bg-amber-950 dark:text-amber-100",
    title: w.rejected.length || w.discarded.length
      ? "Saved — but not all of it"
      : "Saved — the server added a note",
    description: (
      <div className="space-y-2 text-xs">
        {w.rejected.length > 0 && (
          <div>
            <p>
              {w.rejected.length === 1
                ? "This field was not accepted and was not changed:"
                : "These fields were not accepted and were not changed:"}
            </p>
            <FieldList keys={w.rejected} testid="rejected-fields-list" />
          </div>
        )}
        {w.discarded.length > 0 && (
          <div>
            <p>Sent again after the decision was already recorded, and discarded:</p>
            <FieldList keys={w.discarded} testid="discarded-fields-list" />
          </div>
        )}
        {w.hints.map(h => <p key={h} data-testid="api-warning-hint">{h}</p>)}
        {w.other.map(o => <p key={o}>{o}</p>)}
        {(w.rejected.length > 0 || w.discarded.length > 0) && (
          <p className="opacity-80">Everything else you entered was saved.</p>
        )}
      </div>
    ),
    action: (
      <ToastAction altText="Dismiss this warning" data-testid="button-dismiss-api-warning">
        Dismiss
      </ToastAction>
    ),
  });
}
