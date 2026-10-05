import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { CadraApiError } from "@/lib/api";
import {
  confirmTagAffixed, fetchAssetTagging,
  type AssetTagging, type ConfirmAffixedResult,
} from "@/lib/dataProvider";
import { invalidateTagQueries } from "@/components/TagReplacementDialogs";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { formatIsoDateTime } from "@/lib/utils";
import { AlertCircle, Camera, Check, Info, Keyboard, Loader2, Tag } from "lucide-react";
import { cn } from "@/lib/utils";
import BarcodeScanner from "@/components/BarcodeScanner";
import { SCAN_FORMAT_LABELS, type ScanFormat } from "@/lib/scanFormats";

/**
 * Confirming that a printed label is on the asset — handoff 39.
 *
 * The person has a scanner, a label and the asset in front of them. They scan
 * the label INTO THIS DIALOG, and the server compares what they scanned with
 * the tag it issued for the asset. That comparison is the control: it is what
 * makes the record evidence that the right label is on the right asset,
 * rather than an assertion that someone tagged something.
 *
 * So the one rule this file is built around: **this component never hands
 * the expected number over.** Not in the title, not as a placeholder, not as
 * a default, not as a suggestion. If the screen handed the number over, the
 * check would compare Cadra's number with Cadra's number, always pass, and
 * manufacture a record that says a human verified something no human
 * verified. The station page masks the number on the card behind this
 * dialog for the same reason. ONE place it does appear, by instruction: the
 * server's wrong-tag refusal names the issued number ("…does not match the
 * tag issued for this asset (X)"), and the handoff requires that sentence
 * verbatim. That tension is the Architect's to rule on (report 39 §F).
 *
 * Modelled on the dialogs in `TagReplacementDialogs.tsx`: the same `Dialog`,
 * the same error panel, the same rule that a USER cannot close it while the
 * request is in flight (closing resets the mutation and a refusal would then
 * be shown nowhere), while the success handler may.
 *
 * Three outcomes, and they are not the same thing:
 *
 *   refused   400 `validation_failed` — the wrong tag, a serial that does not
 *             match, no serial on file to check against; 400 `invalid_request`
 *             — no active tag; 403 — the signed-in user lacks `tagging:write`.
 *             The server's sentence is shown as written and the inputs stay
 *             so the person can try again.
 *   recorded  the label is affixed; who fitted it and when are on the row.
 *   already   the server answered normally but WROTE NOTHING: a second
 *             confirmation keeps the original record (`_mark_affixed`). The
 *             dialog says so, with the original date — not "done", because
 *             nothing was done, and not an error, because nothing went wrong.
 *             Told apart by reading the block before posting, not by a clock.
 *
 * Handoff 40 adds the CAMERA as a second way into the tag field (and the
 * serial field), as a Type / Camera toggle like the station's own. The
 * handheld-scanner path above is the primary design and is unchanged: the
 * tag field is auto-focused, the scanner's trailing Enter submits, and
 * switching the camera off returns focus to the field. The camera is
 * `BarcodeScanner` as it is — the same component the station's lookup box
 * uses — mounted under whichever field asked for it, one at a time.
 *
 * **A camera detection fills the field. It does not submit.** This will read
 * as an inconsistency next to the Enter-submits rule, so: a trigger pull on
 * a handheld is a deliberate act — the person aimed at THIS label and
 * squeezed. A camera is looking at the room continuously and will read
 * whatever passes the lens: the neighbouring label, a box, another asset's
 * tag, the one still on the desk. Filling the field lets the person see
 * what was read before they commit, so a misread costs a glance instead of
 * a false record (or a refusal that names the issued number, see above).
 * Confirm is one more tap, or Enter, exactly as for a typed number.
 */

const inputCls = "mt-1.5 w-full px-3 py-2 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20";
const labelCls = "text-[11px] font-semibold text-muted-foreground uppercase tracking-wide";
const cancelCls = "px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground";

type Outcome =
  | { kind: "already"; tagging: AssetTagging };

/** Which field, if any, has the camera open under it. One at a time: a
 *  second live camera would be two streams and two detect loops for one
 *  pair of hands. */
type CameraFor = "tag" | "serial" | null;

/** The station's Type / Camera control (`ModeButton` in `BarcodeStation.tsx`,
 *  which is a page and cannot be imported by a component the page itself
 *  imports), in the same classes, so it reads as the same control in a
 *  smaller place. */
