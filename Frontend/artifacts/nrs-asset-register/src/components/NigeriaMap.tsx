import { useMemo } from "react";
import { MapContainer, TileLayer, Marker, Popup, CircleMarker } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { getBrand } from "@/lib/brand";

// Custom pin marker — inline SVG via divIcon. Compact enough to read at country
// zoom without crowding the tiles. Built per call rather than as a constant so
// it picks up the TENANT's colour: one static bundle serves every tenant, so a
// hardcoded red pin lands on Jaiz navy and GTB orange alike.
const pinSvg = (colour: string) => `
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 32" width="14" height="18">
    <path d="M12 0c-6.6 0-12 5.4-12 12 0 9 12 20 12 20s12-11 12-20c0-6.6-5.4-12-12-12z"
          fill="${colour}" stroke="#FFFFFF" stroke-width="1.5"/>
    <circle cx="12" cy="12" r="4" fill="#FFFFFF"/>
  </svg>`;
/** Cached per colour — divIcon creation is cheap but this runs per marker. */
const pinIcons = new Map<string, L.DivIcon>();
function brandPinIcon(colour: string): L.DivIcon {
  let icon = pinIcons.get(colour);
  if (!icon) {
    icon = L.divIcon({
      html: pinSvg(colour),
      className: "nrs-pin",
      iconSize:    [16, 19],
      iconAnchor:  [ 7, 18],
      popupAnchor: [ 0, -14],
    });
    pinIcons.set(colour, icon);
  }
  return icon;
}

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
  // Markers follow the tenant's brand, like every other coloured surface.
  const brandColour = getBrand().primary;
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
              pathOptions={{ color: brandColour, fillColor: brandColour, fillOpacity: 0.6, weight: 1 }}
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
              icon={brandPinIcon(brandColour)}
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
