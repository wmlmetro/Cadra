/**
 * Camera barcode scanner for the Barcode Station — handoff 54.
 *
 * The engine is BUNDLED (`src/lib/scanEngine.ts`, ZXing compiled to WASM),
 * not the platform's `BarcodeDetector`: a scanner whose behaviour depends on
 * which phone it runs on cannot be made to work every time by fixing the
 * code around it. iPhone Safari, Firefox and Chrome on Windows/Linux all
 * scan now; the only remaining reasons the camera cannot be used are no
 * camera, no https, and permission denied — each keeps its sentence.
 *
 * The rules this component enforces, from handoff 54:
 *
 *  - The engine module (and its ~930 KB wasm) loads when the camera STARTS,
 *    never on app boot.
 *  - The reticle is true: each frame is cropped to the reticle's rectangle
 *    and decoded there first; the full frame is a second pass only when the
 *    crop finds nothing, so a label held off-centre is still read.
 *  - Decoding is throttled to ~10 frames a second — WASM decode on a
 *    low-end Android is not free.
 *  - A 1D value is accepted when TWO CONSECUTIVE decodes agree (1D has no
 *    error correction worth the name; a partial read can yield a valid,
 *    wrong string). A 2D value is accepted on one. While a 1D value waits
 *    for its second read, the status says "Reading…" so a flicker of
 *    success is not mistaken for a failure.
 *  - Two DIFFERENT values in one frame — a laptop's underside — are never
 *    guessed between: the reticle crop is preferred, and if that still
 *    leaves more than one, both are shown and the operative taps.
 *  - The loop is never silent: after 4 s with no decode, a sentence; after
 *    10 s, the same plus "or type the code", and `onSuggestType` lets the
 *    parent focus its typed field with the camera left running.
 *  - The camera is asked for what the label needs: 1920×1080 ideal,
 *    continuous focus where the track supports it, a zoom control where
 *    `getCapabilities().zoom` exists, and a camera picker when the device
 *    has more than one (a MacBook's fixed-focus built-in camera vs a
 *    Continuity Camera or USB webcam — the operative chooses, and the
 *    choice is remembered per browser).
 *
 * A detection still STOPS the camera and hands the value up — it fills a
 * field and never submits (handoffs 39/40, unchanged).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, CameraOff, AlertCircle, Zap, ZapOff, ZoomIn } from "lucide-react";
import { cn } from "@/lib/utils";
import { SCAN_FORMAT_LABELS, type ScanFormat, type ScanHit } from "@/lib/scanFormats";
import { decideScan } from "@/lib/scanDecision";

export type { ScanFormat };

/** Loaded on demand — see the file comment. */
type Engine = typeof import("@/lib/scanEngine");

type Support = "checking" | "ok" | "no-camera" | "insecure";

/** Where the reticle sits, as fractions of the preview box. Shared by the
 *  overlay div and the crop so the rectangle people centre the label in is
 *  the rectangle the decoder reads. */
const RETICLE = { w: 0.74, h: 0.38 };

const DECODE_INTERVAL_MS = 100; // ~10 fps
const HINT_FIRST_MS = 4_000;
const HINT_SECOND_MS = 10_000;
const HINT_SENTENCE = "Nothing read yet — move closer, hold steady, or try the light.";

const DEVICE_STORE_KEY = "cadra.scanner.device";

function rememberDevice(id: string) {
  try { localStorage.setItem(DEVICE_STORE_KEY, id); } catch { /* per-browser convenience only */ }
}
function rememberedDevice(): string | null {
  try { return localStorage.getItem(DEVICE_STORE_KEY); } catch { return null; }
}

/** Map the reticle (fractions of the container) into source pixels of the
 *  video, accounting for `object-cover` cropping the video to fill the box. */
