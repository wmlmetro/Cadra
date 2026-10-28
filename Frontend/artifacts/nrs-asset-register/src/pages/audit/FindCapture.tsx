/**
 * Find a capture (handoff 69 §4 B2) — on Audit review and Audit campaigns.
 *
 * The owner had a capture the phone said was sent and a review page that
 * did not show it. This box answers "where is it?" whatever hid it: paste a
 * capture_id, a printed code or an old FIRS tag, and the server's exact
 * match (`GET /audit/captures?q=`, no campaign or state filter) comes back
 * with its campaign — open or closed — its room, state, who captured it on
 * which device, when the server received it, and who may review it. A
 * person who is not one of the campaign's reviewers is told so in words,
 * with the names of those who are; nothing found says where else to look.
 */
import { useState } from "react";
import { Link } from "wouter";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import type { CadraApiError } from "@/lib/api";
import {
  AUDIT_KEY, OUTCOME_WORDS, STATE_WORDS, findCaptures, myUid,
  type AuditCapture, type CapturesPage,
} from "@/lib/auditCapture";
import { cn } from "@/lib/utils";
import { Btn, ErrorPanel, INPUT, Pill, when } from "./shared";

/** Where a reviewer is sent to review a found capture. */
export interface ReviewTarget { campaignId: number; locationId: number; state: AuditCapture["state"]; captureId: string }

/** The Audit review address that opens on one capture — read back by
 *  `AuditReview` from its search string. */
export function reviewHref(t: ReviewTarget): string {
  const s = new URLSearchParams({
    campaign: String(t.campaignId), room: String(t.locationId), show: t.state, capture: t.captureId,
  });
  return `/audit/review?${s.toString()}`;
}

export function FindCapture({ canReview, canSeeRefusals, onReview }: {
  /** The person holds `audit:review` — only then is "review it" offered. */
  canReview: boolean;
  /** The person holds `audit:manage` — the not-found sentence links to
   *  Devices and codes › Refused syncs. */
  canSeeRefusals: boolean;
  /** On Audit review: open the capture on this page. Elsewhere a link to
   *  Audit review is drawn instead. */
  onReview?: (t: ReviewTarget) => void;
}) {
  const [text, setText] = useState("");
  const [asked, setAsked] = useState("");
  const q = useQuery<CapturesPage, CadraApiError>({
    queryKey: [...AUDIT_KEY, "find", asked],
    queryFn: () => findCaptures(asked),
    enabled: asked.length > 0,
    // Asked again, asked of the server again: "not found" may have become
    // found when the phone synced a minute later.
    staleTime: 0,
  });
  const rows = q.data?.rows ?? [];

  return (
    <div className="space-y-2" data-testid="find-capture">
      <form className="flex flex-wrap gap-2 items-center"
            onSubmit={(e) => {
              e.preventDefault();
              const next = text.trim();
              if (next === asked) void q.refetch(); else setAsked(next);
            }}>
        <label className="text-[11px] text-muted-foreground" htmlFor="find-capture-input">Find a capture</label>
        <input id="find-capture-input" value={text} onChange={e => setText(e.target.value)}
               placeholder="A capture ID, a printed code, or an old FIRS tag"
               className={cn(INPUT, "w-80 font-mono")} data-testid="input-find-capture" />
        <Btn type="submit" kind="plain" testid="button-find-capture" disabled={!text.trim()} pending={q.isFetching && asked.length > 0}>
          <Search size={12} /> Find
        </Btn>
        {asked && (
          <button type="button" className="text-[11px] text-muted-foreground hover:underline" data-testid="button-find-clear"
                  onClick={() => { setText(""); setAsked(""); }}>Clear</button>
        )}
      </form>
      {q.error && <ErrorPanel err={q.error} testid="find-capture-error" />}
      {asked && q.data && rows.length === 0 && (
        <p className="text-[12px]" data-testid="find-capture-none">
          No capture on this register has that ID or code. If the phone says it was submitted, it may have been
          refused or sent elsewhere:{" "}
          {canSeeRefusals
            ? <Link href="/audit/devices?section=refused-syncs" className="text-primary font-semibold hover:underline"
                    data-testid="link-refused-syncs">Devices and codes › Refused syncs</Link>
            : <span className="font-semibold">Devices and codes › Refused syncs</span>}.
        </p>
      )}
      {rows.length > 0 && (
        <ul className="space-y-2" data-testid="find-capture-results">
          {rows.map(c => <Found key={c.capture_id} c={c} canReview={canReview} onReview={onReview} />)}
        </ul>
      )}
      {q.data?.nextCursor && (
        <p className="text-[11px] text-muted-foreground">
          Showing {rows.length} of {q.data.totalEstimate ?? "more"} matches.
        </p>
      )}
    </div>
  );
}

