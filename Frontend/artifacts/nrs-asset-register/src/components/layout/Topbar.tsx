import { Search, Sun, Moon, Bell } from "lucide-react";
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
        {/* Notifications */}
        <button
          aria-label="Notifications"
          className="relative w-8 h-8 rounded-xl flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-accent transition-all"
        >
          <Bell size={14} />
          <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-primary" />
        </button>

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

        {/* Avatar */}
        <div className="flex items-center gap-2 pl-1 cursor-pointer group">
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold text-white shadow-sm"
            style={{ background: "hsl(var(--primary))" }}
          >
            A
          </div>
          <div className="hidden sm:block">
            <p className="text-[12px] font-semibold text-foreground leading-tight">Admin User</p>
            <p className="text-[10px] text-muted-foreground leading-tight">Administrator</p>
          </div>
        </div>
      </div>
    </header>
  );
}
