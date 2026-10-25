/**
 * Capture at the Barcode Station (handoff 67 §1, Lot 6) — the parts of the
 * capture screen that only the station draws. The flow is 66's, unchanged:
 * the same `POST /audit/captures`, the same review. What differs is where it
 * runs.
 *
 * - **The station is a device.** The Asset Controller registers it like a
 *   phone and binds it to whoever is signed in at the station. This browser
 *   remembers which of that person's devices it is, so the next capture
 *   names the same one without being asked.
 * - **A shift change** is block-per-person: the person leaving returns their
 *   block (unused codes voided), the Asset Controller rebinds the station to
 *   the next person, and they are issued a fresh block. Rebinding never has
 *   to reason about another person's half-used codes.
 * - **Print through the station's funnel.** A code is printed with the same
 *   `printLabels` the station prints every tag with, then the print is
 *   RECORDED (`POST /audit/codes/printed`), as every tag print is since 61.
 * - **A spoiled label** voids that one code, with a reason; it is never
 *   reissued, and the screen moves to the next reserved code.
 *
 * Every refusal is the server's sentence, verbatim.
 */
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, MonitorSmartphone, Printer, Undo2 } from "lucide-react";
import type { CadraApiError } from "@/lib/api";
import { printLabels, type LabelSize } from "@/lib/labels";
import {
  recordCodesPrinted, returnBlock, voidSpoiledCode,
  type AuditBlock, type AuditCode, type AuditDevice,
} from "@/lib/auditCapture";
import LabelSizePicker from "@/components/station/LabelSizePicker";
import { Btn, ErrorPanel, INPUT, invalidateAudit, when } from "@/pages/audit/shared";
import { cn } from "@/lib/utils";

/** Which of the signed-in person's devices this station is. Per browser:
 *  a station is one computer. Storage can be missing or refuse (a private
 *  window); the screen then preselects the person's first device. */
const STATION_DEVICE_KEY = "cadra.station.device_code";

export function readStationDeviceCode(): string | null {
  try {
    return window.localStorage.getItem(STATION_DEVICE_KEY);
  } catch {
    return null;
  }
}

export function rememberStationDeviceCode(code: string) {
  try {
    window.localStorage.setItem(STATION_DEVICE_KEY, code);
  } catch {
    // Not remembered; the screen still works, it just asks again next time.
  }
}

/** The shift-change rule, said once where the person reads their block. */
export const SHIFT_CHANGE_RULE =
  "At a shift change the person leaving returns their block, and the Asset Controller rebinds the station to the next person, who is issued a fresh block.";

