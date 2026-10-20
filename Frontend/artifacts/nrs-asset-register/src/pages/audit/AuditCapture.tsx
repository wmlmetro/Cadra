/**
 * Audit capture, at a desk (handoff 66 §4, §6) — one screen, the same route
 * the phone uses (`POST /api/v1/audit/captures`). The phone app remains the
 * mobile team's; this is for an item brought to a desk, or a room audited
 * from a laptop.
 *
 *   1. the campaign (only those naming this person as a capturer), the
 *      device bound to them (sent as `X-Cadra-Device`), and the room —
 *      picked from the campaign's rooms or its room code typed or scanned;
 *   2. a photo (the browser's camera on a phone, a file on a desk), made
 *      smaller than 300 KB in the browser and synced first; *Identify from
 *      photo* fills the fields as SUGGESTIONS the person confirms or
 *      changes, and the capture names the suggestion it used;
 *   3. the outcome — (a) on Cadra's register: an asset of the room, or its
 *      label scanned; (b) in SAP's register: one of the office's SAP records
 *      or the matcher's; (c) none of these;
 *   4. for (b) and (c), the next code from this device's block, shown to be
 *      printed, and the label then scanned or typed off the item — the two
 *      must be equal, the affix check;
 *   5. send. The capture's `capture_id` is made here, once per item, so a
 *      retry after a failed send is the same capture, not a second one.
 *
 * Every refusal is the server's sentence, verbatim.
 *
 * Since handoff 67 the same screen is the Barcode Station's *Capture* mode
 * (Lot 6): `CaptureScreen variant="station"`. One screen, one flow, no new
 * rules — the station differs only in where it runs: it IS a device (it
 * remembers which of the person's devices it is), the room is found by
 * scanning its room label first, and a code is printed through the
 * station's print funnel and the print recorded, with *Spoiled label* and
 * *Return my block* beside it (`components/station/CaptureStationParts`).
 * Both places identify a photo by the id it was synced under
 * (`audit_photo_id`), never by uploading it twice, and may record where the
 * item was captured (GPS, off unless ticked; on the capture record only).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, CheckCircle2, Keyboard, Loader2, MapPin, ScanLine, Sparkles, X } from "lucide-react";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { ScopeRefusal } from "@/components/ScopeRefusal";
import BarcodeScanner from "@/components/BarcodeScanner";
import { useAiSwitch, AiNotice, SizeBandLine } from "@/components/IdentifyFromPhoto";
import {
  StationBlockLine, StationCodePrint, StationDeviceLine, readStationDeviceCode, rememberStationDeviceCode,
} from "@/components/station/CaptureStationParts";
import type { CadraApiError } from "@/lib/api";
import { useScopes, SCOPE } from "@/hooks/use-scopes";
import { preparePhotoForUpload } from "@/lib/assetPhotos";
import { identifyAuditPhoto, type AiSuggestion } from "@/lib/aiIdentify";
import type { LabelSize } from "@/lib/labels";
import { fetchAssetCategories } from "@/lib/dataProvider";
import {
  AUDIT_KEY, LABEL_WORDS, OUTCOME_WORDS, STATE_WORDS,
  fetchBlock, fetchBlocks, fetchCampaigns, fetchCaptures, fetchDevices, fetchRoomsUnder, fetchSlice,
  lookupScan, matchSap, myUid, nowIso, sendCapture, uploadAuditPhoto,
  type AuditCampaign, type AuditCapture, type AuditPhoto, type CaptureBody, type CaptureGps, type ConfirmedFields,
  type LabelState, type MatchResult, type Outcome, type RoomRef, type SliceAsset, type SliceSapRecord,
} from "@/lib/auditCapture";
import { cn, formatIsoDate } from "@/lib/utils";
import {
  Btn, Empty, ErrorPanel, INPUT, LABEL, PageHeader, Photo, Pill, TEXTAREA, invalidateAudit, when,
} from "./shared";

const CONDITIONS = ["new", "good", "fair", "poor"] as const;
type Condition = typeof CONDITIONS[number];

/** The confirmed fields the screen offers, in order. `category_id` and
 *  `condition` are drawn as selects; the rest are text. */
const TEXT_FIELDS: { key: Exclude<keyof ConfirmedFields, "category_id" | "condition" | "notes">; label: string }[] = [
  { key: "name", label: "Description" },
  { key: "make", label: "Make" },
  { key: "model_name", label: "Model" },
  { key: "serial_number", label: "Serial" },
  { key: "colour", label: "Colour" },
  { key: "material", label: "Material" },
  { key: "dimensions", label: "Dimensions" },
  { key: "legacy_asset_code", label: "Old tag (FIRS)" },
];

type Values = Record<string, string>;

export default function AuditCapture() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const scopes = useScopes();
  const canCapture = scopes.has(SCOPE.auditCapture);

  useEffect(() => {
    setTitle("Audit capture");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  if (!canCapture) {
    return <ScopeRefusal scope={SCOPE.auditCapture} detail="Audit Capturers hold it, on a device the Asset Controller bound to them." />;
  }
  return <CaptureScreen />;
}

/** Where the screen runs. `desk` is the Audit capture page (66); `station`
 *  is the Barcode Station's Capture mode (67), which also carries the
 *  station's label size so a code prints the size the desk's printer holds. */
export type CaptureScreenProps =
  | { variant?: "desk" }
  | { variant: "station"; labelSize: LabelSize; onLabelSize: (s: LabelSize) => void };

/** Where the item is, from the browser — asked once, at send time, only when
 *  the person ticked the box. Never sent anywhere but the capture body. */
function currentGps(): Promise<CaptureGps> {
  return new Promise((resolve, reject) => {
    if (!("geolocation" in navigator)) {
      reject(new Error("this browser has no location service"));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({
        latitude: p.coords.latitude, longitude: p.coords.longitude,
        ...(Number.isFinite(p.coords.accuracy) ? { accuracy_m: Math.max(0, p.coords.accuracy) } : {}),
      }),
      (e) => reject(new Error(e.code === e.PERMISSION_DENIED ? "the browser was not allowed to read the location"
        : e.code === e.TIMEOUT ? "the location did not arrive within 10 seconds" : "the location could not be read")),
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 60_000 },
    );
  });
}

