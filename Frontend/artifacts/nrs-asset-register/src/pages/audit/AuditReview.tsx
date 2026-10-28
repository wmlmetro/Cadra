/**
 * Audit review (handoff 66 §5, §6) — the second person.
 *
 * The reviewer (`audit:review`) picks a campaign and a room and reads each
 * capture somebody else made: its photos side by side, the outcome and what
 * it names (the Cadra asset, the SAP record, or neither), the code used and
 * the label scanned, and the fields the capturer confirmed beside what the
 * AI suggested when the capture used a suggestion — a field the person
 * changed is marked. A capture held as a duplicate (the same Cadra asset,
 * SAP record or old tag captured twice in one campaign) is highlighted and
 * drawn beside its twin, photos and all.
 *
 * Accept or return each (a return needs a reason, in words), or *Accept the
 * room*: a preview first — the server's dry run, N single acceptances
 * rolled back — then the batch, a line per capture with the server's own
 * sentence for any refused. Held duplicates are left out of a room's batch
 * by the server and reviewed one by one. The server refuses a capturer
 * reviewing their own capture; the refusal is shown verbatim.
 *
 * Handoff 69 (where the captures went): nothing past the first page is
 * invisible any more — the list follows the server's cursor, 100 at a time,
 * and says how many of how many it shows; the dropdown opens on a campaign
 * with captures waiting; captures waiting where this person is no reviewer
 * are counted under it; a find box finds any capture by ID or code; and
 * each card names the device it came from and when the server received it.
 *
 * Handoff 70: an administrator under the tenant's override reviews alone —
 * the dropdown lists EVERY open campaign, and on a capture whose review
 * needs the override (their own, or a campaign not naming them a reviewer)
 * the buttons say "(as administrator)". A capture captured or reviewed that
 * way says so on its card. With the switch off nothing here changes.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearch } from "wouter";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ClipboardCheck, Copy, Loader2, XCircle } from "lucide-react";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { ScopeRefusal } from "@/components/ScopeRefusal";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import type { CadraApiError } from "@/lib/api";
import { useScopes, SCOPE } from "@/hooks/use-scopes";
import { useAdminOverride } from "@/hooks/use-admin-override";
import {
  AUDIT_KEY, CONFIRMED_FIELD_WORDS, DUPLICATE_WORDS, LABEL_WORDS, OUTCOME_WORDS, OVERRIDE_RULE_WORDS, STATE_WORDS,
  acceptCapture, acceptRoom, fetchCampaign, fetchCampaigns, fetchCapture, fetchCaptures, myUid, returnCapture,
  type AcceptBatchAnswer, type AuditCampaign, type AuditCapture, type CapturesPage, type CaptureState, type ConfirmedFields,
} from "@/lib/auditCapture";
import { cn, formatIsoDate } from "@/lib/utils";
import {
  Btn, Empty, ErrorPanel, INPUT, LABEL, Loading, PageHeader, Photo, Pill, TEXTAREA, invalidateAudit, n, when,
} from "./shared";
import { FindCapture, type ReviewTarget } from "./FindCapture";

/** One page of the review list — the server's own limit. */
const PAGE = 100;

/** What the "Showing N of M …" line calls the rows, by the Show filter. */
const SHOW_WORD: Record<CaptureState | "all", string> = {
  pending_review: "waiting", accepted: "accepted", returned: "returned", all: "captures",
};

const SHOWS: (CaptureState | "all")[] = ["pending_review", "accepted", "returned", "all"];

