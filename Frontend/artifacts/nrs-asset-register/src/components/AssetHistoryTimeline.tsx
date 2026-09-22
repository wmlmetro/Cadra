import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity, AlertCircle, AlertTriangle, ArrowDown, ArrowRightLeft, ArrowUp,
  CalendarClock, CheckCircle2, ChevronDown, ChevronRight, CircleDot, Clock, Edit3,
  FilePlus, FileSearch, FileText, Gauge, Info, MapPin, Printer, ScrollText, Send, ShieldCheck,
  Tag, Trash2, Wrench,
  type LucideIcon,
} from "lucide-react";
import { fetchAssetHistory } from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import type { AssetHistoryChange, AssetHistoryEvent } from "@/types";
import { cn } from "@/lib/utils";

// Every rule in this file is the same rule: the screen must not imply more
// than the record supports. This tab reached a client as empty space, and
// empty space reads as "nothing happened" — which no register can know.

// Decoration only. The event types are the server's and the set is open, so
// the row is built from `title` and `summary`, which the server supplies; an
// icon this map has never heard of falls back rather than throws.
const EVENT_ICON: Record<string, LucideIcon> = {
  registered: FilePlus,
  tag_issued: Tag,
  tag_printed: Printer,
  tag_affixed: Tag,
  tag_scrapped: Trash2,
  custody_changed: ArrowRightLeft,
  location_moved: MapPin,
  transfer_recorded: FileText,
  status_changed: Activity,
  condition_changed: Gauge,
  verified: ShieldCheck,
  // NOT the shield. A verification date written any other way than the Verify
  // button names nobody who checked the asset, and the row must not borrow the
  // look of one that does.
  verification_date_set: CalendarClock,
  disposal_approved: CheckCircle2,
  disposal_recorded: Trash2,
  details_changed: Edit3,
  provenance_changed: FileSearch,
  // A change to a warranty's terms (handoff 34). Not the shield: a warranty
  // says nothing about whether anybody has checked the asset.
  warranty_changed: ScrollText,
  integration_event: Send,
  maintenance_request: Wrench,
};
const EVENT_ICON_UNKNOWN: LucideIcon = CircleDot;

// Short words for the five evidence grades. The grade's full meaning is the
// server's sentence (`fidelity.evidence_grades`), printed in the legend above
// the list; a grade this build does not know renders as its own key.
//
// The meaning used to ride on the pill's `title` and nowhere else, which is a
// mouse hover — and this screen is shown to the client on a tablet. A label
// whose qualification cannot be reached says more than the record does, so
// the pill is a button that opens the legend, and the legend is on the page.
const EVIDENCE_LABEL: Record<string, string> = {
  append_only: "Cannot be altered",
  system_stamp: "System-stamped",
  guarded_record: "Protected field",
  editable_record: "Editable record",
  chatter: "Message log only",
};

const PILL = "inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase";
const PILL_NEUTRAL = "bg-muted text-muted-foreground";
const PILL_AMBER = "bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-400";
const PILL_GREEN = "bg-green-50 dark:bg-green-950/30 text-green-700 dark:text-green-400";

// The two grades that can be edited or deleted afterwards without trace are
// the ones a reader has to be warned about; only one grade is beyond doubt.
const EVIDENCE_TONE: Record<string, string> = {
  append_only: PILL_GREEN,
  editable_record: PILL_AMBER,
  chatter: PILL_AMBER,
};

const RECONSTRUCTED_TITLE =
  "Recovered later from the message log — not recorded when it happened.";

/** A bare date stays a bare date: a day-precision event has no time, and
 *  printing 00:00 would be inventing one. */
function formatAt(e: AssetHistoryEvent) {
  return e.atIsDayOnly ? e.at.slice(0, 10) : e.at.replace("T", " ").slice(0, 16);
}

function changeValue(v: AssetHistoryChange["old"]) {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  return String(v);
}

function evidenceLabel(grade: string) {
  return EVIDENCE_LABEL[grade] ?? grade;
}

