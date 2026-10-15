import { useState, useEffect } from "react";
import { useLocation, useParams, useSearch } from "wouter";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import {
  fetchAsset, fetchAssetPendingApproval, markAssetVerified, fetchAssetGateState,
  IDENTIFICATION_MODE_WORDS,
  type ApprovalRequest, type CandidateRow,
} from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import {
  AssetMoveDialog, CustodyTransferDialog, CondemnAssetDialog, MarkMissingDialog,
  MarkFoundDialog, invalidateAssetQueries,
} from "@/components/AssetActionDialogs";
import RecordLink from "@/components/RecordLink";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import type { Asset } from "@/types";
import AssetStatusPills from "@/components/AssetStatusPills";
import ConditionBadge from "@/components/ConditionBadge";
import DepreciationCard from "@/components/DepreciationCard";
import AssetHistoryTimeline from "@/components/AssetHistoryTimeline";
import WarrantyCard from "@/components/WarrantyCard";
import { CandidateBanner, GateActions } from "@/components/GateActions";
import { GateEvidence } from "@/components/GateEvidence";
import {
  ArrowLeft, Monitor, Car, Sofa, User, MapPin, Clock,
  AlertCircle, ChevronRight, Edit3, ShieldCheck, AlertTriangle, Trash2, ArrowRightLeft, Loader2, SearchCheck,
  Hourglass,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useEnumLabel } from "@/hooks/useEnums";
import { useScopes, SCOPE } from "@/hooks/use-scopes";

const WORKFLOW_STEPS = ["Cleared", "In Review", "Disposed"];

/**
 * Which of the three steps describes this asset — or -1, for none of them.
 *
 * It was `status === "Cleared" ? 0 : 1`, so "Disposed" could not be reached by
 * any asset and a condemned one sat highlighted on "Cleared". Two facts feed
 * it, read one at a time: disposed is the third step; an asset in service is
 * on the first when it is cleared and on the second when it is under EITHER
 * review — unverified, or tagged with no SAP code. Every OTHER lifecycle
 * state — missing, under repair, transferred — lights nothing, because none of
 * the three words is true of it; the lifecycle pill in the hero says what it
 * is. -1 also leaves no step drawn as "passed", which is right: a missing
 * asset has not passed "Cleared".
 */
function workflowStep(asset: Asset): number {
  if (asset.lifecycleState === "disposed") return 2;
  if (asset.lifecycleState !== undefined && asset.lifecycleState !== "active") return -1;
  if (asset.status === "Cleared") return 0;
  if (asset.status === "Review — data quality" || asset.status === "Review — no SAP code") return 1;
  return -1;
}

function CategoryIcon({ category }: { category: string }) {
  const cls = "w-full h-full text-white";
  if (category === "IT Equipment") return <Monitor className={cls} />;
  if (category === "Fleet / Vehicles") return <Car className={cls} />;
  return <Sofa className={cls} />;
}

function DetailRow({ label, value }: { label: string; value?: React.ReactNode }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="flex flex-col sm:flex-row sm:gap-4 py-2.5 border-b border-border last:border-0">
      <dt className="text-xs font-medium text-muted-foreground w-44 shrink-0">{label}</dt>
      <dd className="text-xs text-foreground mt-0.5 sm:mt-0">{value}</dd>
    </div>
  );
}

