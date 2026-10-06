import { Search, Sun, Moon } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { fetchWhoAmI } from "@/lib/dataProvider";
import { useTheme } from "next-themes";
import { useState, useEffect } from "react";
import { useLocation, useSearch } from "wouter";

interface TopbarProps {
  title: string;
  onSearch?: (q: string) => void;
}

export default function Topbar({ title, onSearch }: TopbarProps) {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  // Long-lived on purpose: who is signed in does not change under a session.
  // A failure leaves `me` undefined and the bar then shows NO name at all —
  // an avatar with a dot. (`whoami` is never persisted and the cache is
  // cleared on sign-in, so a previous user's name cannot be restored here.)
  const { data: me } = useQuery({
    queryKey: ["whoami"],
    queryFn: fetchWhoAmI,
    staleTime: 30 * 60_000,
    retry: false,
  });
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const [location, nav] = useLocation();
  const searchStr = useSearch();

  // next-themes hydrates `resolvedTheme` after mount; guard the toggle render
  // so the icon doesn't flash the wrong state on first paint.
  useEffect(() => setMounted(true), []);

  // Reflect the URL query in the box when it changes from OUTSIDE typing
  // (landing on /search via a link, back/forward). Skipped while the user is
  // typing so debounced navigation below doesn't fight the input.
  useEffect(() => {
    if (focused) return;
    if (location.startsWith("/search")) {
      setQuery(new URLSearchParams(searchStr).get("q") ?? "");
    }
  }, [location, searchStr, focused]);

  // Search as you type: debounce-navigate to the global results page — UNLESS
  // the page registered its own live-filter handler (list pages), which we let
  // handle the keystrokes in place. Works on every other page (details,
  // dashboards) where the box was previously dead.
  useEffect(() => {
    if (onSearch || !focused) return;
    const term = query.trim();
    const t = setTimeout(() => {
      if (term) nav(`/search?q=${encodeURIComponent(term)}`);
      else if (location.startsWith("/search")) nav("/search");
    }, 220);
    return () => clearTimeout(t);
  }, [query, onSearch, focused, location, nav]);

  // The hat beside the name (handoff 56): the server's own role rows, never
  // derived from scopes — a scope set maps to a role only approximately, and
  // a guessed label would be wrong exactly for the persona it matters for.
  // One role: its name. Two: both. Three or more: the first two and +N, the
  // full list in the line's tooltip (there is no account menu to put it in —
  // the bar has deliberately had none since handoff 29). No roles — an old
  // server, or an account holding none — shows NOTHING: a blank is honest,
  // an invented label is not.
  const roles = me?.roles ?? [];
  const roleNames = roles.map((r) => r.name);
  const roleText =
    roleNames.length === 0
      ? ""
      : roleNames.length <= 2
        ? roleNames.join(" · ")
        : `${roleNames[0]} · ${roleNames[1]} +${roleNames.length - 2}`;

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
    setQuery(e.target.value);
    onSearch?.(e.target.value); // live-filter pages that opt in via setSearchHandler
  };

  // Enter still runs the global search immediately (useful on list pages, whose
  // keystrokes go to their own filter).
  const submitSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const term = query.trim();
    if (term) nav(`/search?q=${encodeURIComponent(term)}`);
  };

  return (
    <header
      className="shrink-0 flex items-center gap-4 px-5 bg-card border-b border-border"
      style={{ height: "52px" }}
    >
      {/* Page title */}
      <p className="text-[13px] font-semibold text-foreground shrink-0">{title}</p>

      {/* Divider */}
      <div className="w-px h-4 bg-border shrink-0" />

      {/* Search */}
      <form onSubmit={submitSearch} className="flex-1 max-w-xs relative">
        <Search
          size={12}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground/50 pointer-events-none"
        />
        <input
          type="search"
          placeholder="Search people, assets, locations…"
          className="w-full pl-8 pr-3 py-1.5 text-[12px] rounded-xl border border-border bg-background/60 text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/30 transition-all"
          value={query}
          onChange={handleSearch}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          data-testid="input-global-search"
        />
      </form>

      {/* Right: actions */}
      <div className="ml-auto flex items-center gap-1.5">
        {/* The notifications bell was here until handoff 29. It had no
            handler — clicking it did nothing — and it drew a PERMANENT unread
            dot: a claim, on every screen, that something was waiting, made by
            a control with nothing behind it. There are no notifications in
            this app. When there are, the bell comes back with them. */}

        {/* Theme toggle */}
        {mounted && (
          <button
            onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
            className="w-8 h-8 rounded-xl flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-accent transition-all"
            data-testid="button-theme-toggle"
            aria-label="Toggle dark mode"
          >
            {resolvedTheme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
          </button>
        )}

        {/* Divider */}
        <div className="w-px h-4 bg-border mx-1" />

        {/* Who is signed in — read from the session, not written here. This
            printed "Admin User / Administrator" for every session until
            handoff 29. Since handoff 28 the Verify button records the
            SIGNED-IN person as the verifier, so a top bar naming somebody
            else sat beside a control that wrote a different name into the
            register. Not clickable: there is no account menu, so it no longer
            carries a pointer cursor promising one. */}
        <div className="flex items-center gap-2 pl-1" data-testid="topbar-user">
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold text-white shadow-sm"
            style={{ background: "hsl(var(--primary))" }}
          >
            {(me?.name ?? "").trim().charAt(0).toUpperCase() || "·"}
          </div>
          <div className="hidden sm:block">
            {me?.name && <p className="text-[12px] font-semibold text-foreground leading-tight">{me.name}</p>}
            {me?.login && <p className="text-[10px] text-muted-foreground leading-tight">{me.login}</p>}
            {roleText && (
              <p
                className="text-[10px] text-muted-foreground leading-tight"
                title={roleNames.length > 2 ? roleNames.join(" · ") : undefined}
                data-testid="topbar-role"
              >
                {roleText}
              </p>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
