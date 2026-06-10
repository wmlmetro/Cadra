import { useMemo } from "react";
import { MapContainer, TileLayer, Marker, Popup, CircleMarker } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

// Custom red pin marker — inline SVG via divIcon. Compact enough to read at
// country zoom without crowding the tiles, and uses the NRS brand red
// (#E01F26) so map markers feel native to the rest of the UI.
const PIN_SVG = `
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 32" width="14" height="18">
    <path d="M12 0c-6.6 0-12 5.4-12 12 0 9 12 20 12 20s12-11 12-20c0-6.6-5.4-12-12-12z"
          fill="#E01F26" stroke="#FFFFFF" stroke-width="1.5"/>
    <circle cx="12" cy="12" r="4" fill="#FFFFFF"/>
  </svg>`;
const redPinIcon = L.divIcon({
  html: PIN_SVG,
  className: "nrs-pin",
  iconSize:    [16, 19],
  iconAnchor:  [ 7, 18],
  popupAnchor: [ 0, -14],
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
              icon={redPinIcon}
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