function EventRow({ e, meanings, onExplain }: {
  e: AssetHistoryEvent;
  meanings: Record<string, string>;
  /** Open the legend and bring it into view. */
  onExplain: () => void;
}) {
  const Icon = EVENT_ICON[e.type] ?? EVENT_ICON_UNKNOWN;
  return (
    <li
      className={cn("border-l-2 border-border pl-3 py-1", e.reconstructed && "border-dashed")}
      data-testid="asset-history-event"
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <Icon size={12} className="text-muted-foreground shrink-0" />
        <span className="text-[12px] font-semibold text-foreground">{e.title}</span>
        {/* A real <button>: reachable by Tab, fired by Enter and Space, and
            by a finger. The `title` stays for whoever does have a mouse. */}
        <button
          type="button"
          onClick={onExplain}
          className={cn(
            PILL, EVIDENCE_TONE[e.evidence] ?? PILL_NEUTRAL,
            "cursor-pointer hover:opacity-80 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
          )}
          title={meanings[e.evidence]}
          aria-label={`${evidenceLabel(e.evidence)} — what this label means`}
          data-testid="history-evidence-pill"
        >
          {evidenceLabel(e.evidence)}
        </button>
        {e.reconstructed && (
          <span className={cn(PILL, PILL_AMBER)} title={RECONSTRUCTED_TITLE}>Reconstructed</span>
        )}
        {e.source === "test" && <span className={cn(PILL, PILL_NEUTRAL)}>Test data</span>}
      </div>

      {/* A tracked change is printed from its values, not from the summary
          the server joined them into — the values keep a `false` or a `0`
          that a one-line summary has no room to distinguish from blank. */}
      {e.changes ? (
        <ul className="mt-1 space-y-0.5">
          {e.changes.map((c, i) => (
            <li key={i} className="text-[12px] text-foreground">
              <span className="text-muted-foreground">{c.label}:</span>{" "}
              {changeValue(c.old)} → {changeValue(c.new)}
            </li>
          ))}
        </ul>
      ) : (
        e.summary && <p className="text-[12px] text-foreground mt-1">{e.summary}</p>
      )}
      {e.reason && <p className="text-[11px] text-muted-foreground mt-0.5">Reason: {e.reason}</p>}

      <div className="flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground mt-1">
        <span title={e.atIsDayOnly ? "Recorded to the day — no time was kept." : undefined}>
          {formatAt(e)}
        </span>
        <span>·</span>
        {/* Blank stays blank. Never "System": the record names nobody, and a
            made-up actor on an audit screen is worse than a missing one. */}
        {e.actorName
          ? <span className="font-semibold text-foreground">{e.actorName}</span>
          : <span className="italic">No person recorded</span>}
        {e.transferReference && (
          <>
            <span>·</span>
            <span className="font-mono">{e.transferReference}</span>
          </>
        )}
        {/* A maintenance request's reference goes only to a sign-in that may
            read service requests. When the server held it back the row SAYS
            so: a bare "Maintenance request raised" reads as a request that
            has no reference, which is a different fact. */}
        {e.requestReference ? (
          <>
            <span>·</span>
            <span className="font-mono" data-testid="history-request-reference">{e.requestReference}</span>
          </>
        ) : e.requestReferenceWithheld ? (
          <>
            <span>·</span>
            <span
              className="italic"
              title="Shown only to a sign-in that may read service requests."
              data-testid="history-request-reference-withheld"
            >
              Reference withheld — this sign-in cannot read service requests
            </span>
          </>
        ) : null}
      </div>
    </li>
  );
}

