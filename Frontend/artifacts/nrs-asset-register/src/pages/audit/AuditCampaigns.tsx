/**
 * Audit campaigns (handoff 66 §3, §6) — the audits, their progress, and the
 * two lists each exists for.
 *
 * Everybody on the audit (`audit:read`: capturer, reviewer, Asset
 * Controller, Auditor) sees every campaign with its progress — captured,
 * reviewed, waiting, exceptions — and, for one campaign, its rooms and its
 * two lists per office:
 *
 *   Found, not in SAP     accepted captures of items in neither register;
 *   In SAP, not found     active SAP records in the campaign's offices that
 *                         no accepted capture matched and no Cadra asset
 *                         links to. SAP records with no office are a count,
 *                         said in the server's own sentence.
 *
 * Each list downloads as a CSV through the bearer token. An open campaign's
 * lists are computed now; a closed one's are as they stood at closing — the
 * page says which.
 *
 * Opening and closing are the Asset Controller's (`audit:manage`); the
 * controls are drawn only for a holder and the server refuses everybody
 * else. Closing needs every capture reviewed: the server says how many are
 * still waiting, verbatim.
 */
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardList, Download, Plus, X } from "lucide-react";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { ScopeRefusal } from "@/components/ScopeRefusal";
import RecordPicker from "@/components/RecordPicker";
import { apiGet, type CadraApiError } from "@/lib/api";
import { useScopes, SCOPE } from "@/hooks/use-scopes";
import {
  AUDIT_KEY, closeCampaign, downloadCampaignList, fetchAuditPeople, fetchCampaign, fetchCampaignLists,
  fetchCampaigns, openCampaign,
  type AuditCampaign, type CampaignLists, type ListKey,
} from "@/lib/auditCapture";
import { cn, formatIsoDate } from "@/lib/utils";
import {
  Btn, Empty, ErrorPanel, INPUT, LABEL, Loading, PageHeader, Pill, Tabs, invalidateAudit, n, when,
} from "./shared";