/** One match: where it is, how it got there, and who may review it. */
function Found({ c, canReview, onReview }: {
  c: AuditCapture; canReview: boolean; onReview?: (t: ReviewTarget) => void;
}) {
  const me = myUid();
  const reviewers = c.campaign.reviewers;
  const isReviewer = me != null && !!reviewers?.some(u => u.id === me);
  const open = c.campaign.state !== "closed";
  const target: ReviewTarget = { campaignId: c.campaign.id, locationId: c.location.id, state: c.state, captureId: c.capture_id };
  const names = (reviewers ?? []).map(u => u.name).join(", ");

  return (
    <li className="rounded-xl border border-border bg-card p-3 space-y-1 text-[12px]"
        data-testid={`found-capture-${c.capture_id}`} data-campaign-id={c.campaign.id} data-state={c.state}
        data-reviewer={isReviewer ? "true" : "false"}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold" data-testid="found-campaign">{c.campaign.name}</span>
        {c.campaign.state && (
          <Pill tone={open ? "green" : "plain"} testid="found-campaign-state">{open ? "Open" : "Closed"}</Pill>
        )}
        <Pill tone={c.state === "accepted" ? "green" : c.state === "returned" ? "red" : "plain"} testid="found-state">{STATE_WORDS[c.state]}</Pill>
        <span className="text-muted-foreground">{OUTCOME_WORDS[c.outcome]}</span>
      </div>
      <p data-testid="found-where">
        Room <span className="font-semibold">{c.location.name}</span>
        {c.location.location_code && <span className="font-mono text-muted-foreground"> {c.location.location_code}</span>}
        {c.code && <> · code <span className="font-mono">{c.code}</span></>}
        {" "}· capture <span className="font-mono">{c.capture_id}</span>
      </p>
      <p className="text-muted-foreground" data-testid="found-provenance">
        Captured by {c.captured_by?.name ?? "—"} on <span data-testid="found-device">{c.device?.name ?? "—"}</span>, {when(c.captured_at)};
        {" "}received <span data-testid="found-received">{when(c.received_at)}</span>
        {c.reviewed_by && <>; reviewed by {c.reviewed_by.name}, {when(c.reviewed_at)}</>}
      </p>
      {reviewers && (
        <p data-testid="found-reviewers">Reviewers: {names || "none named"}.</p>
      )}
      {reviewers && !isReviewer && (
        <p className="text-amber-800 dark:text-amber-300" data-testid="found-not-a-reviewer">
          You are not a reviewer on {c.campaign.name}.{" "}
          {names ? <>Its reviewers are {names}</> : <>Its reviewers: none named</>}; the Asset Controller adds reviewers on Audit campaigns.
        </p>
      )}
      {isReviewer && !open && (
        <p className="text-muted-foreground" data-testid="found-closed">The campaign is closed; nothing more is reviewed in it.</p>
      )}
      {isReviewer && open && canReview && (
        onReview
          ? <Btn kind="plain" testid={`button-review-found-${c.capture_id}`} onClick={() => onReview(target)}>Review it here</Btn>
          : <Link href={reviewHref(target)} className="inline-block text-primary font-semibold hover:underline"
                  data-testid={`link-review-found-${c.capture_id}`}>Review it on Audit review</Link>
      )}
    </li>
  );
}
