/**
 * Printing a ROOM label — handoff 61 §7 (ruling R8).
 *
 * Two pieces:
 *
 *   - `RoomLabelPrintControl` — the size choice (medium / large, never
 *     small) and the Print button for ONE location. Used on the location
 *     page, on the station's room card, and below.
 *   - `RoomLabelPrint` (default) — the station's panel: find a room by name
 *     or code and print its label.
 *
 * The label is the server's PDF (`GET /api/v1/locations/<id>/label`, scope
 * `locations:read`), opened in a new tab for the browser's own print. Both
 * pieces render nothing for somebody without `locations:read`, because the
 * server would refuse them.
 */
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Printer, Loader2, DoorOpen, Search, AlertCircle } from "lucide-react";
import { CadraApiError } from "@/lib/api";
import {
  ROOM_LABEL_SIZES, printRoomLabel, searchRooms,
  type RoomLabelSize, type RoomOption,
} from "@/lib/locationLabels";
import { useScopes, SCOPE } from "@/hooks/use-scopes";
import { cn } from "@/lib/utils";

export function RoomLabelPrintControl({
  locationId, code, compact = false,
}: { locationId: number | string; code: string | null; compact?: boolean }) {
  const scopes = useScopes();
  const [size, setSize] = useState<RoomLabelSize>("medium");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  if (!scopes.has(SCOPE.locationsRead)) return null;

  async function print() {
    if (!code) return;
    setBusy(true);
    setNote(null);
    try {
      const res = await printRoomLabel(locationId, code, size);
      setNote({
        kind: "ok",
        text: res.how === "tab"
          ? `Room label ${code} opened in a new tab — print it from there.`
          : `Your browser blocked the new tab, so ${res.filename} was downloaded instead.`,
      });
    } catch (e) {
      const err = e as CadraApiError;
      setNote({ kind: "error", text: err?.message || "The room label could not be printed." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-1.5" data-testid="room-label-print">
      <div className={cn("flex items-center gap-2 flex-wrap", compact && "gap-1.5")}>
        <div className="flex items-center gap-1 rounded-xl border border-border p-0.5" role="radiogroup" aria-label="Room label size">
          {ROOM_LABEL_SIZES.map((s) => (
            <button
              key={s.value}
              type="button"
              role="radio"
              aria-checked={size === s.value}
              onClick={() => setSize(s.value)}
              title={s.hint}
              data-testid={`room-label-size-${s.value}`}
              className={cn(
                "px-2.5 py-1 rounded-lg text-[11px] font-medium",
                size === s.value ? "bg-primary text-white" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {s.label} <span className="opacity-70">{s.hint}</span>
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => void print()}
          disabled={!code || busy}
          data-testid="room-label-print-button"
          className={cn(
            "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[11px] font-semibold",
            code && !busy ? "bg-primary text-white hover:opacity-90" : "bg-muted text-muted-foreground cursor-not-allowed",
          )}
        >
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Printer size={12} />}
          Print room label
        </button>
      </div>
      {!code && (
        <p className="text-[11px] text-muted-foreground">
          This location has no room code yet, so there is no label to print.
        </p>
      )}
      {note && (
        <p
          className={cn("text-[11px]", note.kind === "error" ? "text-red-700 dark:text-red-400" : "text-muted-foreground")}
          data-testid="room-label-note"
        >
          {note.text}
        </p>
      )}
    </div>
  );
}

/** The station's panel: find a room, print its label. */
export default function RoomLabelPrint() {
  const scopes = useScopes();
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [picked, setPicked] = useState<RoomOption | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 250);
    return () => clearTimeout(t);
  }, [q]);

  const results = useQuery<RoomOption[], CadraApiError>({
    queryKey: ["room-label-search", debounced],
    queryFn: () => searchRooms(debounced),
    enabled: debounced.length >= 2 && scopes.has(SCOPE.locationsRead),
    staleTime: 30_000,
  });

  if (!scopes.has(SCOPE.locationsRead)) return null;

  return (
    <div className="bg-card border border-border rounded-2xl p-5 space-y-3" data-testid="room-label-panel">
      <div className="flex items-center gap-2">
        <DoorOpen size={14} className="text-primary" />
        <h2 className="text-[13px] font-bold">Print a room label</h2>
      </div>
      <p className="text-[11px] text-muted-foreground">
        A room label carries the room's code as a QR and a barcode, so the room is scanned before
        anything in it. Medium (50 × 30 mm) or large (100 × 60 mm) — there is no small room label,
        because a camera cannot read the small barcode.
      </p>
      <div className="relative">
        <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60 pointer-events-none" />
        <input
          type="search"
          value={q}
          onChange={(e) => { setQ(e.target.value); setPicked(null); }}
          placeholder="Find a room by name or room code — e.g. LOC-HQ-F10"
          data-testid="room-label-search"
          className="w-full pl-7 pr-3 py-2 text-sm border border-border rounded-xl bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
        />
      </div>

      {results.error && (
        <div className="flex items-start gap-2 text-[12px] text-red-700 dark:text-red-400">
          <AlertCircle size={13} className="shrink-0 mt-0.5" />
          <span>{results.error.message}</span>
        </div>
      )}

      {!picked && debounced.length >= 2 && results.data && (
        results.data.length === 0 ? (
          <p className="text-[12px] text-muted-foreground">No location matches “{debounced}”.</p>
        ) : (
          <ul className="divide-y divide-border border border-border rounded-xl overflow-hidden" data-testid="room-label-results">
            {results.data.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => setPicked(r)}
                  className="w-full text-left px-3 py-2 hover:bg-muted/30 flex items-center justify-between gap-3"
                >
                  <span className="min-w-0">
                    <span className="block text-[13px] font-medium text-foreground truncate">{r.name}</span>
                    <span className="block text-[11px] text-muted-foreground truncate">{r.location_type ?? "Location"}</span>
                  </span>
                  <span className="font-mono text-[11px] text-muted-foreground shrink-0">{r.location_code ?? "no code"}</span>
                </button>
              </li>
            ))}
          </ul>
        )
      )}

      {picked && (
        <div className="border border-primary/30 rounded-xl p-3 space-y-2" data-testid="room-label-picked">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[13px] font-semibold text-foreground truncate">{picked.name}</p>
              <p className="font-mono text-[12px] text-muted-foreground">{picked.location_code ?? "No room code"}</p>
            </div>
            <button type="button" onClick={() => setPicked(null)} className="text-[11px] text-muted-foreground hover:text-foreground">
              Change
            </button>
          </div>
          <RoomLabelPrintControl locationId={picked.id} code={picked.location_code} />
        </div>
      )}
    </div>
  );
}
