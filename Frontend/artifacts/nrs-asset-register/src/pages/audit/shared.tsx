/**
 * What the five audit pages (handoff 66 §6) share: the header, the error
 * panel that prints the server's sentence verbatim, a photo drawn through
 * the bearer token, and the small controls drawn the way `SapLinks.tsx`
 * draws its own.
 */
import { useEffect, useState, type ReactNode } from "react";
import type { QueryClient } from "@tanstack/react-query";
import { AlertCircle, Clock, Image as ImageIcon, Inbox, Loader2 } from "lucide-react";
import type { CadraApiError } from "@/lib/api";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { fetchPictureObjectUrl } from "@/lib/assetPhotos";
import { AUDIT_KEY } from "@/lib/auditCapture";
import { cn, formatIsoDateTime } from "@/lib/utils";

export const INPUT = "px-2.5 py-1.5 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20";
export const TEXTAREA = "mt-1.5 w-full px-3 py-2 text-xs border border-border rounded-xl bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20";
export const LABEL = "text-[11px] font-semibold text-muted-foreground uppercase tracking-wide";

export const n = (v: number | null | undefined) => (v == null ? "—" : v.toLocaleString());
/** The server's instants are UTC, `YYYY-MM-DDTHH:MM:SSZ`. */
export const when = (at: string | null | undefined) => (at ? formatIsoDateTime(at.replace(" ", "T")) : "—");

/** After any act: every audit query. */
export function invalidateAudit(qc: QueryClient) {
  qc.invalidateQueries({ queryKey: AUDIT_KEY });
}

export function PageHeader({ icon, title, children, tabs }: {
  icon: ReactNode; title: string; children?: ReactNode; tabs?: ReactNode;
}) {
  return (
    <div className="px-5 py-3 border-b border-border bg-card">
      <h1 className="text-[14px] font-bold text-foreground flex items-center gap-2">{icon} {title}</h1>
      {children && <div className="text-[11px] text-muted-foreground mt-0.5 max-w-3xl">{children}</div>}
      {tabs}
    </div>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange, label, testidPrefix }: {
  tabs: { key: T; label: string }[]; value: T; onChange: (t: T) => void; label: string; testidPrefix: string;
}) {
  return (
    <div className="flex gap-1 mt-3 flex-wrap items-center" role="tablist" aria-label={label}>
      {tabs.map(t => (
        <button key={t.key} role="tab" aria-selected={value === t.key} onClick={() => onChange(t.key)}
          data-testid={`${testidPrefix}-${t.key}`}
          className={cn(
            "px-3 py-1.5 text-xs font-semibold rounded-xl border transition-colors",
            value === t.key ? "bg-primary text-white border-primary"
                            : "border-border text-muted-foreground hover:bg-accent hover:text-foreground",
          )}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function ErrorPanel({ err, testid = "audit-error" }: { err: CadraApiError | Error; testid?: string }) {
  return (
    <div className="flex items-start gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3"
         data-testid={testid}>
      <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
      {"code" in err
        ? <ApiErrorMessage err={err as CadraApiError} />
        : <p className="text-[12px] text-red-700 dark:text-red-400">{err.message}</p>}
    </div>
  );
}

export function Loading({ what }: { what: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3">
      <Clock size={20} className="text-muted-foreground/40 animate-pulse" />
      <p className="text-sm text-muted-foreground">{what}</p>
    </div>
  );
}

export function Empty({ children, testid }: { children: ReactNode; testid: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 gap-3 px-6 text-center" data-testid={testid}>
      <Inbox size={24} className="text-muted-foreground/30" />
      <p className="text-sm font-semibold">{children}</p>
    </div>
  );
}

export function Btn({ onClick, disabled, pending, children, testid, kind = "primary", type = "button" }: {
  onClick?: () => void; disabled?: boolean; pending?: boolean; children: ReactNode; testid?: string;
  kind?: "primary" | "plain" | "danger"; type?: "button" | "submit";
}) {
  const off = disabled || pending;
  return (
    <button type={type} disabled={off} onClick={onClick} data-testid={testid}
      className={cn(
        "px-3 py-1.5 text-xs font-semibold rounded-xl inline-flex items-center gap-1.5 transition-colors",
        off ? "bg-muted text-muted-foreground cursor-not-allowed"
          : kind === "primary" ? "bg-primary text-primary-foreground hover:bg-primary/90"
          : kind === "danger" ? "bg-red-600 text-white hover:bg-red-700"
          : "border border-border text-foreground hover:bg-accent",
      )}>
      {pending && <Loader2 size={12} className="animate-spin" />}
      {children}
    </button>
  );
}

/** A photo that needs the bearer token: fetched as a blob, never an
 *  `<img src>` pointing at the API. */
export function Photo({ url, size = "md", testid = "audit-photo" }: {
  url: string; size?: "sm" | "md" | "lg"; testid?: string;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let live = true;
    let made: string | null = null;
    setSrc(null);
    setFailed(false);
    fetchPictureObjectUrl({ url, mimetype: null })
      .then((u) => { made = u; if (live) setSrc(u); else URL.revokeObjectURL(u); })
      .catch(() => { if (live) setFailed(true); });
    return () => { live = false; if (made) URL.revokeObjectURL(made); };
  }, [url]);
  const box = size === "lg" ? "w-48 h-48" : size === "md" ? "w-32 h-32" : "w-14 h-14";
  return (
    <div className={cn(box, "rounded-lg border border-border bg-muted flex items-center justify-center overflow-hidden shrink-0")}
         data-testid={testid} data-loaded={src ? "true" : "false"}>
      {src ? <img src={src} alt="" className="w-full h-full object-cover" />
        : failed ? <ImageIcon size={14} className="text-muted-foreground/50" />
        : <Loader2 size={12} className="animate-spin text-muted-foreground/50" />}
    </div>
  );
}

export function Pill({ children, tone = "plain", testid }: {
  children: ReactNode; tone?: "plain" | "amber" | "green" | "red" | "blue"; testid?: string;
}) {
  const tones = {
    plain: "bg-muted text-foreground border-border",
    amber: "bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/30 dark:text-amber-300 dark:border-amber-800/40",
    green: "bg-green-50 text-green-800 border-green-200 dark:bg-green-950/30 dark:text-green-300 dark:border-green-800/40",
    red: "bg-red-50 text-red-800 border-red-200 dark:bg-red-950/30 dark:text-red-300 dark:border-red-800/40",
    blue: "bg-blue-50 text-blue-800 border-blue-200 dark:bg-blue-950/30 dark:text-blue-300 dark:border-blue-800/40",
  } as const;
  return (
    <span className={cn("inline-block px-2 py-0.5 rounded-lg border text-[11px] font-semibold", tones[tone])} data-testid={testid}>
      {children}
    </span>
  );
}
