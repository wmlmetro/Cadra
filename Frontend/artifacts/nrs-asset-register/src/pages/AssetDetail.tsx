import { useState, useEffect } from "react";
import { useLocation, useParams } from "wouter";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { fetchAsset, markAssetVerified, markAssetMissing } from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import { AssetMoveDialog, CustodyTransferDialog, CondemnAssetDialog } from "@/components/AssetActionDialogs";
import RecordLink from "@/components/RecordLink";
import type { Asset } from "@/types";
import StatusPill from "@/components/StatusPill";
import ConditionBadge from "@/components/ConditionBadge";
import DepreciationCard from "@/components/DepreciationCard";
import {
  ArrowLeft, Monitor, Car, Sofa, User, MapPin, Clock,
  AlertCircle, ChevronRight, Edit3, ShieldCheck, AlertTriangle, Trash2, ArrowRightLeft, Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";

const WORKFLOW_STEPS = ["Cleared", "In Review", "Disposed"];

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

export default function AssetDetail() {
  const { id } = useParams<{ id: string }>();
  const [, setNavLocation] = useLocation();
  const { setTitle, setSearchHandler } = useLayoutCtx();

  const qc = useQueryClient();
  const { data: asset, isLoading, error } = useQuery<Asset | null, CadraApiError>({
    queryKey: ["asset", id],
    queryFn: () => fetchAsset(id ?? ""),
    enabled: !!id,
    staleTime: 60_000,
  });

  const [moveOpen, setMoveOpen] = useState(false);
  const [custodyOpen, setCustodyOpen] = useState(false);
  const [condemnOpen, setCondemnOpen] = useState(false);
  const invalidate = () => qc.invalidateQueries({ queryKey: ["asset", id] });
  const verifyMut = useMutation({ mutationFn: () => markAssetVerified(id ?? ""), onSuccess: invalidate });
  const missingMut = useMutation({ mutationFn: () => markAssetMissing(id ?? ""), onSuccess: invalidate });

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
        <button className="mt-4 text-primary text-sm hover:underline" onClick={() => setNavLocation("/assets")}>
          Back to Asset Register
        </button>
      </div>
    );
  }

  const isFleet = asset.category === "Fleet / Vehicles";
  const isIT = asset.category === "IT Equipment";

  const currentStep = asset.status === "Cleared" ? 0 : 1;

  const iconBg =
    asset.category === "IT Equipment" ? "bg-blue-500" :
    asset.category === "Fleet / Vehicles" ? "bg-emerald-500" :
    "bg-amber-500";

  return (
    <div className="max-w-4xl mx-auto px-5 py-5">
      {/* Back */}
      <button
        onClick={() => setNavLocation("/assets")}
        className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground mb-4 transition-colors"
        data-testid="button-back"
      >
        <ArrowLeft size={13} /> Back to Asset Register
      </button>

      {/* Header band */}
      <div className="bg-card border border-card-border rounded-xl mb-5 overflow-hidden">
        {/* Workflow */}
        <div className="px-5 py-3 border-b border-border bg-muted/30 flex flex-wrap items-center gap-2">
          {WORKFLOW_STEPS.map((step, i) => (
            <div key={step} className="flex items-center gap-2">
              {i > 0 && <ChevronRight size={12} className="text-muted-foreground" />}
              <span className={cn(
                "px-3 py-1 rounded-full text-xs font-semibold border",
                i === currentStep
                  ? "bg-primary text-white border-primary"
                  : i < currentStep
                  ? "bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-300 border-green-200 dark:border-green-800"
                  : "text-muted-foreground border-border"
              )}>
                {step}
              </span>
            </div>
          ))}

          {/* Action bar */}
          <div className="ml-auto flex items-center gap-1.5 flex-wrap">
            <button
              onClick={() => setNavLocation(`/assets/${id}/edit`)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
              data-testid="button-edit"
            >
              <Edit3 size={12} /> Edit
            </button>
            <button
              onClick={() => setMoveOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
              data-testid="button-move"
            >
              <MapPin size={12} /> Move
            </button>
            <button
              onClick={() => setCustodyOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
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
            <button
              onClick={() => {
                if (confirm("Mark this asset as missing? This is reversible — you can move/verify it again later.")) {
                  missingMut.mutate();
                }
              }}
              disabled={missingMut.isPending}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-amber-200/70 dark:border-amber-800/30 text-xs font-medium text-amber-700 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-950/30 disabled:opacity-50"
              data-testid="button-missing"
            >
              {missingMut.isPending ? <Loader2 size={12} className="animate-spin" /> : <AlertTriangle size={12} />}
              Mark missing
            </button>
            <button
              onClick={() => setCondemnOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-200/70 dark:border-red-800/30 text-xs font-medium text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30"
              data-testid="button-condemn"
            >
              <Trash2 size={12} /> Condemn
            </button>
          </div>
        </div>

        {/* Hero */}
        <div className="p-5 flex gap-5">
          <div className={cn("w-16 h-16 rounded-xl flex items-center justify-center shrink-0 p-4", iconBg)}>
            <CategoryIcon category={asset.category} />
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-bold text-foreground leading-snug">{asset.name}</h1>
            <p className="text-xs text-muted-foreground font-mono mt-0.5">
              {asset.assetTag && <span>{asset.assetTag} · </span>}
              {asset.legacyCode}
            </p>
            <div className="flex flex-wrap gap-2 mt-3">
              <span className="px-2 py-0.5 rounded-full bg-accent text-accent-foreground text-xs font-medium border border-border">{asset.category}</span>
              <span className="px-2 py-0.5 rounded-full bg-accent text-accent-foreground text-xs font-medium border border-border">{asset.subcategory}</span>
              <ConditionBadge condition={asset.condition} />
              <StatusPill status={asset.status} showDot />
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
                  <DetailRow label="Asset Tag" value={asset.assetTag} />
                  <DetailRow label="Serial / VIN" value={asset.serial} />
                  <DetailRow label="Manufacturer" value={asset.manufacturer} />
                  <DetailRow label="Model" value={asset.model} />
                  <DetailRow label="Asset Type" value={asset.assetType} />
                  {isIT && <DetailRow label="System Domain" value={asset.systemDomain} />}
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
                  <DetailRow label="Condition" value={asset.condition} />
                  <DetailRow label="Lifecycle State" value={asset.lifecycleState} />
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

              {asset.financials?.depreciation && (
                <DepreciationCard
                  assetId={asset.id}
                  depreciation={asset.financials.depreciation}
                  currency={asset.financials.currency}
                />
              )}

              {asset.keyDates && Object.values(asset.keyDates).some(Boolean) && (
                <section>
                  <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Key Dates</h3>
                  <dl className="bg-card border border-card-border rounded-xl px-5 py-1">
                    <DetailRow label="Purchase Date" value={asset.keyDates.purchaseDate} />
                    <DetailRow label="Warranty Expiry" value={asset.keyDates.warrantyExpiry} />
                    <DetailRow label="Acquisition Date" value={asset.keyDates.acquisitionDate} />
                    <DetailRow label="Last Verified" value={asset.keyDates.lastVerifiedDate} />
                    <DetailRow label="Next Service" value={asset.keyDates.nextServiceDate} />
                    <DetailRow label="Disposal Date" value={asset.keyDates.disposalDate} />
                  </dl>
                </section>
              )}

              {(asset.maintenanceVendor || asset.pmCount || asset.requestCount) && (
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
                <p className="text-xs font-medium text-muted-foreground mb-3">Approval Status</p>
                <StatusPill status={asset.status} showDot />

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

                {asset.status === "Review — possible duplicate" && (
                  <div className="mt-4 p-3 bg-purple-50 dark:bg-purple-900/10 border border-purple-200 dark:border-purple-800/30 rounded-lg">
                    <p className="text-xs text-purple-800 dark:text-purple-300 font-semibold">Possible Duplicate Detected</p>
                    <p className="text-[10px] text-purple-600 dark:text-purple-400 mt-1">Review the flagged duplicate entry in the asset register before approving.</p>
                  </div>
                )}
              </div>

            </div>
          ),
        },
        {
          label: "Legacy Data",
          content: (
            <dl className="bg-card border border-card-border rounded-xl px-5 py-1">
              <DetailRow label="Legacy Code" value={asset.legacyCode} />
              {isFleet && <DetailRow label="Registration No." value={asset.registrationNo} />}
              {isFleet && <DetailRow label="Engine No." value={asset.engineNo} />}
              <DetailRow label="Source" value="Migrated from FIRS legacy system" />
              <DetailRow label="Migration Date" value="March 2024" />
            </dl>
          ),
        },
      ]} />

      <AssetMoveDialog        assetId={asset.id} open={moveOpen}    onOpenChange={setMoveOpen} />
      <CustodyTransferDialog  assetId={asset.id} open={custodyOpen} onOpenChange={setCustodyOpen} />
      <CondemnAssetDialog     assetId={asset.id} open={condemnOpen} onOpenChange={setCondemnOpen} />
    </div>
  );
}
