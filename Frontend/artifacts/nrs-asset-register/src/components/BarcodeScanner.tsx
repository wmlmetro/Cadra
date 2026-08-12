/**
 * Camera barcode scanner for the Barcode Station.
 *
 * Uses the built-in BarcodeDetector API — no bundled decoding library. That
 * keeps the bundle small and the decode fast (it's the platform's own scanner),
 * at the cost of support: Chrome/Edge and Android WebView have it, Safari and
 * Firefox do not. Field handhelds are Android, so this is the right trade —
 * but the component states the limitation plainly instead of silently failing,
 * and typing a code always remains available.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, CameraOff, AlertCircle, Zap, ZapOff } from "lucide-react";
import { cn } from "@/lib/utils";

// BarcodeDetector isn't in lib.dom yet.
interface DetectedBarcode { rawValue: string; format: string }
interface BarcodeDetectorLike { detect(source: CanvasImageSource): Promise<DetectedBarcode[]> }
type BarcodeDetectorCtor = new (opts?: { formats?: string[] }) => BarcodeDetectorLike;

const FORMATS = ["code_128", "qr_code", "code_39", "ean_13", "data_matrix"];

function detectorCtor(): BarcodeDetectorCtor | null {
  const w = window as unknown as { BarcodeDetector?: BarcodeDetectorCtor };
  return w.BarcodeDetector ?? null;
}

type Support = "checking" | "ok" | "no-detector" | "no-camera" | "insecure";

export default function BarcodeScanner({
  onDetected,
  className,
}: {
  /** Called with the decoded value. The scanner stops itself first. */
  onDetected: (value: string) => void;
  className?: string;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number | null>(null);
  const runningRef = useRef(false);
  // Held in a ref so the detect loop always calls the latest handler without
  // being torn down and restarted on every parent render.
  const onDetectedRef = useRef(onDetected);
  onDetectedRef.current = onDetected;

  const [support, setSupport] = useState<Support>("checking");
  const [active, setActive] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [torchOn, setTorchOn] = useState(false);
  const [torchAvailable, setTorchAvailable] = useState(false);

  useEffect(() => {
    if (!window.isSecureContext) return setSupport("insecure");
    if (!navigator.mediaDevices?.getUserMedia) return setSupport("no-camera");
    if (!detectorCtor()) return setSupport("no-detector");
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
    setActive(false);
    setTorchOn(false);
    setTorchAvailable(false);
    setStatus("");
  }, []);

  // Release the camera when the page unmounts — an orphaned stream keeps the
  // device's camera light on and blocks other apps from opening it.
  useEffect(() => stop, [stop]);

  const start = useCallback(async () => {
    setError(null);
    const Ctor = detectorCtor();
    if (!Ctor) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
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

      const track = stream.getVideoTracks()[0];
      const caps = track?.getCapabilities?.() as (MediaTrackCapabilities & { torch?: boolean }) | undefined;
      setTorchAvailable(Boolean(caps?.torch));

      const detector = new Ctor({ formats: FORMATS });
      runningRef.current = true;

      const tick = async () => {
        if (!runningRef.current) return;
        try {
          const found = await detector.detect(video);
          if (found.length && found[0].rawValue) {
            const value = found[0].rawValue.trim();
            stop();
            onDetectedRef.current(value);
            return;
          }
        } catch {
          // A transient decode failure (e.g. a frame arriving mid-resize) is
          // normal — keep scanning rather than tearing the session down.
        }
        if (runningRef.current) rafRef.current = requestAnimationFrame(() => void tick());
      };
      rafRef.current = requestAnimationFrame(() => void tick());
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(
        /denied|NotAllowed/i.test(msg)
          ? "Camera access was denied. Allow it in the browser's site settings, then try again."
          : `Camera error: ${msg}`,
      );
      stop();
    }
  }, [stop]);

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

  if (support === "checking") return null;

  if (support !== "ok") {
    const msg =
      support === "insecure"
        ? "Camera scanning needs a secure (https) connection."
        : support === "no-camera"
        ? "This device has no camera available to the browser."
        : "This browser has no built-in barcode detector. Chrome or Edge on Android/desktop can scan; " +
          "on Safari or Firefox, use a handheld scanner or type the code.";
    return (
      <div className={cn("flex items-start gap-2 rounded-xl border border-border bg-muted/30 p-3", className)}>
        <AlertCircle size={14} className="mt-0.5 shrink-0 text-muted-foreground" />
        <p className="text-[12px] text-muted-foreground">{msg}</p>
      </div>
    );
  }

  return (
    <div className={cn("space-y-2", className)}>
      <div className="relative overflow-hidden rounded-xl border border-border bg-black/90 aspect-video">
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
          // Scan reticle — helps users centre the tag, which materially
          // improves the detector's hit rate on small printed barcodes.
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <div className="h-[38%] w-[74%] rounded-lg border-2 border-white/80 shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]" />
          </div>
        )}
      </div>

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

        {status && <span className="text-[11px] text-muted-foreground">{status}</span>}
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-xl border border-red-200/70 bg-red-50 p-3 dark:border-red-800/30 dark:bg-red-950/30">
          <AlertCircle size={14} className="mt-0.5 shrink-0 text-red-600 dark:text-red-400" />
          <p className="text-[12px] text-red-700 dark:text-red-400">{error}</p>
        </div>
      )}
    </div>
  );
}