export function StationDeviceLine({ device, loaded, devices, onDevice }: {
  device: AuditDevice | null; loaded: boolean; devices: AuditDevice[]; onDevice: (id: number) => void;
}) {
  if (!loaded) return null;
  if (!device) {
    return (
      <p className="text-[12px] text-amber-800 dark:text-amber-300" data-testid="station-no-device">
        No device is bound to you, so this station cannot capture for you yet. The Asset Controller binds the
        station's device to whoever is signed in at the station, on <span className="font-semibold">Devices and codes</span>.
      </p>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <p className="text-[12px] flex items-center gap-1.5" data-testid="station-device-line" data-device-code={device.device_code}>
        <MonitorSmartphone size={13} className="text-primary" />
        This station is <span className="font-semibold">{device.name}</span>
        <span className="font-mono text-muted-foreground">({device.device_code})</span>, bound to you.
      </p>
      {/* A person bound to more than one device (a phone and the station)
          says which one this computer is; the choice is remembered here. */}
      {devices.length > 1 && (
        <select className={INPUT} data-testid="capture-device" aria-label="Which device this station is"
                value={device.id} onChange={e => onDevice(Number(e.target.value))}>
          {devices.map(d => <option key={d.id} value={d.id}>{d.name} ({d.device_code})</option>)}
        </select>
      )}
    </div>
  );
}

/** The station's open block, and *Return my block*: the person's own, with
 *  an optional reason and a confirm step that says what returning does. */
export function StationBlockLine({ block, loading }: { block: AuditBlock | null | undefined; loading: boolean }) {
  const qc = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState("");
  const giveBack = useMutation<AuditBlock, CadraApiError>({
    mutationFn: () => returnBlock(block!.id, reason),
    onSuccess: () => {
      setConfirming(false);
      setReason("");
      invalidateAudit(qc);
    },
  });
  const reserved = block?.codes?.filter(c => c.state === "reserved").length ?? block?.codes_by_state?.reserved ?? 0;

  return (
    <div className="space-y-1.5" data-testid="station-block">
      {giveBack.data && (
        <p className="text-[12px] text-green-800 dark:text-green-300 flex items-center gap-1.5" data-testid="return-block-done">
          <CheckCircle2 size={13} /> Block {giveBack.data.name} returned; {giveBack.data.voided_now ?? 0} unused
          code{giveBack.data.voided_now === 1 ? "" : "s"} voided.
        </p>
      )}
      {loading ? null : !block ? (
        <p className="text-[12px] text-amber-800 dark:text-amber-300" data-testid="station-no-block">
          No block of codes is open on this station's device. The Asset Controller issues one on <span className="font-semibold">Devices and codes</span>.
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-[12px]" data-testid="station-block-line">
            Block <span className="font-semibold">{block.name}</span>
            {block.first_code && block.last_code && <span className="font-mono text-muted-foreground"> {block.first_code}–{block.last_code}</span>}
            {" "}· {reserved} code{reserved === 1 ? "" : "s"} left
          </p>
          {!confirming && (
            <Btn kind="plain" testid="button-return-block" onClick={() => { giveBack.reset(); setConfirming(true); }}>
              <Undo2 size={12} /> Return my block
            </Btn>
          )}
        </div>
      )}
      {block && confirming && (
        <div className="rounded-xl border border-amber-300 bg-amber-50 dark:bg-amber-950/30 p-3 space-y-2" data-testid="return-block-confirm">
          <p className="text-[12px] text-amber-900 dark:text-amber-200">
            Returning {block.name} voids its {reserved} unused code{reserved === 1 ? "" : "s"}. A voided code is never
            reissued. Codes already used in a capture are not touched.
          </p>
          <input className={cn(INPUT, "w-full")} placeholder="Reason (optional) — e.g. end of shift"
                 value={reason} onChange={e => setReason(e.target.value)} data-testid="input-return-block-reason" />
          <div className="flex gap-2">
            <Btn kind="danger" testid="button-return-block-confirm" pending={giveBack.isPending} onClick={() => giveBack.mutate()}>
              Return the block
            </Btn>
            <Btn kind="plain" onClick={() => setConfirming(false)}>Keep it</Btn>
          </div>
        </div>
      )}
      {giveBack.error && <ErrorPanel err={giveBack.error} testid="return-block-error" />}
      <p className="text-[11px] text-muted-foreground" data-testid="station-shift-rule">{SHIFT_CHANGE_RULE}</p>
    </div>
  );
}

/**
 * The code for the item's label, at the station: *Print label* through the
 * station's print funnel, the print recorded, and *Spoiled label* beside it.
 * `codeRow` is the code's ledger row from the block, read for its print
 * count; it refreshes after the print is recorded.
 */
export function StationCodePrint({ code, codeRow, deviceCode, assetName, serialNumber, size, onSize, onSpoiled }: {
  code: string; codeRow: AuditCode | null; deviceCode: string | null; assetName: string; serialNumber?: string;
  size: LabelSize; onSize: (s: LabelSize) => void; onSpoiled: () => void;
}) {
  const qc = useQueryClient();
  const [notice, setNotice] = useState<{ kind: "ok" | "warn" | "error"; text: string } | null>(null);
  const [printing, setPrinting] = useState(false);
  const [spoiling, setSpoiling] = useState(false);
  const [spoilReason, setSpoilReason] = useState("");

  /** The station's `print()` (handoff 61), for an audit code: print first,
   *  then record. A failure to record does not undo the print; it is said,
   *  in words. */
  async function print() {
    setNotice(null);
    setPrinting(true);
    let printed = false;
    try {
      const res = await printLabels([{ tag_number: code, asset_code: code, asset_name: assetName, serial_number: serialNumber }], size);
      printed = true;
      if (res.qrUnavailable) {
        setNotice({ kind: "warn", text: "QR codes could not be loaded from the server, so the label printed with the Code128 barcode only." });
      }
    } catch (e) {
      setNotice({ kind: "error", text: e instanceof Error ? e.message : "Could not open the print view." });
    }
    if (printed && deviceCode) {
      try {
        await recordCodesPrinted(deviceCode, [code]);
        invalidateAudit(qc);
      } catch (e) {
        setNotice({
          kind: "warn",
          text: `The label printed, but the print was not recorded (${e instanceof Error ? e.message : "unknown error"}). Print it again from here to record it.`,
        });
      }
    }
    setPrinting(false);
  }

  const spoil = useMutation<AuditCode, CadraApiError>({
    mutationFn: () => voidSpoiledCode(code, spoilReason),
    onSuccess: (row) => {
      setSpoiling(false);
      setSpoilReason("");
      setNotice({ kind: "ok", text: `Code ${row.code} voided${row.void_reason ? ` (${row.void_reason})` : ""}. A voided code is never reissued; the next code is below.` });
      invalidateAudit(qc);
      onSpoiled();
    },
  });

  const printCount = codeRow?.print_count ?? 0;
  return (
    <div className="space-y-2" data-testid="station-code-print">
      <div className="flex flex-wrap items-center gap-2">
        <Btn testid="button-print-code" pending={printing} onClick={() => void print()}>
          <Printer size={12} /> Print label
        </Btn>
        <LabelSizePicker value={size} onChange={onSize} />
        {!spoiling && (
          <button type="button" className="text-[11px] underline text-muted-foreground hover:text-foreground"
                  data-testid="button-spoil-code" onClick={() => { spoil.reset(); setSpoiling(true); }}>
            Spoiled label
          </button>
        )}
      </div>
      {printCount > 0 && (
        <p className="text-[11px] text-muted-foreground" data-testid="capture-code-printed" data-print-count={printCount}>
          Printed {printCount === 1 ? "once" : `${printCount} times`}
          {codeRow?.last_printed_at && <>, last {when(codeRow.last_printed_at)}</>}
          {codeRow?.last_printed_by && <> by {codeRow.last_printed_by.name}</>}.
        </p>
      )}
      {notice && (
        <p className={cn("text-[11px]",
          notice.kind === "ok" ? "text-green-800 dark:text-green-300"
            : notice.kind === "warn" ? "text-amber-800 dark:text-amber-300"
            : "text-red-700 dark:text-red-400")} data-testid="station-print-notice" data-kind={notice.kind}>
          {notice.text}
        </p>
      )}
      {spoiling && (
        <div className="rounded-xl border border-border p-3 space-y-2" data-testid="spoil-code-confirm">
          <p className="text-[12px]">
            Void <span className="font-mono font-semibold">{code}</span> — the label is spoiled. A voided code is never reissued.
          </p>
          <input className={cn(INPUT, "w-full")} placeholder="Reason (required) — e.g. label torn at print"
                 value={spoilReason} onChange={e => setSpoilReason(e.target.value)} data-testid="input-spoil-reason" />
          <div className="flex gap-2">
            <Btn kind="danger" testid="button-spoil-confirm" disabled={!spoilReason.trim()} pending={spoil.isPending}
                 onClick={() => spoil.mutate()}>
              Void this code
            </Btn>
            <Btn kind="plain" onClick={() => setSpoiling(false)}>Keep it</Btn>
          </div>
          {spoil.error && <ErrorPanel err={spoil.error} testid="spoil-code-error" />}
        </div>
      )}
    </div>
  );
}
