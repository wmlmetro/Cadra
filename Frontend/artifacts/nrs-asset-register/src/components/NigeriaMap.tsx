import { useMemo } from "react";
import { MapContainer, TileLayer, Marker, Popup, CircleMarker } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

// Leaflet's default marker icons are loaded from URLs that don't resolve
// under Vite's bundler. Wire them up explicitly. This runs once per import.
delete (L.Icon.Default.prototype as unknown as { _getIconUrl?: unknown })._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl:       "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl:     "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

export interface MapPinData {
  id: string;
  lat: number;
  lng: number;
  label: string;
  sublabel?: string;
  count?: number;
  onClick?: () => void;
}

interface Props {
  pins: MapPinData[];
  height?: number | string;
  // Centered on Nigeria by default (Abuja-ish).
  center?: [number, number];
  zoom?: number;
  // When true, render lightweight CircleMarkers instead of full pin icons —
  // better for hundreds of points.
  asCircles?: boolean;
}

export default function NigeriaMap({
  pins,
  height = 420,
  center = [9.0820, 8.6753],
  zoom = 6,
  asCircles = false,
}: Props) {
  // Dedupe identical coords + collapse near-duplicates into a count.
  const cleaned = useMemo(() => pins.filter(p => Number.isFinite(p.lat) && Number.isFinite(p.lng)), [pins]);

  return (
    <div className="rounded-2xl overflow-hidden border border-border" style={{ height }}>
      <MapContainer
        center={center}
        zoom={zoom}
        scrollWheelZoom={false}
        style={{ height: "100%", width: "100%" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {cleaned.map(p =>
          asCircles ? (
            <CircleMarker
              key={p.id}
              center={[p.lat, p.lng]}
              radius={Math.max(5, Math.min(14, Math.log10((p.count ?? 1) + 1) * 6 + 5))}
              pathOptions={{ color: "#E01F26", fillColor: "#E01F26", fillOpacity: 0.6, weight: 1 }}
              eventHandlers={p.onClick ? { click: p.onClick } : undefined}
            >
              <Popup>
                <div className="text-xs">
                  <p className="font-bold">{p.label}</p>
                  {p.sublabel && <p className="text-muted-foreground">{p.sublabel}</p>}
                  {typeof p.count === "number" && <p className="mt-1">{p.count.toLocaleString()} assets</p>}
                </div>
              </Popup>
            </CircleMarker>
          ) : (
            <Marker
              key={p.id}
              position={[p.lat, p.lng]}
              eventHandlers={p.onClick ? { click: p.onClick } : undefined}
            >
              <Popup>
                <div className="text-xs">
                  <p className="font-bold">{p.label}</p>
                  {p.sublabel && <p className="text-muted-foreground">{p.sublabel}</p>}
                  {typeof p.count === "number" && <p className="mt-1">{p.count.toLocaleString()} assets</p>}
                </div>
              </Popup>
            </Marker>
          )
        )}
      </MapContainer>
    </div>
  );
}
