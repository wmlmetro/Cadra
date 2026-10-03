import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { fetchBranding, updateBranding, type TenantBranding } from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import { applyBrand, getBrand } from "@/lib/brand";
import BrandPill from "@/components/BrandPill";
import {
  AlertCircle, Clock, Check, Loader2, Upload, RotateCcw, Info, Image as ImageIcon, Mail,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { useScopes, SCOPE } from "@/hooks/use-scopes";

/** Keep in step with the API's guard — a logo rides in every page load. */
const LOGO_MAX_CHARS = 262_144;
const HEX = /^#[0-9A-Fa-f]{6}$/;
/** The server's own test (`odoo.tools.mail.single_email_re`): one bare
 *  address, no display name. The server refuses in words either way; this
 *  only stops the Save button offering a save that would be refused. */
const EMAIL = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,63}$/;

const inputCls =
  "w-full rounded-lg border border-border bg-background px-2.5 py-1.5 text-[12px] " +
  "focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-40";

/** Darken a hex colour — a sensible default for the hover/pressed shade so
 *  nobody has to hand-pick two colours that agree. */
function darken(hex: string, amount = 0.18): string {
  if (!HEX.test(hex)) return hex;
  const n = parseInt(hex.slice(1), 16);
  const f = (v: number) => Math.max(0, Math.round(v * (1 - amount)));
  const r = f((n >> 16) & 255), g = f((n >> 8) & 255), b = f(n & 255);
  return "#" + [r, g, b].map(v => v.toString(16).padStart(2, "0")).join("").toUpperCase();
}

function Field({ label, hint, children }: {
  label: string; hint?: string; children: React.ReactNode;
}) {
  return (
    <div>
      <label className="text-[11px] font-medium text-muted-foreground">{label}</label>
      <div className="mt-1">{children}</div>
      {hint && <p className="text-[10px] text-muted-foreground mt-1">{hint}</p>}
    </div>
  );
}