function reticleSourceRect(video: HTMLVideoElement, box: HTMLElement) {
  const vw = video.videoWidth, vh = video.videoHeight;
  const cw = box.clientWidth, ch = box.clientHeight;
  if (!vw || !vh || !cw || !ch) return null;
  const scale = Math.max(cw / vw, ch / vh);
  // Container point -> video point.
  const toVideo = (x: number, y: number) => ({
    x: (x - (cw - vw * scale) / 2) / scale,
    y: (y - (ch - vh * scale) / 2) / scale,
  });
  const tl = toVideo(cw * (1 - RETICLE.w) / 2, ch * (1 - RETICLE.h) / 2);
  const br = toVideo(cw * (1 + RETICLE.w) / 2, ch * (1 + RETICLE.h) / 2);
  const x = Math.max(0, Math.round(tl.x));
  const y = Math.max(0, Math.round(tl.y));
  return {
    x, y,
    w: Math.min(vw, Math.round(br.x)) - x,
    h: Math.min(vh, Math.round(br.y)) - y,
  };
}

interface ZoomRange { min: number; max: number; step: number }

export default function BarcodeScanner({
  onDetected,
  onSuggestType,
  className,
}: {
  /** Called with the decoded value and the symbology it was read from.
   *  The scanner stops itself first. */
  onDetected: (value: string, format: ScanFormat) => void;
  /** After 10 s with nothing read, the scanner suggests typing instead and
   *  calls this (once per camera session) so the parent can focus its typed
   *  field. The camera is left running. */
  onSuggestType?: () => void;
  className?: string;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number | null>(null);
  const runningRef = useRef(false);
  const busyRef = useRef(false);
  const engineRef = useRef<Engine | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  // Held in refs so the decode loop always sees the latest without being
  // torn down and restarted on every parent render.
  const onDetectedRef = useRef(onDetected);
  onDetectedRef.current = onDetected;
  const onSuggestTypeRef = useRef(onSuggestType);
  onSuggestTypeRef.current = onSuggestType;
  // §4's agreement rule: the 1D value waiting for its second read.
  const pending1DRef = useRef<ScanHit | null>(null);
  const lastTickRef = useRef(0);
  // The no-decode clock. Reset when the first decode attempt COMPLETES so
  // the wasm compile on the first start is not counted as silence.
  const lastReadRef = useRef(0);
  const firstDecodeDoneRef = useRef(false);
  const suggestedRef = useRef(false);
  const choicesRef = useRef<ScanHit[] | null>(null);

  const [support, setSupport] = useState<Support>("checking");
  const [active, setActive] = useState(false);
  const [status, setStatus] = useState("");
  const [hint, setHint] = useState<0 | 1 | 2>(0);
  const [error, setError] = useState<string | null>(null);
  const [torchOn, setTorchOn] = useState(false);
  const [torchAvailable, setTorchAvailable] = useState(false);
  const [zoomRange, setZoomRange] = useState<ZoomRange | null>(null);
  const [zoom, setZoom] = useState(1);
  const [devices, setDevices] = useState<{ id: string; label: string }[]>([]);
  const [deviceId, setDeviceId] = useState<string | null>(rememberedDevice);
  const [choices, setChoices] = useState<ScanHit[] | null>(null);
  const [granted, setGranted] = useState<string | null>(null);

  useEffect(() => {
    if (!window.isSecureContext) return setSupport("insecure");
    if (!navigator.mediaDevices?.getUserMedia) return setSupport("no-camera");
    setSupport("ok");
  }, []);

  const stop = useCallback(() => {
    runningRef.current = false;
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    pending1DRef.current = null;
    choicesRef.current = null;
    setChoices(null);
    setActive(false);
    setTorchOn(false);
    setTorchAvailable(false);
    setZoomRange(null);
    setStatus("");
    setHint(0);
    setGranted(null);
  }, []);

  // Release the camera when the page unmounts — an orphaned stream keeps the
  // device's camera light on and blocks other apps from opening it.
  useEffect(() => stop, [stop]);

  const accept = useCallback((hit: ScanHit) => {
    stop();
    onDetectedRef.current(hit.value, hit.format);
  }, [stop]);

  const start = useCallback(async (overrideDeviceId?: string | null) => {
    setError(null);
    try {
      const wanted = overrideDeviceId !== undefined ? overrideDeviceId : deviceId;
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          // A remembered device that was unplugged must not kill the camera
          // outright, so the id is `ideal`, not `exact`: the browser falls
          // back to what exists.
          ...(wanted ? { deviceId: { ideal: wanted } } : { facingMode: { ideal: "environment" } }),
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
      });
      streamRef.current = stream;
      const video = videoRef.current;
      if (!video) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      video.srcObject = stream;
      await video.play();
      setActive(true);
      setStatus("Point the camera at a tag");
      setHint(0);
      suggestedRef.current = false;
      firstDecodeDoneRef.current = false;
      pending1DRef.current = null;
      lastReadRef.current = performance.now();

      const track = stream.getVideoTracks()[0];
      const caps = track?.getCapabilities?.() as (MediaTrackCapabilities & {
        torch?: boolean;
        zoom?: { min: number; max: number; step?: number };
        focusMode?: string[];
      }) | undefined;
      setTorchAvailable(Boolean(caps?.torch));
      // Continuous focus where the track supports it — `ideal` resolution
      // above and this are requests, not outcomes; what was actually
      // granted is shown under the preview (§3's `getSettings()`).
      if (caps?.focusMode?.includes("continuous")) {
        track.applyConstraints({
          advanced: [{ focusMode: "continuous" } as unknown as MediaTrackConstraintSet],
        }).catch(() => undefined);
      }
      if (caps?.zoom && caps.zoom.max > caps.zoom.min) {
        setZoomRange({
          min: caps.zoom.min,
          max: caps.zoom.max,
          step: caps.zoom.step || (caps.zoom.max - caps.zoom.min) / 10,
        });
        const current = (track.getSettings() as MediaTrackSettings & { zoom?: number }).zoom;
        setZoom(current ?? caps.zoom.min);
      }
      const s = track?.getSettings?.();
      if (s?.width && s?.height) setGranted(`${s.width}×${s.height}`);

      // Labels are only readable after permission, which we now have. More
      // than one camera => the operative chooses (a MacBook's fixed-focus
      // built-in vs an autofocusing Continuity Camera or USB webcam).
      navigator.mediaDevices.enumerateDevices().then((all) => {
        const cams = all.filter((d) => d.kind === "videoinput")
          .map((d, i) => ({ id: d.deviceId, label: d.label || `Camera ${i + 1}` }));
        setDevices(cams);
        const settingsId = (track.getSettings() as MediaTrackSettings).deviceId;
        if (settingsId) setDeviceId(settingsId);
      }).catch(() => undefined);

      // The engine, loaded now and not before — the wasm is fetched on the
      // first decode, never on app boot.
      const engine = (engineRef.current ??= await import("@/lib/scanEngine"));
      // Stopped while the engine loaded: the stream is gone, don't scan it.
      if (!streamRef.current) return;
      runningRef.current = true;

      const tick = async (now: number) => {
        if (!runningRef.current) return;
        const schedule = () => {
          if (runningRef.current) rafRef.current = requestAnimationFrame((t) => void tick(t));
        };
        if (busyRef.current || choicesRef.current || now - lastTickRef.current < DECODE_INTERVAL_MS) {
          return schedule();
        }
        lastTickRef.current = now;
        busyRef.current = true;
        try {
          const box = boxRef.current;
          if (!video.videoWidth || !box) return;
          const canvas = (canvasRef.current ??= document.createElement("canvas"));
          const ctx = canvas.getContext("2d", { willReadFrequently: true });
          if (!ctx) return;

          const grab = (x: number, y: number, w: number, h: number) => {
            canvas.width = w;
            canvas.height = h;
            ctx.drawImage(video, x, y, w, h, 0, 0, w, h);
            return ctx.getImageData(0, 0, w, h);
          };

          // Pass 1: the reticle region — what makes the reticle true.
          let hits: ScanHit[] = [];
          const rect = reticleSourceRect(video, box);
          if (rect && rect.w > 16 && rect.h > 16) {
            hits = await engine.decodeFrame(grab(rect.x, rect.y, rect.w, rect.h));
          }
          // Pass 2, only when the crop finds nothing: the whole frame, so a
          // label held off-centre is still read.
          if (hits.length === 0) {
            hits = await engine.decodeFrame(grab(0, 0, video.videoWidth, video.videoHeight));
          }
          if (!runningRef.current) return;

          const t = performance.now();
          if (!firstDecodeDoneRef.current) {
            // The first decode paid for the wasm compile; silence starts now.
            firstDecodeDoneRef.current = true;
            if (hits.length === 0) lastReadRef.current = t;
          }

          if (hits.length === 0) {
            const quiet = t - lastReadRef.current;
            if (quiet >= HINT_SECOND_MS) {
              setHint(2);
              if (!suggestedRef.current) {
                suggestedRef.current = true;
                onSuggestTypeRef.current?.();
              }
            } else if (quiet >= HINT_FIRST_MS) {
              setHint(1);
            }
            return;
          }

          lastReadRef.current = t;
          setHint(0);

          // §2 and §4 live in `decideScan` (pure, proved by spec 54 without
          // a camera): 2D accepted on one decode, 1D on two agreeing,
          // several distinct values become the operative's choice — never a
          // guess. The reticle preference was already applied above: what
          // reaches here as plural survived the crop pass.
          const step = decideScan(hits, pending1DRef.current);
          pending1DRef.current = step.pending;
          switch (step.decision.kind) {
            case "accept":
              return accept(step.decision.hit);
            case "choose":
              choicesRef.current = step.decision.hits;
              setChoices(step.decision.hits);
              setStatus("");
              return;
            case "reading":
              // First read of this 1D value, or two frames disagreed: wait
              // for the agreeing read, and say so, briefly, so a flicker of
              // success is not mistaken for a failure.
              setStatus("Reading…");
              return;
          }
        } catch {
          // A transient decode failure (e.g. a frame arriving mid-resize) is
          // normal — keep scanning rather than tearing the session down.
        } finally {
          busyRef.current = false;
          schedule();
        }
      };
      rafRef.current = requestAnimationFrame((t) => void tick(t));
    } catch (e) {
      const name = e instanceof DOMException ? e.name : "";
      const msg = e instanceof Error ? e.message : String(e);
      setError(
        /denied|NotAllowed/i.test(name + msg)
          ? "Camera access was denied. Allow it in the browser's site settings, then try again."
          : /NotFound|DevicesNotFound/i.test(name + msg)
          ? "This device has no camera available to the browser."
          : `Camera error: ${msg}`,
      );
      stop();
    }
  }, [accept, deviceId, stop]);

  const toggleTorch = useCallback(async () => {
    const track = streamRef.current?.getVideoTracks()[0];
    if (!track) return;
    const next = !torchOn;
    try {
      // `torch` is a real constraint on Android Chrome but isn't in lib.dom.
      await track.applyConstraints({ advanced: [{ torch: next }] } as unknown as MediaTrackConstraints);
      setTorchOn(next);
    } catch {
      setTorchAvailable(false);
    }
  }, [torchOn]);

  const applyZoom = useCallback((value: number) => {
    setZoom(value);
    const track = streamRef.current?.getVideoTracks()[0];
    track?.applyConstraints({ advanced: [{ zoom: value }] } as unknown as MediaTrackConstraints)
      .catch(() => setZoomRange(null));
  }, []);

  const pickDevice = useCallback((id: string) => {
    setDeviceId(id);
    rememberDevice(id);
    if (runningRef.current || streamRef.current) {
      stop();
      void start(id);
    }
  }, [start, stop]);

  const resumeScanning = useCallback(() => {
    choicesRef.current = null;
    pending1DRef.current = null;
    lastReadRef.current = performance.now();
    setChoices(null);
    setStatus("Point the camera at a tag");
  }, []);

  if (support === "checking") return null;

  if (support !== "ok") {
    const msg =
      support === "insecure"
        ? "Camera scanning needs a secure (https) connection."
        : "This device has no camera available to the browser.";
    return (
      <div className={cn("flex items-start gap-2 rounded-xl border border-border bg-muted/30 p-3", className)}>
        <AlertCircle size={14} className="mt-0.5 shrink-0 text-muted-foreground" />
        <p className="text-[12px] text-muted-foreground">{msg}</p>
      </div>
    );
  }

  const hintText = hint === 0 ? null
    : hint === 1 ? HINT_SENTENCE
    : `${HINT_SENTENCE.slice(0, -1)} — or type the code.`;

  return (
    <div className={cn("space-y-2", className)}>
      <div ref={boxRef} className="relative overflow-hidden rounded-xl border border-border bg-black/90 aspect-video">
        <video
          ref={videoRef}
          playsInline
          muted
          className={cn("h-full w-full object-cover", !active && "invisible")}
        />
        {!active && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-white/60">
            <Camera size={22} />
            <p className="text-[12px]">Camera is off</p>
          </div>
        )}
        {active && (
          // The reticle is not cosmetic: the frame is cropped to this
          // rectangle and decoded there first (RETICLE above).
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <div
              className="rounded-lg border-2 border-white/80 shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]"
              style={{ width: `${RETICLE.w * 100}%`, height: `${RETICLE.h * 100}%` }}
            />
          </div>
        )}
        {active && granted && (
          <span
            className="absolute bottom-1 right-2 text-[10px] font-mono text-white/50"
            data-testid="scanner-granted"
          >{granted}</span>
        )}
      </div>

      {choices && (
        <div className="rounded-xl border border-border bg-muted/30 p-3 space-y-2" data-testid="scan-chooser">
          <p className="text-[12px] text-muted-foreground">
            More than one code is in view — tap the one you meant:
          </p>
          <div className="flex flex-wrap gap-2">
            {choices.map((c) => (
              <button
                key={`${c.format}:${c.value}`}
                type="button"
                onClick={() => accept(c)}
                data-testid="scan-choice"
                className="inline-flex items-center gap-1.5 rounded-xl border border-primary/40 bg-background px-3 py-2 text-xs hover:bg-primary/5"
              >
                <span className="font-mono font-semibold">{c.value}</span>
                <span className="text-[10px] text-muted-foreground">
                  {SCAN_FORMAT_LABELS[c.format]}
                </span>
              </button>
            ))}
            <button
              type="button"
              onClick={resumeScanning}
              data-testid="scan-choice-dismiss"
              className="rounded-xl border border-border px-3 py-2 text-xs text-muted-foreground hover:bg-muted/40"
            >
              Neither — keep scanning
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {!active ? (
          <button
            type="button"
            onClick={() => void start()}
            className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-3 py-2 text-xs font-semibold text-white hover:opacity-90"
          >
            <Camera size={12} /> Start camera
          </button>
        ) : (
          <button
            type="button"
            onClick={stop}
            className="inline-flex items-center gap-1.5 rounded-xl border border-border px-3 py-2 text-xs font-semibold hover:bg-muted/40"
          >
            <CameraOff size={12} /> Stop
          </button>
        )}

        {active && torchAvailable && (
          <button
            type="button"
            onClick={() => void toggleTorch()}
            className="inline-flex items-center gap-1.5 rounded-xl border border-border px-3 py-2 text-xs font-semibold hover:bg-muted/40"
          >
            {torchOn ? <ZapOff size={12} /> : <Zap size={12} />} {torchOn ? "Light off" : "Light on"}
          </button>
        )}

        {active && zoomRange && (
          <label className="inline-flex items-center gap-1.5 rounded-xl border border-border px-3 py-2">
            <ZoomIn size={12} className="text-muted-foreground" />
            <input
              type="range"
              min={zoomRange.min}
              max={zoomRange.max}
              step={zoomRange.step}
              value={zoom}
              onChange={(e) => applyZoom(Number(e.target.value))}
              data-testid="scanner-zoom"
              className="w-20 accent-[var(--primary)]"
              aria-label="Zoom"
            />
          </label>
        )}

        {devices.length > 1 && (
          <select
            value={deviceId ?? ""}
            onChange={(e) => pickDevice(e.target.value)}
            data-testid="scanner-device"
            aria-label="Which camera to use"
            className="rounded-xl border border-border bg-background px-2 py-2 text-xs max-w-[180px]"
          >
            {devices.map((d) => (
              <option key={d.id} value={d.id}>{d.label}</option>
            ))}
          </select>
        )}

        {status && !choices && (
          <span className="text-[11px] text-muted-foreground" data-testid="scanner-status">{status}</span>
        )}
      </div>

      {hintText && !choices && (
        <p className="text-[12px] text-muted-foreground" data-testid="scanner-hint" role="status">
          {hintText}
        </p>
      )}

      {error && (
        <div className="flex items-start gap-2 rounded-xl border border-red-200/70 bg-red-50 p-3 dark:border-red-800/30 dark:bg-red-950/30">
          <AlertCircle size={14} className="mt-0.5 shrink-0 text-red-600 dark:text-red-400" />
          <p className="text-[12px] text-red-700 dark:text-red-400">{error}</p>
        </div>
      )}
    </div>
  );
}
