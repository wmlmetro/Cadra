import { useState, useEffect, useMemo } from "react";
import { useLocation, useParams } from "wouter";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import RecordPicker from "@/components/RecordPicker";
import RecordLink from "@/components/RecordLink";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import {
  fetchRequest, assignRequest, transitionRequest, commentOnRequest, updateRequest,
} from "@/lib/dataProvider";
import { apiGet, CadraApiError } from "@/lib/api";
import { useEnum } from "@/hooks/useEnums";
import type { ServiceRequest } from "@/types";
import {
  ArrowLeft, AlertCircle, Clock, Loader2, Send, ArrowRightLeft,
  UserPlus, MessageCircle, Edit3,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useScopes, SCOPE } from "@/hooks/use-scopes";

interface ApiUserRef { id: number; name: string; login?: string }

const searchUsers = async (q: string) => {
  // The API doesn't expose /users directly, but /identity/employees serves the
  // most useful "who can be assigned" surface for now. We use it as a stand-in
  // — assignee FK is res.users though, so this is approximate; pickers
  // upgrade once a /users endpoint lands.
  const res = await apiGet<ApiUserRef[]>("/api/v1/identity/employees", { q, limit: 10 });
  return res.data.map(u => ({ id: u.id, label: u.name, sublabel: u.login }));
};

// PRIORITY_LABELS used to live here, hard-coded as
// 0=Very low / 1=Low / 2=Normal / 3=High / 4=Urgent — every label one step
// below the model's own (0=Low, 1=Normal, 2=High, 3=Critical, 4=Very Urgent).
// This select wrote the raw key, so picking "High" on this screen set the
// record to Critical. The set now comes from the model via
// GET /api/v1/meta/enums; see lib/enums.ts.