export default function BrandingPage() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState<TenantBranding | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [localErr, setLocalErr] = useState<string | null>(null);
  // Handoff 46: `PATCH /settings/branding` needs `settings:write`. Somebody
  // who reaches this page without it sees the tenant's branding as it is —
  // the fields drawn, disabled — and a sentence where Save would be, rather
  // than a Save the server refuses.
  const scopes = useScopes();
  const readOnly = !scopes.has(SCOPE.settingsWrite);

  useEffect(() => {
    setTitle("Settings — Branding");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const branding = useQuery({
    queryKey: ["branding"],
    queryFn: fetchBranding,
    staleTime: 30_000,
  });

  useEffect(() => { if (branding.data) setDraft(branding.data); }, [branding.data]);

  const save = useMutation({
    mutationFn: (body: Partial<TenantBranding>) => updateBranding(body),
    onSuccess: (d) => {
      setNote("Branding saved.");
      qc.setQueryData(["branding"], d);
      // Repaint immediately rather than waiting for a reload — this is the one
      // settings page where the effect is the whole point.
      applyBrand({
        name: d.name, short_name: d.short_name,
        primary: d.primary || getBrand().primary,
        primary_dark: d.primary_dark || getBrand().primary_dark,
        logo: d.logo,
        // Saving branding says nothing about the login challenge — carry the
        // tenant's current setting through rather than resetting it.
        turnstile: getBrand().turnstile,
      });
    },
  });

  const err = (branding.error ?? save.error) as CadraApiError | null;

  if (branding.isLoading || !draft) return (
    <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
      <Clock size={20} className="animate-pulse" />
      <p className="text-sm">Loading branding…</p>
    </div>
  );

  const saved = branding.data!;
  const dirty = (Object.keys(saved) as (keyof TenantBranding)[])
    .some(k => draft[k] !== saved[k]);
  const colourOk = (!draft.primary || HEX.test(draft.primary)) &&
                   (!draft.primary_dark || HEX.test(draft.primary_dark));
  const senderEmail = (draft.sender_email ?? "").trim();
  // The address already stored is accepted as it stands, as the server does —
  // an address saved before this check existed must not block a colour save.
  const senderOk = !senderEmail || EMAIL.test(senderEmail) ||
                   senderEmail === (saved.sender_email ?? "").trim();
  const canSave = colourOk && senderOk;

  const onPickLogo = (file: File) => {
    setLocalErr(null);
    if (!/^image\/(svg\+xml|png|jpeg|webp)$/.test(file.type)) {
      setLocalErr(`${file.type || "That file"} is not a supported image (SVG, PNG, JPEG or WebP).`);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const uri = String(reader.result || "");
      if (uri.length > LOGO_MAX_CHARS) {
        setLocalErr(
          `Logo is ${Math.round(uri.length / 1024)}KB encoded — the limit is ` +
          `${Math.round(LOGO_MAX_CHARS / 1024)}KB because it is sent with every page load. ` +
          `An SVG is usually a few KB.`);
        return;
      }
      setDraft({ ...draft, logo: uri });
    };
    reader.readAsDataURL(file);
  };

  return (
    <div className="p-6 space-y-5 max-w-[900px] mx-auto">
      <div className="flex items-start gap-3">
        <BrandPill />
        <div>
          <h1 className="text-xl font-bold text-foreground">Branding</h1>
          <p className="text-xs text-muted-foreground mt-1">
            How this tenant looks. One build serves every customer and the brand
            is fetched per host at startup, so changes take effect without a
            release.
          </p>
        </div>
      </div>

      {err && (
        <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3">
          <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
          {/* Which fields, in words, when the save was refused for naming one
              the API does not accept — see ApiErrorMessage. */}
          <ApiErrorMessage err={err} stacked />
        </div>
      )}
      {localErr && (
        <div className="bg-amber-50 dark:bg-amber-950/20 border border-amber-200/70 dark:border-amber-800/30 rounded-2xl px-4 py-3 flex items-start gap-2">
          <AlertCircle size={14} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
          <p className="text-[12px] text-amber-800 dark:text-amber-300">{localErr}</p>
        </div>
      )}
      {note && !err && (
        <div className="bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200/70 dark:border-emerald-800/30 rounded-2xl px-4 py-3 flex items-center gap-2">
          <Check size={14} className="text-emerald-600 dark:text-emerald-400" />
          <p className="text-[12px] text-emerald-800 dark:text-emerald-300">{note}</p>
        </div>
      )}

      {/* Preview */}
      <section className="bg-card border border-border rounded-2xl p-5">
        <h2 className="text-[13px] font-bold mb-3">Preview</h2>
        <div className="rounded-xl border border-border overflow-hidden">
          <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
            {draft.logo
              ? <img src={draft.logo} alt="" className="h-8 max-w-[180px] object-contain" />
              : <span className="text-[11px] text-muted-foreground italic">no logo — bundled mark is used</span>}
          </div>
          <div className="flex items-center gap-3 px-4 py-4">
            <span className="inline-flex items-center px-2 py-1 rounded-lg text-[10px] font-extrabold tracking-wider"
                  style={{ background: draft.primary || "#888", color: "white" }}>
              {draft.short_name || draft.name || "—"}
            </span>
            <span className="text-[15px] font-bold">{draft.name}</span>
            <button className="ml-auto px-3 py-1.5 rounded-lg text-[11px] font-medium text-white"
                    style={{ background: draft.primary || "#888" }} type="button">
              Primary
            </button>
            <button className="px-3 py-1.5 rounded-lg text-[11px] font-medium text-white"
                    style={{ background: draft.primary_dark || "#666" }} type="button">
              Hover
            </button>
          </div>
        </div>
      </section>

      {/* `disabled` on a fieldset disables every control inside it; `contents`
          keeps it out of the layout, so the sections space as they did. */}
      <fieldset disabled={readOnly} className="contents">
      {/* Identity */}
      <section className="bg-card border border-border rounded-2xl p-5 space-y-4">
        <h2 className="text-[13px] font-bold">Identity</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Tenant name"
                 hint="Shown in the browser tab and headings. This renames the company record.">
            <input className={inputCls} value={draft.name} data-testid="brand-name"
                   onChange={e => setDraft({ ...draft, name: e.target.value })} />
          </Field>
          <Field label="Short name" hint="Used on the badge beside page titles. Keep it to a few characters.">
            <input className={inputCls} value={draft.short_name} data-testid="brand-short-name"
                   onChange={e => setDraft({ ...draft, short_name: e.target.value })} />
          </Field>
        </div>
      </section>

      {/* Letters */}
      <section className="bg-card border border-border rounded-2xl p-5 space-y-4">
        <h2 className="text-[13px] font-bold inline-flex items-center gap-1.5">
          <Mail size={13} /> Letters
        </h2>
        <Field label="Sender address"
               hint={"The address invitations and password resets give as their sender, " +
                     "where the mail server lets us choose one. If it is empty, a letter " +
                     "goes out from the address of whoever sent it, or failing that the " +
                     "recipient's own, which many mail servers refuse to deliver. On the " +
                     "hosted service the mail relay currently sends as its own address."}>
          <input className={cn(inputCls, !senderOk && "border-red-400")}
                 type="email" inputMode="email" autoComplete="off" spellCheck={false}
                 value={draft.sender_email ?? ""} placeholder="assets@your-organisation.gov.ng"
                 data-testid="brand-sender-email"
                 onChange={e => setDraft({ ...draft, sender_email: e.target.value })} />
        </Field>
        {!senderOk && (
          <p className="text-[11px] text-red-600 dark:text-red-400">
            The sender address must be one email address, like assets@example.org,
            with no name or spaces. Leave it empty to clear it.
          </p>
        )}
      </section>

      {/* Colour */}
      <section className="bg-card border border-border rounded-2xl p-5 space-y-4">
        <h2 className="text-[13px] font-bold">Colour</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Primary" hint="Buttons, active navigation, chart accents.">
            <div className="flex gap-2">
              <input type="color" className="h-8 w-10 rounded border border-border bg-background"
                     value={HEX.test(draft.primary) ? draft.primary : "#000000"}
                     onChange={e => setDraft({
                       ...draft,
                       primary: e.target.value.toUpperCase(),
                       primary_dark: darken(e.target.value.toUpperCase()),
                     })} />
              <input className={cn(inputCls, !HEX.test(draft.primary) && draft.primary && "border-red-400")}
                     value={draft.primary} placeholder="#004080" data-testid="brand-primary"
                     onChange={e => setDraft({ ...draft, primary: e.target.value })} />
            </div>
          </Field>
          <Field label="Primary (dark)" hint="Hover and pressed states. Derived when you pick a primary.">
            <div className="flex gap-2">
              <input type="color" className="h-8 w-10 rounded border border-border bg-background"
                     value={HEX.test(draft.primary_dark) ? draft.primary_dark : "#000000"}
                     onChange={e => setDraft({ ...draft, primary_dark: e.target.value.toUpperCase() })} />
              <input className={cn(inputCls, !HEX.test(draft.primary_dark) && draft.primary_dark && "border-red-400")}
                     value={draft.primary_dark} placeholder="#00305F"
                     onChange={e => setDraft({ ...draft, primary_dark: e.target.value })} />
            </div>
          </Field>
        </div>
        {!colourOk && (
          <p className="text-[11px] text-red-600 dark:text-red-400">
            Colours must be 6-digit hex, e.g. #004080.
          </p>
        )}
      </section>

      {/* Logo */}
      <section className="bg-card border border-border rounded-2xl p-5 space-y-3">
        <h2 className="text-[13px] font-bold">Logo</h2>
        <div className="flex items-center gap-3 flex-wrap">
          <button
            type="button" onClick={() => fileRef.current?.click()}
            data-testid="brand-logo-upload"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-accent"
          >
            <Upload size={12} /> Choose image
          </button>
          {draft.logo && (
            <button
              type="button" onClick={() => setDraft({ ...draft, logo: "" })}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border hover:bg-accent"
            >
              <RotateCcw size={12} /> Clear
            </button>
          )}
          <span className="text-[11px] text-muted-foreground inline-flex items-center gap-1">
            <ImageIcon size={11} />
            {draft.logo
              ? `${Math.round(draft.logo.length / 1024)}KB encoded`
              : "using the bundled mark"}
          </span>
          <input
            ref={fileRef} type="file" className="hidden"
            accept="image/svg+xml,image/png,image/jpeg,image/webp"
            onChange={e => { const f = e.target.files?.[0]; if (f) onPickLogo(f); e.target.value = ""; }}
          />
        </div>
        <div className="flex gap-2 items-start text-[11px] text-sky-800 dark:text-sky-300 bg-sky-50 dark:bg-sky-950/20 rounded-lg px-3 py-2">
          <Info size={13} className="shrink-0 mt-px" />
          <span>
            The logo is stored inline and sent with every page load, so SVG is
            strongly preferred — usually a few KB against hundreds for a PNG.
          </span>
        </div>
      </section>
      </fieldset>

      {readOnly ? (
        <p className="text-[11px] text-muted-foreground" data-testid="settings-read-only">
          Changing this needs the settings:write scope.
        </p>
      ) : (
      <div className="flex items-center gap-3">
        <button
          disabled={!dirty || !canSave || save.isPending}
          onClick={() => {
            setLocalErr(null);
            save.mutate({ ...draft, sender_email: (draft.sender_email ?? "").trim() });
          }}
          data-testid="brand-save"
          className={cn(
            "inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-medium border",
            dirty && canSave && !save.isPending
              ? "border-primary text-primary hover:bg-primary/5"
              : "border-transparent text-muted-foreground/40 cursor-default",
          )}
        >
          {save.isPending ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
          Save branding
        </button>
        {dirty && (
          <button
            onClick={() => { setDraft(saved); setLocalErr(null); }}
            className="text-[11px] text-muted-foreground hover:text-foreground underline"
          >
            Discard changes
          </button>
        )}
        <span className="text-[10px] text-muted-foreground ml-auto">
          Other signed-in users pick this up within about five minutes.
        </span>
      </div>
      )}
    </div>
  );
}
