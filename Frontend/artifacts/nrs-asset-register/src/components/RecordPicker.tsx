import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, X, Check } from "lucide-react";
import { cn } from "@/lib/utils";

interface Option {
  id: number;
  label: string;
  sublabel?: string;
}

interface Props {
  value: Option | null;
  onChange: (opt: Option | null) => void;
  /** queryFn receives the user's typed query, must return up to ~10 options. */
  search: (q: string) => Promise<Option[]>;
  /** Stable cache key prefix — combined with the query string. */
  queryKey: string;
  placeholder?: string;
  disabled?: boolean;
}

// Lightweight typeahead — no Combobox primitives, just an input + results list.
// 250ms debounce; min 2 chars before search fires; click-outside closes.
export default function RecordPicker({
  value,
  onChange,
  search,
  queryKey,
  placeholder = "Type to search…",
  disabled,
}: Props) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [debounced, setDebounced] = useState("");
  const wrap = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 250);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  const { data: results = [], isFetching } = useQuery<Option[]>({
    queryKey: [queryKey, debounced],
    queryFn: () => search(debounced),
    enabled: debounced.length >= 2,
    staleTime: 30_000,
  });

  if (value) {
    return (
      <div className="flex items-center justify-between gap-2 px-3 py-2 border border-border rounded-xl bg-muted/30">
        <div className="min-w-0">
          <p className="text-[13px] font-semibold text-foreground truncate">{value.label}</p>
          {value.sublabel && <p className="text-[11px] text-muted-foreground truncate">{value.sublabel}</p>}
        </div>
        {!disabled && (
          <button
            type="button"
            onClick={() => { onChange(null); setQ(""); }}
            className="shrink-0 text-muted-foreground hover:text-foreground"
            aria-label="Clear selection"
          >
            <X size={14} />
          </button>
        )}
      </div>
    );
  }

  return (
    <div ref={wrap} className="relative">
      <div className="relative">
        <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60 pointer-events-none" />
        <input
          type="search"
          value={q}
          onChange={e => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder}
          disabled={disabled}
          className="w-full pl-7 pr-3 py-1.5 text-xs border border-border rounded-xl bg-background text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-primary/20"
        />
      </div>
      {open && debounced.length >= 2 && (
        <div className="absolute top-full mt-1 left-0 right-0 z-50 bg-popover border border-border rounded-xl shadow-lg max-h-64 overflow-auto py-1">
          {isFetching && results.length === 0 ? (
            <p className="px-3 py-2 text-xs text-muted-foreground">Searching…</p>
          ) : results.length === 0 ? (
            <p className="px-3 py-2 text-xs text-muted-foreground">No matches.</p>
          ) : (
            results.map(r => (
              <button
                key={r.id}
                type="button"
                onClick={() => { onChange(r); setOpen(false); setQ(""); }}
                className={cn("w-full text-left px-3 py-2 text-xs hover:bg-accent flex items-center gap-2")}
              >
                <Check size={11} className="opacity-0" />
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-foreground truncate">{r.label}</p>
                  {r.sublabel && <p className="text-muted-foreground truncate">{r.sublabel}</p>}
                </div>
              </button>
            ))
          )}
        </div>
      )}
      {open && debounced.length < 2 && q.length > 0 && (
        <div className="absolute top-full mt-1 left-0 right-0 z-50 bg-popover border border-border rounded-xl shadow-lg p-3">
          <p className="text-xs text-muted-foreground">Keep typing — at least 2 characters.</p>
        </div>
      )}
    </div>
  );
}
