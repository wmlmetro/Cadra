import { useState, useEffect } from "react";
import { useLocation, useParams } from "wouter";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { getAsset } from "@/lib/dataProvider";
import StatusPill from "@/components/StatusPill";
import ConditionBadge from "@/components/ConditionBadge";
import {
  ArrowLeft, Monitor, Car, Sofa, User, MapPin, Clock,
  CheckCircle2, AlertCircle, ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";

const WORKFLOW_STEPS = ["Cleared", "In Review", "Disposed"];

function CategoryIcon({ category }: { category: string }) {
  const cls = "w-full h-full text-white";
  if (category === "IT Equipment") return <Monitor className={cls} />;
  if (category === "Fleet / Vehicles") return <Car className={cls} />;
  return <Sofa className={cls} />;
}

function DetailRow({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
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

  const asset = getAsset(id ?? "");

  useEffect(() => {
    setTitle(asset ? asset.name : "Asset Detail");
    setSearchHandler(undefined);
  }, [asset, setTitle, setSearchHandler]);

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

          {/* Smart buttons */}
          <div className="ml-auto flex items-center gap-2 flex-wrap">
            <button className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors" data-testid="button-custodian">
              <User size={12} />
              {asset.custodianName ? `Custodian · ${asset.custodianName}` : "Custodian"}
            </button>
            <button className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors" data-testid="button-location-btn">
              <MapPin size={12} />
              Location
            </button>
            <button className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors" data-testid="button-history">
              <Clock size={12} />
              History · 3
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
                </dl>
              </section>
            </div>
          ),
        },
        {
          label: "Custodian & Assignment",
          content: (
            <div className="space-y-4">
              <dl className="bg-card border border-card-border rounded-xl px-5 py-1">
                <DetailRow label="Custodian Name" value={asset.custodianName} />
                <DetailRow label="IR Number" value={asset.custodianIR} />
                <DetailRow label="Department" value={asset.department} />
                <DetailRow label="Zone" value={asset.location.zone} />
                <DetailRow label="State" value={asset.location.state} />
                <DetailRow label="Office" value={asset.location.office} />
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

              <div className="flex gap-3">
                <button
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold bg-green-600 hover:bg-green-700 text-white transition-colors"
                  onClick={() => console.log("Approve", asset.id)}
                  data-testid="button-approve"
                >
                  <CheckCircle2 size={14} /> Approve
                </button>
                <button
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold border border-amber-300 dark:border-amber-700 text-amber-700 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-900/20 transition-colors"
                  onClick={() => console.log("Override", asset.id)}
                  data-testid="button-override"
                >
                  Override
                </button>
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
    </div>
  );
}