export function CaptureScreen(props: CaptureScreenProps = {}) {
  const station = props.variant === "station" ? props : null;
  const isStation = !!station;
  const qc = useQueryClient();
  const ai = useAiSwitch();

  // ── 1. where ──
  const campaigns = useQuery<AuditCampaign[], CadraApiError>({
    queryKey: [...AUDIT_KEY, "campaigns", "open", "capturing"],
    queryFn: async () => {
      const me = myUid();
      const all = await fetchCampaigns("open");
      return me == null ? all : all.filter(c => c.capturers.some(u => u.id === me));
    },
  });
  const devices = useQuery({ queryKey: [...AUDIT_KEY, "devices", "mine"], queryFn: () => fetchDevices(true) });
  const myDevices = (devices.data ?? []).filter(d => d.active);
  const [campaignId, setCampaignId] = useState<number | null>(null);
  const [deviceId, setDeviceId] = useState<number | null>(null);
  const [room, setRoom] = useState<RoomRef | null>(null);
  useEffect(() => {
    if (campaignId == null && campaigns.data?.length) setCampaignId(campaigns.data[0].id);
  }, [campaigns.data, campaignId]);
  useEffect(() => {
    if (deviceId != null || !myDevices.length) return;
    // The station remembers which of the person's devices it is.
    const remembered = isStation ? readStationDeviceCode() : null;
    setDeviceId((myDevices.find(d => d.device_code === remembered) ?? myDevices[0]).id);
  }, [myDevices, deviceId, isStation]);
  useEffect(() => { setRoom(null); }, [campaignId]);
  const campaign = campaigns.data?.find(c => c.id === campaignId) ?? null;
  const device = myDevices.find(d => d.id === deviceId) ?? null;
  const deviceCode = device?.device_code ?? null;
  useEffect(() => {
    if (isStation && deviceCode) rememberStationDeviceCode(deviceCode);
  }, [isStation, deviceCode]);

  const rooms = useQuery<RoomRef[], CadraApiError>({
    queryKey: [...AUDIT_KEY, "rooms", campaignId],
    queryFn: async () => {
      const out: RoomRef[] = [];
      for (const line of campaign?.scope ?? []) {
        if (!line.location) continue;
        out.push({ id: line.location.id, name: line.location.name, location_code: null });
        for (const r of await fetchRoomsUnder(line.location.id)) out.push({ ...r, name: `${line.location.name} / ${r.name}` });
      }
      const seen = new Set<number>();
      return out.filter(r => (seen.has(r.id) ? false : (seen.add(r.id), true)));
    },
    enabled: !!campaign,
  });

  // ── 2. the item ──
  const [captureId, setCaptureId] = useState<string>(() => crypto.randomUUID());
  const [photos, setPhotos] = useState<AuditPhoto[]>([]);
  // The photo *Identify* asks about: the last one synced, by its id
  // (handoff 67 §2.1 — the bytes are already on the server).
  const [lastPhotoId, setLastPhotoId] = useState<number | null>(null);
  const [photoError, setPhotoError] = useState<Error | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const [values, setValues] = useState<Values>({ condition: "" });
  const [suggested, setSuggested] = useState<Values>({});
  const [suggestion, setSuggestion] = useState<AiSuggestion | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [asset, setAsset] = useState<{ id: number; asset_code: string; name: string | null } | null>(null);
  const [label, setLabel] = useState<LabelState>("present");
  const [sap, setSap] = useState<{ id: number; asset_number: string; description: string | null } | null>(null);
  const [scanned, setScanned] = useState("");
  const [sent, setSent] = useState<AuditCapture | null>(null);

  const categories = useQuery({ queryKey: ["asset-categories"], queryFn: fetchAssetCategories, staleTime: 5 * 60_000 });
  const needsCode = outcome === "in_sap" || outcome === "in_neither";
  const classOptions = (categories.data ?? []).filter(c => !needsCode || c.identification_mode !== "record_only");

  const setField = (k: string, v: string) => setValues(prev => ({ ...prev, [k]: v }));

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    setPhotoError(null);
    setUploading(true);
    try {
      const prepared = await preparePhotoForUpload(file);
      const photo = await uploadAuditPhoto(prepared.blob, prepared.filename);
      setPhotos(ps => ps.some(p => p.id === photo.id) ? ps : [...ps, photo]);
      setLastPhotoId(photo.id);
    } catch (e) {
      setPhotoError(e as Error);
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  /** A photo left out takes its suggestion with it: the server refuses a
   *  capture naming a suggestion made from a photo it does not carry
   *  (verification pass, 67). The values the person has typed stay. */
  const leavePhotoOut = (id: number) => {
    const rest = photos.filter(x => x.id !== id);
    setPhotos(rest);
    if (lastPhotoId === id) setLastPhotoId(rest.length ? rest[rest.length - 1].id : null);
    if (suggestion?.photo?.id === id) { setSuggestion(null); setSuggested({}); }
  };

  const identify = useMutation<AiSuggestion, CadraApiError>({
    mutationFn: () => identifyAuditPhoto(lastPhotoId as number),
    onSuccess: (s) => {
      const proposed: Values = {};
      if (s.category?.id) proposed.category_id = String(s.category.id);
      for (const k of ["name", "colour", "material", "make", "model_name", "dimensions"] as const) {
        const v = s.attributes?.[k];
        if (v) proposed[k] = v;
      }
      if (s.condition?.value && (CONDITIONS as readonly string[]).includes(s.condition.value)) proposed.condition = s.condition.value;
      setSuggestion(s);
      setSuggested(proposed);
      setValues(prev => ({ ...prev, ...proposed }));
    },
  });

  // ── 3. the outcome's targets ──
  const assetsSlice = useQuery({
    queryKey: [...AUDIT_KEY, "slice", campaignId, room?.id, "assets"],
    queryFn: () => fetchSlice<SliceAsset>(campaignId as number, room!.id, "assets"),
    enabled: outcome === "on_register" && campaignId != null && !!room,
  });
  const sapSlice = useQuery({
    queryKey: [...AUDIT_KEY, "slice", campaignId, room?.id, "sap_records"],
    queryFn: () => fetchSlice<SliceSapRecord>(campaignId as number, room!.id, "sap_records"),
    enabled: outcome === "in_sap" && campaignId != null && !!room,
  });

  // ── 4. the code ──
  const block = useQuery({
    queryKey: [...AUDIT_KEY, "my-block", deviceId],
    queryFn: async () => {
      const open = await fetchBlocks({ deviceId: deviceId as number, state: "issued" });
      return open[0] ? fetchBlock(open[0].id) : null;
    },
    // The station shows its block all the time — it is where *Return my
    // block* lives; the desk reads it only when a code is needed.
    enabled: (needsCode || isStation) && deviceId != null,
  });
  const nextCodeRow = block.data?.codes?.find(c => c.state === "reserved") ?? null;
  const nextCode = nextCodeRow?.code ?? null;
  const reservedLeft = block.data?.codes?.filter(c => c.state === "reserved").length ?? 0;

  // ── 5. send ──
  const fields: ConfirmedFields = useMemo(() => {
    const out: ConfirmedFields = {};
    for (const f of TEXT_FIELDS) {
      const v = (values[f.key] ?? "").trim();
      if (v) out[f.key] = v;
    }
    if (values.category_id) out.category_id = Number(values.category_id);
    if (values.condition) out.condition = values.condition as Condition;
    if ((values.notes ?? "").trim()) out.notes = values.notes.trim();
    return out;
  }, [values]);

  // ── GPS (AI-FR-10, handoff 67 §2.4) — off unless ticked ──
  const [withGps, setWithGps] = useState(false);
  const [gpsNote, setGpsNote] = useState<string | null>(null);

  const send = useMutation<AuditCapture, CadraApiError>({
    mutationFn: async () => {
      setGpsNote(null);
      let gps: CaptureGps | undefined;
      if (withGps) {
        try {
          gps = await currentGps();
        } catch (e) {
          // Sent without it, and said after.
          setGpsNote(`Sent without GPS: ${e instanceof Error ? e.message : "the location could not be read"}.`);
        }
      }
      const body: CaptureBody = {
        capture_id: captureId, campaign_id: campaignId as number, location_id: room!.id,
        outcome: outcome as Outcome, photo_ids: photos.map(p => p.id), captured_at: nowIso(), fields,
      };
      if (suggestion) body.ai_suggestion_id = suggestion.suggestion_id;
      if (outcome === "on_register" && asset) { body.asset_id = asset.id; body.label = label; }
      if (outcome === "in_sap" && sap) body.sap_record_id = sap.id;
      if (needsCode) { body.code = nextCode ?? ""; body.scanned_label = scanned.trim(); }
      if (gps) body.gps = gps;
      return sendCapture(device!.device_code, body);
    },
    onSuccess: (c) => {
      setSent(c);
      invalidateAudit(qc);
      // The next item: a new capture id, everything about the item cleared;
      // the campaign, device and room stay — the person is still in it.
      setCaptureId(crypto.randomUUID());
      setPhotos([]); setLastPhotoId(null); setValues({ condition: "" }); setSuggested({}); setSuggestion(null);
      setOutcome(null); setAsset(null); setSap(null); setScanned(""); setLabel("present");
      identify.reset();
    },
  });

  const targetReady = outcome === "on_register" ? !!asset
    : outcome === "in_sap" ? !!sap && !!nextCode && !!scanned.trim()
    : outcome === "in_neither" ? !!nextCode && !!scanned.trim()
    : false;
  const ready = !!campaign && !!device && !!room && photos.length > 0 && !!values.condition && targetReady
    && (!needsCode || !!values.category_id) && (outcome !== "in_neither" || !!(values.name ?? "").trim());

  const missing: string[] = [];
  if (!campaign) missing.push("a campaign");
  if (!device) missing.push("your device");
  if (!room) missing.push("the room");
  if (photos.length === 0) missing.push("a photo");
  if (!outcome) missing.push("what the item is");
  else if (outcome === "on_register" && !asset) missing.push("the Cadra asset");
  else if (outcome === "in_sap" && !sap) missing.push("the SAP record");
  if (needsCode && !scanned.trim()) missing.push("the label scanned");
  if (!values.condition) missing.push("the condition");
  if (needsCode && !values.category_id) missing.push("the class");
  if (outcome === "in_neither" && !(values.name ?? "").trim()) missing.push("a description");

  return (
    <div className={station ? undefined : "flex flex-col h-full"} data-testid={station ? "station-capture" : undefined}>
      {!station && (
        <PageHeader icon={<ScanLine size={15} />} title="Audit capture">
          Capture one item at a time, at a desk. The same capture the phone makes: a photo, what the item is, and — for
          an item not on Cadra's register — the next code from your device's block, printed and fixed to it. A reviewer
          accepts it; you cannot review your own.
        </PageHeader>
      )}
      <div className={station ? "space-y-5" : "flex-1 overflow-y-auto px-5 py-4 space-y-5 max-w-4xl"}>
        {sent && (
          <div className="rounded-xl border border-green-300 bg-green-50 dark:bg-green-950/30 p-3 text-[12px]" data-testid="capture-sent"
               data-capture-id={sent.capture_id}>
            <p className="font-semibold text-green-900 dark:text-green-300 flex items-center gap-1.5">
              <CheckCircle2 size={13} /> {sent.replayed ? "Already synced" : "Synced"} — {OUTCOME_WORDS[sent.outcome]}, {STATE_WORDS[sent.state].toLowerCase()}.
            </p>
            <p className="text-muted-foreground">
              Capture <span className="font-mono">{sent.capture_id}</span>
              {sent.code && <> · code <span className="font-mono">{sent.code}</span></>}
              {sent.duplicate_of && <> · held as a duplicate of an earlier capture, for the reviewer to compare</>}
              {sent.gps && <> · with where it was captured</>}
            </p>
          </div>
        )}
        {gpsNote && !send.isPending && (
          <p className="text-[11px] text-amber-800 dark:text-amber-300" data-testid="capture-gps-note">{gpsNote}</p>
        )}

        {/* 1 — where */}
        <section className="space-y-2" aria-label="Where">
          <p className={LABEL}>1 · Where</p>
          {campaigns.error && <ErrorPanel err={campaigns.error} />}
          {devices.error && <ErrorPanel err={devices.error as CadraApiError} />}
          <div className="flex flex-wrap gap-2 items-center">
            <select className={INPUT} data-testid="capture-campaign" aria-label="Campaign"
                    value={campaignId ?? ""} onChange={e => setCampaignId(e.target.value ? Number(e.target.value) : null)}>
              {(campaigns.data ?? []).length === 0 && <option value="">No open campaign names you as a capturer</option>}
              {(campaigns.data ?? []).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            {!station && (
              <select className={INPUT} data-testid="capture-device" aria-label="Device"
                      value={deviceId ?? ""} onChange={e => setDeviceId(e.target.value ? Number(e.target.value) : null)}>
                {myDevices.length === 0 && <option value="">No device is bound to you</option>}
                {myDevices.map(d => <option key={d.id} value={d.id}>{d.name} ({d.device_code})</option>)}
              </select>
            )}
          </div>
          {!station && devices.data && myDevices.length === 0 && (
            <p className="text-[11px] text-amber-800 dark:text-amber-300">The Asset Controller binds a device to you on <span className="font-semibold">Devices and codes</span>; a capture names the device it was taken on.</p>
          )}
          {station && (
            <>
              <StationDeviceLine device={device} loaded={!!devices.data} devices={myDevices} onDevice={setDeviceId} />
              {device && <StationBlockLine block={block.data} loading={block.isLoading} />}
            </>
          )}
          {campaign && (
            <RoomChooser rooms={rooms.data ?? []} loading={rooms.isLoading} room={room} onRoom={setRoom}
                         campaignId={campaign.id} scanFirst={isStation} />
          )}
          {rooms.error && <ErrorPanel err={rooms.error} />}
        </section>

        {/* 2 — the photo */}
        <section className="space-y-2" aria-label="Photo">
          <p className={LABEL}>2 · Photograph the item</p>
          <div className="flex flex-wrap gap-2 items-center">
            <input ref={fileInput} type="file" accept="image/*" capture="environment" className="hidden"
                   data-testid="input-capture-photo" onChange={e => onFile(e.target.files?.[0])} />
            <Btn kind="plain" testid="button-capture-photo" pending={uploading} onClick={() => fileInput.current?.click()}>
              <Camera size={12} /> {photos.length ? "Add another photo" : "Take or choose a photo"}
            </Btn>
            {ai && lastPhotoId != null && (
              <Btn kind="plain" testid="button-identify" pending={identify.isPending} onClick={() => identify.mutate()}>
                <Sparkles size={12} /> Identify from photo
              </Btn>
            )}
          </div>
          {photos.length > 0 && (
            <div className="flex gap-2 flex-wrap" data-testid="capture-photos-chosen">
              {photos.map(p => (
                <div key={p.id} className="relative">
                  <Photo url={p.url} size="sm" testid="capture-photo-thumb" />
                  <button type="button" aria-label="Leave this photo out" onClick={() => leavePhotoOut(p.id)}
                          className="absolute -top-1.5 -right-1.5 bg-card border border-border rounded-full p-0.5"><X size={10} /></button>
                </div>
              ))}
            </div>
          )}
          {photoError && <ErrorPanel err={photoError} testid="capture-photo-error" />}
          {ai && <AiNotice text={ai.notice} />}
          {identify.error && <ErrorPanel err={identify.error} testid="identify-error" />}
          {suggestion && (
            <p className="text-[11px] text-muted-foreground" data-testid="identify-done">
              Suggested by {suggestion.provider_label}: the fields marked <Pill tone="blue">suggested</Pill> came from the photo.
              Confirm or change each before sending.
            </p>
          )}
        </section>

        {/* 3 — what it is */}
        <section className="space-y-2" aria-label="Outcome">
          <p className={LABEL}>3 · What is it?</p>
          <div className="flex flex-col gap-1" role="radiogroup" aria-label="Outcome">
            {(["on_register", "in_sap", "in_neither"] as Outcome[]).map(o => (
              <label key={o} className="text-[12px] flex items-center gap-2">
                <input type="radio" name="outcome" className="accent-primary" checked={outcome === o}
                       onChange={() => { setOutcome(o); setAsset(null); setSap(null); }} data-testid={`outcome-${o}`} />
                {o === "in_neither" ? "None of these — found, not in SAP" : OUTCOME_WORDS[o]}
              </label>
            ))}
          </div>
          {outcome === "on_register" && (
            <OnRegisterPicker slice={assetsSlice.data?.records ?? []} loading={assetsSlice.isLoading} error={assetsSlice.error as CadraApiError | null}
              asset={asset} onAsset={setAsset} label={label} onLabel={setLabel} hasRoom={!!room} />
          )}
          {outcome === "in_sap" && (
            <InSapPicker slice={sapSlice.data} loading={sapSlice.isLoading} error={sapSlice.error as CadraApiError | null}
              sap={sap} onSap={setSap} hasRoom={!!room} values={values} />
          )}
        </section>

        {/* 4 — the fields */}
        <section className="space-y-2" aria-label="Fields">
          <p className={LABEL}>4 · Confirm what you see</p>
          {suggestion && <SizeBandLine band={suggestion.size_band} />}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <FieldRow label="Class" suggestedValue={suggested.category_id} value={values.category_id ?? ""}>
              <select className={cn(INPUT, "w-full")} data-testid="select-field-category" aria-label="Class"
                      value={values.category_id ?? ""} onChange={e => setField("category_id", e.target.value)}>
                <option value="">Choose…</option>
                {classOptions.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </FieldRow>
            <FieldRow label="Condition" suggestedValue={suggested.condition} value={values.condition ?? ""}>
              <select className={cn(INPUT, "w-full")} data-testid="select-field-condition" aria-label="Condition"
                      value={values.condition ?? ""} onChange={e => setField("condition", e.target.value)}>
                <option value="">Choose…</option>
                {CONDITIONS.map(c => <option key={c} value={c}>{c[0].toUpperCase() + c.slice(1)}</option>)}
              </select>
            </FieldRow>
            {TEXT_FIELDS.map(f => (
              <FieldRow key={f.key} label={f.label} suggestedValue={suggested[f.key]} value={values[f.key] ?? ""}>
                <input className={cn(INPUT, "w-full")} value={values[f.key] ?? ""} aria-label={f.label}
                       data-testid={`input-field-${f.key}`} onChange={e => setField(f.key, e.target.value)} />
              </FieldRow>
            ))}
          </div>
          <div>
            <label className="text-[11px] text-muted-foreground" htmlFor="capture-notes">Notes</label>
            <textarea id="capture-notes" rows={2} className={TEXTAREA} value={values.notes ?? ""}
                      data-testid="input-field-notes" onChange={e => setField("notes", e.target.value)} />
          </div>
        </section>

        {/* 5 — the code (b, c) */}
        {needsCode && (
          <section className="space-y-2" aria-label="Code" data-testid="capture-code-section">
            <p className={LABEL}>5 · The code for its label</p>
            {block.error && <ErrorPanel err={block.error as CadraApiError} />}
            {block.isLoading ? <p className="text-[11px] text-muted-foreground flex items-center gap-1.5"><Loader2 size={12} className="animate-spin" /> Reading your block…</p>
              : !block.data ? <p className="text-[12px] text-amber-800 dark:text-amber-300" data-testid="capture-no-block">This device has no block of codes. The Asset Controller issues one on <span className="font-semibold">Devices and codes</span>.</p>
              : !nextCode ? <p className="text-[12px] text-amber-800 dark:text-amber-300" data-testid="capture-no-code">Every code in {block.data.name} is used. Ask the Asset Controller for another block.</p>
              : (
                <div className="space-y-2">
                  <p className="text-[12px]">
                    {station ? "Print this code's label here" : "Print this code on a label"} and fix it to the item ({reservedLeft} left in {block.data.name}):
                  </p>
                  <p className="text-[22px] font-mono font-bold tracking-wide" data-testid="capture-next-code">{nextCode}</p>
                  {station && (
                    <StationCodePrint key={captureId} code={nextCode} codeRow={nextCodeRow} deviceCode={deviceCode}
                      assetName={(values.name ?? "").trim() || "Audit capture"}
                      size={station.labelSize} onSize={station.onLabelSize} onSpoiled={() => setScanned("")} />
                  )}
                  <ScannedLabel value={scanned} onChange={setScanned} expected={nextCode} />
                </div>
              )}
          </section>
        )}

        <div className="space-y-2 pb-6">
          {/* AI-FR-10: optional, off by default, asked of the browser once at
              send time. On the capture record only — never sent to the AI
              provider, never on a label. */}
          <label className="text-[12px] flex items-center gap-2">
            <input type="checkbox" className="accent-primary" checked={withGps} onChange={e => setWithGps(e.target.checked)}
                   data-testid="input-capture-gps" />
            <MapPin size={12} className="text-muted-foreground" /> Record where this was captured (GPS)
          </label>
          {send.error && <ErrorPanel err={send.error} testid="capture-send-error" />}
          <div className="flex items-center gap-3 flex-wrap">
            <Btn testid="button-send-capture" disabled={!ready} pending={send.isPending} onClick={() => { setSent(null); send.mutate(); }}>
              Send the capture
            </Btn>
            {!ready && missing.length > 0 && (
              <span className="text-[11px] text-muted-foreground" data-testid="capture-missing">Still needed: {missing.join(", ")}.</span>
            )}
          </div>
        </div>

        <MyCaptures campaignId={campaignId} />
      </div>
    </div>
  );
}

function FieldRow({ label, suggestedValue, value, children }: {
  label: string; suggestedValue?: string; value: string; children: React.ReactNode;
}) {
  const marked = suggestedValue != null;
  const changed = marked && suggestedValue !== value;
  return (
    <div>
      <div className="flex items-center gap-1.5">
        <span className="text-[11px] text-muted-foreground">{label}</span>
        {marked && !changed && <Pill tone="blue" testid="field-suggested">suggested</Pill>}
        {changed && <Pill tone="amber" testid="field-changed">changed</Pill>}
      </div>
      <div className="mt-0.5">{children}</div>
    </div>
  );
}

function ScanOrType({ onValue, placeholder, testid, autoFocus }: {
  onValue: (v: string) => void; placeholder: string; testid: string; autoFocus?: boolean;
}) {
  const [mode, setMode] = useState<"type" | "camera">("type");
  const [typed, setTyped] = useState("");
  return (
    <div className="space-y-1.5">
      <div className="flex gap-2 items-center flex-wrap">
        <div className="inline-flex rounded-xl border border-border overflow-hidden" role="group">
          <button type="button" onClick={() => setMode("type")} aria-pressed={mode === "type"}
                  className={cn("px-2 py-1 text-[11px] inline-flex items-center gap-1", mode === "type" ? "bg-primary text-white" : "text-muted-foreground")}>
            <Keyboard size={11} /> Type
          </button>
          <button type="button" onClick={() => setMode("camera")} aria-pressed={mode === "camera"}
                  className={cn("px-2 py-1 text-[11px] inline-flex items-center gap-1", mode === "camera" ? "bg-primary text-white" : "text-muted-foreground")}>
            <Camera size={11} /> Camera
          </button>
        </div>
        {mode === "type" && (
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (typed.trim()) onValue(typed.trim()); }}>
            {/* A handheld scanner types into whatever has focus, then Enter. */}
            <input value={typed} onChange={e => setTyped(e.target.value)} placeholder={placeholder} autoFocus={autoFocus}
                   className={cn(INPUT, "w-56 font-mono")} data-testid={testid} />
            <Btn type="submit" kind="plain" disabled={!typed.trim()} testid={`${testid}-go`}>Find</Btn>
          </form>
        )}
      </div>
      {mode === "camera" && (
        <BarcodeScanner onDetected={(v) => { setMode("type"); setTyped(v); onValue(v); }} className="max-w-sm" />
      )}
    </div>
  );
}

/**
 * The room: chosen from the campaign's rooms, or found by its room code
 * (`LOC-…`) scanned off the room's label. A code is matched against the
 * campaign's rooms first; one the list does not hold (a room deeper than
 * the list goes) is resolved by the scan lookup and then asked of the
 * campaign's own slice, so a room outside the campaign is refused in the
 * server's words before anything is captured in it. At the station the
 * scan comes first and the list is the fallback.
 */
function RoomChooser({ rooms, loading, room, onRoom, campaignId, scanFirst }: {
  rooms: RoomRef[]; loading: boolean; room: RoomRef | null; onRoom: (r: RoomRef | null) => void;
  campaignId: number; scanFirst?: boolean;
}) {
  const scan = useMutation<RoomRef, CadraApiError | Error, string>({
    mutationFn: async (v) => {
      const typed = v.trim().toUpperCase();
      const listed = rooms.find(r => r.location_code && r.location_code.toUpperCase() === typed);
      if (listed) return listed;
      const a = await lookupScan(v);
      if (a.kind !== "room") throw new Error(`${v} is an asset's label (${a.asset.asset_code}), not a room's code.`);
      const inList = rooms.find(r => r.id === a.room.id);
      if (inList) return { ...inList, location_code: inList.location_code ?? a.room.location_code };
      // Not in the list: the campaign decides. Its slice refuses a room it
      // does not cover ("<room> is outside campaign <name>."), verbatim.
      await fetchSlice<SliceAsset>(campaignId, a.room.id, "assets");
      return a.room;
    },
    onSuccess: (r) => onRoom(r),
  });
  const chooser = (
    <div className="flex flex-wrap gap-2 items-center">
      {scanFirst && <span className="text-[11px] text-muted-foreground">or choose it:</span>}
      <select className={INPUT} data-testid="capture-room" aria-label="Room" value={room?.id ?? ""}
              onChange={e => { const r = rooms.find(x => x.id === Number(e.target.value)); onRoom(r ?? null); }}>
        <option value="">{loading ? "Reading the rooms…" : "Choose the room…"}</option>
        {room && !rooms.some(r => r.id === room.id) && <option value={room.id}>{room.name}</option>}
        {rooms.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
      </select>
      {!scanFirst && <span className="text-[11px] text-muted-foreground">or scan its room code:</span>}
    </div>
  );
  return (
    <div className="space-y-1.5">
      {scanFirst && <p className="text-[12px]">Scan the room's label (its room code), or type it:</p>}
      {!scanFirst && chooser}
      <ScanOrType onValue={(v) => scan.mutate(v)} placeholder="LOC-…" testid="input-room-code" autoFocus={scanFirst} />
      {scanFirst && chooser}
      {scan.error && <ErrorPanel err={scan.error} testid="room-scan-error" />}
      {room && <p className="text-[12px]" data-testid="capture-room-chosen">Room: <span className="font-semibold">{room.name}</span>{room.location_code && <span className="font-mono text-muted-foreground"> {room.location_code}</span>}</p>}
    </div>
  );
}

function OnRegisterPicker({ slice, loading, error, asset, onAsset, label, onLabel, hasRoom }: {
  slice: SliceAsset[]; loading: boolean; error: CadraApiError | null;
  asset: { id: number; asset_code: string; name: string | null } | null;
  onAsset: (a: { id: number; asset_code: string; name: string | null } | null) => void;
  label: LabelState; onLabel: (l: LabelState) => void; hasRoom: boolean;
}) {
  const scan = useMutation<{ id: number; asset_code: string; name: string | null }, CadraApiError | Error, string>({
    mutationFn: async (v) => {
      const a = await lookupScan(v);
      if (a.kind !== "asset") throw new Error(`${v} is a room's code, not an asset's label.`);
      return a.asset;
    },
    onSuccess: (a) => onAsset(a),
  });
  return (
    <div className="pl-5 space-y-2" data-testid="on-register-picker">
      <p className="text-[11px] text-muted-foreground">Scan its Cadra label (or type its code or serial), or pick it from the room's assets.</p>
      <ScanOrType onValue={(v) => scan.mutate(v)} placeholder="Label, asset code or serial" testid="input-asset-scan" />
      {scan.error && <ErrorPanel err={scan.error} testid="asset-scan-error" />}
      {!hasRoom ? <p className="text-[11px] text-muted-foreground">Choose the room to see its assets.</p>
        : loading ? <p className="text-[11px] text-muted-foreground">Reading the room's assets…</p>
        : error ? <ErrorPanel err={error} />
        : slice.length === 0 ? <p className="text-[11px] text-muted-foreground">The register has no asset in this room.</p>
        : (
          <ul className="max-h-56 overflow-y-auto rounded-xl border border-border divide-y divide-border">
            {slice.map(a => (
              <li key={a.id}>
                <label className="px-3 py-1.5 text-[12px] flex items-center gap-2">
                  <input type="radio" name="asset" className="accent-primary" checked={asset?.id === a.id}
                         onChange={() => onAsset({ id: a.id, asset_code: a.asset_code, name: a.name })} data-testid={`pick-asset-${a.id}`} />
                  <span className="font-mono font-semibold">{a.asset_code}</span> {a.name}
                  <span className="text-muted-foreground">{a.category}{a.legacy_asset_code && <> · old tag {a.legacy_asset_code}</>}{a.serial_number && <> · {a.serial_number}</>}</span>
                </label>
              </li>
            ))}
          </ul>
        )}
      {asset && <p className="text-[12px]" data-testid="capture-asset-chosen">The item is <span className="font-semibold">{asset.asset_code}</span>{asset.name && <> — {asset.name}</>}.</p>}
      <div className="flex gap-3 flex-wrap">
        {(Object.keys(LABEL_WORDS) as LabelState[]).map(l => (
          <label key={l} className="text-[12px] flex items-center gap-1.5">
            <input type="radio" name="label" className="accent-primary" checked={label === l} onChange={() => onLabel(l)} data-testid={`label-${l}`} />
            {LABEL_WORDS[l]}
          </label>
        ))}
      </div>
      {label !== "present" && <p className="text-[11px] text-muted-foreground">A label is reprinted under its existing code when the reviewer accepts — no new code.</p>}
    </div>
  );
}

function InSapPicker({ slice, loading, error, sap, onSap, hasRoom, values }: {
  slice: { office_code: string | null; records: SliceSapRecord[]; note?: string } | undefined;
  loading: boolean; error: CadraApiError | null;
  sap: { id: number; asset_number: string; description: string | null } | null;
  onSap: (s: { id: number; asset_number: string; description: string | null } | null) => void;
  hasRoom: boolean; values: Values;
}) {
  const [oldTag, setOldTag] = useState("");
  const [desc, setDesc] = useState("");
  const match = useMutation({
    mutationFn: () => matchSap({
      old_tag: oldTag || values.legacy_asset_code, description: desc || values.name,
      office: slice?.office_code ?? undefined, serial: values.serial_number,
    }),
  });
  const unlinked = (slice?.records ?? []).filter(r => !r.linked_asset_id);
  return (
    <div className="pl-5 space-y-2" data-testid="in-sap-picker">
      <p className="text-[11px] text-muted-foreground">Pick SAP's record for it: from this office's SAP records, or ask the matcher.</p>
      <div className="flex gap-2 flex-wrap items-center">
        <input value={oldTag} onChange={e => setOldTag(e.target.value)} placeholder="Old tag" className={cn(INPUT, "w-40 font-mono")} data-testid="input-match-old-tag" />
        <input value={desc} onChange={e => setDesc(e.target.value)} placeholder="Description" className={cn(INPUT, "w-48")} data-testid="input-match-description" />
        <Btn kind="plain" testid="button-match" pending={match.isPending} onClick={() => match.mutate()}>Match</Btn>
      </div>
      {match.error && <ErrorPanel err={match.error as CadraApiError} testid="match-error" />}
      {match.data && (
        match.data.results.length === 0
          ? <p className="text-[11px] text-muted-foreground" data-testid="match-none">No active, unlinked SAP record matched.{match.data.notes.length ? ` ${match.data.notes.join(" ")}` : ""}</p>
          : <ul className="rounded-xl border border-border divide-y divide-border" data-testid="match-results">
              {match.data.results.map((r: MatchResult) => (
                <li key={r.sap_asset.id}>
                  <label className="px-3 py-1.5 text-[12px] flex items-center gap-2">
                    <input type="radio" name="sap" className="accent-primary" checked={sap?.id === r.sap_asset.id}
                           onChange={() => onSap({ id: r.sap_asset.id, asset_number: r.sap_asset.asset_number, description: r.sap_asset.description })} />
                    <span className="font-mono font-semibold">{r.sap_asset.asset_number}</span> {r.sap_asset.description}
                    <span className="text-muted-foreground">{r.reason}</span>
                  </label>
                </li>
              ))}
            </ul>
      )}
      {!hasRoom ? <p className="text-[11px] text-muted-foreground">Choose the room to see its office's SAP records.</p>
        : loading ? <p className="text-[11px] text-muted-foreground">Reading SAP's records for this office…</p>
        : error ? <ErrorPanel err={error} />
        : slice?.note ? <p className="text-[11px] text-muted-foreground">{slice.note}</p>
        : unlinked.length === 0 ? <p className="text-[11px] text-muted-foreground">Every SAP record of office {slice?.office_code ?? "—"} is already on Cadra's register.</p>
        : (
          <ul className="max-h-56 overflow-y-auto rounded-xl border border-border divide-y divide-border" data-testid="sap-slice">
            {unlinked.map(r => (
              <li key={r.id}>
                <label className="px-3 py-1.5 text-[12px] flex items-center gap-2">
                  <input type="radio" name="sap" className="accent-primary" checked={sap?.id === r.id}
                         onChange={() => onSap({ id: r.id, asset_number: r.asset_number, description: r.description })} data-testid={`pick-sap-${r.id}`} />
                  <span className="font-mono font-semibold">{r.asset_number}</span> {r.description}
                  <span className="text-muted-foreground">class {r.class ?? "—"}{r.old_tag && <> · old tag {r.old_tag}</>}{r.capitalized_on && <> · {formatIsoDate(r.capitalized_on)}</>}</span>
                </label>
              </li>
            ))}
          </ul>
        )}
      {sap && <p className="text-[12px]" data-testid="capture-sap-chosen">SAP record <span className="font-mono font-semibold">{sap.asset_number}</span>{sap.description && <> — {sap.description}</>}.</p>}
    </div>
  );
}

function ScannedLabel({ value, onChange, expected }: { value: string; onChange: (v: string) => void; expected: string }) {
  const [camera, setCamera] = useState(false);
  const mismatch = value.trim() !== "" && value.trim() !== expected;
  return (
    <div className="space-y-1.5">
      <label className="text-[11px] text-muted-foreground" htmlFor="scanned-label">Now scan the label on the item, or type what it says</label>
      <div className="flex gap-2 items-center flex-wrap">
        <input id="scanned-label" value={value} onChange={e => onChange(e.target.value)} autoComplete="off"
               className={cn(INPUT, "w-56 font-mono", mismatch && "border-red-400")} data-testid="input-scanned-label" />
        <Btn kind="plain" onClick={() => setCamera(c => !c)}><Camera size={12} /> {camera ? "Stop the camera" : "Scan with the camera"}</Btn>
      </div>
      {camera && <BarcodeScanner onDetected={(v) => { setCamera(false); onChange(v); }} className="max-w-sm" />}
      {mismatch && (
        <p className="text-[11px] text-red-700 dark:text-red-400" data-testid="scanned-label-mismatch">
          The label scanned is not the code printed for this item. Fix the right label to it and scan again.
        </p>
      )}
    </div>
  );
}

function MyCaptures({ campaignId }: { campaignId: number | null }) {
  const q = useQuery({
    queryKey: [...AUDIT_KEY, "captures", "mine", campaignId],
    queryFn: () => fetchCaptures({ campaign_id: campaignId as number, mine: true, limit: 50 }),
    enabled: campaignId != null,
  });
  if (campaignId == null) return null;
  const rows = q.data?.rows ?? [];
  return (
    <section className="space-y-2 border-t border-border pt-4" aria-label="My captures">
      <p className={LABEL}>My captures in this campaign</p>
      {q.error && <ErrorPanel err={q.error as CadraApiError} />}
      {rows.length === 0 && !q.isLoading ? <Empty testid="my-captures-empty">You have not captured anything in this campaign yet.</Empty> : (
        <table className="w-full text-xs" data-testid="my-captures">
          <thead className="text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr><th className="text-left py-1 pr-3">Item</th><th className="text-left pr-3">Outcome</th><th className="text-left pr-3">Room</th><th className="text-left pr-3">State</th><th className="text-left">Captured</th></tr>
          </thead>
          <tbody>
            {rows.map(c => (
              <tr key={c.capture_id} className="border-b border-border" data-testid={`my-capture-${c.capture_id}`} data-state={c.state}>
                <td className="py-1 pr-3">{c.name ?? c.asset?.asset_code ?? "—"}{c.code && <span className="font-mono text-muted-foreground"> {c.code}</span>}</td>
                <td className="pr-3">{OUTCOME_WORDS[c.outcome]}</td>
                <td className="pr-3">{c.location.name}</td>
                <td className="pr-3">
                  {STATE_WORDS[c.state]}
                  {c.state === "returned" && c.return_reason && <div className="text-red-700 dark:text-red-400">{c.return_reason}</div>}
                </td>
                <td className="text-muted-foreground">{when(c.captured_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