function ModeToggle({ mode, onChange, disabled, idPrefix }: {
  mode: "type" | "camera"; onChange: (m: "type" | "camera") => void; disabled: boolean; idPrefix: string;
}) {
  const btn = (m: "type" | "camera", Icon: typeof Tag, label: string) => (
    <button
      type="button"
      onClick={() => onChange(m)}
      disabled={disabled}
      aria-pressed={mode === m}
      data-testid={`${idPrefix}-mode-${m}`}
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10px] font-semibold",
        mode === m ? "bg-primary text-white" : "text-muted-foreground hover:bg-muted/40",
        disabled && "opacity-50 cursor-not-allowed",
      )}
    >
      <Icon size={10} /> {label}
    </button>
  );
  return (
    <div className="flex items-center gap-0.5 rounded-lg border border-border p-0.5" role="group" aria-label="How to enter the number">
      {btn("type", Keyboard, "Type")}
      {btn("camera", Camera, "Camera")}
    </div>
  );
}

interface Props {
  assetId: number;
  assetName: string;
  /** Whether the record has a serial to check a scanned one against. When it
   *  has none the serial field is not offered — the route would refuse any
   *  value — and the dialog says why. */
  hasSerialOnFile: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The label was recorded as affixed by THIS confirmation. */
  onConfirmed?: (res: ConfirmAffixedResult) => void;
  /** The label was already affixed; nothing was written. */
  onAlready?: (tagging: AssetTagging) => void;
}