export default function AssetHistoryTimeline({ assetId }: { assetId: string }) {
  // Newest first: the reader's first question is where the asset is now and
  // how it got there.
  const [sort, setSort] = useState<"newest" | "oldest">("newest");
  // Unset until the reader chooses; until then it follows `isEmpty` below.
  const [showNotRecorded, setShowNotRecorded] = useState<boolean>();
  // Collapsed by default: five sentences above every history would bury the
  // history. Any evidence pill opens it.
  const [showLegend, setShowLegend] = useState(false);
  const legendRef = useRef<HTMLDivElement>(null);
  // Bumped by a pill; the scroll waits for the render that opens the legend,
  // so the sentences are on the page by the time it moves.
  const [explainTick, setExplainTick] = useState(0);
  useEffect(() => {
    if (explainTick === 0) return;
    legendRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    // Focus follows, so a keyboard reader lands on the thing they asked for
    // rather than being left on the pill with the answer somewhere above.
    legendRef.current?.querySelector("button")?.focus({ preventScroll: true });
  }, [explainTick]);
  const explain = () => {
    setShowLegend(true);
    setExplainTick(t => t + 1);
  };

  const q = useQuery({
    // `sort` is in the key so that flipping it refetches; invalidating
    // ["asset-history", assetId] prefix-matches both orders.
    queryKey: ["asset-history", assetId, sort],
    queryFn: () => fetchAssetHistory(assetId, sort),
    staleTime: 60_000,
    // Keep the list on screen while the other order loads — but only ever
    // THIS asset's list. A bare `keepPreviousData` would show the last
    // asset's history under this one's name for as long as the fetch took.
    placeholderData: (prev, prevQuery) =>
      prevQuery?.queryKey[1] === assetId ? prev : undefined,
  });
  const h = q.data;

  const isEmpty = !!h && h.summary.eventsAfterRegistration === 0;
  // When there is no history, what Cadra never writes down is the answer to
  // the reader's next question — so it opens itself.
  const notRecordedOpen = showNotRecorded ?? isEmpty;

  return (
    <section data-testid="asset-history">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">History</h3>
        {/* Shown on an error too: hiding it would leave the reader stuck in
            whichever order failed, with no way back to the one that worked. */}
        {(h || q.error) && (
          <button
            onClick={() => setSort(sort === "newest" ? "oldest" : "newest")}
            title={sort === "newest"
              ? "Newest first — where the asset is now, then how it got there"
              : "Oldest first — from registration forward"}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border border-border bg-card text-foreground hover:border-primary/30 hover:shadow-sm transition-all"
            data-testid="button-history-sort-order"
          >
            {sort === "newest" ? <ArrowDown size={13} /> : <ArrowUp size={13} />}
            {sort === "newest" ? "Newest first" : "Oldest first"}
          </button>
        )}
      </div>

      <div className="bg-card border border-card-border rounded-xl p-5">
        {q.isLoading ? (
          <div className="py-6 flex items-center justify-center gap-2 text-muted-foreground">
            <Clock size={14} className="animate-pulse" />
            <span className="text-[12px]">Loading history…</span>
          </div>
        ) : q.error ? (
          <div className="flex items-start gap-2 text-[11px] text-red-700 dark:text-red-400
                          bg-red-50 dark:bg-red-950/30 rounded-lg px-3 py-2">
            <AlertCircle size={13} className="shrink-0 mt-px" />
            <span>Could not load the history ({(q.error as CadraApiError).code ?? "network_error"}).</span>
          </div>
        ) : !h ? (
          // No live API. There is no mock history, on purpose.
          <p className="text-[12px] text-muted-foreground" data-testid="asset-history-unavailable">
            History is only available when connected to a live Cadra server.
          </p>
        ) : (
          <>
            {isEmpty ? (
              <div
                className="flex items-start gap-2 bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-800/30 rounded-lg px-3 py-2.5 mb-4"
                data-testid="asset-history-empty"
              >
                <Info size={12} className="text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
                <p className="text-xs text-amber-800 dark:text-amber-300">
                  {h.summary.statement}
                </p>
              </div>
            ) : (
              <p className="text-[11px] text-muted-foreground mb-4" data-testid="asset-history-statement">
                {h.summary.statement}
              </p>
            )}

            {/* What the pills mean, in the server's sentences and the
                server's order — strongest first. Above the list, because a
                label should be explained before it is read fifty times. */}
            {h.evidenceGrades.length > 0 && (
              <div
                ref={legendRef}
                className="mb-4 pb-3 border-b border-border scroll-mt-4"
                data-testid="asset-history-legend"
              >
                <button
                  type="button"
                  onClick={() => setShowLegend(!showLegend)}
                  aria-expanded={showLegend}
                  aria-controls="asset-history-legend-list"
                  className="inline-flex items-center gap-1 text-[11px] font-semibold
                             text-muted-foreground hover:text-foreground"
                  data-testid="toggle-history-legend"
                >
                  {showLegend ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                  What these labels mean
                </button>
                {showLegend && (
                  <dl id="asset-history-legend-list" className="mt-2 space-y-2">
                    {h.evidenceGrades.map(g => (
                      <div key={g.grade} className="flex flex-col sm:flex-row sm:items-start gap-1 sm:gap-2">
                        <dt className="shrink-0 sm:w-32">
                          <span className={cn(PILL, EVIDENCE_TONE[g.grade] ?? PILL_NEUTRAL)}>
                            {evidenceLabel(g.grade)}
                          </span>
                        </dt>
                        <dd className="text-[11px] text-muted-foreground">{g.meaning}</dd>
                      </div>
                    ))}
                  </dl>
                )}
              </div>
            )}

            {h.events.length > 0 ? (
              // Dimmed while it is still the previous order's list.
              <ol className={cn("space-y-3", q.isPlaceholderData && "opacity-60")}>
                {h.events.map(e => (
                  <EventRow key={e.id} e={e} meanings={h.evidenceMeanings} onExplain={explain} />
                ))}
              </ol>
            ) : (
              <p className="text-[12px] text-muted-foreground">
                The server returned no events for this asset — not even its registration.
              </p>
            )}

            {/* Where the record begins. After the list in both orders, so the
                list never simply trails off as though it were the whole story. */}
            {/* The API publishes naive server time, which is UTC. Said once,
                here, rather than on every row. */}
            <p className="mt-3 text-[10px] text-muted-foreground">All times are UTC.</p>

            <div className="mt-4 pt-3 border-t border-border" data-testid="asset-history-begins">
              <p className="text-[11px] font-semibold text-muted-foreground mb-1">Where this history begins</p>
              {h.custody.custodianHeldBeforeFirstLink ? (
                <div className="flex items-start gap-2 bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-800/30 rounded-lg px-3 py-2.5">
                  <AlertTriangle size={12} className="text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
                  <p className="text-xs text-amber-800 dark:text-amber-300">
                    {h.custody.statement}
                  </p>
                </div>
              ) : (
                <p className="text-[11px] text-muted-foreground">
                  {h.custody.statement}
                </p>
              )}
              {/* The same question asked of where it has been. Same rule: a
                  notice when the asset was already somewhere the record never
                  saw it arrive, muted text otherwise — and nothing at all
                  from a server that does not keep the movement record. */}
              {h.location && (
                h.location.locatedBeforeFirstMovement ? (
                  <div
                    className="mt-2 flex items-start gap-2 bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-800/30 rounded-lg px-3 py-2.5"
                    data-testid="asset-history-location-notice"
                  >
                    <AlertTriangle size={12} className="text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
                    <p className="text-xs text-amber-800 dark:text-amber-300">
                      {h.location.statement}
                    </p>
                  </div>
                ) : (
                  <p className="mt-2 text-[11px] text-muted-foreground" data-testid="asset-history-location-statement">
                    {h.location.statement}
                  </p>
                )
              )}
              {/* And of each kind of event that has had a record nobody can
                  alter since handoff 30 — a verification, a change of status,
                  a change to the GRN / PO / SAP number. One sentence per kind,
                  the server's: the kinds share a table and did not
                  necessarily begin on the same day on a given database.
                  Nothing from a server that does not send the block. */}
              {h.eventRecording.length > 0 && (
                <ul className="mt-2 space-y-1" data-testid="asset-history-event-recording">
                  {h.eventRecording.map(f => (
                    <li key={f.event} className="text-[11px] text-muted-foreground" data-event={f.event}>
                      {f.statement}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="mt-3 pt-3 border-t border-border" data-testid="asset-history-not-recorded">
              <button
                onClick={() => setShowNotRecorded(!notRecordedOpen)}
                className="inline-flex items-center gap-1 text-[11px] font-semibold
                           text-muted-foreground hover:text-foreground"
                data-testid="toggle-history-not-recorded"
              >
                {notRecordedOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                What Cadra does not record ({h.notRecorded.length})
              </button>
              {notRecordedOpen && (
                <div className="mt-2 space-y-2">
                  <ul className="space-y-1.5 list-disc pl-4">
                    {h.notRecorded.map(n => (
                      <li key={n.event} className="text-[11px] text-muted-foreground">
                        {n.statement}
                      </li>
                    ))}
                  </ul>
                  {h.verification && (
                    <p className="text-[11px] text-muted-foreground">
                      <span className="font-semibold">About verification.</span>{" "}
                      {h.verification}
                    </p>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