function TabPanel({ tabs }: { tabs: { label: string; content: React.ReactNode }[] }) {
  const [active, setActive] = useState(0);
  return (
    <div>
      <div className="flex border-b border-border mb-4">
        {tabs.map((tab, i) => (
          <button
            key={tab.label}
            onClick={() => setActive(i)}
            className={cn(
              "px-4 py-2.5 text-xs font-semibold border-b-2 transition-colors",
              active === i
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
            data-testid={`tab-${tab.label.toLowerCase().replace(/[\s&]+/g, "-")}`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {tabs[active].content}
    </div>
  );
}

/**
 * Where *Back* goes (handoff 60 §2d). An asset opened from the Candidates
 * list carries `?from=candidates` — and `&tab=<waiting_on>` for the tab it
 * was opened from — so Back returns to that list and tab rather than to the
 * register, which does not even show a candidate. Anything else goes back
 * to the register list, as it always has.
 */
function backTarget(search: string): { path: string; label: string } {
  const q = new URLSearchParams(search);
  if (q.get("from") === "candidates") {
    const tab = q.get("tab");
    return {
      path: tab ? `/candidates?waiting_on=${encodeURIComponent(tab)}` : "/candidates",
      label: "Back to Candidates",
    };
  }
  return { path: "/assets/list", label: "Back to Asset Register" };
}

/** Before IAD has verified a unit there is ordinarily nothing to show, so
 *  the evidence panel draws nothing there unless an earlier verification
 *  exists (a unit queried and re-sent keeps its first one). */
const BEFORE_VERIFICATION = new Set(["captured", "vfm_pending"]);

export default function AssetDetail() {
  const { id } = useParams<{ id: string }>();
  const [, setNavLocation] = useLocation();
  const back = backTarget(useSearch());
  const { setTitle, setSearchHandler } = useLayoutCtx();
  // Handoff 46: every button in the action bar is a write that needs
  // `assets:write` — Edit, Move, Transfer, Mark verified, Mark found, Mark
  // missing, Condemn — so the bar is drawn only for somebody who holds it.
  // Hidden, not greyed: a greyed button says "not now", and for a reader it
  // is "never". The record, its history and the approval notice stay.
  const scopes = useScopes();
  const canWrite = scopes.has(SCOPE.assetsWrite);
  // What IAD saw (handoff 60 §2b) is served under `candidates:read`.
  const canReadEvidence = scopes.has(SCOPE.candidatesRead);

  const qc = useQueryClient();
  // `asset.condition` is the model's key (`good`, `decommissioned`), not a
  // display word — it is spelled for the reader here and nowhere else.
  const conditionLabelOf = useEnumLabel("condition");
  // Handoff 25 C1. The FM domain is rendered by its model LABEL, never
  // its key — the row used to show the bare `it` under a heading that
  // meant something else entirely.
  const fmDomainLabel = useEnumLabel("domain");
  // And the lifecycle state, which printed its raw key (`in_repair`) two rows
  // below a condition that was spelled properly. Published as `asset_state`.
  const stateLabelOf = useEnumLabel("asset_state");
  const { data: asset, isLoading, error } = useQuery<Asset | null, CadraApiError>({
    queryKey: ["asset", id],
    queryFn: () => fetchAsset(id ?? ""),
    enabled: !!id,
    staleTime: 60_000,
  });

  /**
   * THE REQUEST IN THE WAY, if there is one (handoff 35).
   *
   * At most one request can be pending against an asset — a partial-unique
   * index in the database says so — and while there is one, `/move` and
   * `/transfer-custody` answer 409 for everybody. Somebody opening this page
   * should not have to press a button to find that out: *"a person opening an
   * asset should not have to guess why the Move button is behaving
   * differently"* is the handoff's sentence for it.
   *
   * Asked on EVERY asset, including on a register with approval switched off,
   * because a tenant that has thrown the switch can still be holding requests
   * raised while it was on, and one of them may be about this asset.
   *
   * On an error this renders NOTHING and the two buttons stay live. The banner
   * is additive information; the server is the authority, and if the read
   * failed the move route still refuses with the reference in its `details`,
   * which the Move dialog prints (`PendingConflictNotice`). What must not
   * happen is the opposite — an asset whose actions are switched off because a
   * request that does not exist could not be read.
   */
  const { data: pendingApproval } = useQuery<ApprovalRequest | null, CadraApiError>({
    queryKey: ["asset-approvals", id],
    queryFn: () => fetchAssetPendingApproval(id ?? ""),
    enabled: !!id,
    staleTime: 30_000,
  });

  // THE RECEIPT GATES (handoff 57, kept by 58).
  // Read raw and on its own key: the mapped `Asset` does not carry them, and
  // the buttons are the server's answer for THIS caller now (`can_fire` has
  // the no-two-gates rule applied), so they are refreshed after every gate.
  const { data: gateRow } = useQuery<CandidateRow, CadraApiError>({
    queryKey: ["asset-gates", id],
    queryFn: () => fetchAssetGateState(id ?? ""),
    enabled: !!id,
    staleTime: 15_000,
  });
  const isCandidate = !!gateRow?.register_state && gateRow.register_state !== "registered";
  // Handoff 59 §2: a `record_only` unit never has a label. The mapped
  // `assetTag` falls back to the asset code, which here would read as a label
  // that exists, so the tag is said to be none wherever it is shown.
  const noLabel = gateRow?.identification_mode === "record_only";

  const [moveOpen, setMoveOpen] = useState(false);
  const [custodyOpen, setCustodyOpen] = useState(false);
  const [condemnOpen, setCondemnOpen] = useState(false);
  const [missingOpen, setMissingOpen] = useState(false);
  const [foundOpen, setFoundOpen] = useState(false);
  // Verifying an asset is itself an event, so the history goes stale with the
  // asset — and so do the register list and every count of unverified assets,
  // which this did not refresh. One list, shared with the dialogs.
  const verifyMut = useMutation({
    mutationFn: () => markAssetVerified(id ?? ""),
    onSuccess: () => invalidateAssetQueries(qc, id),
  });
  // Verify is a button, not a dialog, so it has nowhere of its own to say no.
  // It said nothing: a refused verify (a 403, say) stopped the spinner and
  // looked exactly like a success.
  const verifyErr = verifyMut.error as CadraApiError | null;

  useEffect(() => {
    setTitle(asset ? asset.name : "Asset Detail");
    setSearchHandler(undefined);
  }, [asset, setTitle, setSearchHandler]);

  if (isLoading) {
    return (
      <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
        <Clock size={20} className="animate-pulse" />
        <p className="text-sm">Loading asset…</p>
      </div>
    );
  }
  if (error) {
    return (
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
  }
  if (!asset) {
    return (
      <div className="p-8 text-center">
        <p className="text-muted-foreground text-sm">Asset not found.</p>
        <button className="mt-4 text-primary text-sm hover:underline" onClick={() => setNavLocation(back.path)}>
          {back.label}
        </button>
      </div>
    );
  }

  const isFleet = asset.category === "Fleet / Vehicles";

  // DISPOSAL IS TERMINAL, and the rule is the model's, not this page's:
  // `nrs.asset.write` refuses a change of status, location or custodian on a
  // disposed asset for every writer — this app, Vendra, the importer, the
  // shell (handoff 30 §B). Until then this page offered *Mark missing* on a
  // disposed asset, which overwrote `disposed` and put it back on the
  // register with a 200. All this page does is not OFFER what the server
  // will refuse, and say why in words on the page rather than in a tooltip —
  // it is shown to the client on a tablet, where nothing is hovered. If this
  // copy of the asset is stale and a dialog is opened anyway, the dialog
  // prints the server's own sentence.
  //
  // VERIFY IS NOT ONE OF THEM, by ruling (handoff 31 §C2, `DECISIONS.md`): "a
  // disposed asset somebody physically finds on the premises is an audit
  // finding, and a register that refuses to record 'I saw it, today' is
  // suppressing the one fact that matters". The Odoo form used to hide the
  // button on a disposed asset while this page offered it — one rule, two
  // answers. The form now offers it in every state, this page always did,
  // and the notice below says so, because a person reading "disposal is the
  // end of an asset's record" beside a live green button would fairly assume
  // the button was the mistake.
  const isDisposed = asset.lifecycleState === "disposed";
  const isMissing = asset.lifecycleState === "missing";
  const DISPOSED_TITLE = "This asset has been disposed of";

  // A pending request blocks BOTH acts, not only the one it is about: the
  // database's unique index is per ASSET and not per change type, so a
  // custody request waiting for approval makes `/move` a 409 as well. The
  // buttons say so rather than opening a dialog that will be refused — and
  // the banner below says which request, who was asked, and what they were
  // asked for, because "Move is greyed out" is not an explanation.
  const blockedBy = pendingApproval ?? null;
  const AWAITING_TITLE = blockedBy
    ? `${blockedBy.reference} is already waiting for approval on this asset`
    : undefined;

  const currentStep = workflowStep(asset);

  const iconBg =
    asset.category === "IT Equipment" ? "bg-blue-500" :
    asset.category === "Fleet / Vehicles" ? "bg-emerald-500" :
    "bg-amber-500";

  // The Provenance tab, as a list, so that "every row is blank" is something
  // the page can see and say instead of rendering an empty panel.
  const prov = asset.provenance;
  const provenanceRows: { label: string; value: React.ReactNode }[] = [
    { label: "Legacy Code", value: asset.legacyCode },
    { label: "Registration No.", value: isFleet ? asset.registrationNo : undefined },
    { label: "Engine No.", value: isFleet ? asset.engineNo : undefined },
    // The model's key (`vendra`, `sap`, …), printed as the key it is.
    // `/meta/enums` does not publish this set, so there is no server label to
    // read — and a label map declared here would be a copy of a Selection the
    // server owns, which is how this page came to mislabel things before.
    { label: "Data Source", value: prov?.importSource && <span className="font-mono">{prov.importSource}</span> },
    { label: "Import Date", value: prov?.importDate },
    { label: "Import Reference", value: prov?.importRef && <span className="font-mono">{prov.importRef}</span> },
    { label: "GRN Reference", value: prov?.grnReference && <span className="font-mono">{prov.grnReference}</span> },
    { label: "PO Reference", value: prov?.purchaseOrderReference && <span className="font-mono">{prov.purchaseOrderReference}</span> },
    { label: "Purchase Vendor", value: prov?.purchaseVendor },
    { label: "Registered", value: prov?.registeredAt?.replace("T", " ").slice(0, 16) },
    { label: "Registered By", value: prov?.registeredBy },
  ].filter(r => r.value !== null && r.value !== undefined && r.value !== "");

  return (
    <div className="max-w-4xl mx-auto px-5 py-5">
      {/* Back — to the register LIST. `/assets` is the KPI dashboard, which is
          not what the label says and not where the user came from. Opened
          from Candidates (`?from=candidates`), back to Candidates and the
          same tab (handoff 60 §2d). */}
      <button
        onClick={() => setNavLocation(back.path)}
        className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground mb-4 transition-colors"
        data-testid="button-back"
        data-back-to={back.path}
      >
        <ArrowLeft size={13} /> {back.label}
      </button>

      {/* A candidate is not a register asset, and says so before anything
          else on the page (handoff 57). */}
      {isCandidate && gateRow && (
        <div className="mb-5 space-y-3" data-testid="asset-gates">
          <CandidateBanner row={gateRow} />
          {/* The IAD approver reads what IAD saw BEFORE the approve button
              (handoff 60 §2b) — until then they approved blind. */}
          {canReadEvidence && (
            <GateEvidence
              assetId={id ?? ""}
              hideWhenEmpty={BEFORE_VERIFICATION.has(gateRow.register_state)}
            />
          )}
          <GateActions row={gateRow} />
        </div>
      )}
      {/* A registered asset that came through the gates keeps its
          verification; shown only when there is one, so an asset that was
          registered before the gates existed draws nothing. */}
      {!isCandidate && gateRow && canReadEvidence && (
        <div className="mb-5">
          <GateEvidence assetId={id ?? ""} hideWhenEmpty />
        </div>
      )}

      {/* Header band */}
      <div className="bg-card border border-card-border rounded-xl mb-5 overflow-hidden">
        {/* Workflow */}
        <div className="px-5 py-3 border-b border-border bg-muted/30 flex flex-wrap items-center gap-2">
          {/* A candidate is in none of the three — it is not on the
              register yet; the banner above says where it is. */}
          {!isCandidate && WORKFLOW_STEPS.map((step, i) => (
            <div key={step} className="flex items-center gap-2">
              {i > 0 && <ChevronRight size={12} className="text-muted-foreground" />}
              {/* Only the current step is drawn. Steps before it used to be
                  painted green as "passed" — which put a green "Cleared" on
                  every unverified asset, and, once "Disposed" became
                  reachable, on every condemned one. Nothing records that an
                  asset passed through a step, so nothing is drawn as passed. */}
              <span
                className={cn(
                  "px-3 py-1 rounded-full text-xs font-semibold border",
                  i === currentStep
                    ? "bg-primary text-white border-primary"
                    : "text-muted-foreground border-border"
                )}
                data-testid={`workflow-step-${i}`}
                data-current={i === currentStep ? "true" : "false"}
              >
                {step}
              </span>
            </div>
          ))}

          {/* Action bar */}
          {/* A candidate is moved on by its gates, not by the register's
              controls — Move, Verify, Condemn on a unit that is not yet an
              asset would act on something the register does not hold. */}
          {canWrite && !isCandidate && (
          <div className="ml-auto flex items-center gap-1.5 flex-wrap" data-testid="asset-action-bar">
            <button
              onClick={() => setNavLocation(`/assets/${id}/edit`)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
              data-testid="button-edit"
            >
              <Edit3 size={12} /> Edit
            </button>
            <button
              onClick={() => setMoveOpen(true)}
              disabled={isDisposed || !!blockedBy}
              title={isDisposed ? DISPOSED_TITLE : AWAITING_TITLE}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:text-muted-foreground"
              data-testid="button-move"
            >
              <MapPin size={12} /> {asset.location.locationId ? "Move" : "Place"}
            </button>
            <button
              onClick={() => setCustodyOpen(true)}
              disabled={isDisposed || !!blockedBy}
              title={isDisposed ? DISPOSED_TITLE : AWAITING_TITLE}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:text-muted-foreground"
              data-testid="button-transfer-custody"
            >
              <ArrowRightLeft size={12} /> {asset.custodianName ? "Transfer" : "Assign custodian"}
            </button>
            <button
              onClick={() => verifyMut.mutate()}
              disabled={verifyMut.isPending}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-green-200/70 dark:border-green-800/30 text-xs font-medium text-green-700 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-950/30 disabled:opacity-50"
              data-testid="button-verify"
            >
              {verifyMut.isPending ? <Loader2 size={12} className="animate-spin" /> : <ShieldCheck size={12} />}
              Mark verified
            </button>
            {/* Disabled when the server would refuse it: the asset is already
                missing, or it is disposed (both a 409 from `/mark-missing`).
                Offered on an asset that was ALREADY missing, this used to open
                a dialog, send a PATCH, get a 200 and change no row — a control
                reporting success while nothing happened; offered on a DISPOSED
                one it un-disposed it. One key compared at a time: see
                LifecyclePill. */}
            {/* *Mark found*, on a MISSING asset and on no other: the route is a
                409 for every other state, so it is not drawn greyed-out on the
                thousands of assets that were never lost. It sits where *Mark
                missing* sits — which on a missing asset is disabled — because
                it is that button's other half. */}
            {isMissing && (
              <button
                onClick={() => setFoundOpen(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-emerald-200/70 dark:border-emerald-800/30 text-xs font-medium text-emerald-700 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-950/30"
                data-testid="button-found"
              >
                <SearchCheck size={12} />
                Mark found
              </button>
            )}
            <button
              onClick={() => setMissingOpen(true)}
              disabled={isMissing || isDisposed}
              title={isMissing ? "This asset is already marked missing"
                : isDisposed ? DISPOSED_TITLE : undefined}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-amber-200/70 dark:border-amber-800/30 text-xs font-medium text-amber-700 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-950/30 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent"
              data-testid="button-missing"
            >
              <AlertTriangle size={12} />
              Mark missing
            </button>
            <button
              onClick={() => setCondemnOpen(true)}
              disabled={isDisposed}
              title={isDisposed ? "This asset has already been disposed of" : undefined}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-200/70 dark:border-red-800/30 text-xs font-medium text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent"
              data-testid="button-condemn"
            >
              <Trash2 size={12} /> Condemn
            </button>
          </div>
          )}
        </div>

        {/* WHY four of the buttons above are grey, on the page. `role="note"`
            and not an alert: it is a standing fact about this record, not
            something that just happened. */}
        {isDisposed && (
          <div className="px-5 py-3 border-b border-border" data-testid="asset-disposed-notice" role="note">
            <div className="flex items-start gap-2 bg-slate-100 dark:bg-slate-800/60 border border-slate-300/80 dark:border-slate-600/60 rounded-xl p-3">
              <Trash2 size={14} className="text-slate-600 dark:text-slate-300 shrink-0 mt-0.5" />
              <p className="text-[12px] text-slate-800 dark:text-slate-200">
                <span className="font-semibold">This asset has been disposed of, and disposal is the end of an asset's record.</span>{" "}
                It cannot be marked missing, moved, handed to another custodian or returned to service, so those actions are switched off.
                {/* Only to somebody who has the buttons (handoff 46): the
                    action bar is hidden without assets:write. */}
                {canWrite && <>It can still be marked verified: if it is physically found on the premises, that sighting is worth recording.
                Its other details can still be corrected with Edit.</>}
              </p>
            </div>
          </div>
        )}

        {/* WHAT IS WAITING, and why two buttons are grey (handoff 35).
            `role="status"` and not `alert`: it is a standing fact about this
            record that the reader has just arrived at, not something that
            happened while they were looking. It names the reference, who was
            asked and what was asked for — the three things somebody needs
            before they can do anything about it — and links to the queue,
            because the answer to "why can I not move this" is a screen. */}
        {blockedBy && (
          <div className="px-5 py-3 border-b border-border" data-testid="asset-pending-approval" role="status">
            <div className="flex items-start gap-2 bg-amber-50 dark:bg-amber-950/30 border border-amber-200/70 dark:border-amber-800/30 rounded-xl p-3">
              <Hourglass size={14} className="text-amber-700 dark:text-amber-400 shrink-0 mt-0.5" />
              <div className="text-[12px] text-amber-800 dark:text-amber-300">
                <p>
                  <span className="font-semibold">
                    {blockedBy.change_type === "location"
                      ? "A move of this asset is waiting for approval."
                      : "A change of custodian for this asset is waiting for approval."}
                  </span>{" "}
                  {/* The string copies, not the links: `requested_by_name` and
                      the `to_*_name` fields survive a user being archived or a
                      location renamed, which is the whole reason the record
                      keeps both halves. */}
                  <span className="font-mono font-semibold">{blockedBy.reference}</span> —{" "}
                  {blockedBy.requested_by_name ?? blockedBy.requested_by?.name ?? "somebody"} asked{" "}
                  {blockedBy.approver?.name ?? "an approver"}
                  {blockedBy.change_type === "location"
                    ? <> to move it to <span className="font-semibold">{blockedBy.to_location_name ?? blockedBy.to_location?.name ?? "another location"}</span></>
                    : <> to hand it to <span className="font-semibold">{blockedBy.to_custodian_name ?? blockedBy.to_custodian?.name ?? "somebody else"}</span></>}.
                </p>
                <p className="mt-1 opacity-90">
                  Nothing has changed yet, and nothing will until it is decided.
                  {canWrite && <> Move and Transfer are switched off meanwhile — one request at a time per asset.</>}
                </p>
                <button
                  type="button"
                  onClick={() => setNavLocation("/approvals")}
                  className="mt-1.5 font-semibold underline underline-offset-2"
                  data-testid="link-asset-approval-queue"
                >
                  Open the approvals queue
                </button>
              </div>
            </div>
          </div>
        )}

        {verifyErr && (
          <div className="px-5 py-3 border-b border-border" data-testid="asset-action-error">
            <div className="flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3">
              <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
              <ApiErrorMessage err={verifyErr} />
            </div>
          </div>
        )}

        {/* Hero */}
        <div className="p-5 flex gap-5">
          <div className={cn("w-16 h-16 rounded-xl flex items-center justify-center shrink-0 p-4", iconBg)}>
            <CategoryIcon category={asset.category} />
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-bold text-foreground leading-snug">{asset.name}</h1>
            <p className="text-xs text-muted-foreground font-mono mt-0.5">
              {asset.assetTag && !noLabel && <span>{asset.assetTag} · </span>}
              {asset.legacyCode}
            </p>
            <div className="flex flex-wrap gap-2 mt-3" data-testid="asset-hero-badges">
              <span className="px-2 py-0.5 rounded-full bg-accent text-accent-foreground text-xs font-medium border border-border">{asset.category}</span>
              {/* Only when there is one: this chip used to render EMPTY — a
                  grey blob between the category and the condition. */}
              {asset.subcategory && (
                <span className="px-2 py-0.5 rounded-full bg-accent text-accent-foreground text-xs font-medium border border-border">{asset.subcategory}</span>
              )}
              <ConditionBadge condition={asset.condition} />
              <AssetStatusPills status={asset.status} lifecycleState={asset.lifecycleState} showDot />
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <TabPanel tabs={[
        {
          label: "Details",
          content: (
            <div className="space-y-5">
              <section>
                <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Identification</h3>
                <dl className="bg-card border border-card-border rounded-xl px-5 py-1">
                  <DetailRow label="Asset Code" value={asset.assetCode} />
                  {/* `assetTag` falls back to the asset code when there is
                      no tag, which on a candidate reads as a label that was
                      never issued (the mint moved to request-tagging). */}
                  <DetailRow label="Asset Tag" value={noLabel
                    ? "None — identified by its SAP record"
                    : isCandidate
                      ? (gateRow?.tag ?? "Not issued yet")
                      : asset.assetTag} />
                  <DetailRow label="Serial / VIN" value={asset.serial} />
                  <DetailRow label="Manufacturer" value={asset.manufacturer} />
                  <DetailRow label="Model" value={asset.model} />
                  {/* Handoff 58: what a TAG ID unit is told apart by, and the
                      mode it was received under. Read off the raw asset (the
                      gate query), which the mapped `Asset` does not carry;
                      each row is absent when the record has no value. */}
                  <DetailRow label="Colour" value={gateRow?.colour} />
                  <DetailRow label="Material" value={gateRow?.material} />
                  <DetailRow label="Dimensions" value={gateRow?.dimensions} />
                  <DetailRow label="Reference" value={gateRow?.record_reference} />
                  <DetailRow label="Identified by" value={gateRow?.identification_mode
                    ? IDENTIFICATION_MODE_WORDS[gateRow.identification_mode] : undefined} />
                  <DetailRow label="Asset Type" value={asset.assetType} />
                  <DetailRow label="FM Domain" value={fmDomainLabel(asset.fmDomain)} />
                  {isFleet && <DetailRow label="Registration No." value={asset.registrationNo} />}
                  {isFleet && <DetailRow label="Engine No." value={asset.engineNo} />}
                </dl>
              </section>

              <section>
                <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Classification</h3>
                <dl className="bg-card border border-card-border rounded-xl px-5 py-1">
                  <DetailRow label="Category" value={asset.category} />
                  <DetailRow label="Subcategory" value={asset.subcategory} />
                  <DetailRow label="Asset Type" value={asset.assetType} />
                  <DetailRow label="Condition" value={conditionLabelOf(asset.condition)} />
                  <DetailRow label="Lifecycle State" value={asset.lifecycleState ? stateLabelOf(asset.lifecycleState) : undefined} />
                  <DetailRow label="Verified" value={asset.isVerified == null ? null : asset.isVerified ? "Yes" : "No"} />
                </dl>
              </section>

              <section>
                <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Location</h3>
                <dl className="bg-card border border-card-border rounded-xl px-5 py-1">
                  <DetailRow
                    label="Office / Building"
                    value={asset.location.office && (
                      <RecordLink to={`/locations/${asset.location.locationId}`} enabled={!!asset.location.locationId}>
                        {asset.location.office}
                      </RecordLink>
                    )}
                  />
                  <DetailRow label="State" value={asset.location.state || undefined} />
                  <DetailRow label="Zone" value={asset.location.zone || undefined} />
                  <DetailRow label="Address" value={asset.location.path} />
                </dl>
              </section>

              <section>
                <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Custody</h3>
                <dl className="bg-card border border-card-border rounded-xl px-5 py-1">
                  <DetailRow
                    label="Current Custodian"
                    value={asset.custodianName && (
                      <RecordLink to={`/hr/employees/${asset.custodianId}`} enabled={!!asset.custodianId}>
                        {asset.custodianName}
                      </RecordLink>
                    )}
                  />
                  <DetailRow label="Department" value={asset.department} />
                  {asset.parentAssetName && (
                    <DetailRow
                      label="Parent Asset"
                      value={
                        <RecordLink to={`/assets/${asset.parentAssetId}`} enabled={!!asset.parentAssetId}>
                          {asset.parentAssetName}
                        </RecordLink>
                      }
                    />
                  )}
                  {asset.childCount ? <DetailRow label="Sub-assets" value={String(asset.childCount)} /> : null}
                </dl>
              </section>

              {asset.financials && (
                <section>
                  <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Financials</h3>
                  <dl className="bg-card border border-card-border rounded-xl px-5 py-1">
                    <DetailRow label="Currency" value={asset.financials.currency} />
                    <DetailRow label="Purchase Value" value={asset.financials.purchaseValue != null ? asset.financials.purchaseValue.toLocaleString() : undefined} />
                    <DetailRow label="Replacement Cost" value={asset.financials.replacementCost != null ? asset.financials.replacementCost.toLocaleString() : undefined} />
                    <DetailRow label="Acquisition Cost" value={asset.financials.acquisitionCost != null ? asset.financials.acquisitionCost.toLocaleString() : undefined} />
                    <DetailRow label="Current Value (manual)" value={asset.financials.currentValue != null ? asset.financials.currentValue.toLocaleString() : undefined} />
                  </dl>
                </section>
              )}

              {asset.keyDates && Object.values(asset.keyDates).some(Boolean) && (
                <section>
                  <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Key Dates</h3>
                  <dl className="bg-card border border-card-border rounded-xl px-5 py-1">
                    <DetailRow label="Purchase Date" value={asset.keyDates.purchaseDate} />
                    <DetailRow label="Warranty Expiry" value={asset.keyDates.warrantyExpiry} />
                    <DetailRow label="Acquisition Date" value={asset.keyDates.acquisitionDate} />
                    <DetailRow label="Last Verified" value={asset.keyDates.lastVerifiedDate} />
                    {/* `DetailRow` hides an empty value, and here that would be
                        the defect: a date with no person beside it reads as a
                        date nobody thought to show a person for. Every
                        verification made before the Verify button recorded its
                        verifier is exactly that, so the row says so — in the
                        history timeline's words. No date, no row. */}
                    {asset.keyDates.lastVerifiedDate && (
                      <DetailRow
                        label="Verified By"
                        value={asset.verifiedBy
                          ?? <span className="italic text-muted-foreground">No person recorded</span>}
                      />
                    )}
                    <DetailRow label="Next Service" value={asset.keyDates.nextServiceDate} />
                    <DetailRow label="Disposal Date" value={asset.keyDates.disposalDate} />
                  </dl>
                </section>
              )}

              {/* Its own section, below the dates and nowhere near the pills
                  in the hero: a warranty is a contract, not the asset's
                  health (handoff 34 §C). */}
              <WarrantyCard asset={asset} />

              {!!(asset.maintenanceVendor || asset.pmCount || asset.requestCount) && (
                <section>
                  <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Maintenance</h3>
                  <dl className="bg-card border border-card-border rounded-xl px-5 py-1">
                    <DetailRow label="Vendor" value={asset.maintenanceVendor} />
                    {asset.pmCount      ? <DetailRow label="PM Schedules"   value={String(asset.pmCount)} /> : null}
                    {asset.requestCount ? <DetailRow label="Linked Requests" value={String(asset.requestCount)} /> : null}
                  </dl>
                </section>
              )}

              {asset.notes && (
                <section>
                  <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Notes</h3>
                  <div className="bg-card border border-card-border rounded-xl px-5 py-3">
                    <p className="text-xs text-foreground whitespace-pre-wrap">{asset.notes}</p>
                  </div>
                </section>
              )}
            </div>
          ),
        },
        ...(asset.financials?.depreciation ? [{
          label: "Depreciation",
          content: (
            <div className="space-y-5">
              <DepreciationCard
                assetId={asset.id}
                depreciation={asset.financials.depreciation}
                currency={asset.financials.currency}
              />
            </div>
          ),
        }] : []),
        {
          label: "Custodian & Assignment",
          content: (
            <div className="space-y-4">
              <dl className="bg-card border border-card-border rounded-xl px-5 py-1">
                <DetailRow
                  label="Custodian Name"
                  value={asset.custodianName && (
                    <RecordLink to={`/hr/employees/${asset.custodianId}`} enabled={!!asset.custodianId}>
                      {asset.custodianName}
                    </RecordLink>
                  )}
                />
                <DetailRow label="IR Number" value={asset.custodianIR} />
                <DetailRow label="Department" value={asset.department} />
                <DetailRow label="Zone" value={asset.location.zone} />
                <DetailRow label="State" value={asset.location.state} />
                <DetailRow
                  label="Office"
                  value={asset.location.office && (
                    <RecordLink to={`/locations/${asset.location.locationId}`} enabled={!!asset.location.locationId}>
                      {asset.location.office}
                    </RecordLink>
                  )}
                />
                <DetailRow label="Full Path" value={asset.location.path} />
              </dl>
              {isFleet && asset.custodianScore !== undefined && (
                <div className="bg-card border border-card-border rounded-xl p-5">
                  <p className="text-xs font-medium text-muted-foreground mb-3">Custodian Match Score</p>
                  <div className="flex items-center gap-3">
                    <div className="flex-1 h-2.5 bg-muted rounded-full overflow-hidden">
                      <div
                        className={cn("h-full rounded-full transition-all", asset.custodianScore >= 80 ? "bg-green-500" : asset.custodianScore >= 60 ? "bg-amber-500" : "bg-red-500")}
                        style={{ width: `${asset.custodianScore}%` }}
                      />
                    </div>
                    <span className="text-sm font-bold text-foreground tabular-nums w-10 text-right">{asset.custodianScore}</span>
                  </div>
                  <p className="text-[10px] text-muted-foreground mt-1">out of 100</p>
                </div>
              )}
            </div>
          ),
        },
        {
          label: "Audit & Review",
          content: (
            <div className="space-y-4">
              <div className="bg-card border border-card-border rounded-xl p-5">
                {/* Was "Approval Status". There is no approval record anywhere
                    in this system, so the heading claimed one. */}
                <p className="text-xs font-medium text-muted-foreground mb-3">Status</p>
                <AssetStatusPills status={asset.status} lifecycleState={asset.lifecycleState} showDot />

                {asset.reviewFlags.length > 0 && (
                  <div className="mt-4 space-y-2">
                    <p className="text-xs font-semibold text-muted-foreground mb-2">Review Flags</p>
                    {asset.reviewFlags.map((flag, i) => (
                      <div key={i} className="flex items-start gap-2 bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-800/30 rounded-lg px-3 py-2.5">
                        <AlertCircle size={12} className="text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
                        <p className="text-xs text-amber-800 dark:text-amber-300">{flag}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <AssetHistoryTimeline assetId={asset.id} />
            </div>
          ),
        },
        {
          // Was "Legacy Data", and printed "Migrated from FIRS legacy system"
          // and "March 2024" as literals on EVERY asset — one received from
          // Vendra this month included. Show what the record says, or show
          // nothing: every row below is a field on the record, and a record
          // that holds none of them says so in words.
          label: "Provenance",
          content: provenanceRows.length > 0 ? (
            <dl className="bg-card border border-card-border rounded-xl px-5 py-1" data-testid="asset-provenance">
              {provenanceRows.map(r => <DetailRow key={r.label} label={r.label} value={r.value} />)}
            </dl>
          ) : (
            <div className="bg-card border border-card-border rounded-xl px-5 py-4" data-testid="asset-provenance-empty">
              <p className="text-xs text-muted-foreground">No provenance is recorded for this asset.</p>
            </div>
          ),
        },
      ]} />

      <AssetMoveDialog        assetId={asset.id} open={moveOpen}    onOpenChange={setMoveOpen} placed={!!asset.location.locationId} />
      <CustodyTransferDialog  assetId={asset.id} open={custodyOpen} onOpenChange={setCustodyOpen} />
      <CondemnAssetDialog     assetId={asset.id} open={condemnOpen} onOpenChange={setCondemnOpen} />
      <MarkMissingDialog      assetId={asset.id} open={missingOpen} onOpenChange={setMissingOpen} />
      <MarkFoundDialog        assetId={asset.id} open={foundOpen}   onOpenChange={setFoundOpen} />
    </div>
  );
}