export default function AuditReview() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const scopes = useScopes();
  const canReview = scopes.has(SCOPE.auditReview);
  // Handoff 70: an administrator under the override may review in any open
  // campaign, so every one is listed for them.
  const { active: overrideOn } = useAdminOverride();
  // Handoff 69: a found capture opens here through the address — Audit
  // campaigns' find box links to `?campaign=&room=&show=&capture=`.
  const search = useSearch();
  const initial = useMemo(() => {
    const p = new URLSearchParams(search);
    const num = (k: string) => (p.get(k) && /^\d+$/.test(p.get(k) as string) ? Number(p.get(k)) : null);
    const show = p.get("show") as CaptureState | "all" | null;
    return { campaign: num("campaign"), room: num("room"), show: show && SHOWS.includes(show) ? show : null, capture: p.get("capture") };
    // Read once, on arrival.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [campaignId, setCampaignId] = useState<number | null>(initial.campaign);
  const [roomId, setRoomId] = useState<number | null>(initial.room);
  const [show, setShow] = useState<CaptureState | "all">(initial.show ?? "pending_review");
  const [focus, setFocus] = useState<string | null>(initial.capture);
  const [batch, setBatch] = useState(false);
  /** A campaign the person chose (or arrived on) is never replaced by the
   *  default. */
  const chosen = useRef(initial.campaign != null);

  useEffect(() => {
    setTitle("Audit review");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  // Every open campaign; the dropdown lists those naming this person as a
  // reviewer (the server names the team), and the rest are counted so a
  // capture waiting where nobody here may review it is said (handoff 69 B3).
  // An administrator under the override is listed every one (handoff 70).
  const openCampaigns = useQuery<AuditCampaign[], CadraApiError>({
    queryKey: [...AUDIT_KEY, "campaigns", "open"],
    queryFn: () => fetchCampaigns("open"),
    enabled: canReview,
  });
  const { mine, waitingElsewhere, waitingMine } = useMemo(() => {
    const me = myUid();
    const all = openCampaigns.data ?? [];
    const mineList = me == null || overrideOn ? all : all.filter(c => c.reviewers.some(u => u.id === me));
    const ids = new Set(mineList.map(c => c.id));
    const sum = (cs: AuditCampaign[]) => cs.reduce((t, c) => t + (c.progress?.waiting_for_review ?? 0), 0);
    return { mine: mineList, waitingMine: sum(mineList), waitingElsewhere: sum(all.filter(c => !ids.has(c.id))) };
  }, [openCampaigns.data, overrideOn]);
  // The default (handoff 69, the staging defect): the first campaign naming
  // this person that has captures WAITING — the newest open one may have
  // none while an older one has five — falling back to the first.
  useEffect(() => {
    if (chosen.current || mine.length === 0) return;
    if (campaignId != null && mine.some(c => c.id === campaignId)) return;
    const pick = mine.find(c => (c.progress?.waiting_for_review ?? 0) > 0) ?? mine[0];
    setCampaignId(pick.id);
    setRoomId(null);
  }, [mine, campaignId]);
  const chooseCampaign = (id: number | null) => {
    chosen.current = true;
    setCampaignId(id);
    setRoomId(null);
    setFocus(null);
  };
  const openFound = (t: ReviewTarget) => {
    chosen.current = true;
    setCampaignId(t.campaignId);
    setRoomId(t.locationId);
    setShow(t.state);
    setFocus(t.captureId);
  };
  const campaign = useQuery<AuditCampaign, CadraApiError>({
    queryKey: [...AUDIT_KEY, "campaign", campaignId],
    queryFn: () => fetchCampaign(campaignId as number),
    enabled: canReview && campaignId != null,
  });
  const rooms = campaign.data?.rooms ?? [];

  // Every page, not only the first (handoff 69 B1, H3): the server's order
  // (id ascending — oldest waiting first) and its cursor, 100 at a time.
  const captures = useInfiniteQuery<CapturesPage, CadraApiError>({
    queryKey: [...AUDIT_KEY, "captures", "review", campaignId, roomId, show],
    queryFn: ({ pageParam }) => fetchCaptures({
      campaign_id: campaignId as number, location_id: roomId ?? undefined,
      state: show === "all" ? undefined : show, limit: PAGE, cursor: pageParam as string | undefined,
    }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    enabled: canReview && campaignId != null,
  });
  // Handoff 69b: a found capture past the first page — load the pages up
  // to it, one at a time; its card scrolls itself into view on mount.
  const { data: pages, isFetching, hasNextPage, fetchNextPage } = captures;
  useEffect(() => {
    if (!focus || !pages || isFetching || !hasNextPage) return;
    if (!pages.pages.some(p => p.rows.some(r => r.capture_id === focus))) void fetchNextPage();
  }, [focus, pages, isFetching, hasNextPage, fetchNextPage]);

  if (!canReview) {
    return <ScopeRefusal scope={SCOPE.auditReview} detail="Audit Reviewers hold it — never the person who captured." />;
  }
  const rows = (captures.data?.pages ?? []).flatMap(p => p.rows);
  const total = captures.data?.pages[0]?.totalEstimate ?? null;
  const waitingHere = rows.filter(c => c.state === "pending_review" && !c.duplicate_of).length;
  // Handoff 70: whether THIS person's review of a capture needs the
  // override — their own capture, or a campaign that does not name them a
  // reviewer. The server decides; this only words the buttons.
  const me = myUid();
  const reviewersOf = (cid: number) =>
    (campaign.data?.id === cid ? campaign.data.reviewers : undefined)
    ?? openCampaigns.data?.find(x => x.id === cid)?.reviewers ?? [];
  const reviewAsAdmin = (c: AuditCapture) => overrideOn && me != null
    && (c.captured_by?.id === me || !(c.campaign.reviewers ?? reviewersOf(c.campaign.id)).some(u => u.id === me));
  const roomAsAdmin = overrideOn && roomId != null
    && rows.some(c => c.state === "pending_review" && !c.duplicate_of && c.location.id === roomId && reviewAsAdmin(c));

  return (
    <div className="flex flex-col h-full">
      <PageHeader icon={<ClipboardCheck size={15} />} title="Audit review">
        You are the second person. Read each capture — the photos, what it names, what the capturer confirmed — and
        accept it or return it to the capturer with a reason. You cannot review a capture you made.
        {overrideOn && (
          <span className="block mt-1 text-amber-800 dark:text-amber-300" data-testid="review-override-on">
            The administrator override is on: as an administrator you may review in every open campaign, your own
            captures included. Each such review is listed under Audit › Administrator overrides.
          </span>
        )}
      </PageHeader>
      <div className="px-5 py-3 border-b border-border">
        <FindCapture canReview={canReview} canSeeRefusals={scopes.has(SCOPE.auditManage)} onReview={openFound} />
      </div>
      <div className="px-5 py-3 border-b border-border flex flex-wrap gap-2 items-center">
        <label className="text-[11px] text-muted-foreground" htmlFor="review-campaign">Campaign</label>
        <select id="review-campaign" className={INPUT} data-testid="review-campaign"
                value={campaignId ?? ""} onChange={e => chooseCampaign(e.target.value ? Number(e.target.value) : null)}>
          {mine.length === 0 && <option value="">{overrideOn ? "No campaign is open" : "No open campaign names you as a reviewer"}</option>}
          {mine.map(c => (
            <option key={c.id} value={c.id}>{c.name} ({n(c.progress?.waiting_for_review ?? 0)} waiting)</option>
          ))}
        </select>
        <label className="text-[11px] text-muted-foreground ml-2" htmlFor="review-room">Room</label>
        <select id="review-room" className={INPUT} data-testid="review-room"
                value={roomId ?? ""} onChange={e => { setRoomId(e.target.value ? Number(e.target.value) : null); setFocus(null); }}>
          <option value="">Every room</option>
          {rooms.map(r => (
            <option key={r.location.id} value={r.location.id}>
              {r.location.name} ({r.waiting_for_review} waiting of {r.captured})
            </option>
          ))}
        </select>
        <label className="text-[11px] text-muted-foreground ml-2" htmlFor="review-show">Show</label>
        <select id="review-show" className={INPUT} data-testid="review-show"
                value={show} onChange={e => setShow(e.target.value as CaptureState | "all")}>
          <option value="pending_review">Waiting for review</option>
          <option value="accepted">Accepted</option>
          <option value="returned">Returned</option>
          <option value="all">All</option>
        </select>
        <div className="ml-auto flex items-center gap-2">
          {roomId == null && <span className="text-[11px] text-muted-foreground">Choose a room to accept it as a batch.</span>}
          <Btn testid="button-accept-room" disabled={campaignId == null || roomId == null} onClick={() => setBatch(true)}>
            {roomAsAdmin ? "Accept the room (as administrator)" : "Accept the room"}
          </Btn>
        </div>
      </div>
      {openCampaigns.data && waitingMine === 0 && waitingElsewhere > 0 && (
        <p className="px-5 pt-2 text-[12px] text-amber-800 dark:text-amber-300" data-testid="review-waiting-elsewhere">
          {n(waitingElsewhere)} {waitingElsewhere === 1 ? "capture waits" : "captures wait"} in campaigns that don't name you as a reviewer.
        </p>
      )}
      {campaign.data && (
        <p className="px-5 pt-2 text-[11px] text-muted-foreground" data-testid="review-progress">
          {campaign.data.name}: {n(campaign.data.progress.waiting_for_review)} waiting for review of {n(campaign.data.progress.captured)} captured
          {campaign.data.progress.duplicates_held > 0 && <>, {n(campaign.data.progress.duplicates_held)} held as duplicates</>}.
          {roomId != null && <> In this room, {waitingHere} can be accepted as a batch.</>}
        </p>
      )}
      <div className="flex-1 overflow-y-auto px-5 py-3 space-y-3">
        {openCampaigns.error && <ErrorPanel err={openCampaigns.error} />}
        {captures.error && <ErrorPanel err={captures.error} />}
        {captures.isLoading ? <Loading what="Reading the captures…" /> : rows.length === 0 && !captures.error ? (
          <Empty testid="review-empty">
            {campaignId == null ? (overrideOn ? "No campaign is open." : "No open campaign names you as a reviewer.") : show === "pending_review" ? "Nothing here is waiting for review." : "No capture matches."}
          </Empty>
        ) : (
          <>
            {total != null && (
              <p className="text-[11px] text-muted-foreground" data-testid="review-count"
                 data-shown={rows.length} data-total={total}>
                Showing {n(rows.length)} of {n(total)} {SHOW_WORD[show]}{roomId != null ? " in this room" : ""}.
              </p>
            )}
            {rows.map(c => <CaptureCard key={c.capture_id} c={c} siblings={rows} focused={focus === c.capture_id}
                                        asAdmin={reviewAsAdmin(c)} />)}
          </>
        )}
        {captures.hasNextPage && (
          <div className="flex items-center gap-2">
            <Btn kind="plain" testid="button-review-next" pending={captures.isFetchingNextPage}
                 onClick={() => captures.fetchNextPage()}>Show the next {PAGE}</Btn>
            {total != null && <span className="text-[11px] text-muted-foreground">{n(Math.max(total - rows.length, 0))} more after these.</span>}
          </div>
        )}
      </div>
      {batch && campaignId != null && roomId != null && (
        <AcceptRoomDialog campaignId={campaignId} roomId={roomId}
          roomName={rooms.find(r => r.location.id === roomId)?.location.name ?? `room ${roomId}`}
          onClose={() => setBatch(false)} />
      )}
    </div>
  );
}

// ─── one capture ─────────────────────────────────────────────────────────────

type Compared = { field: string; label: string; suggested: string | null; confirmed: string | null };

/** The AI's proposal against what the person confirmed, field by field. */
function compare(c: AuditCapture): Compared[] {
  const s = (c.ai_suggestion?.suggested ?? null) as null | {
    category?: { id?: number; name?: string | null };
    attributes?: Record<string, string | null>;
    condition?: { value?: string | null };
  };
  const proposed: Record<string, string> = {};
  if (s) {
    if (s.category?.id) proposed.category_id = s.category.name ?? `class ${s.category.id}`;
    for (const [k, v] of Object.entries(s.attributes ?? {})) if (v) proposed[k] = String(v);
    if (s.condition?.value) proposed.condition = s.condition.value;
  }
  const confirmed: Record<string, string> = {};
  for (const [k, v] of Object.entries(c.fields ?? {})) {
    if (v === null || v === undefined || v === "") continue;
    confirmed[k] = k === "category_id" ? (c.category?.name ?? `class ${v}`) : String(v);
  }
  const order = Object.keys(CONFIRMED_FIELD_WORDS) as (keyof ConfirmedFields)[];
  const keys = [...order.filter(k => k in proposed || k in confirmed),
                ...Object.keys({ ...proposed, ...confirmed }).filter(k => !order.includes(k as keyof ConfirmedFields))];
  return keys.map(k => ({
    field: k, label: CONFIRMED_FIELD_WORDS[k as keyof ConfirmedFields] ?? k,
    suggested: proposed[k] ?? null, confirmed: confirmed[k] ?? null,
  }));
}

function Target({ c }: { c: AuditCapture }) {
  if (c.outcome === "on_register" && c.asset) {
    return (
      <p className="text-[12px]" data-testid="capture-target">
        Cadra asset <Link href={`/assets/${c.asset.id}`} className="font-semibold text-primary hover:underline">{c.asset.asset_code}</Link>
        {c.asset.name && <> — {c.asset.name}</>}
        {c.asset.location && <span className="text-muted-foreground"> · on the register at {c.asset.location}</span>}
        {c.label && <> · <Pill tone={c.label === "present" ? "plain" : "amber"}>{LABEL_WORDS[c.label]}</Pill></>}
      </p>
    );
  }
  if (c.outcome === "in_sap" && c.sap_record) {
    const s = c.sap_record;
    return (
      <p className="text-[12px]" data-testid="capture-target">
        SAP <span className="font-mono font-semibold">{s.asset_number}{s.sub_number && s.sub_number !== "0" ? `-${s.sub_number}` : ""}</span>
        {" "}· class <span className="font-mono">{s.class ?? "—"}</span>
        {s.office_code && <> · office <span className="font-mono">{s.office_code}</span></>}
        {s.description && <> — {s.description}</>}
        {s.old_tag && <span className="text-muted-foreground"> · old tag <span className="font-mono">{s.old_tag}</span></span>}
        {s.capitalized_on && <span className="text-muted-foreground"> · capitalised {formatIsoDate(s.capitalized_on)}</span>}
      </p>
    );
  }
  return <p className="text-[12px]" data-testid="capture-target">Neither register holds it — on acceptance it becomes an exception for the Asset Controller.</p>;
}

/** The override's own line on a card (handoff 70): which act went ahead
 *  only because an administrator was under the override, and the rule it
 *  lifted. Nothing is drawn for a capture neither flag is on. */
function OverrideNote({ c }: { c: AuditCapture }) {
  const codes = c.override_of ?? [];
  const words = (wanted: string[]) => codes.filter(x => wanted.includes(x)).map(x => OVERRIDE_RULE_WORDS[x] ?? x);
  const lines: string[] = [];
  if (c.captured_as_admin) {
    const w = words(["not_a_capturer"]);
    lines.push(`Captured by an administrator under the override${w.length ? ` (${w.join("; ")})` : ""}.`);
  }
  if (c.reviewed_as_admin) {
    const w = words(["own_capture", "not_a_reviewer"]);
    const verb = c.state === "returned" ? "Returned" : "Accepted";
    lines.push(`${verb} by an administrator under the override${w.length ? ` (${w.join("; ")})` : ""}.`);
  }
  if (lines.length === 0) return null;
  return (
    <p className="text-[11px] text-amber-800 dark:text-amber-300" data-testid="capture-override-note">
      {lines.join(" ")}
    </p>
  );
}

function CaptureCard({ c, siblings, focused = false, asAdmin = false }: {
  c: AuditCapture; siblings: AuditCapture[]; focused?: boolean;
  /** This person's review of it goes ahead only under the override. */
  asAdmin?: boolean;
}) {
  const qc = useQueryClient();
  const accept = useMutation<AuditCapture, CadraApiError>({
    mutationFn: () => acceptCapture(c.capture_id),
    onSuccess: () => invalidateAudit(qc),
  });
  const [returning, setReturning] = useState(false);
  const rows = useMemo(() => compare(c), [c]);
  const held = !!c.duplicate_of;
  const twinInList = held ? siblings.find(s => s.capture_id === c.duplicate_of) : undefined;
  const twin = useQuery<AuditCapture, CadraApiError>({
    queryKey: [...AUDIT_KEY, "capture", c.duplicate_of],
    queryFn: () => fetchCapture(c.duplicate_of as string),
    enabled: held && !twinInList,
  });
  const twinCapture = twinInList ?? twin.data;
  const waiting = c.state === "pending_review";
  // A capture opened from the find box is brought into view (handoff 69).
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => { if (focused) box.current?.scrollIntoView({ block: "center" }); }, [focused]);

  return (
    <div ref={box} className={cn("rounded-2xl border p-3 space-y-2", held ? "border-amber-400 bg-amber-50/40 dark:bg-amber-950/20" : "border-border bg-card",
                    focused && "ring-2 ring-primary")}
         data-testid={`capture-card-${c.capture_id}`} data-focused={focused ? "true" : "false"} data-state={c.state} data-duplicate={held ? "true" : "false"}>
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={c.outcome === "on_register" ? "green" : c.outcome === "in_sap" ? "blue" : "amber"} testid="capture-outcome">{OUTCOME_WORDS[c.outcome]}</Pill>
        <Pill tone={c.state === "accepted" ? "green" : c.state === "returned" ? "red" : "plain"} testid="capture-state">{STATE_WORDS[c.state]}</Pill>
        {/* Where it came from (handoff 69 B4): the device tells a phone
            capture from a station one, and received-at is when the server
            had it — a gap from captured-at is time spent queued on the phone. */}
        <span className="text-[11px] text-muted-foreground" data-testid="capture-provenance">
          {c.location.name} · captured by {c.captured_by?.name ?? "—"} on{" "}
          <span className="font-semibold text-foreground" data-testid="capture-device">{c.device?.name ?? "—"}</span>, {when(c.captured_at)};
          {" "}received <span data-testid="capture-received">{when(c.received_at)}</span>
        </span>
      </div>
      {held && (
        <p className="text-[12px] text-amber-900 dark:text-amber-300 flex items-center gap-1.5" data-testid="capture-duplicate-note">
          <Copy size={12} /> Held as a duplicate: {DUPLICATE_WORDS[c.duplicate_basis ?? ""] ?? "the same item"} was captured before in this campaign
          {twinCapture ? <> (capture by {twinCapture.captured_by?.name ?? "—"}, {STATE_WORDS[twinCapture.state].toLowerCase()})</> : null}.
          Compare the two before deciding.
        </p>
      )}
      <Target c={c} />
      {(c.code || c.scanned_label) && (
        <p className="text-[12px]" data-testid="capture-code">
          Code <span className="font-mono font-semibold">{c.code ?? "—"}</span> · label scanned <span className="font-mono">{c.scanned_label ?? "—"}</span>
        </p>
      )}
      <div className={cn("flex gap-4 flex-wrap", held && "items-start")}>
        <div>
          <p className={LABEL}>{held ? "This capture" : "Photos"}</p>
          <div className="flex gap-2 mt-1 flex-wrap" data-testid="capture-photos">
            {c.photos.map(p => <Photo key={p.id} url={p.url} size="md" testid="capture-photo" />)}
          </div>
        </div>
        {held && twinCapture && (
          <div data-testid="capture-twin">
            <p className={LABEL}>The capture it repeats</p>
            <div className="flex gap-2 mt-1 flex-wrap">
              {twinCapture.photos.map(p => <Photo key={p.id} url={p.url} size="md" testid="twin-photo" />)}
            </div>
            <p className="text-[11px] text-muted-foreground mt-1">
              {twinCapture.name ?? "—"} · {twinCapture.condition ?? "—"} · {twinCapture.location.name}
            </p>
          </div>
        )}
        {held && twin.error && <ErrorPanel err={twin.error} />}
      </div>
      {rows.length > 0 && (
        <table className="text-xs w-full max-w-2xl" data-testid="capture-fields">
          <thead className="text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="text-left py-1 pr-3 w-32">Field</th>
              {c.ai_suggestion && <th className="text-left pr-3">AI suggested</th>}
              <th className="text-left">Confirmed by the capturer</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => {
              const changed = !!c.ai_suggestion && r.suggested != null && r.confirmed != null
                && r.suggested.trim().toLowerCase() !== r.confirmed.trim().toLowerCase();
              return (
                <tr key={r.field} data-testid={`capture-field-${r.field}`} data-changed={changed ? "true" : "false"}>
                  <td className="py-0.5 pr-3 text-muted-foreground">{r.label}</td>
                  {c.ai_suggestion && <td className="pr-3 text-muted-foreground">{r.suggested ?? "—"}</td>}
                  <td className={cn(changed && "font-semibold text-amber-800 dark:text-amber-300")}>
                    {r.confirmed ?? "—"}{changed && <span className="font-normal text-[10px]"> (changed from the suggestion)</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {!c.ai_suggestion && <p className="text-[11px] text-muted-foreground">No AI suggestion was used for this capture.</p>}
      {c.state === "returned" && c.return_reason && (
        <p className="text-[12px] text-red-700 dark:text-red-400">Returned by {c.reviewed_by?.name ?? "—"}: {c.return_reason}</p>
      )}
      {c.state === "accepted" && (
        <p className="text-[12px] text-green-800 dark:text-green-300" data-testid="capture-accepted">
          Accepted by {c.reviewed_by?.name ?? "—"}, {when(c.reviewed_at)}
          {c.result_asset && <> — <Link href={`/assets/${c.result_asset.id}`} className="font-semibold hover:underline">{c.result_asset.asset_code}</Link></>}
          {c.exception_state && <> — exception {c.exception_state}</>}.
        </p>
      )}
      <OverrideNote c={c} />
      {waiting && (
        <div className="flex gap-2 items-center flex-wrap">
          <Btn testid={`button-accept-${c.capture_id}`} pending={accept.isPending} onClick={() => accept.mutate()}>
            {asAdmin ? "Accept (as administrator)" : "Accept"}
          </Btn>
          <Btn testid={`button-return-${c.capture_id}`} kind="plain" onClick={() => setReturning(true)}>
            {asAdmin ? "Return to the capturer (as administrator)" : "Return to the capturer"}
          </Btn>
        </div>
      )}
      {accept.error && <ErrorPanel err={accept.error} testid="accept-error" />}
      {returning && <ReturnDialog c={c} onClose={() => setReturning(false)} />}
    </div>
  );
}

function ReturnDialog({ c, onClose }: { c: AuditCapture; onClose: () => void }) {
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  const m = useMutation<AuditCapture, CadraApiError>({
    mutationFn: () => returnCapture(c.capture_id, reason),
    onSuccess: () => { invalidateAudit(qc); onClose(); },
  });
  return (
    <Dialog open onOpenChange={(next) => { if (!next && !m.isPending) onClose(); }}>
      <DialogContent className="sm:max-w-md" data-testid="return-dialog">
        <DialogHeader>
          <DialogTitle>Return to {c.captured_by?.name ?? "the capturer"}</DialogTitle>
          <DialogDescription>Say what to capture again. {c.code ? `Code ${c.code} is kept for the re-capture.` : ""}</DialogDescription>
        </DialogHeader>
        <textarea rows={3} value={reason} onChange={e => setReason(e.target.value)} className={TEXTAREA}
                  data-testid="input-return-reason" aria-label="Reason" />
        {m.error && <ErrorPanel err={m.error} testid="return-error" />}
        <DialogFooter>
          <Btn kind="plain" onClick={onClose}>Cancel</Btn>
          <Btn testid="button-return-send" disabled={!reason.trim()} pending={m.isPending} onClick={() => m.mutate()}>Return it</Btn>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── a room's batch ──────────────────────────────────────────────────────────

function batchSummary(a: AcceptBatchAnswer): string {
  if (a.dry_run) return `${a.done} of ${a.total} would be accepted, ${a.refused} would be refused. Nothing has been written yet.`;
  return `${a.done} of ${a.total} accepted, ${a.refused} refused.`;
}

function AcceptRoomDialog({ campaignId, roomId, roomName, onClose }: {
  campaignId: number; roomId: number; roomName: string; onClose: () => void;
}) {
  const qc = useQueryClient();
  const preview = useMutation<AcceptBatchAnswer, CadraApiError>({ mutationFn: () => acceptRoom(campaignId, roomId, true) });
  const send = useMutation<AcceptBatchAnswer, CadraApiError>({
    mutationFn: () => acceptRoom(campaignId, roomId, false),
    onSuccess: () => invalidateAudit(qc),
  });
  const fired = useRef(false);
  useEffect(() => {
    if (fired.current) return;
    fired.current = true;
    preview.mutate();
  }, [preview]);
  const busy = preview.isPending || send.isPending;
  const answer = send.data ?? preview.data;
  const wouldDo = preview.data?.done ?? 0;

  return (
    <Dialog open onOpenChange={(next) => { if (!next && !busy) onClose(); }}>
      <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto" data-testid="accept-room-dialog"
                     data-phase={send.data ? "sent" : preview.data ? "preview" : "loading"}>
        <DialogHeader>
          <DialogTitle>{send.data ? "Accepted — the answer" : `Accept the room: ${roomName}`}</DialogTitle>
          <DialogDescription data-testid="accept-room-summary">
            {answer ? batchSummary(answer) : "Asking the server what would happen to each capture waiting in this room…"}
          </DialogDescription>
        </DialogHeader>
        {preview.isPending && <p className="text-[11px] text-muted-foreground flex items-center gap-2"><Loader2 size={12} className="animate-spin" /> Checking each capture…</p>}
        {answer && answer.total === 0 && <p className="text-[12px]">Nothing in this room is waiting for review (held duplicates are reviewed one by one).</p>}
        {answer && answer.total > 0 && (
          <ul className="max-h-72 overflow-y-auto rounded-xl border border-border divide-y divide-border" data-testid="accept-room-lines">
            {answer.results.map(l => {
              const ok = l.outcome !== "refused";
              return (
                <li key={l.capture_id} className="px-3 py-2 text-[11px] flex items-start gap-2"
                    data-testid={`accept-line-${l.capture_id}`} data-outcome={l.outcome}>
                  {ok ? <CheckCircle2 size={13} className="text-green-600 dark:text-green-400 shrink-0 mt-0.5" />
                      : <XCircle size={13} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />}
                  <p className="min-w-0">
                    <span className="font-mono">{l.capture_id.slice(0, 8)}</span>{" — "}
                    {ok ? (l.outcome === "would_do" ? "would be accepted" : "accepted")
                        : <span className="text-red-700 dark:text-red-400" data-testid="accept-line-message">{l.message ?? "Refused."}</span>}
                  </p>
                </li>
              );
            })}
          </ul>
        )}
        {preview.error && <ErrorPanel err={preview.error} testid="accept-room-error" />}
        {send.error && <ErrorPanel err={send.error} testid="accept-room-error" />}
        <DialogFooter>
          <Btn kind="plain" testid="button-accept-room-close" onClick={() => { if (!busy) onClose(); }}>{send.data ? "Close" : "Cancel"}</Btn>
          {!send.data && (
            <Btn testid="button-accept-room-send" disabled={wouldDo === 0} pending={send.isPending} onClick={() => send.mutate()}>
              Accept {wouldDo}
            </Btn>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
