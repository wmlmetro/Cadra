/**
 * Settings — Sidebar: which items this tenant shows (handoff 48).
 *
 * The page says, before anything else, that this is NOT a permission. An
 * administrator who switched Fleet off believing Fleet was now secured would
 * have been misled by this screen — the server answers exactly as it did,
 * and the address still opens the page — so the sentence is the first thing
 * on it and it comes from the server (`statement`), not from here.
 *
 * Group switches are master switches: an item is shown when its own switch
 * and its group's are both on. An item whose group is off keeps its own
 * switch, and says why it is hidden.
 */
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import {
  fetchSidebarSettings, updateSidebarSettings, type SidebarSettings,
} from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import { ALL_NAV_GROUPS } from "@/lib/navigation";
import { SIDEBAR_SETTINGS_KEY } from "@/hooks/use-tenant-sidebar";
import { useScopes, SCOPE } from "@/hooks/use-scopes";
import { Switch } from "@/components/ui/switch";
import { ApiErrorMessage } from "@/components/ApiErrorMessage";
import { AlertCircle, Check, Clock, EyeOff, Loader2, Lock, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";

/** `group:<key>` / `item:<key>` → enabled. One map for both kinds, so the
 *  draft and the saved state compare in one pass. */
type Switches = Record<string, boolean>;

function switchesOf(s: SidebarSettings): Switches {
  const out: Switches = {};
  for (const g of s.groups) {
    out[`group:${g.key}`] = g.enabled;
    for (const it of g.items) out[`item:${it.key}`] = it.enabled;
  }
  return out;
}

function changed(by: { name: string } | null, at: string | null): string | null {
  if (!by || !at) return null;
  const when = new Date(at.endsWith("Z") || at.includes("+") ? at : at.replace(" ", "T") + "Z");
  return `Last changed by ${by.name}, ${when.toLocaleString(undefined, {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  })}`;
}

export default function SidebarSettingsPage() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const qc = useQueryClient();
  const scopes = useScopes();
  // `admin`, as the server's PATCH is. Anybody else who types the address
  // sees the switches as they are, disabled.
  const readOnly = !scopes.has(SCOPE.admin);
  const [draft, setDraft] = useState<Switches | null>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    setTitle("Settings — Sidebar");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  const settings = useQuery({
    queryKey: SIDEBAR_SETTINGS_KEY,
    queryFn: fetchSidebarSettings,
    staleTime: 0,
  });

  const saved = useMemo(
    () => (settings.data ? switchesOf(settings.data) : null), [settings.data]);
  useEffect(() => { if (saved) setDraft(saved); }, [saved]);

  const save = useMutation({
    mutationFn: updateSidebarSettings,
    onSuccess: (d) => {
      qc.setQueryData(SIDEBAR_SETTINGS_KEY, d);
      setNote("Saved. The sidebar on this tenant now shows what is switched on below.");
    },
  });

  const err = (settings.error ?? save.error) as CadraApiError | null;

  if (settings.isLoading || (!draft && !err)) return (
    <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
      <Clock size={20} className="animate-pulse" />
      <p className="text-sm">Loading the sidebar settings…</p>
    </div>
  );

  const data = settings.data;
  const labels = new Map<string, string>();
  for (const g of ALL_NAV_GROUPS) {
    labels.set(`group:${g.key}`, g.label);
    for (const it of g.items) labels.set(`item:${it.key}`, it.name);
  }
  const paths = new Map(ALL_NAV_GROUPS.flatMap(g => g.items.map(it => [it.key, it.path] as const)));

  const diff = draft && saved
    ? Object.keys(draft).filter(k => draft[k] !== saved[k]) : [];
  const dirty = diff.length > 0;

  const onSave = () => {
    if (!draft) return;
    setNote(null);
    const body: { items?: Record<string, boolean>; groups?: Record<string, boolean> } = {};
    for (const k of diff) {
      const [kind, key] = k.split(":");
      const bucket = kind === "group" ? (body.groups ??= {}) : (body.items ??= {});
      bucket[key] = draft[k];
    }
    save.mutate(body);
  };

  const hiddenNow = draft && data
    ? data.groups.reduce((n, g) => n + g.items.filter(it =>
        !(draft[`group:${g.key}`] && draft[`item:${it.key}`])).length, 0)
    : 0;
  const total = data ? data.groups.reduce((n, g) => n + g.items.length, 0) : 0;

  return (
    <div className="p-6 space-y-5 max-w-[900px] mx-auto">
      <div>
        <h1 className="text-xl font-bold text-foreground">Sidebar</h1>
        <p className="text-xs text-muted-foreground mt-1">
          Which items this organisation's sidebar shows. A person is drawn an
          item only when it is switched on here <em>and</em> their role opens it.
        </p>
      </div>

      {/* The sentence that matters most on this page, first and in full. */}
      <div
        data-testid="sidebar-not-a-permission"
        className="bg-amber-50 dark:bg-amber-950/20 border border-amber-300/70 dark:border-amber-800/40 rounded-2xl p-4 flex items-start gap-3"
      >
        <ShieldAlert size={18} className="text-amber-700 dark:text-amber-400 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <p className="text-[13px] font-bold text-amber-900 dark:text-amber-200">
            This changes what is shown, not what is permitted.
          </p>
          <p className="text-[12px] text-amber-900 dark:text-amber-200">
            {data?.statement ??
              "Switching an item off does not stop anybody opening that page by its address."}
          </p>
        </div>
      </div>

      {err && (
        <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3">
          <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
          <ApiErrorMessage err={err} stacked />
        </div>
      )}
      {note && !err && (
        <div className="bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200/70 dark:border-emerald-800/30 rounded-2xl px-4 py-3 flex items-center gap-2">
          <Check size={14} className="text-emerald-600 dark:text-emerald-400" />
          <p className="text-[12px] text-emerald-800 dark:text-emerald-300">{note}</p>
        </div>
      )}

      {data && draft && (
        <>
          <p className="text-[11px] text-muted-foreground" data-testid="sidebar-count">
            {total - hiddenNow} of {total} items shown on this tenant.
            {" "}{data.rule}
          </p>

          {data.groups.map((g) => {
            const gk = `group:${g.key}`;
            const groupOn = draft[gk];
            const gChanged = changed(g.changed_by, g.changed_at);
            return (
              <section
                key={g.key}
                data-testid={`sidebar-group-${g.key}`}
                className="bg-card border border-border rounded-2xl p-5 space-y-3"
              >
                <div className="flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <h2 className="text-[13px] font-bold inline-flex items-center gap-1.5">
                      {labels.get(gk) ?? g.key}
                      {g.locked && <Lock size={12} className="text-muted-foreground" />}
                    </h2>
                    {g.locked ? (
                      <p className="text-[11px] text-muted-foreground">
                        Always on. {data.locked_reason}
                      </p>
                    ) : (
                      <p className="text-[11px] text-muted-foreground">
                        {groupOn ? "The whole group is on." :
                          "The whole group is off — every item in it is hidden, and keeps its own switch for when the group is switched back on."}
                        {gChanged && <> · {gChanged}</>}
                      </p>
                    )}
                  </div>
                  <Switch
                    checked={groupOn}
                    disabled={readOnly || g.locked}
                    data-testid={`sidebar-switch-group-${g.key}`}
                    aria-label={`${labels.get(gk) ?? g.key} group`}
                    onCheckedChange={(v) => setDraft({ ...draft, [gk]: v })}
                  />
                </div>

                <ul className="divide-y divide-border border-t border-border">
                  {g.items.map((it) => {
                    const ik = `item:${it.key}`;
                    const on = draft[ik];
                    const shown = groupOn && on;
                    const iChanged = changed(it.changed_by, it.changed_at);
                    return (
                      <li key={it.key} className="flex items-center gap-3 py-2"
                          data-testid={`sidebar-item-${it.key}`}
                          data-shown={shown ? "true" : "false"}>
                        <div className="flex-1 min-w-0">
                          <p className={cn("text-[12px] font-medium inline-flex items-center gap-1.5",
                                           !shown && "text-muted-foreground")}>
                            {!shown && <EyeOff size={11} />}
                            {labels.get(ik) ?? it.key}
                            {it.locked && <Lock size={11} className="text-muted-foreground" />}
                            <span className="text-[10px] font-normal text-muted-foreground">
                              {paths.get(it.key)}
                            </span>
                          </p>
                          <p className="text-[10px] text-muted-foreground">
                            {it.locked ? "Always on — this is where these switches are changed."
                              : on && !groupOn ? `Hidden because the ${labels.get(gk)} group is off.`
                              : !on ? "Hidden on this tenant. Still opens by its address for anybody whose role allows it."
                              : "Shown to everybody whose role opens it."}
                            {iChanged && <> · {iChanged}</>}
                          </p>
                        </div>
                        <Switch
                          checked={on}
                          disabled={readOnly || it.locked}
                          data-testid={`sidebar-switch-item-${it.key}`}
                          aria-label={labels.get(ik) ?? it.key}
                          onCheckedChange={(v) => setDraft({ ...draft, [ik]: v })}
                        />
                      </li>
                    );
                  })}
                </ul>
              </section>
            );
          })}

          {readOnly ? (
            <p className="text-[11px] text-muted-foreground" data-testid="settings-read-only">
              Changing this needs the administrator role.
            </p>
          ) : (
            <div className="flex items-center gap-3 sticky bottom-0 bg-background py-3">
              <button
                disabled={!dirty || save.isPending}
                onClick={onSave}
                data-testid="sidebar-save"
                className={cn(
                  "inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-medium border",
                  dirty && !save.isPending
                    ? "border-primary text-primary hover:bg-primary/5"
                    : "border-transparent text-muted-foreground/40 cursor-default",
                )}
              >
                {save.isPending ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                Save {dirty ? `${diff.length} change${diff.length === 1 ? "" : "s"}` : "sidebar"}
              </button>
              {dirty && (
                <button
                  onClick={() => { if (saved) setDraft(saved); setNote(null); }}
                  className="text-[11px] text-muted-foreground hover:text-foreground underline"
                >
                  Discard changes
                </button>
              )}
              <span className="text-[10px] text-muted-foreground ml-auto">
                Other signed-in people pick this up within about five minutes, or when they reload.
              </span>
            </div>
          )}
        </>
      )}
    </div>
  );
}