export default function RequestDetail() {
  const { id } = useParams<{ id: string }>();
  const [, nav] = useLocation();
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const qc = useQueryClient();
  // Handoff 46: every control on this page that changes the request —
  // priority, assign, edit, post a message, move it to the next stage — is a
  // `requests:write` route. Somebody who only reads the desk (an Auditor)
  // sees the request, its conversation and where it can go next, as text.
  const scopes = useScopes();
  const canWrite = scopes.has(SCOPE.requestsWrite);

  // Top-level, not inside the option map: useEnum is a hook.
  const priorityOpts = useEnum("priority");

  const { data: req, isLoading, error } = useQuery<ServiceRequest | null, CadraApiError>({
    queryKey: ["request", id],
    queryFn: () => fetchRequest(id ?? "", ["routes", "messages"]),
    enabled: !!id,
    staleTime: 30_000,
  });

  useEffect(() => {
    setTitle(req?.reference ?? "Request");
    setSearchHandler(undefined);
  }, [req, setTitle, setSearchHandler]);

  // Mutation state
  const [assigneeOpen, setAssigneeOpen] = useState(false);
  const [assigneePick, setAssigneePick] = useState<{ id: number; label: string } | null>(null);
  const [transitionId, setTransitionId] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [internal, setInternal] = useState(true);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["request", id] });

  const assignMut = useMutation({
    mutationFn: () => assignRequest(id ?? "", assigneePick?.id ?? null),
    onSuccess: () => { invalidate(); setAssigneeOpen(false); setAssigneePick(null); },
  });
  const transitionMut = useMutation({
    mutationFn: () => transitionRequest(id ?? "", { route_id: transitionId! }),
    onSuccess: () => { invalidate(); setTransitionId(null); },
  });
  const commentMut = useMutation({
    mutationFn: () => commentOnRequest(id ?? "", comment, internal),
    onSuccess: () => { invalidate(); setComment(""); },
  });
  const updatePriorityMut = useMutation({
    mutationFn: (p: string) => updateRequest(id ?? "", { priority: p }),
    onSuccess: invalidate,
  });

  const errs = useMemo(() => [assignMut.error, transitionMut.error, commentMut.error, updatePriorityMut.error]
    .filter(Boolean) as CadraApiError[], [assignMut.error, transitionMut.error, commentMut.error, updatePriorityMut.error]);

  if (isLoading) return (
    <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
      <Clock size={20} className="animate-pulse" />
      <p className="text-sm">Loading request…</p>
    </div>
  );
  if (error) return (
    <div className="p-8 max-w-xl mx-auto">
      <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3">
        <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-[13px] font-semibold text-red-700 dark:text-red-400">{error.code}</p>
          <p className="text-[12px] text-red-700 dark:text-red-400 mt-0.5">{error.message}</p>
        </div>
      </div>
    </div>
  );
  if (!req) return <div className="p-8 text-center text-muted-foreground">Request not found.</div>;

  return (
    <div className="max-w-5xl mx-auto px-5 py-5 space-y-5">
      <button onClick={() => nav("/service-desk")} className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
        <ArrowLeft size={13} /> Back to Service Desk
      </button>

      {/* Hero / header */}
      <div className="bg-card border border-border rounded-2xl p-6">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <p className="text-[20px] font-mono font-extrabold text-foreground">{req.reference}</p>
              <span className={cn(
                "inline-flex items-center px-2 py-0.5 rounded-lg text-[11px] font-bold border",
                req.stageClosed
                  ? "bg-muted border-border text-muted-foreground"
                  : "bg-blue-50 dark:bg-blue-950/30 border-blue-200/70 text-blue-700 dark:text-blue-400",
              )}>{req.stageName}</span>
              {canWrite ? (
                <select
                  value={req.priority}
                  onChange={e => updatePriorityMut.mutate(e.target.value)}
                  disabled={updatePriorityMut.isPending}
                  className="text-[11px] font-semibold border border-border rounded-lg px-2 py-0.5 bg-background"
                >
                  {priorityOpts.map(o => (
                    <option key={o.value} value={o.value}>Priority: {o.label}</option>
                  ))}
                </select>
              ) : (
                <span className="text-[11px] font-semibold border border-border rounded-lg px-2 py-0.5" data-testid="request-priority">
                  Priority: {priorityOpts.find(o => o.value === req.priority)?.label ?? req.priority}
                </span>
              )}
            </div>
            <p className="text-[13px] text-muted-foreground mt-2">
              {req.typeName} {req.categoryName && <>· {req.categoryName}</>}
              {req.kanbanState === "blocked" && (
                <span className="ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10px] font-bold bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400">
                  Blocked
                </span>
              )}
              {req.kanbanState === "done" && (
                <span className="ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10px] font-bold bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400">
                  Ready
                </span>
              )}
            </p>
            {(req.impact || req.urgency) && (
              <div className="mt-1.5 flex gap-3 text-[11px] text-muted-foreground">
                {req.impact && <span>Impact: <span className="text-foreground font-semibold">{req.impact}</span></span>}
                {req.urgency && <span>Urgency: <span className="text-foreground font-semibold">{req.urgency}</span></span>}
              </div>
            )}
            {req.tags.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {req.tags.map(t => (
                  <span key={t.id} className="text-[10px] font-semibold px-2 py-0.5 rounded-lg bg-muted text-muted-foreground border border-border">
                    {t.name}
                  </span>
                ))}
              </div>
            )}
            <div className="mt-3 prose prose-sm dark:prose-invert max-w-none text-[13px]"
                 dangerouslySetInnerHTML={{ __html: req.requestText }} />
            {req.responseText && (
              <div className="mt-4 border-l-4 border-green-500/50 bg-green-50/50 dark:bg-green-950/20 rounded-r-xl px-4 py-3">
                <p className="text-[10px] uppercase tracking-wider font-bold text-green-700 dark:text-green-400 mb-1">Resolution</p>
                <div className="prose prose-sm dark:prose-invert max-w-none text-[13px]"
                     dangerouslySetInnerHTML={{ __html: req.responseText }} />
              </div>
            )}
          </div>
          <div className="shrink-0 min-w-[200px] text-right space-y-1.5 text-[12px]">
            <Meta label="Created"  value={req.createdAt?.slice(0, 16).replace("T", " ")} />
            <Meta label="Assigned" value={req.assignedAt?.slice(0, 16).replace("T", " ")} />
            <Meta label="Moved"    value={req.movedAt?.slice(0, 16).replace("T", " ")} />
            <Meta label="Closed"   value={req.closedAt?.slice(0, 16).replace("T", " ")} />
            <Meta label="Deadline" value={req.deadline} />
            <Meta
              label="Author"
              value={req.author?.name && (
                <RecordLink to={`/hr/employees/${req.author.id}`} enabled={!!req.author.id}>
                  {req.author.name}
                </RecordLink>
              )}
            />
            <Meta
              label="Assignee"
              value={req.assignee?.name
                ? <RecordLink to={`/hr/employees/${req.assignee.id}`} enabled={!!req.assignee.id}>{req.assignee.name}</RecordLink>
                : "Unassigned"}
            />
            {req.partner && <Meta label="Partner" value={req.partner.name} />}
            {req.service && <Meta label="Service" value={req.service.name} />}
            {req.parentId != null && <Meta label="Parent" value={`#${req.parentId}`} />}
          </div>
        </div>

        {/* Action bar */}
        {canWrite && (
        <div className="mt-5 pt-5 border-t border-border flex flex-wrap gap-2">
          <button
            onClick={() => setAssigneeOpen(o => !o)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-accent"
          >
            <UserPlus size={12} /> {req.assignee ? "Reassign" : "Assign"}
          </button>
          <button
            onClick={() => nav(`/service-desk/${id}/edit`)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-accent"
          >
            <Edit3 size={12} /> Edit details
          </button>
        </div>
        )}

        {/* Assignee picker */}
        {canWrite && assigneeOpen && (
          <div className="mt-3 p-3 bg-muted/30 border border-border rounded-xl space-y-2">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Assign to</p>
            <RecordPicker
              value={assigneePick}
              onChange={setAssigneePick}
              search={searchUsers}
              queryKey="picker-assignees"
              placeholder="Type a name…"
            />
            <div className="flex gap-2">
              <button onClick={() => setAssigneeOpen(false)} className="px-2 py-1 text-xs text-muted-foreground hover:text-foreground">Cancel</button>
              <button
                onClick={() => assignMut.mutate()}
                disabled={!assigneePick || assignMut.isPending}
                className={cn(
                  "px-3 py-1 text-xs font-semibold rounded-lg",
                  assigneePick && !assignMut.isPending ? "bg-primary text-white" : "bg-muted text-muted-foreground cursor-not-allowed",
                )}
              >
                {assignMut.isPending ? <Loader2 size={11} className="animate-spin" /> : "Assign"}
              </button>
            </div>
          </div>
        )}
      </div>

      {errs.length > 0 && (
        <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-3 space-y-1">
          {errs.map((e, i) => (
            <div key={i} className="flex items-start gap-1">
              <AlertCircle size={11} className="text-red-700 dark:text-red-400 shrink-0 mt-[3px]" />
              <ApiErrorMessage err={e} />
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Conversation */}
        <div className="lg:col-span-2 bg-card border border-border rounded-2xl p-5 space-y-3">
          <h2 className="text-[13px] font-bold flex items-center gap-2"><MessageCircle size={14} /> Conversation</h2>
          {(!req.messages || req.messages.length === 0) ? (
            <p className="text-[12px] text-muted-foreground py-4 text-center">No messages yet.</p>
          ) : (
            <ol className="space-y-3">
              {req.messages.map(m => (
                <li key={m.id} className="border-l-2 border-border pl-3 py-1">
                  <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                    {/* Was `?? "System"`. A message with no author is a message
                        whose record names nobody; "System" is an actor this
                        page made up, and the asset history refuses the same
                        word for the same reason. */}
                    {m.author?.name
                      ? <span className="font-semibold text-foreground">{m.author.name}</span>
                      : <span className="italic">No person recorded</span>}
                    <span>·</span>
                    <span>{m.date?.replace("T", " ").slice(0, 16)}</span>
                    {m.is_internal && <span className="ml-1 inline-flex items-center px-1.5 py-0.5 rounded text-[9px] bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-400 font-semibold uppercase">Internal</span>}
                  </div>
                  {m.subject && <p className="text-[12px] font-semibold mt-1">{m.subject}</p>}
                  <div className="prose prose-xs dark:prose-invert max-w-none text-[12px]"
                       dangerouslySetInnerHTML={{ __html: m.body_html ?? "" }} />
                </li>
              ))}
            </ol>
          )}

          {/* Comment box */}
          {canWrite && (
          <div className="pt-3 border-t border-border space-y-2">
            <textarea
              rows={3}
              value={comment}
              onChange={e => setComment(e.target.value)}
              placeholder="Write a message…"
              className="w-full px-3 py-2 text-xs border border-border rounded-xl bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
            <div className="flex items-center gap-2">
              <label className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
                <input type="checkbox" checked={internal} onChange={e => setInternal(e.target.checked)} />
                Internal note (not visible to author)
              </label>
              <button
                onClick={() => commentMut.mutate()}
                disabled={!comment.trim() || commentMut.isPending}
                className={cn(
                  "ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl",
                  comment.trim() && !commentMut.isPending ? "bg-primary text-white hover:opacity-90" : "bg-muted text-muted-foreground cursor-not-allowed",
                )}
              >
                {commentMut.isPending ? <Loader2 size={11} className="animate-spin" /> : <Send size={11} />}
                Post
              </button>
            </div>
          </div>
          )}
        </div>

        {/* Routes / transitions */}
        <div className="bg-card border border-border rounded-2xl p-5 space-y-3">
          <h2 className="text-[13px] font-bold flex items-center gap-2"><ArrowRightLeft size={14} /> Next actions</h2>
          {(!req.routes || req.routes.length === 0) ? (
            <p className="text-[11px] text-muted-foreground py-2">No outbound transitions from this stage.</p>
          ) : (
            <ul className="space-y-2">
              {req.routes.map(r => (
                <li key={r.id}>
                  {canWrite ? (
                  <button
                    onClick={() => { setTransitionId(r.id); transitionMut.mutate(); }}
                    disabled={transitionMut.isPending}
                    className={cn(
                      "w-full text-left px-3 py-2 rounded-xl border text-[12px] font-medium flex items-center justify-between gap-2",
                      transitionMut.isPending && transitionId === r.id
                        ? "border-primary/50 bg-primary/5"
                        : "border-border hover:border-primary/40 hover:bg-muted/30",
                    )}
                  >
                    <span>{r.name}</span>
                    <span className="text-[10px] text-muted-foreground">→ {r.to_stage_name}</span>
                  </button>
                  ) : (
                    <div className="w-full px-3 py-2 rounded-xl border border-border text-[12px] font-medium flex items-center justify-between gap-2" data-testid="request-route">
                      <span>{r.name}</span>
                      <span className="text-[10px] text-muted-foreground">→ {r.to_stage_name}</span>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}

          {/* Linked records */}
          {(req.asset || req.location || req.vehicle) && (
            <div className="pt-3 border-t border-border space-y-1.5 text-[12px]">
              <p className="text-[10px] uppercase tracking-wider font-bold text-muted-foreground">Linked</p>
              {req.asset && (
                <button onClick={() => nav(`/assets/${req.asset!.id}`)} className="block w-full text-left text-muted-foreground hover:text-foreground">
                  Asset: <span className="text-primary font-semibold hover:underline">{req.asset.name}</span>
                </button>
              )}
              {req.location && (
                <button onClick={() => nav(`/locations/${req.location!.id}`)} className="block w-full text-left text-muted-foreground hover:text-foreground">
                  Location: <span className="text-primary font-semibold hover:underline">{req.location.name}</span>
                </button>
              )}
              {req.vehicle && (
                <p className="text-muted-foreground">Vehicle: <span className="text-foreground font-semibold">{req.vehicle.name}</span></p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Meta({ label, value }: { label: string; value?: React.ReactNode }) {
  if (!value) return null;
  return (
    <div className="text-muted-foreground">
      <p className="text-[10px] uppercase tracking-wider">{label}</p>
      <p className="text-foreground font-semibold">{value}</p>
    </div>
  );
}