export function ConfirmAffixedDialog({
  assetId, assetName, hasSerialOnFile, open, onOpenChange, onConfirmed, onAlready,
}: Props) {
  const qc = useQueryClient();
  const [tagNumber, setTagNumber] = useState("");
  const [serial, setSerial] = useState("");
  const [fittedBy, setFittedBy] = useState("");
  // Which symbology the camera read each value off — handoff 54. Sent as
  // `scanned_format` / `serial_format` so the refused-affix record can say
  // whether the number came off Cadra's label or a manufacturer's. Typing
  // (or a keyboard-wedge scanner, which is typing) clears it: the client
  // only claims a format it actually observed.
  const [tagFormat, setTagFormat] = useState<ScanFormat | null>(null);
  const [serialFormat, setSerialFormat] = useState<ScanFormat | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  // Default Type, as the station does. Never auto-selected on a small screen
  // or anywhere else: the handheld path is the primary design.
  const [cameraFor, setCameraFor] = useState<CameraFor>(null);
  const tagRef = useRef<HTMLInputElement>(null);
  const serialRef = useRef<HTMLInputElement>(null);
  const prevCameraRef = useRef<CameraFor>(null);

  // Switching the camera off — by the toggle or by a detection — puts the
  // cursor back in the field it was open for, so the handheld path (Enter
  // submits) is exactly where it was before. A submit also switches it off,
  // but the field is disabled while the request is pending, so focus is lost
  // there exactly as it is on the typed path.
  useEffect(() => {
    const prev = prevCameraRef.current;
    prevCameraRef.current = cameraFor;
    if (!open || cameraFor !== null || prev === null) return;
    (prev === "tag" ? tagRef : serialRef).current?.focus();
  }, [cameraFor, open]);

  const mutation = useMutation({
    mutationFn: async () => {
      // Read the block BEFORE posting. A repeat confirmation returns exactly
      // what a first one does, so this is the only clock-free way to know
      // whether the server recorded anything.
      const before = await fetchAssetTagging(assetId);
      const res = await confirmTagAffixed(assetId, {
        tag_number: tagNumber, serial_number: serial, affixed_by_name: fittedBy,
        scanned_format: tagFormat ?? undefined,
        serial_format: serial.trim() ? serialFormat ?? undefined : undefined,
      });
      // Same label, already affixed before the POST, same instant after it.
      // The `label_id` comparison matters only for an asset carrying more
      // than one non-scrapped label, where the block may describe the older
      // affixed one while the scan box holds the newer.
      const already = before.label_state === "affixed"
        && before.label_id !== null
        && before.label_id === res.tagging.label_id
        && before.affixed_at !== null
        && before.affixed_at === res.tagging.affixed_at;
      return { res, already };
    },
    onSuccess: ({ res, already }) => {
      invalidateTagQueries(qc);
      qc.invalidateQueries({ queryKey: ["asset-tagging", assetId] });
      qc.invalidateQueries({ queryKey: ["asset", String(assetId)] });
      if (already) {
        setOutcome({ kind: "already", tagging: res.tagging });
        onAlready?.(res.tagging);
        return;
      }
      setOpen(false, true);
      onConfirmed?.(res);
    },
    onError: (e) => {
      // 400 `invalid_request` "no active tag": the card is stale — the label
      // was replaced or is pending replacement since the lookup.
      if ((e as CadraApiError).status === 400 || (e as CadraApiError).status === 409) {
        qc.invalidateQueries({ queryKey: ["asset-tagging", assetId] });
      }
    },
  });
  const err = mutation.error as CadraApiError | null;
  const ready = tagNumber.trim().length > 0;

  const setOpen = (next: boolean, done = false) => {
    if (!next && mutation.isPending && !done) return;
    if (!next) {
      setTagNumber("");
      setSerial("");
      setFittedBy("");
      setTagFormat(null);
      setSerialFormat(null);
      setOutcome(null);
      // Unmounting `BarcodeScanner` stops its stream (its own unmount
      // effect); a camera left running after the dialog is gone is a battery
      // problem and the kind of thing somebody notices on a projector.
      setCameraFor(null);
      mutation.reset();
    }
    onOpenChange(next);
  };

  const submit = () => {
    if (!ready || mutation.isPending || outcome) return;
    // A submit with the camera open stops it, for the same reason as close.
    setCameraFor(null);
    mutation.mutate();
  };

  const locked = mutation.isPending || outcome !== null;
  const camera = (field: Exclude<CameraFor, null>) => cameraFor === field ? "camera" : "type";
  const toggleCamera = (field: Exclude<CameraFor, null>, m: "type" | "camera") =>
    setCameraFor(m === "camera" ? field : null);

  return (
    <Dialog open={open} onOpenChange={(next) => setOpen(next)}>
      {/* A column whose middle scrolls: with the camera preview open the
          form is taller than a 720px viewport, and the first run of spec 40
          found Confirm scrolled out of sight below it. The header and the
          footer stay put; the fields and the preview scroll between them.
          (A sticky footer was tried first and floated over the form.) */}
      <DialogContent className="sm:max-w-md max-h-[calc(100vh-2rem)] flex flex-col" data-testid="dialog-confirm-affixed">
        <DialogHeader className="shrink-0">
          <DialogTitle className="flex items-center gap-2">
            <Tag size={16} className="text-primary" /> Confirm the label is on the asset
          </DialogTitle>
          <DialogDescription>
            Scan the label fixed to <span className="font-semibold text-foreground">{assetName}</span>,
            with a handheld scanner or the camera.
            Cadra checks the number you scan against the tag it issued for this asset and refuses
            the confirmation if it is not the same label. The expected number is deliberately not
            shown here: the check is only worth something if the number comes off the label in
            your hand.
          </DialogDescription>
        </DialogHeader>

        {/* A form so a handheld scanner's trailing Enter submits; the footer's
            Confirm button is this form's submit button (`form=` attribute). */}
        <form
          id="affix-form"
          onSubmit={(e) => { e.preventDefault(); submit(); }}
          className="space-y-3 min-h-0 overflow-y-auto -mx-1 px-1"
        >
          <div>
            <div className="flex items-center justify-between gap-2">
              <label htmlFor="affix-tag-number" className={labelCls}>Tag number on the label</label>
              <ModeToggle idPrefix="affix-tag" mode={camera("tag")} onChange={m => toggleCamera("tag", m)} disabled={locked} />
            </div>
            {/* The input stays mounted in camera mode, as the station's does:
                a handheld scanner emulates a keyboard and still lands here. */}
            <input
              id="affix-tag-number"
              ref={tagRef}
              type="text"
              autoFocus
              autoComplete="off"
              spellCheck={false}
              value={tagNumber}
              onChange={e => { setTagNumber(e.target.value); setTagFormat(null); }}
              disabled={locked}
              className={cn(inputCls, "font-mono")}
              placeholder="Scan the label"
              data-testid="input-affix-tag-number"
            />
            {cameraFor === "tag" && (
              <div className="mt-2" data-testid="affix-camera" data-for="tag">
                {/* Fills the field and switches back to Type (which returns
                    focus to the field). It does NOT submit — see the file
                    comment: the camera reads whatever passes the lens. */}
                <BarcodeScanner
                  onDetected={(value, format) => { setTagNumber(value); setTagFormat(format); setCameraFor(null); }}
                  onSuggestType={() => tagRef.current?.focus()}
                />
              </div>
            )}
            {tagFormat && (
              <p className="text-[11px] text-muted-foreground mt-1" data-testid="affix-tag-format">
                Camera read: {SCAN_FORMAT_LABELS[tagFormat]}.
              </p>
            )}
          </div>

          <div>
            <label htmlFor="affix-fitted-by" className={labelCls}>Fitted by</label>
            <input
              id="affix-fitted-by"
              type="text"
              autoComplete="off"
              value={fittedBy}
              onChange={e => setFittedBy(e.target.value)}
              disabled={locked}
              className={inputCls}
              placeholder="Optional — the person who fixed it, if not you"
              data-testid="input-affix-fitted-by"
            />
          </div>

          {hasSerialOnFile ? (
            <div>
              <div className="flex items-center justify-between gap-2">
                <label htmlFor="affix-serial" className={labelCls}>Serial number on the asset</label>
                <ModeToggle idPrefix="affix-serial" mode={camera("serial")} onChange={m => toggleCamera("serial", m)} disabled={locked} />
              </div>
              <input
                id="affix-serial"
                ref={serialRef}
                type="text"
                autoComplete="off"
                spellCheck={false}
                value={serial}
                onChange={e => { setSerial(e.target.value); setSerialFormat(null); }}
                disabled={locked}
                className={cn(inputCls, "font-mono")}
                placeholder="Optional — scan the manufacturer serial too, if legible"
                data-testid="input-affix-serial"
              />
              {cameraFor === "serial" && (
                <div className="mt-2" data-testid="affix-camera" data-for="serial">
                  <BarcodeScanner
                    onDetected={(value, format) => { setSerial(value); setSerialFormat(format); setCameraFor(null); }}
                    onSuggestType={() => serialRef.current?.focus()}
                  />
                </div>
              )}
              {serialFormat && (
                <p className="text-[11px] text-muted-foreground mt-1" data-testid="affix-serial-format">
                  Camera read: {SCAN_FORMAT_LABELS[serialFormat]}.
                </p>
              )}
              <p className="text-[11px] text-muted-foreground mt-1">
                If you scan it, it is checked against the record as well: the tag check proves the
                label is the one Cadra issued, the serial check proves it went onto the right box.
              </p>
            </div>
          ) : (
            <p className="text-[11px] text-muted-foreground inline-flex items-start gap-1.5" data-testid="affix-no-serial">
              <Info size={12} className="shrink-0 mt-0.5" />
              This record has no serial number, so a scanned serial cannot be checked and is not asked for.
            </p>
          )}

          {err && (
            <div className="flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3" data-testid="affix-refusal" role="alert">
              <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
              <ApiErrorMessage err={err} />
            </div>
          )}

          {outcome?.kind === "already" && (
            <div className="flex items-start gap-2 bg-amber-50 dark:bg-amber-950/30 border border-amber-200/70 dark:border-amber-800/30 rounded-xl p-3" data-testid="affix-already" role="status">
              <Info size={14} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
              <p className="text-[12px] text-amber-700 dark:text-amber-400">
                <span className="font-semibold">
                  Already confirmed on {formatIsoDateTime(outcome.tagging.affixed_at)}
                  {outcome.tagging.affixed_by_name ? ` by ${outcome.tagging.affixed_by_name}` : ""}.
                </span>{" "}
                Nothing was changed: the original record of who fitted this label and when stands.
              </p>
            </div>
          )}
        </form>

        <DialogFooter className="shrink-0">
          {outcome ? (
            <button type="button" onClick={() => setOpen(false, true)} data-testid="button-close-affix" className="px-3 py-1.5 text-xs font-semibold rounded-xl border border-border hover:bg-muted/40">
              Close
            </button>
          ) : (
            <>
              <button type="button" onClick={() => setOpen(false)} className={cancelCls}>Cancel</button>
              <button
                type="submit"
                form="affix-form"
                disabled={!ready || mutation.isPending}
                data-testid="button-submit-affixed"
                className={cn(
                  "px-3 py-1.5 text-xs font-semibold rounded-xl inline-flex items-center gap-1.5",
                  ready && !mutation.isPending
                    ? "bg-primary text-white hover:opacity-90"
                    : "bg-muted text-muted-foreground cursor-not-allowed",
                )}
              >
                {mutation.isPending ? <Loader2 size={12} className="animate-spin" /> : <><Check size={12} /> Confirm affixed</>}
              </button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
