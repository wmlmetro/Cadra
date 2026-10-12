import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "wouter";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import BarcodeScanner from "@/components/BarcodeScanner";
import { SCAN_FORMAT_LABELS, type ScanFormat } from "@/lib/scanFormats";
import {
  fetchBarcodeKpis, fetchBarcodeRecentTags, lookupBarcode,
  fetchUntaggedAssets, generateBarcodes, fetchTag, fetchPendingTagReplacements, fetchAssetTagging,
  fetchAssetIdentification,
  type BarcodeTag, type BarcodeLookupHit, type BarcodeMatchedBy, type UntaggedAsset, type TagLabel,
  type TagReplacementRaised, type TagReplacementApproved, type AssetTagging, type ConfirmAffixedResult,
} from "@/lib/dataProvider";
// The FM domain set and its labels come from the server, not from a constant
// in dataProvider. There used to be two identical hand-written copies of that
// set in that one file; this screen imported one of them.
import { useEnum, useEnumLabel } from "@/hooks/useEnums";
import { CadraApiError } from "@/lib/api";
import { printLabels, floorRoomFromTag, LABEL_SIZES, type LabelData, type LabelSize } from "@/lib/labels";
import {
  RequestTagReplacementDialog, ApproveTagReplacementDialog, RejectTagReplacementDialog,
} from "@/components/TagReplacementDialogs";
import { ConfirmAffixedDialog } from "@/components/ConfirmAffixedDialog";
import { useScopes, SCOPE } from "@/hooks/use-scopes";
import {
  ScanBarcode, AlertCircle, Tag, Package, AlertTriangle, XCircle,
  ArrowRight, Search, Printer, Keyboard, Camera, SearchX, Sparkles, Check,
  RefreshCw, Hourglass,
} from "lucide-react";
import { cn, formatIsoDateTime } from "@/lib/utils";

const MATCHED_BY_WORDS: Record<BarcodeMatchedBy, string> = {
  tag_number: "Found by tag",
  asset_code: "Found by asset code",
  serial_number: "Found by serial number",
};

type Mode = "type" | "camera";
type Notice = { kind: "error" | "warn" | "ok"; text: string } | null;

