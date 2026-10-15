/**
 * What the station shows when a scan named a ROOM — handoff 61 §7 (R8).
 *
 * `GET /api/v1/barcode/lookup` tries a room code LAST, after tag, asset code
 * and serial, and answers `matched_by: "location"` with `matched_location`
 * and no asset at all. This card is that answer: *This is a room: <name>*,
 * its code and where it sits — never "not found", and never an asset card
 * with blank fields.
 */
import { useLocation } from "wouter";
import { DoorOpen, ArrowRight, Archive } from "lucide-react";
import type { MatchedLocation } from "@/lib/locationLabels";
import { RoomLabelPrintControl } from "./RoomLabelPrint";

export default function RoomScanResult({ room }: { room: MatchedLocation }) {
  const [, nav] = useLocation();
  return (
    <div className="bg-background border border-primary/30 rounded-xl p-4 space-y-3" data-testid="lookup-room">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center bg-primary/10 shrink-0">
            <DoorOpen size={16} className="text-primary" />
          </div>
          <div className="min-w-0">
            <p className="text-[14px] font-bold text-foreground" data-testid="lookup-room-title">
              This is a room: {room.name}
            </p>
            <p className="text-[12px] text-muted-foreground font-mono" data-testid="lookup-room-code">
              {room.location_code}
            </p>
            {room.path && room.path !== room.name && (
              <p className="text-[11px] text-muted-foreground mt-0.5" data-testid="lookup-room-path">{room.path}</p>
            )}
          </div>
        </div>
        <span
          className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-primary/10 text-primary shrink-0"
          data-testid="lookup-matched-by"
        >Found by room code</span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1 text-[12px]">
        <div>
          <span className="text-muted-foreground">Type: </span>
          {room.type?.name ?? room.location_type ?? "—"}
        </div>
        <div data-testid="lookup-room-assets" title="Registered assets whose location is this one — not the rooms inside it">
          <span className="text-muted-foreground">Assets registered here: </span>
          {room.asset_count.toLocaleString()}
        </div>
      </div>

      {!room.active && (
        <div className="flex items-start gap-2 text-[12px] text-amber-800 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/30 border border-amber-200/70 dark:border-amber-800/30 rounded-lg p-2">
          <Archive size={13} className="shrink-0 mt-0.5" />
          <span>This location is archived. Its label still scans; nothing should be placed here.</span>
        </div>
      )}

      <div className="flex items-end justify-between gap-3 flex-wrap border-t border-border pt-3">
        <RoomLabelPrintControl locationId={room.id} code={room.location_code} compact />
        <button
          type="button"
          onClick={() => nav(`/locations/${room.id}`)}
          className="inline-flex items-center gap-1 text-[12px] text-primary hover:opacity-80"
        >
          Open the location <ArrowRight size={12} />
        </button>
      </div>
    </div>
  );
}
