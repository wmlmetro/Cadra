/**
 * The frame every anonymous page shares — sign-in's own look, lifted so the
 * invitation, reset and "Forgot password?" pages are the same product as the
 * sign-in page a person lands on next (handoff 45 §2.1: one brand source,
 * one design system, nothing to keep in sync with an inherited Odoo view).
 */
import type { ReactNode } from "react";
import { AlertCircle, CheckCircle2 } from "lucide-react";
import { brandLogoSrc, getBrand } from "@/lib/brand";

export function AuthShell({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-6">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-3">
          <img src={brandLogoSrc()} alt={getBrand().name} className="h-16 w-auto" draggable={false} />
          <div className="text-center">
            <h1 className="text-[18px] font-bold text-foreground" data-testid="auth-title">{title}</h1>
            {subtitle && <p className="text-[12px] text-muted-foreground mt-1">{subtitle}</p>}
          </div>
        </div>
        <div className="bg-card border border-border rounded-2xl p-6 space-y-4">{children}</div>
      </div>
    </div>
  );
}

export function AuthError({ children }: { children: ReactNode }) {
  return (
    <div role="alert" data-testid="auth-error"
      className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-xl p-3 flex items-start gap-2">
      <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
      <p className="text-[12px] text-red-700 dark:text-red-400">{children}</p>
    </div>
  );
}

export function AuthNotice({ children }: { children: ReactNode }) {
  return (
    <div role="status" data-testid="auth-notice"
      className="bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200/70 dark:border-emerald-800/30 rounded-xl p-3 flex items-start gap-2">
      <CheckCircle2 size={14} className="text-emerald-700 dark:text-emerald-400 shrink-0 mt-0.5" />
      <p className="text-[12px] text-emerald-800 dark:text-emerald-300">{children}</p>
    </div>
  );
}

export const authLabel = "text-[11px] font-semibold text-muted-foreground uppercase tracking-wide";
export const authInput = "w-full px-3 py-2 text-sm border border-border rounded-xl bg-background focus:outline-none focus:ring-2 focus:ring-primary/20";
export const authButton = (enabled: boolean) =>
  "w-full inline-flex items-center justify-center gap-2 px-4 py-2 text-sm font-semibold rounded-xl " +
  (enabled ? "bg-primary text-white hover:opacity-90" : "bg-muted text-muted-foreground cursor-not-allowed");
export const authLink = "text-[12px] font-semibold text-primary hover:underline";