export default function BarcodeStation() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const [, nav] = useLocation();
  // Handoffs 46/47: the station is three jobs held by different people, and
  // each control is drawn only for the scope its route requires. Minting a
  // barcode, asking for a replacement and confirming a label on the asset
  // are all `tagging:write` since handoff 47 — issuing and replacing a tag
  // is tagging, not asset-writing, so the Tag-Issuing Unit's own scope now
  // covers the unit's own job (until then the unit could confirm a label
  // and not print one, while every Asset Manager could). Deciding a
  // replacement stays `approvals:write` — the second person. Looking up,
  // reading and printing are reads, and stay for everybody who reaches the
  // page.
  const scopes = useScopes();
  const canGenerate = scopes.has(SCOPE.taggingWrite);
  const canRequestReplacement = scopes.has(SCOPE.taggingWrite);
  const canDecideReplacement = scopes.has(SCOPE.approvalsWrite);
  const canTag = scopes.has(SCOPE.taggingWrite);

  useEffect(() => {
    setTitle("Barcode Station");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const domainOptions = useEnum("domain");
  const domainLabelOf = useEnumLabel("domain");
  // `condition` comes off the tag/asset payloads as the raw
  // `nrs.asset.condition` key, so printing it straight put `decommissioned` in
  // front of a tagging clerk. The model's labels are what the rest of the app
  // shows; this screen now agrees with it.
  const conditionLabelOf = useEnumLabel("condition");
  // The tag's state pill used to print the raw key (`pending`); the model's
  // label is "Replacement Pending", which is what a clerk needs to read.
  const tagStateLabelOf = useEnumLabel("tag_state");
  const replacementReasonLabelOf = useEnumLabel("tag_replacement_reason");

  const kpis   = useQuery({ queryKey: ["barcode-kpis"],   queryFn: fetchBarcodeKpis,   staleTime: 30_000 });
  const recent = useQuery({ queryKey: ["barcode-recent"], queryFn: () => fetchBarcodeRecentTags({ limit: 200 }), staleTime: 30_000 });

  const [mode, setMode] = useState<Mode>("type");
  const [query, setQuery] = useState("");
  // Which symbology the camera read the current query off, when it was the
  // camera that filled it. Typing clears it: a typed string has no format.
  const [scanFormat, setScanFormat] = useState<ScanFormat | null>(null);
  const scanBoxRef = useRef<HTMLInputElement>(null);
  const [size, setSize] = useState<LabelSize>("standard");
  const [domain, setDomain] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [notice, setNotice] = useState<Notice>(null);

  const lookup = useMutation({ mutationFn: (q: string) => lookupBarcode(q) });

  // `untagged` is derived server-side as total assets minus active tags, which
  // goes negative on any asset carrying more than one active tag. Floor it —
  // a negative count of untagged assets is meaningless to the user.
  const raw = kpis.data;
  const k = {
    total_assets: raw?.total_assets ?? 0,
    active_tags: raw?.active_tags ?? 0,
    pending_replacement: raw?.pending_replacement ?? 0,
    scrapped_tags: raw?.scrapped_tags ?? 0,
    untagged: Math.max(0, raw?.untagged ?? 0),
  };

  function runLookup(q: string) {
    const trimmed = q.trim();
    if (!trimmed) return;
    setQuery(trimmed);
    setNotice(null);
    lookup.mutate(trimmed);
  }

  // A re-lookup the page triggers itself (after a write) keeps the notice
  // and puts the query it is actually running into the box, so the "Found
  // by …" badge never describes a different string from the one shown.
  function relookup(q: string) {
    setQuery(q);
    lookup.mutate(q);
  }

  // A miss is a 404 `not_found` — `/api/v1/barcode/lookup` runs the station
  // controller's `{found: false}` through `_delegate_failure` and the error
  // envelope is thrown by `parseEnvelope` — so it lands in `lookup.error`,
  // never in `lookup.data`. An ambiguous serial (one serial on several
  // assets) is the same 404 with `details.ambiguous` and `details.matches`.
  const result = lookup.data;
  const hit: BarcodeLookupHit | null = result && result.found ? result : null;
  const lookupErr = lookup.error as CadraApiError | null;
  const missed = lookupErr?.code === "not_found";
  const missDetails = (missed ? lookupErr?.details : null) as
    { ambiguous?: boolean; matches?: number; matched_by?: string } | null | undefined;
  const ambiguousCount = missDetails?.ambiguous && typeof missDetails.matches === "number"
    ? missDetails.matches : null;

  // The pending replacement, when the hit's tag is one. `fetchTag` is what
  // knows the reason, who asked, who was asked and whether THIS user may
  // decide; the lookup payload carries only the tag's number and state.
  const pendingTag = useQuery({
    queryKey: ["tag", hit?.tag_id],
    queryFn: () => fetchTag(hit!.tag_id!),
    enabled: Boolean(hit && hit.tag_id && hit.tag_state === "pending"),
    staleTime: 10_000,
  });
  const pendingList = useQuery({
    queryKey: ["tag-pending"],
    queryFn: fetchPendingTagReplacements,
    staleTime: 30_000,
  });

  // ── Confirm affixed (handoff 39) ──────────────────────────────────────
  //
  // The lookup payload carries the TAG's state (active / pending / scrapped)
  // and not the LABEL's (issued → printed → affixed), so the card reads the
  // asset's `tagging` block to know whether this label is still waiting to
  // be confirmed on the asset or, once it is, who fitted it and when. Read
  // only for an active tag: a pending one is somebody else's decision and a
  // card with no tag has nothing to confirm. `label_id` is compared with the
  // scan box's `tag_id` so a block describing another label is not trusted.
  const tagging = useQuery({
    queryKey: ["asset-tagging", hit?.asset_id],
    queryFn: () => fetchAssetTagging(hit!.asset_id),
    enabled: Boolean(hit && hit.tag_id && hit.tag_state === "active"),
    staleTime: 10_000,
  });
  const label: AssetTagging | null =
    hit && tagging.data && tagging.data.label_id === hit.tag_id ? tagging.data : null;
  // The block describes a different label from the one scanned: the asset
  // carries more than one non-scrapped label (the lookup returns the matched
  // active tag, the block the one physically on the asset). Rare, and said
  // rather than rendered as nothing.
  const labelMismatch = Boolean(
    hit && tagging.data && tagging.data.label_id !== null && tagging.data.label_id !== hit.tag_id,
  );
  // How the unit is identified (handoff 58): a `tag_id` unit is confirmed
  // by its label and a tick that the item matches its attributes, not by a
  // serial. The lookup payload carries neither the mode nor the attributes,
  // so they are read off the asset, as the `tagging` block is, and the
  // button waits for them — a dialog opened before they arrived would offer
  // a serial field to a unit that has none to check.
  const identification = useQuery({
    queryKey: ["asset-identification", hit?.asset_id],
    queryFn: () => fetchAssetIdentification(hit!.asset_id),
    enabled: Boolean(hit && hit.tag_id && hit.tag_state === "active"),
    staleTime: 60_000,
  });
  const canConfirmAffixed = Boolean(
    canTag && label && hit?.tag_state === "active"
      && label.label_state !== "affixed" && label.label_state !== "scrapped"
      && identification.data,
  );
  const [affixOpen, setAffixOpen] = useState(false);

  const [replaceOpen, setReplaceOpen] = useState(false);
  const [deciding, setDeciding] = useState<{ tag: TagLabel; action: "approve" | "reject" } | null>(null);
  const [printableNewTag, setPrintableNewTag] = useState<TagLabel | null>(null);

  const tags = recent.data ?? [];
  const visible = useMemo(
    () => (domain ? tags.filter((t) => t.domain === domain) : tags),
    [tags, domain],
  );

  // Only ever act on rows the current filter shows, so a stale selection from
  // another domain can't be printed by surprise.
  const visibleIds = useMemo(() => new Set(visible.map((t) => t.tag_id)), [visible]);
  const selectedVisible = useMemo(
    () => visible.filter((t) => selected.has(t.tag_id)),
    [visible, selected],
  );
  const allVisibleSelected = visible.length > 0 && selectedVisible.length === visible.length;

  function toggleRow(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) visibleIds.forEach((id) => next.delete(id));
      else visibleIds.forEach((id) => next.add(id));
      return next;
    });
  }

  /** `keepNotice` leaves an existing message in place — used when printing
   *  follows generation, so "Generated 12 barcodes" survives a clean print. */
  async function print(labels: LabelData[], keepNotice = false) {
    if (!keepNotice) setNotice(null);
    try {
      const res = await printLabels(labels, size);
      if (res.qrUnavailable) {
        setNotice({
          kind: "warn",
          text: "QR codes could not be loaded from the server, so labels printed with the Code128 barcode only.",
        });
      }
    } catch (e) {
      setNotice({ kind: "error", text: e instanceof Error ? e.message : "Could not open the print view." });
    }
  }

  const printHit = () =>
    hit && print([{
      tag_number: hit.tag_number,
      asset_name: hit.asset_name,
      asset_code: hit.asset_code,
      location: hit.location,
      category: hit.category,
      custodian: hit.custodian,
      floor_room: floorRoomFromTag(hit.tag_number),
    }]);

  const printSelected = () =>
    print(selectedVisible.map((t) => ({
      tag_number: t.tag_number,
      asset_name: t.asset_name,
      location: t.location,
      floor_room: floorRoomFromTag(t.tag_number),
    })));

  // ── Barcode generation ────────────────────────────────────────────────
  const qc = useQueryClient();
  const [assetQuery, setAssetQuery] = useState("");
  const [assetSearch, setAssetSearch] = useState("");
  const [pickedAssets, setPickedAssets] = useState<Set<number>>(new Set());

  const untagged = useQuery({
    queryKey: ["barcode-untagged", assetSearch],
    queryFn: () => fetchUntaggedAssets({ q: assetSearch || undefined, limit: 200 }),
    staleTime: 30_000,
  });

  const generate = useMutation({
    mutationFn: (ids: number[]) => generateBarcodes(ids),
    onSuccess: (res) => {
      setPickedAssets(new Set());
      // The new tags change the untagged list, the KPI counts and the tag
      // inventory, so refetch all three rather than patching caches by hand.
      qc.invalidateQueries({ queryKey: ["barcode-untagged"] });
      qc.invalidateQueries({ queryKey: ["barcode-kpis"] });
      qc.invalidateQueries({ queryKey: ["barcode-recent"] });
      // A tag issued is an event in each of those assets' histories.
      qc.invalidateQueries({ queryKey: ["asset-history"] });

      const made = res.generated.length;
      const already = res.skipped.filter((s) => s.reason === "already_tagged").length;
      const missing = res.skipped.filter((s) => s.reason === "not_found").length;
      const extra = [
        already ? `${already} already had one` : "",
        missing ? `${missing} no longer exist` : "",
      ].filter(Boolean).join(", ");
      setNotice({
        kind: made ? "ok" : "warn",
        text: `Generated ${made} barcode${made === 1 ? "" : "s"}${extra ? ` — ${extra}.` : "."}`,
      });
    },
    onError: (e) => {
      const err = e as CadraApiError;
      setNotice({ kind: "error", text: `${err.code ?? "error"}: ${err.message}` });
    },
  });

  const untaggedRows = untagged.data ?? [];
  const pickedRows = useMemo(
    () => untaggedRows.filter((a) => pickedAssets.has(a.asset_id)),
    [untaggedRows, pickedAssets],
  );
  const allPicked = untaggedRows.length > 0 && pickedRows.length === untaggedRows.length;

  function togglePicked(id: number) {
    setPickedAssets((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function togglePickAll() {
    setPickedAssets((prev) => {
      const next = new Set(prev);
      for (const a of untaggedRows) {
        if (allPicked) next.delete(a.asset_id); else next.add(a.asset_id);
      }
      return next;
    });
  }

  /** Mint barcodes, then send the ones just created straight to the printer —
   *  generating and labelling is one job in the field, not two. */
  async function generateAndPrint() {
    let res;
    try {
      res = await generate.mutateAsync([...pickedAssets]);
    } catch {
      return;  // the mutation's onError has already surfaced it
    }
    if (!res.generated.length) return;
    await print(res.generated.map((g) => ({
      tag_number: g.tag_number,
      asset_name: g.asset_name,
      asset_code: g.asset_code,
      location: g.location,
      floor_room: floorRoomFromTag(g.tag_number),
    })), true);
  }

  // ── Tag replacement (handoff 38) ──────────────────────────────────────
  //
  // Every handler below re-runs the LOOKUP rather than patching the card:
  // the card is the server's answer to a scan, and after any of these the
  // answer has changed. A pending tag's NUMBER stops resolving (only active
  // tags match by number — unchanged, on purpose), so the re-run goes by
  // asset code; after an approval it goes by the NEW number, which proves
  // the new label resolves before anybody prints it.

  /** Mint a barcode for the asset on the card, then look it up again so the
   *  card shows the number it just got. */
  async function generateForHit() {
    if (!hit) return;
    const code = hit.asset_code;
    try {
      await generate.mutateAsync([hit.asset_id]);
    } catch {
      return;  // the mutation's onError has already surfaced it
    }
    if (code) relookup(code);
  }

  function onReplacementRaised(res: TagReplacementRaised) {
    setNotice({
      kind: "ok",
      text: `Replacement of ${res.tag.tag_number} requested — waiting on ${res.tag.approver?.name ?? "the approver"}. Nothing is scrapped or minted until they decide; look the asset up by its code meanwhile.`,
    });
    if (hit?.asset_code) relookup(hit.asset_code);
  }

  function onReplacementApproved(res: TagReplacementApproved) {
    setPrintableNewTag(res.new_tag);
    setNotice({
      kind: "ok",
      text: `${res.tag.tag_number} scrapped; new tag ${res.new_tag.tag_number} minted for ${res.new_tag.asset.name}. Print it.`,
    });
    relookup(res.new_tag.tag_number);
  }

  function onReplacementRejected(tag: TagLabel) {
    setNotice({ kind: "warn", text: `Replacement of ${tag.tag_number} rejected — the label stays active.` });
    if (hit && hit.asset_id === tag.asset.id && hit.asset_code) relookup(hit.asset_code);
  }

  // The card is not re-looked-up after a confirmation: the lookup answer does
  // not change (the tag stays `active`), only the `tagging` block does, and
  // the dialog invalidates that query. The success notice names the number
  // because the dialog has closed by then. The "already" notice does NOT —
  // that dialog stays open, in its result state, over the blurred page.
  function onAffixConfirmed(res: ConfirmAffixedResult) {
    const who = res.tagging.affixed_by_name ?? res.tagging.affixed_by?.name;
    setNotice({
      kind: "ok",
      text: `Label ${res.tagging.tag_number} confirmed on ${res.asset.name}${who ? `, fitted by ${who}` : ""}. The asset now reads as tagged.`,
    });
  }

  function onAffixAlready(t: AssetTagging) {
    setNotice({
      kind: "warn",
      text: `This label was already confirmed on ${formatIsoDateTime(t.affixed_at)}; nothing was changed.`,
    });
  }

  const printNewTag = () =>
    printableNewTag && print([{
      tag_number: printableNewTag.tag_number,
      asset_name: printableNewTag.asset.name,
      asset_code: printableNewTag.asset_code,
      floor_room: floorRoomFromTag(printableNewTag.tag_number),
    }], true);

  return (
    // Blurred while the confirm dialog is open. The dialog's overlay dims the
    // page but leaves it legible, and the tag number is on this page in
    // several places — the scan box, the card, the recent-tags table — any
    // of which would hand the person the number the check exists to take
    // off the physical label. A blur, not a removal: the text stays in the
    // DOM, illegible and unselectable. The dialog is portaled, so it is not
    // blurred.
    <div className={cn("p-6 space-y-5 max-w-[1100px] mx-auto", affixOpen && "blur-md select-none")} data-testid="barcode-station" data-blurred={affixOpen ? "true" : undefined}>
      <div>
        <h1 className="text-xl font-bold text-foreground">Barcode Station</h1>
        <p className="text-xs text-muted-foreground mt-1">
          Look up an asset by tag, asset code or serial number, generate barcodes for untagged assets, replace a damaged tag, and print labels.
        </p>
      </div>

      {kpis.error && (
        <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3">
          <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
          <p className="text-[12px] text-red-700 dark:text-red-400">
            <span className="font-semibold">{(kpis.error as CadraApiError).code}:</span> {(kpis.error as CadraApiError).message}
          </p>
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <KpiTile label="Total assets"        value={k.total_assets}        icon={Package}        color="text-foreground" />
        <KpiTile label="Active tags"         value={k.active_tags}         icon={Tag}            color="text-green-600 dark:text-green-400" />
        <KpiTile label="Pending replacement" value={k.pending_replacement} icon={AlertTriangle}  color="text-amber-600 dark:text-amber-400" />
        <KpiTile label="Scrapped"            value={k.scrapped_tags}       icon={XCircle}        color="text-red-600 dark:text-red-400" />
        <KpiTile label="Untagged"            value={k.untagged}            icon={Tag}            color="text-muted-foreground" />
      </div>

      {notice && <Notice notice={notice} />}
      {printableNewTag && (
        <div className="flex items-center gap-2 -mt-2">
          <button
            type="button"
            onClick={() => void printNewTag()}
            data-testid="button-print-new-tag"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-primary text-white text-[11px] font-semibold hover:opacity-90"
          >
            <Printer size={12} /> Print new label {printableNewTag.tag_number}
          </button>
          <SizePicker value={size} onChange={setSize} />
        </div>
      )}

      {/* Scan / lookup */}
      <div className="bg-card border border-border rounded-2xl p-5 space-y-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <ScanBarcode size={14} className="text-primary" />
            <h2 className="text-[13px] font-bold">Scan or type a tag, asset code or serial number</h2>
          </div>
          <div className="flex items-center gap-1 rounded-xl border border-border p-0.5">
            <ModeButton active={mode === "type"}   onClick={() => setMode("type")}   icon={Keyboard} label="Type" />
            <ModeButton active={mode === "camera"} onClick={() => setMode("camera")} icon={Camera}   label="Camera" />
          </div>
        </div>

        {/* The input stays mounted in camera mode: handheld scanners emulate a
            keyboard, and a detected code is written straight into it. */}
        <form onSubmit={(e) => { e.preventDefault(); runLookup(query); }} className="flex gap-2">
          <div className="relative flex-1">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60 pointer-events-none" />
            {/* Emptied while the confirm dialog is open: when the lookup was
                by tag, this box IS the expected number. The query itself is
                kept, so nothing is lost on close. */}
            <input
              autoFocus
              ref={scanBoxRef}
              type="search"
              value={affixOpen ? "" : query}
              onChange={(e) => { setQuery(e.target.value); setScanFormat(null); }}
              data-testid="scan-box"
              placeholder={affixOpen ? "Hidden while you confirm" : "Tag, asset code or serial number — e.g. NRS-LT-00422"}
              className="w-full pl-7 pr-3 py-2 text-sm border border-border rounded-xl bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>
          <button
            type="submit"
            disabled={!query.trim() || lookup.isPending}
            className={cn(
              "px-4 py-2 text-xs font-semibold rounded-xl",
              query.trim() && !lookup.isPending ? "bg-primary text-white hover:opacity-90" : "bg-muted text-muted-foreground cursor-not-allowed",
            )}
          >
            {lookup.isPending ? "Looking up…" : "Lookup"}
          </button>
        </form>

        {mode === "camera" && (
          <BarcodeScanner
            onDetected={(value, format) => { setScanFormat(format); setMode("type"); runLookup(value); }}
            // After 10 s with nothing read, the scanner offers typing; the
            // box is already mounted (handheld scanners land in it), so
            // only focus moves. The camera keeps running.
            onSuggestType={() => scanBoxRef.current?.focus()}
          />
        )}

        {scanFormat && !affixOpen && (
          <p className="text-[11px] text-muted-foreground" data-testid="scan-format">
            Camera read: {SCAN_FORMAT_LABELS[scanFormat]}.
          </p>
        )}

        {lookupErr && !missed && (
          <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3 flex items-start gap-2">
            <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
            <p className="text-[12px] text-red-700 dark:text-red-400">
              <span className="font-semibold">{lookupErr.code}:</span> {lookupErr.message}
            </p>
          </div>
        )}

        {missed && (
          <div className="bg-muted/30 border border-border rounded-xl p-3 flex items-start gap-2" data-testid="lookup-miss">
            <SearchX size={14} className="text-muted-foreground shrink-0 mt-0.5" />
            <p className="text-[12px] text-muted-foreground">
              {ambiguousCount !== null ? (
                <>
                  Serial number <span className="font-mono font-semibold text-foreground">{query}</span> is
                  on <span className="font-semibold text-foreground">{ambiguousCount}</span> assets, so
                  it cannot pick one. Scan the tag or the asset code instead.
                </>
              ) : (
                <>
                  No active tag, asset code or serial number matches <span className="font-mono font-semibold text-foreground">{query}</span>.
                  Check the code, or search the register.
                </>
              )}
            </p>
          </div>
        )}

        {hit && (
          <div className="bg-background border border-primary/30 rounded-xl p-4 space-y-3" data-testid="lookup-result">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[14px] font-bold text-foreground">{hit.asset_name}</p>
                {/* Covered while the confirm dialog is open: the number has
                    to come off the label in the person's hand, not off the
                    card behind the dialog. */}
                <p className="text-[12px] text-muted-foreground font-mono" data-testid="lookup-tag-number">
                  {affixOpen
                    ? <span className="font-sans italic" data-testid="lookup-tag-number-hidden">Tag number hidden while you confirm</span>
                    : (hit.tag_number || "No tag")}
                </p>
              </div>
              <div className="shrink-0 flex items-center gap-1.5">
                {/* Which field the scan hit. A serial lookup that looked like a
                    tag lookup is how a wrong claim gets made in a demo. */}
                <span
                  className="inline-flex items-center px-2 py-0.5 rounded-lg text-[11px] font-semibold border bg-primary/5 border-primary/30 text-primary"
                  data-testid="lookup-matched-by"
                >{MATCHED_BY_WORDS[hit.matched_by] ?? `Found by ${hit.matched_by}`}</span>
                {hit.tag_state && (
                  <span className={cn(
                    "inline-flex items-center px-2 py-0.5 rounded-lg text-[11px] font-semibold border",
                    hit.tag_state === "active"
                      ? "bg-green-50 dark:bg-green-950/30 border-green-200/70 text-green-700 dark:text-green-400"
                      : hit.tag_state === "pending"
                      ? "bg-amber-50 dark:bg-amber-950/30 border-amber-200/70 text-amber-700 dark:text-amber-400"
                      : "bg-muted border-border text-muted-foreground",
                  )} data-testid="lookup-tag-state">{tagStateLabelOf(hit.tag_state)}</span>
                )}
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-2 text-[11px]">
              <Field label="Asset code" value={hit.asset_code} mono />
              <Field label="Serial number" value={hit.serial_number} mono />
              <Field label="Category"   value={hit.category} />
              <Field label="Domain"     value={domainLabelOf(hit.domain)} />
              <Field label="Location"   value={hit.location} />
              <Field label="Custodian"  value={hit.custodian} />
              <Field label="Condition"  value={conditionLabelOf(hit.condition)} />
              <Field label="Last service" value={hit.last_service_date} />
              <Field label="Next service" value={hit.next_service_date} />
              <Field label="SAP number"   value={hit.sap_asset_number} mono />
            </div>

            {/* No active tag and no pending one either: the asset was found by
                code or serial and has never been labelled, or its label was
                scrapped. Mint one here rather than sending the clerk to the
                picker below to find it again. */}
            {!hit.tagged && !hit.tag_id && (
              <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200/70 dark:border-amber-800/30 rounded-xl p-3 flex items-center justify-between gap-3 flex-wrap" data-testid="lookup-no-tag">
                <p className="text-[12px] text-amber-700 dark:text-amber-400 inline-flex items-center gap-1.5">
                  <AlertTriangle size={13} /> No active tag on this asset.
                </p>
                {canGenerate && (
                  <button
                    type="button"
                    disabled={generate.isPending}
                    onClick={() => void generateForHit()}
                    data-testid="button-generate-for-hit"
                    className={cn(
                      "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[11px] font-semibold",
                      generate.isPending ? "bg-muted text-muted-foreground cursor-not-allowed" : "bg-primary text-white hover:opacity-90",
                    )}
                  >
                    <Tag size={12} /> {generate.isPending ? "Generating…" : "Generate barcode"}
                  </button>
                )}
              </div>
            )}

            {hit.tag_state === "active" && hit.tag_id && (
              <LabelStatePanel
                label={label}
                mismatch={labelMismatch}
                loading={tagging.isLoading}
                error={tagging.error as CadraApiError | null}
              />
            )}

            {hit.tag_state === "pending" && (
              <PendingTagPanel
                tag={pendingTag.data ?? null}
                loading={pendingTag.isLoading}
                error={pendingTag.error as CadraApiError | null}
                reasonLabelOf={replacementReasonLabelOf}
                mayDecide={canDecideReplacement}
                onApprove={(t) => setDeciding({ tag: t, action: "approve" })}
                onReject={(t) => setDeciding({ tag: t, action: "reject" })}
              />
            )}

            <div className="flex flex-wrap items-center gap-2 pt-1">
              {hit.tagged && (
                <button
                  onClick={() => void printHit()}
                  className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-primary text-white text-xs font-semibold hover:opacity-90"
                >
                  <Printer size={12} /> Print label
                </button>
              )}
              {canConfirmAffixed && (
                <button
                  type="button"
                  onClick={() => setAffixOpen(true)}
                  data-testid="button-confirm-affixed"
                  className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-green-600 text-white text-xs font-semibold hover:bg-green-700"
                >
                  <Check size={12} /> Confirm affixed
                </button>
              )}
              {canRequestReplacement && hit.tag_state === "active" && hit.tag_id && (
                <button
                  type="button"
                  onClick={() => setReplaceOpen(true)}
                  data-testid="button-replace-tag"
                  className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-border text-xs font-semibold hover:bg-muted/40"
                >
                  <RefreshCw size={12} /> Replace tag
                </button>
              )}
              {hit.asset_id > 0 && (
                <button
                  onClick={() => nav(`/assets/${hit.asset_id}`)}
                  className="inline-flex items-center gap-1 px-3 py-2 rounded-xl border border-border text-xs font-semibold hover:bg-muted/40"
                >
                  Open asset <ArrowRight size={11} />
                </button>
              )}
              <SizePicker value={size} onChange={setSize} />
            </div>
          </div>
        )}
      </div>

      {/* Tag replacements waiting on a decision */}
      <div className="bg-card border border-border rounded-2xl p-5" data-testid="pending-replacements">
        <div className="flex items-start justify-between gap-3 flex-wrap mb-3">
          <div>
            <h2 className="text-[13px] font-bold inline-flex items-center gap-1.5">
              <Hourglass size={13} className="text-amber-600 dark:text-amber-400" /> Pending replacements
            </h2>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Labels somebody has asked to replace. The old number is scrapped and a new one minted only on approval.
            </p>
          </div>
        </div>

        {pendingList.error && (
          <p className="text-[12px] text-red-700 dark:text-red-400 py-2">
            {(pendingList.error as CadraApiError).code}: {(pendingList.error as CadraApiError).message}
          </p>
        )}

        {pendingList.isLoading ? (
          <p className="text-[12px] text-muted-foreground py-4 text-center">Loading…</p>
        ) : (pendingList.data?.tags ?? []).length === 0 ? (
          <p className="text-[12px] text-muted-foreground py-4 text-center inline-flex items-center gap-1.5 w-full justify-center" data-testid="pending-replacements-empty">
            <Check size={12} className="text-green-600 dark:text-green-400" /> Nothing waiting.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px]">
              <thead>
                <tr className="border-b border-border">
                  {["Tag", "Asset", "Reason", "Requested by", "Asked", ""].map((h, i) => (
                    <th key={i} className="text-left px-3 py-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(pendingList.data?.tags ?? []).map((t) => (
                  <PendingRow
                    key={t.id}
                    tag={t}
                    reasonLabelOf={replacementReasonLabelOf}
                    mayDecide={canDecideReplacement}
                    onOpen={() => nav(`/assets/${t.asset.id}`)}
                    onApprove={() => setDeciding({ tag: t, action: "approve" })}
                    onReject={() => setDeciding({ tag: t, action: "reject" })}
                  />
                ))}
              </tbody>
            </table>
            {/* A list that ends says whether it is the end — handoff 52 §2.
                This panel rendered one page of 100 as the whole of what was
                waiting (test19 held 214, the panel showed 100, nothing said
                so). The station is a scan console, not the decision queue:
                the full, paged record lives on the Approvals page, so the
                honest cap — the real remainder, from the server's own
                `total_estimate` — was chosen over paging a glance-list. */}
            {pendingList.data?.nextCursor != null && (
              <p className="text-[11px] text-muted-foreground pt-3 px-3" data-testid="pending-replacements-truncated">
                Showing the {(pendingList.data?.tags ?? []).length} most recent
                {pendingList.data?.totalEstimate != null
                  ? ` — ${(pendingList.data.totalEstimate - (pendingList.data?.tags ?? []).length).toLocaleString()} more on the Approvals page.`
                  : " — more are waiting; the full queue is on the Approvals page."}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Generate barcodes for assets that have none */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <div className="flex items-start justify-between gap-3 flex-wrap mb-3">
          <div>
            <h2 className="text-[13px] font-bold inline-flex items-center gap-1.5">
              <Sparkles size={13} className="text-primary" /> {canGenerate ? "Generate barcodes" : "Untagged assets"}
            </h2>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Assets with an asset code but no barcode yet.
              {untaggedRows.length > 0 && ` ${untaggedRows.length} shown`}
              {pickedRows.length > 0 && ` · ${pickedRows.length} picked`}
            </p>
          </div>
          {/* Without `tagging:write` the list stays — which assets have no
              barcode is a read — and the two buttons and the pick boxes
              that only feed them are not drawn (handoffs 46/47). */}
          {canGenerate && (
          <div className="flex flex-wrap items-center gap-2">
            <SizePicker value={size} onChange={setSize} />
            <button
              onClick={() => void generate.mutateAsync([...pickedAssets]).catch(() => {})}
              disabled={pickedRows.length === 0 || generate.isPending}
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[11px] font-semibold border",
                pickedRows.length && !generate.isPending
                  ? "border-border hover:bg-muted/40"
                  : "border-border text-muted-foreground cursor-not-allowed",
              )}
            >
              <Tag size={12} /> Generate only
            </button>
            <button
              onClick={() => void generateAndPrint()}
              disabled={pickedRows.length === 0 || generate.isPending}
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[11px] font-semibold",
                pickedRows.length && !generate.isPending
                  ? "bg-primary text-white hover:opacity-90"
                  : "bg-muted text-muted-foreground cursor-not-allowed",
              )}
            >
              <Printer size={12} />
              {generate.isPending
                ? "Generating…"
                : pickedRows.length
                ? `Generate & print ${pickedRows.length}`
                : "Generate & print"}
            </button>
          </div>
          )}
        </div>

        <form
          onSubmit={(e) => { e.preventDefault(); setAssetSearch(assetQuery.trim()); }}
          className="flex gap-2 mb-3"
        >
          <div className="relative flex-1">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60 pointer-events-none" />
            <input
              type="search"
              value={assetQuery}
              onChange={(e) => setAssetQuery(e.target.value)}
              placeholder="Filter by asset name, asset code, or serial…"
              className="w-full pl-7 pr-3 py-1.5 text-[12px] border border-border rounded-xl bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>
          <button type="submit" className="px-3 py-1.5 text-[11px] font-semibold rounded-xl border border-border hover:bg-muted/40">
            Search
          </button>
        </form>

        {untagged.error && (
          <p className="text-[12px] text-red-700 dark:text-red-400 py-2">
            {(untagged.error as CadraApiError).code}: {(untagged.error as CadraApiError).message}
          </p>
        )}

        {untagged.isLoading ? (
          <p className="text-[12px] text-muted-foreground py-4 text-center">Loading…</p>
        ) : untaggedRows.length === 0 ? (
          <p className="text-[12px] text-muted-foreground py-4 text-center inline-flex items-center gap-1.5 w-full justify-center">
            <Check size={12} className="text-green-600 dark:text-green-400" />
            {assetSearch ? "No untagged assets match that search." : "Every asset has a barcode."}
          </p>
        ) : (
          <div className="overflow-x-auto max-h-[320px] overflow-y-auto">
            <table className="w-full min-w-[620px]">
              <thead className="sticky top-0 bg-card">
                <tr className="border-b border-border">
                  {canGenerate && (
                    <th className="w-8 px-3 py-2">
                      <input
                        type="checkbox"
                        aria-label="Select all untagged assets shown"
                        checked={allPicked}
                        onChange={togglePickAll}
                        className="accent-primary cursor-pointer"
                      />
                    </th>
                  )}
                  {["Asset code", "Asset", "Category", "Location", "Condition"].map((h) => (
                    <th key={h} className="text-left px-3 py-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {untaggedRows.map((a) => (
                  <UntaggedRow
                    key={a.asset_id}
                    asset={a}
                    pickable={canGenerate}
                    checked={pickedAssets.has(a.asset_id)}
                    onToggle={() => togglePicked(a.asset_id)}
                    onOpen={() => nav(`/assets/${a.asset_id}`)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Tag inventory + batch print */}
      <div className="bg-card border border-border rounded-2xl p-5">
        <div className="flex items-start justify-between gap-3 flex-wrap mb-3">
          <div>
            <h2 className="text-[13px] font-bold">Recent tags</h2>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              {visible.length} shown{selectedVisible.length > 0 && ` · ${selectedVisible.length} selected`}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              className="px-2 py-1.5 text-[11px] border border-border rounded-xl bg-background"
            >
              <option value="">All domains</option>
              {domainOptions.map((d) => (
                <option key={d.value} value={d.value}>{d.label}</option>
              ))}
            </select>
            <SizePicker value={size} onChange={setSize} />
            <button
              onClick={() => void printSelected()}
              disabled={selectedVisible.length === 0}
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[11px] font-semibold",
                selectedVisible.length
                  ? "bg-primary text-white hover:opacity-90"
                  : "bg-muted text-muted-foreground cursor-not-allowed",
              )}
            >
              <Printer size={12} />
              {selectedVisible.length ? `Print ${selectedVisible.length} label${selectedVisible.length > 1 ? "s" : ""}` : "Print labels"}
            </button>
          </div>
        </div>

        {recent.error && (
          <p className="text-[12px] text-red-700 dark:text-red-400 py-2">
            {(recent.error as CadraApiError).code}: {(recent.error as CadraApiError).message}
          </p>
        )}

        {visible.length === 0 ? (
          <p className="text-[12px] text-muted-foreground py-4 text-center">
            {tags.length === 0 ? "No recent tags." : "No tags in this domain."}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px]">
              <thead>
                <tr className="border-b border-border">
                  <th className="w-8 px-3 py-2">
                    <input
                      type="checkbox"
                      aria-label="Select all shown tags"
                      checked={allVisibleSelected}
                      onChange={toggleAll}
                      className="accent-primary cursor-pointer"
                    />
                  </th>
                  {["Tag", "Asset", "Domain", "Condition", "Location", "State"].map((h) => (
                    <th key={h} className="text-left px-3 py-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map((t) => (
                  <TagRow
                    key={t.tag_id}
                    tag={t}
                    checked={selected.has(t.tag_id)}
                    onToggle={() => toggleRow(t.tag_id)}
                    onOpen={() => nav(`/assets/${t.asset_id}`)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {hit && hit.tag_id && (
        <ConfirmAffixedDialog
          assetId={hit.asset_id}
          assetName={hit.asset_name}
          hasSerialOnFile={Boolean(hit.serial_number)}
          identificationMode={identification.data?.identification_mode ?? null}
          attributes={identification.data}
          open={affixOpen}
          onOpenChange={setAffixOpen}
          onConfirmed={onAffixConfirmed}
          onAlready={onAffixAlready}
        />
      )}
      {hit && hit.tag_id && (
        <RequestTagReplacementDialog
          tagId={hit.tag_id}
          tagNumber={hit.tag_number}
          open={replaceOpen}
          onOpenChange={setReplaceOpen}
          onRaised={onReplacementRaised}
        />
      )}
      {deciding && deciding.action === "approve" && (
        <ApproveTagReplacementDialog
          tag={deciding.tag}
          open
          onOpenChange={(o) => { if (!o) setDeciding(null); }}
          onApproved={onReplacementApproved}
        />
      )}
      {deciding && deciding.action === "reject" && (
        <RejectTagReplacementDialog
          tag={deciding.tag}
          open
          onOpenChange={(o) => { if (!o) setDeciding(null); }}
          onRejected={() => onReplacementRejected(deciding.tag)}
        />
      )}
    </div>
  );
}

/** Words for `label_state`. Display only — the set is the server's, and a
 *  value outside these two prints as itself rather than as nothing. */
const LABEL_STATE_WORDS: Record<string, string> = {
  issued: "Label issued",
  printed: "Label printed",
};

/**
 * Where this label is in its life, on the card — and once it is affixed, the
 * RECORD instead of a button: who fitted it and when. The confirm button is
 * in the card's action row beside Print label and Replace tag; this panel
 * says what it would do, or what has been done.
 */
function LabelStatePanel({ label, mismatch, loading, error }: {
  label: AssetTagging | null;
  mismatch: boolean;
  loading: boolean;
  error: CadraApiError | null;
}) {
  if (error) {
    return (
      <p className="text-[12px] text-red-700 dark:text-red-400" data-testid="tag-label-state-error">
        <span className="font-semibold">{error.code}:</span> {error.message}
      </p>
    );
  }
  if (mismatch) {
    return (
      <p className="text-[11px] text-muted-foreground" data-testid="tag-label-state-mismatch">
        This asset carries more than one label and the one on record is not the one scanned, so it cannot be confirmed from here. Open the asset.
      </p>
    );
  }
  if (!label) {
    return loading
      ? <p className="text-[11px] text-muted-foreground" data-testid="tag-label-state-loading">Checking the label…</p>
      : null;
  }
  if (label.label_state === "affixed") {
    const who = label.affixed_by_name ?? label.affixed_by?.name;
    return (
      <div className="bg-green-50 dark:bg-green-950/30 border border-green-200/70 dark:border-green-800/30 rounded-xl p-3" data-testid="tag-affixed-state">
        <p className="text-[12px] font-semibold text-green-700 dark:text-green-400 inline-flex items-center gap-1.5">
          <Check size={13} /> Label confirmed on the asset
        </p>
        <p className="text-[11px] text-green-700/90 dark:text-green-400/90 mt-0.5">
          {formatIsoDateTime(label.affixed_at) || "date not recorded"}
          {who ? <> · fitted by <span className="font-semibold" data-testid="tag-affixed-by">{who}</span></> : null}
        </p>
      </div>
    );
  }
  return (
    <div className="bg-muted/30 border border-border rounded-xl p-3" data-testid="tag-label-state">
      <p className="text-[12px] font-semibold text-foreground inline-flex items-center gap-1.5">
        <Tag size={13} className="text-muted-foreground" />
        {LABEL_STATE_WORDS[label.label_state ?? ""] ?? label.label_state}
        {label.label_state === "printed" && label.printed_at ? ` ${formatIsoDateTime(label.printed_at)}` : ""}
      </p>
      <p className="text-[11px] text-muted-foreground mt-0.5">
        Not yet confirmed on the asset. When the label is fixed on, scan it with <span className="font-semibold">Confirm affixed</span>; the asset reads as tagged only after that.
      </p>
    </div>
  );
}

/**
 * What a pending replacement is waiting on, read from the tag itself. The
 * Approve / Reject buttons appear only when the server says THIS user may
 * decide (`can_decide`), which is false for the requester — the refusal is
 * in the model, and the screen simply does not offer it.
 */
function PendingTagPanel({ tag, loading, error, reasonLabelOf, mayDecide, onApprove, onReject }: {
  tag: TagLabel | null;
  loading: boolean;
  error: CadraApiError | null;
  reasonLabelOf: (v: string | null | undefined) => string;
  /** `approvals:write`, what the two decision routes require (handoff 46).
   *  `can_decide` is the server's answer about THIS tag; the scope is the
   *  session's answer about every tag. Both have to be yes. */
  mayDecide: boolean;
  onApprove: (t: TagLabel) => void;
  onReject: (t: TagLabel) => void;
}) {
  return (
    <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200/70 dark:border-amber-800/30 rounded-xl p-3 space-y-2" data-testid="tag-pending-panel">
      <p className="text-[12px] font-semibold text-amber-700 dark:text-amber-400 inline-flex items-center gap-1.5">
        <Hourglass size={13} /> Replacement pending
      </p>
      {error && (
        <p className="text-[12px] text-red-700 dark:text-red-400">
          <span className="font-semibold">{error.code}:</span> {error.message}
        </p>
      )}
      {loading && !tag && <p className="text-[12px] text-muted-foreground">Loading…</p>}
      {tag && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-2 text-[11px]">
            <Field label="Reason" value={reasonLabelOf(tag.replacement_reason)} />
            <Field label="Requested by" value={tag.requested_by?.name} />
            <Field label="Approver asked" value={tag.approver?.name} />
            {tag.replacement_notes && (
              <div className="col-span-2 sm:col-span-3 min-w-0">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Notes</p>
                <p className="text-foreground">{tag.replacement_notes}</p>
              </div>
            )}
          </div>
          {tag.can_decide && mayDecide ? (
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <button
                type="button"
                onClick={() => onApprove(tag)}
                data-testid="button-approve-replacement"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-green-600 text-white text-[11px] font-semibold hover:bg-green-700"
              >
                <Check size={12} /> Approve
              </button>
              <button
                type="button"
                onClick={() => onReject(tag)}
                data-testid="button-reject-replacement"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-border text-[11px] font-semibold hover:bg-muted/40"
              >
                <XCircle size={12} /> Reject
              </button>
            </div>
          ) : (
            <p className="text-[11px] text-muted-foreground">
              Waiting on {tag.approver?.name ?? "the approver"}. {tag.requested_by ? "The person who asked cannot approve it." : ""}
            </p>
          )}
        </>
      )}
    </div>
  );
}

function PendingRow({ tag, reasonLabelOf, mayDecide, onOpen, onApprove, onReject }: {
  tag: TagLabel;
  reasonLabelOf: (v: string | null | undefined) => string;
  /** `approvals:write` — see PendingTagPanel. */
  mayDecide: boolean;
  onOpen: () => void;
  onApprove: () => void;
  onReject: () => void;
}) {
  return (
    <tr className="border-b border-border/40 hover:bg-muted/20" data-testid="pending-replacement-row" data-tag={tag.tag_number}>
      <td onClick={onOpen} className="px-3 py-2 text-[12px] font-mono cursor-pointer">{tag.tag_number}</td>
      <td onClick={onOpen} className="px-3 py-2 text-[12px] truncate max-w-[200px] cursor-pointer">{tag.asset.name}</td>
      <td className="px-3 py-2 text-[12px]">{reasonLabelOf(tag.replacement_reason)}</td>
      <td className="px-3 py-2 text-[12px] text-muted-foreground">{tag.requested_by?.name ?? "—"}</td>
      <td className="px-3 py-2 text-[12px] text-muted-foreground">{tag.approver?.name ?? "—"}</td>
      <td className="px-3 py-2 text-[11px]">
        {tag.can_decide && mayDecide ? (
          <div className="flex items-center gap-1.5 justify-end">
            <button
              type="button"
              onClick={onApprove}
              data-testid="button-approve-replacement"
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-green-600 text-white font-semibold hover:bg-green-700"
            >
              <Check size={11} /> Approve
            </button>
            <button
              type="button"
              onClick={onReject}
              data-testid="button-reject-replacement"
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-border font-semibold hover:bg-muted/40"
            >
              <XCircle size={11} /> Reject
            </button>
          </div>
        ) : (
          <span className="text-muted-foreground">Not yours to decide</span>
        )}
      </td>
    </tr>
  );
}

function TagRow({ tag, checked, onToggle, onOpen }: {
  tag: BarcodeTag; checked: boolean; onToggle: () => void; onOpen: () => void;
}) {
  const domainLabelOf = useEnumLabel("domain");
  const conditionLabelOf = useEnumLabel("condition");
  return (
    <tr className={cn("border-b border-border/40 hover:bg-muted/20", checked && "bg-primary/5")}>
      <td className="px-3 py-2">
        <input
          type="checkbox"
          aria-label={`Select ${tag.tag_number}`}
          checked={checked}
          onChange={onToggle}
          className="accent-primary cursor-pointer"
        />
      </td>
      <td onClick={onOpen} className="px-3 py-2 text-[12px] font-mono cursor-pointer">{tag.tag_number}</td>
      <td onClick={onOpen} className="px-3 py-2 text-[12px] truncate max-w-[200px] cursor-pointer">{tag.asset_name}</td>
      <td onClick={onOpen} className="px-3 py-2 text-[12px] text-muted-foreground cursor-pointer">{domainLabelOf(tag.domain)}</td>
      <td onClick={onOpen} className="px-3 py-2 text-[12px] cursor-pointer">{conditionLabelOf(tag.condition)}</td>
      <td onClick={onOpen} className="px-3 py-2 text-[12px] truncate max-w-[180px] cursor-pointer">{tag.location}</td>
      <td onClick={onOpen} className="px-3 py-2 text-[11px] cursor-pointer">
        <span className={cn(
          "inline-flex items-center px-2 py-0.5 rounded-lg font-semibold border",
          tag.tag_state === "active"
            ? "bg-green-50 dark:bg-green-950/30 border-green-200/70 text-green-700 dark:text-green-400"
            : "bg-muted border-border text-muted-foreground",
        )}>{tag.tag_state}</span>
      </td>
    </tr>
  );
}

function Notice({ notice }: { notice: NonNullable<Notice> }) {
  const tone = {
    error: { box: "bg-red-50 dark:bg-red-950/30 border-red-200/70 dark:border-red-800/30",
             fg: "text-red-700 dark:text-red-400", icon: "text-red-600 dark:text-red-400" },
    warn:  { box: "bg-amber-50 dark:bg-amber-950/30 border-amber-200/70 dark:border-amber-800/30",
             fg: "text-amber-700 dark:text-amber-400", icon: "text-amber-600 dark:text-amber-400" },
    ok:    { box: "bg-green-50 dark:bg-green-950/30 border-green-200/70 dark:border-green-800/30",
             fg: "text-green-700 dark:text-green-400", icon: "text-green-600 dark:text-green-400" },
  }[notice.kind];
  const Icon = notice.kind === "ok" ? Check : AlertCircle;
  return (
    <div className={cn("rounded-2xl border p-3 flex items-start gap-2", tone.box)}>
      <Icon size={14} className={cn("shrink-0 mt-0.5", tone.icon)} />
      <p className={cn("text-[12px]", tone.fg)}>{notice.text}</p>
    </div>
  );
}

function UntaggedRow({ asset, pickable, checked, onToggle, onOpen }: {
  asset: UntaggedAsset; pickable: boolean; checked: boolean; onToggle: () => void; onOpen: () => void;
}) {
  const domainLabelOf = useEnumLabel("domain");
  const conditionLabelOf = useEnumLabel("condition");
  return (
    <tr className={cn("border-b border-border/40 hover:bg-muted/20", checked && "bg-primary/5")}>
      {pickable && (
        <td className="px-3 py-2">
          <input
            type="checkbox"
            aria-label={`Select ${asset.asset_code || asset.asset_name}`}
            checked={checked}
            onChange={onToggle}
            className="accent-primary cursor-pointer"
          />
        </td>
      )}
      <td onClick={onOpen} className="px-3 py-2 text-[12px] font-mono cursor-pointer">{asset.asset_code || "—"}</td>
      <td onClick={onOpen} className="px-3 py-2 text-[12px] truncate max-w-[220px] cursor-pointer">{asset.asset_name}</td>
      <td onClick={onOpen} className="px-3 py-2 text-[12px] text-muted-foreground truncate max-w-[140px] cursor-pointer">{asset.category || domainLabelOf(asset.domain)}</td>
      <td onClick={onOpen} className="px-3 py-2 text-[12px] truncate max-w-[180px] cursor-pointer">{asset.location}</td>
      <td onClick={onOpen} className="px-3 py-2 text-[12px] cursor-pointer">{conditionLabelOf(asset.condition)}</td>
    </tr>
  );
}

function SizePicker({ value, onChange }: { value: LabelSize; onChange: (v: LabelSize) => void }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as LabelSize)}
      title={LABEL_SIZES.find((s) => s.value === value)?.hint}
      aria-label="Label size"
      className="px-2 py-1.5 text-[11px] border border-border rounded-xl bg-background"
    >
      {LABEL_SIZES.map((s) => (
        <option key={s.value} value={s.value}>{s.label} — {s.hint.split(" — ")[0]}</option>
      ))}
    </select>
  );
}

function ModeButton({ active, onClick, icon: Icon, label }: {
  active: boolean; onClick: () => void; icon: typeof Tag; label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-semibold",
        active ? "bg-primary text-white" : "text-muted-foreground hover:bg-muted/40",
      )}
    >
      <Icon size={11} /> {label}
    </button>
  );
}

function Field({ label, value, mono }: { label: string; value?: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={cn("text-foreground font-semibold truncate", mono && "font-mono")}>{value || "—"}</p>
    </div>
  );
}

function KpiTile({ label, value, icon: Icon, color }: { label: string; value: number; icon: typeof Tag; color: string }) {
  return (
    <div className="bg-card border border-border/50 rounded-2xl px-4 py-4">
      <div className="flex items-center gap-1.5 mb-1.5">
        <Icon size={12} className={color} />
        <p className={cn("text-[10px] font-semibold uppercase tracking-widest", color)}>{label}</p>
      </div>
      <p className={cn("text-[22px] font-extrabold leading-none tabular-nums", color)}>{value.toLocaleString()}</p>
    </div>
  );
}