export default function AuditCampaigns() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const scopes = useScopes();
  const canRead = scopes.has(SCOPE.auditRead);
  const canManage = scopes.has(SCOPE.auditManage);
  const [selected, setSelected] = useState<number | null>(null);
  const [opening, setOpening] = useState(false);

  useEffect(() => {
    setTitle("Audit campaigns");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const q = useQuery<AuditCampaign[], CadraApiError>({
    queryKey: [...AUDIT_KEY, "campaigns"],
    queryFn: () => fetchCampaigns(),
    enabled: canRead,
  });

  if (!canRead) {
    return <ScopeRefusal scope={SCOPE.auditRead}
      detail="The audit team — capturers and reviewers — the Asset Controller and Auditors hold it." />;
  }
  const rows = q.data ?? [];

  return (
    <div className="flex flex-col h-full">
      <PageHeader icon={<ClipboardList size={15} />} title="Audit campaigns">
        An audit team walks each room and captures every item: already on Cadra's register, in SAP's register but
        not Cadra's, or in neither. A reviewer — never the capturer — accepts each capture. Closing a campaign keeps
        its two lists as they stood.
      </PageHeader>
      <div className="flex-1 overflow-y-auto">
        {canManage && (
          <div className="px-5 py-3 border-b border-border">
            {opening
              ? <OpenCampaignForm onClose={(id) => { setOpening(false); if (id) setSelected(id); }} />
              : <Btn testid="button-open-campaign" onClick={() => setOpening(true)}><Plus size={12} /> Open a campaign</Btn>}
          </div>
        )}
        {q.error && <div className="px-5 py-2"><ErrorPanel err={q.error} /></div>}
        {q.isLoading ? <Loading what="Reading the campaigns…" /> : rows.length === 0 && !q.error ? (
          <Empty testid="audit-campaigns-empty">No audit campaign has been opened on this tenant.</Empty>
        ) : (
          <table className="w-full text-xs" data-testid="audit-campaigns">
            <thead className="bg-muted/40 text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="text-left font-semibold px-5 py-2">Campaign</th>
                <th className="text-left font-semibold px-3 py-2">Covers</th>
                <th className="text-left font-semibold px-3 py-2">Team</th>
                <th className="text-right font-semibold px-3 py-2">Captured</th>
                <th className="text-right font-semibold px-3 py-2">Reviewed</th>
                <th className="text-right font-semibold px-3 py-2">Waiting</th>
                <th className="text-right font-semibold px-5 py-2">Exceptions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(c => (
                <tr key={c.id} onClick={() => setSelected(c.id)}
                    className={cn("border-b border-border align-top cursor-pointer hover:bg-accent/40", selected === c.id && "bg-primary/5")}
                    data-testid={`audit-campaign-row-${c.id}`}>
                  <td className="px-5 py-2.5">
                    <div className="font-semibold text-foreground">{c.name}</div>
                    <div className="mt-0.5 flex gap-1 items-center">
                      <Pill tone={c.state === "open" ? "green" : "plain"}>{c.state === "open" ? "Open" : "Closed"}</Pill>
                      {(c.date_start || c.date_end) && (
                        <span className="text-muted-foreground">
                          {c.date_start ? formatIsoDate(c.date_start) : "…"} – {c.date_end ? formatIsoDate(c.date_end) : "…"}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-muted-foreground">
                    {c.scope.map((s, i) => (
                      <div key={i}>{s.location?.name ?? "Any location"}{s.office_code && <> · office <span className="font-mono">{s.office_code}</span></>}</div>
                    ))}
                  </td>
                  <td className="px-3 py-2.5 text-muted-foreground">
                    <div>Capture: {c.capturers.map(u => u.name).join(", ") || "—"}</div>
                    <div>Review: {c.reviewers.map(u => u.name).join(", ") || "—"}</div>
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{n(c.progress.captured)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{n(c.progress.reviewed)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{n(c.progress.waiting_for_review)}</td>
                  <td className="px-5 py-2.5 text-right tabular-nums">
                    {n(c.progress.exceptions)}
                    {c.progress.exceptions_open > 0 && <div className="text-amber-700 dark:text-amber-400">{c.progress.exceptions_open} open</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {selected != null && <CampaignDetail id={selected} canManage={canManage} onClose={() => setSelected(null)} />}
      </div>
    </div>
  );
}

// ─── one campaign ────────────────────────────────────────────────────────────

function CampaignDetail({ id, canManage, onClose }: { id: number; canManage: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const c = useQuery<AuditCampaign, CadraApiError>({
    queryKey: [...AUDIT_KEY, "campaign", id],
    queryFn: () => fetchCampaign(id),
  });
  const close = useMutation<Awaited<ReturnType<typeof closeCampaign>>, CadraApiError>({
    mutationFn: () => closeCampaign(id),
    onSuccess: () => invalidateAudit(qc),
  });
  const [confirming, setConfirming] = useState(false);
  const camp = c.data;

  return (
    <div className="px-5 py-4 border-t-4 border-primary/20 space-y-4" data-testid="audit-campaign-detail" data-campaign-id={id}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-[13px] font-bold text-foreground" data-testid="audit-campaign-name">{camp?.name ?? `Campaign ${id}`}</h2>
          {camp && (
            <p className="text-[11px] text-muted-foreground" data-testid="audit-campaign-progress">
              {n(camp.progress.captured)} captured · {n(camp.progress.reviewed)} reviewed ({n(camp.progress.accepted)} accepted,{" "}
              {n(camp.progress.returned)} returned) · {n(camp.progress.waiting_for_review)} waiting for review
              {camp.progress.duplicates_held > 0 && <> · {n(camp.progress.duplicates_held)} held as duplicates</>}
              {" "}· {n(camp.progress.exceptions)} found not in SAP ({n(camp.progress.exceptions_open)} open)
            </p>
          )}
          {camp?.state === "closed" && (
            <p className="text-[11px] text-muted-foreground">Closed by {camp.closed_by?.name ?? "—"}, {when(camp.closed_at)}.</p>
          )}
        </div>
        <button type="button" onClick={onClose} aria-label="Close the campaign's detail" className="text-muted-foreground hover:text-foreground">
          <X size={14} />
        </button>
      </div>
      {c.error && <ErrorPanel err={c.error} />}

      {camp && camp.rooms && camp.rooms.length > 0 && (
        <div>
          <p className={LABEL}>Rooms captured</p>
          <ul className="mt-1 text-[12px] space-y-0.5" data-testid="audit-campaign-rooms">
            {camp.rooms.map(r => (
              <li key={r.location.id}>
                {r.location.name} — {n(r.captured)} captured{r.waiting_for_review > 0 && <>, <span className="text-amber-700 dark:text-amber-400">{n(r.waiting_for_review)} waiting for review</span></>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {canManage && camp?.state === "open" && (
        <div className="space-y-2">
          {!confirming ? (
            <Btn testid="button-close-campaign" kind="plain" onClick={() => setConfirming(true)}>Close the campaign</Btn>
          ) : (
            <div className="flex flex-wrap gap-2 items-center" data-testid="close-campaign-confirm">
              <span className="text-[12px]">Close {camp.name}? Nothing more is captured or reviewed in it, and its two lists are kept as they stand now.</span>
              <Btn testid="button-close-campaign-send" pending={close.isPending} onClick={() => close.mutate()}>Close it</Btn>
              <Btn kind="plain" onClick={() => { setConfirming(false); close.reset(); }}>Cancel</Btn>
            </div>
          )}
          {close.error && <ErrorPanel err={close.error} testid="close-campaign-error" />}
        </div>
      )}

      <ClosingLists id={id} />
    </div>
  );
}

const LIST_TABS: { key: ListKey; label: string }[] = [
  { key: "found_not_in_sap", label: "Found, not in SAP" },
  { key: "in_sap_not_found", label: "In SAP, not found" },
];

function ClosingLists({ id }: { id: number }) {
  const [tab, setTab] = useState<ListKey>("found_not_in_sap");
  const q = useQuery<CampaignLists, CadraApiError>({
    queryKey: [...AUDIT_KEY, "lists", id],
    queryFn: () => fetchCampaignLists(id),
  });
  const [dl, setDl] = useState<{ pending: boolean; error: Error | null; done: string | null }>({ pending: false, error: null, done: null });
  const lastUrl = useRef<string | null>(null);
  useEffect(() => () => { if (lastUrl.current) URL.revokeObjectURL(lastUrl.current); }, []);

  const download = async () => {
    setDl({ pending: true, error: null, done: null });
    try {
      const f = await downloadCampaignList(id, tab);
      if (lastUrl.current) URL.revokeObjectURL(lastUrl.current);
      lastUrl.current = f.url;
      const a = document.createElement("a");
      a.href = f.url;
      a.download = f.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setDl({ pending: false, error: null, done: `${f.filename} — ${n(f.bytes)} bytes` });
    } catch (e) {
      setDl({ pending: false, error: e as Error, done: null });
    }
  };

  const lists = q.data;
  return (
    <div data-testid="audit-closing-lists">
      <p className={LABEL}>The two lists</p>
      {lists && (
        <p className="text-[11px] text-muted-foreground mt-0.5" data-testid="audit-lists-as-of">
          {lists.as_of === "closing" ? "As they stood when the campaign closed." : "As they stand now — the campaign is open."}
        </p>
      )}
      <Tabs tabs={LIST_TABS} value={tab} onChange={(t) => { setTab(t); setDl({ pending: false, error: null, done: null }); }}
            label="The two lists" testidPrefix="audit-list-tab" />
      {q.error && <div className="mt-2"><ErrorPanel err={q.error} /></div>}
      {q.isLoading && <Loading what="Computing the lists…" />}
      {lists && (
        <div className="mt-3 space-y-3">
          {lists.by_office.length > 0 && (
            <table className="text-xs" data-testid="audit-lists-by-office">
              <thead className="text-[10px] uppercase tracking-wider text-muted-foreground">
                <tr><th className="text-left pr-4 py-1">Office</th><th className="text-right pr-4">Found, not in SAP</th><th className="text-right">In SAP, not found</th></tr>
              </thead>
              <tbody>
                {lists.by_office.map(o => (
                  <tr key={o.office_code ?? "none"}>
                    <td className="pr-4 py-0.5 font-mono">{o.office_code ?? "no office"}</td>
                    <td className="pr-4 text-right tabular-nums">{n(o.found_not_in_sap)}</td>
                    <td className="text-right tabular-nums">{n(o.in_sap_not_found)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="flex flex-wrap gap-2 items-center">
            <Btn testid={`button-download-${tab}`} kind="plain" pending={dl.pending} onClick={download}>
              <Download size={12} /> Download {tab === "found_not_in_sap" ? "Found, not in SAP" : "In SAP, not found"} (CSV)
            </Btn>
            {dl.done && <span className="text-[11px] text-muted-foreground" data-testid="audit-list-downloaded">{dl.done}</span>}
          </div>
          {dl.error && <ErrorPanel err={dl.error} />}
          {tab === "found_not_in_sap" ? (
            lists.found_not_in_sap.length === 0 ? <Empty testid="audit-list-empty">No accepted capture was found in neither register.</Empty> : (
              <table className="w-full text-xs" data-testid="audit-list-found_not_in_sap">
                <thead className="bg-muted/40 text-[10px] uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="text-left px-3 py-1.5">Office</th><th className="text-left px-3">Code</th><th className="text-left px-3">Item</th>
                    <th className="text-left px-3">Room</th><th className="text-left px-3">Captured</th><th className="text-left px-3">Exception</th>
                  </tr>
                </thead>
                <tbody>
                  {lists.found_not_in_sap.map(r => (
                    <tr key={r.capture_id} className="border-b border-border">
                      <td className="px-3 py-1.5 font-mono">{r.office_code ?? "—"}</td>
                      <td className="px-3 font-mono">{r.code ?? "—"}</td>
                      <td className="px-3">{r.name ?? "—"}{r.category && <span className="text-muted-foreground"> · {r.category}</span>}</td>
                      <td className="px-3">{r.location ?? "—"}</td>
                      <td className="px-3 text-muted-foreground">{r.captured_by ?? "—"}, {when(r.captured_at)}</td>
                      <td className="px-3">{r.exception_state ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          ) : (
            lists.in_sap_not_found.length === 0 ? <Empty testid="audit-list-empty">No active SAP record in the campaign's offices is unaccounted for.</Empty> : (
              <table className="w-full text-xs" data-testid="audit-list-in_sap_not_found">
                <thead className="bg-muted/40 text-[10px] uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="text-left px-3 py-1.5">Office</th><th className="text-left px-3">SAP number</th><th className="text-left px-3">Class</th>
                    <th className="text-left px-3">Description</th><th className="text-left px-3">Old tag</th><th className="text-left px-3">Capitalised</th>
                  </tr>
                </thead>
                <tbody>
                  {lists.in_sap_not_found.map(r => (
                    <tr key={r.sap_record_id} className="border-b border-border">
                      <td className="px-3 py-1.5 font-mono">{r.office_code ?? "—"}</td>
                      <td className="px-3 font-mono">{r.asset_number}{r.sub_number && r.sub_number !== "0" ? `-${r.sub_number}` : ""}</td>
                      <td className="px-3 font-mono">{r.asset_class ?? "—"}</td>
                      <td className="px-3">{r.description ?? "—"}</td>
                      <td className="px-3 font-mono">{r.old_tag ?? "—"}</td>
                      <td className="px-3">{r.capitalized_on ? formatIsoDate(r.capitalized_on) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}
          <p className="text-[11px] text-muted-foreground" data-testid="audit-no-office-note">{lists.no_office_note}</p>
        </div>
      )}
    </div>
  );
}

// ─── opening one ─────────────────────────────────────────────────────────────

interface ScopeLine { location: { id: number; label: string } | null; office: string }

async function searchLocations(q: string) {
  const res = await apiGet<{ id: number; name: string; location_code?: string | null }[]>("/api/v1/locations", { q, limit: 10 });
  return (res.data ?? []).map(l => ({ id: l.id, label: l.name, sublabel: l.location_code ?? undefined }));
}

function OpenCampaignForm({ onClose }: { onClose: (id: number | null) => void }) {
  const qc = useQueryClient();
  const people = useQuery({ queryKey: [...AUDIT_KEY, "people"], queryFn: fetchAuditPeople });
  const [name, setName] = useState("");
  const [lines, setLines] = useState<ScopeLine[]>([{ location: null, office: "" }]);
  const [capturers, setCapturers] = useState<Set<number>>(new Set());
  const [reviewers, setReviewers] = useState<Set<number>>(new Set());
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const m = useMutation<AuditCampaign, CadraApiError>({
    mutationFn: () => openCampaign({
      name,
      scope: lines.filter(l => l.location || l.office.trim()).map(l => {
        const o: { location_id?: number; office_code?: string } = {};
        if (l.location) o.location_id = l.location.id;
        if (l.office.trim()) o.office_code = l.office.trim();
        return o;
      }),
      capturer_ids: [...capturers], reviewer_ids: [...reviewers],
      date_start: start || undefined, date_end: end || undefined,
    }),
    onSuccess: (c) => { invalidateAudit(qc); onClose(c.id); },
  });
  const toggle = (set: Set<number>, fn: (s: Set<number>) => void, id: number) => {
    const next = new Set(set);
    if (next.has(id)) next.delete(id); else next.add(id);
    fn(next);
  };

  return (
    <form className="space-y-3 max-w-3xl" data-testid="open-campaign-form"
          onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
      <div>
        <label className={LABEL} htmlFor="campaign-name">Name</label>
        <input id="campaign-name" value={name} onChange={e => setName(e.target.value)} className={cn(INPUT, "w-full mt-1")}
               data-testid="input-campaign-name" />
      </div>
      <div>
        <p className={LABEL}>What it covers — a building or room, the SAP office its records carry, or both</p>
        {lines.map((l, i) => (
          <div key={i} className="flex gap-2 items-start mt-1.5" data-testid={`scope-line-${i}`}>
            <div className="flex-1">
              <RecordPicker value={l.location} queryKey="audit-scope-location"
                onChange={(o) => setLines(ls => ls.map((x, j) => j === i ? { ...x, location: o ? { id: o.id, label: o.label } : null } : x))}
                search={searchLocations} placeholder="Building or room…" />
            </div>
            <input value={l.office} placeholder="Office code" className={cn(INPUT, "w-32 font-mono")}
                   data-testid={`input-scope-office-${i}`}
                   onChange={e => setLines(ls => ls.map((x, j) => j === i ? { ...x, office: e.target.value } : x))} />
            {lines.length > 1 && (
              <button type="button" aria-label="Remove this line" className="text-muted-foreground hover:text-foreground mt-2"
                      onClick={() => setLines(ls => ls.filter((_x, j) => j !== i))}><X size={12} /></button>
            )}
          </div>
        ))}
        <button type="button" className="mt-1.5 text-[11px] text-primary hover:underline"
                onClick={() => setLines(ls => [...ls, { location: null, office: "" }])}>+ another line</button>
      </div>
      {people.error && <ErrorPanel err={people.error as CadraApiError} />}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <PeopleChecklist title="Capturers" testid="campaign-capturers" people={people.data?.capturers ?? []}
          chosen={capturers} onToggle={(id) => toggle(capturers, setCapturers, id)}
          empty="Nobody holds the Audit Capturer role." />
        <PeopleChecklist title="Reviewers" testid="campaign-reviewers" people={people.data?.reviewers ?? []}
          chosen={reviewers} onToggle={(id) => toggle(reviewers, setReviewers, id)}
          empty="Nobody holds the Audit Reviewer role." />
      </div>
      <div className="flex gap-3 flex-wrap">
        <label className="text-[11px] text-muted-foreground">Starts <input type="date" value={start} onChange={e => setStart(e.target.value)} className={INPUT} /></label>
        <label className="text-[11px] text-muted-foreground">Ends <input type="date" value={end} onChange={e => setEnd(e.target.value)} className={INPUT} /></label>
      </div>
      {m.error && <ErrorPanel err={m.error} testid="open-campaign-error" />}
      <div className="flex gap-2">
        <Btn type="submit" testid="button-open-campaign-send" pending={m.isPending}>Open the campaign</Btn>
        <Btn kind="plain" onClick={() => onClose(null)}>Cancel</Btn>
      </div>
    </form>
  );
}

function PeopleChecklist({ title, people, chosen, onToggle, empty, testid }: {
  title: string; people: { id: number; name: string; login: string }[]; chosen: Set<number>;
  onToggle: (id: number) => void; empty: string; testid: string;
}) {
  return (
    <div data-testid={testid}>
      <p className={LABEL}>{title}</p>
      {people.length === 0 ? <p className="text-[11px] text-muted-foreground mt-1">{empty}</p> : (
        <ul className="mt-1 space-y-0.5 max-h-40 overflow-y-auto">
          {people.map(p => (
            <li key={p.id}>
              <label className="text-[12px] flex items-center gap-2">
                <input type="checkbox" className="accent-primary" checked={chosen.has(p.id)} onChange={() => onToggle(p.id)}
                       data-testid={`${testid}-${p.id}`} />
                {p.name} <span className="text-muted-foreground">{p.login}</span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
