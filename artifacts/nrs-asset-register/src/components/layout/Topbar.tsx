import { Search, Sun, Moon } from "lucide-react";
import { useTheme } from "next-themes";
import { useState, useEffect } from "react";

interface TopbarProps {
  title: string;
  onSearch?: (q: string) => void;
}

export default function Topbar({ title, onSearch }: TopbarProps) {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => setMounted(true), []);

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
    setQuery(e.target.value);
    onSearch?.(e.target.value);
  };

  return (
    <header className="h-13 border-b border-border bg-card px-5 flex items-center gap-4 shrink-0" style={{ height: "52px" }}>
      <h1 className="text-sm font-semibold text-foreground shrink-0 mr-2">{title}</h1>

      <div className="flex-1 max-w-sm relative">
        <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
        <input
          type="search"
          placeholder="Search assets, locations, employees…"
          className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border border-border bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/30 transition-shadow"
          value={query}
          onChange={handleSearch}
          data-testid="input-global-search"
        />
      </div>

      <div className="ml-auto flex items-center gap-2">
        {mounted && (
          <button
            onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            data-testid="button-theme-toggle"
            aria-label="Toggle dark mode"
          >
            {resolvedTheme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
          </button>
        )}

        <div
          className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white"
          style={{ background: "hsl(var(--primary))" }}
        >
          AU
        </div>
      </div>
    </header>
  );
}
