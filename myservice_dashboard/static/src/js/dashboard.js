/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";

// ── Leaflet loaded from CDN in template ──────────────────────────────
const LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
const LEAFLET_JS  = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
const CLUSTER_CSS = "https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css";
const CLUSTER_DEF = "https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css";
const CLUSTER_JS  = "https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js";

function loadScript(src) {
    return new Promise((resolve, reject) => {
        if (document.querySelector(`script[src="${src}"]`)) { resolve(); return; }
        const s = document.createElement('script');
        s.src = src; s.onload = resolve; s.onerror = reject;
        document.head.appendChild(s);
    });
}
function loadStyle(href) {
    if (document.querySelector(`link[href="${href}"]`)) return;
    const l = document.createElement('link');
    l.rel = 'stylesheet'; l.href = href;
    document.head.appendChild(l);
}

// ── Status colours ────────────────────────────────────────────────────
const STATUS_COLOR = {
    ok:          '#28a745',
    due_soon:    '#ffc107',
    overdue:     '#dc3545',
    no_schedule: '#6c757d',
};

function makeCircleMarker(lat, lng, color, radius=8) {
    return window.L.circleMarker([lat, lng], {
        radius,
        fillColor: color,
        color: '#fff',
        weight: 1.5,
        opacity: 1,
        fillOpacity: 0.9,
    });
}

// ── Dashboard Component ───────────────────────────────────────────────
class MyServiceDashboard extends Component {
    static template = "myservice_dashboard.Dashboard";

    setup() {
        this.rpc    = useService("rpc");
        this.action = useService("action");

        this.state = useState({
            kpis: {
                fleet:     { total:0, overdue:0, due_soon:0, ok:0, no_schedule:0 },
                locations: { total:0, mapped:0 },
                requests:  { open:0, maintenance:0, today:0 },
                vendors:   { total:0, approved:0 },
            },
            mapData: { locations:[], fleet:[], recent_requests:[] },
            loading: true,
            filter: 'all',
        });

        this.map = null;
        this.locationLayer = null;
        this.fleetLayer    = null;
        this._refreshTimer = null;

        onMounted(async () => {
            await this._loadLeaflet();
            await this.loadData();
            // Auto-refresh every 5 minutes
            this._refreshTimer = setInterval(() => this.loadData(), 300000);
        });

        onWillUnmount(() => {
            if (this._refreshTimer) clearInterval(this._refreshTimer);
            if (this.map) { this.map.remove(); this.map = null; }
        });
    }

    async _loadLeaflet() {
        loadStyle(LEAFLET_CSS);
        loadStyle(CLUSTER_CSS);
        loadStyle(CLUSTER_DEF);
        await loadScript(LEAFLET_JS);
        await loadScript(CLUSTER_JS);
    }

    async loadData() {
        this.state.loading = true;
        try {
            const [kpis, mapData] = await Promise.all([
                this.rpc('/myservice/dashboard/kpis', {}),
                this.rpc('/myservice/dashboard/map', {}),
            ]);
            this.state.kpis    = kpis;
            this.state.mapData = mapData;
            this._renderMap();
        } catch(e) {
            console.error('Dashboard load error:', e);
        } finally {
            this.state.loading = false;
        }
    }

    _renderMap() {
        if (!window.L) return;

        const container = document.getElementById('ms-map');
        if (!container) return;

        // Clear loading spinner
        container.innerHTML = '';

        // Init map centred on Nigeria
        if (!this.map) {
            this.map = window.L.map('ms-map', {
                center: [9.082, 8.675],
                zoom: 6,
                zoomControl: true,
            });

            window.L.tileLayer(
                'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                { attribution: '© OpenStreetMap contributors', maxZoom: 18 }
            ).addTo(this.map);

            // Filter button handlers
            document.querySelectorAll('.ms-filter-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    document.querySelectorAll('.ms-filter-btn').forEach(b => b.classList.remove('active'));
                    e.target.classList.add('active');
                    this.state.filter = e.target.dataset.filter;
                    this._updateLayerVisibility();
                });
            });
        } else {
            // Remove old layers
            if (this.locationLayer) this.map.removeLayer(this.locationLayer);
            if (this.fleetLayer)    this.map.removeLayer(this.fleetLayer);
        }

        // ── Location markers (blue) ───────────────────────────────────
        this.locationLayer = window.L.markerClusterGroup({
            maxClusterRadius: 40,
            iconCreateFunction: (cluster) => {
                return window.L.divIcon({
                    html: `<div style="background:#007bff;color:#fff;border-radius:50%;
                                width:32px;height:32px;display:flex;align-items:center;
                                justify-content:center;font-weight:700;font-size:12px;
                                border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,255,0.3)">
                                ${cluster.getChildCount()}
                           </div>`,
                    className: '',
                    iconSize: [32, 32],
                });
            }
        });

        (this.state.mapData.locations || []).forEach(loc => {
            const marker = makeCircleMarker(loc.lat, loc.lng, '#007bff', 7);
            marker.bindPopup(this._locationPopup(loc));
            marker.on('click', () => marker.openPopup());
            this.locationLayer.addLayer(marker);
        });

        // ── Fleet markers ─────────────────────────────────────────────
        this.fleetLayer = window.L.markerClusterGroup({
            maxClusterRadius: 40,
            iconCreateFunction: (cluster) => {
                return window.L.divIcon({
                    html: `<div style="background:#E85426;color:#fff;border-radius:50%;
                                width:32px;height:32px;display:flex;align-items:center;
                                justify-content:center;font-weight:700;font-size:12px;
                                border:2px solid #fff;box-shadow:0 2px 6px rgba(232,84,38,0.3)">
                                ${cluster.getChildCount()}
                           </div>`,
                    className: '',
                    iconSize: [32, 32],
                });
            }
        });

        (this.state.mapData.fleet || []).forEach(v => {
            const color = STATUS_COLOR[v.status] || '#6c757d';
            const marker = makeCircleMarker(v.lat, v.lng, color, 6);
            marker.bindPopup(this._vehiclePopup(v));
            marker.on('click', () => marker.openPopup());
            this.fleetLayer.addLayer(marker);
        });

        this.map.addLayer(this.locationLayer);
        this.map.addLayer(this.fleetLayer);
        this._updateLayerVisibility();

        // Force map resize
        setTimeout(() => this.map && this.map.invalidateSize(), 100);
    }

    _updateLayerVisibility() {
        if (!this.map || !this.locationLayer || !this.fleetLayer) return;
        const f = this.state.filter;
        if (f === 'all') {
            this.map.addLayer(this.locationLayer);
            this.map.addLayer(this.fleetLayer);
        } else if (f === 'location') {
            this.map.addLayer(this.locationLayer);
            this.map.removeLayer(this.fleetLayer);
        } else if (f === 'vehicle') {
            this.map.removeLayer(this.locationLayer);
            this.map.addLayer(this.fleetLayer);
        }
    }

    _locationPopup(loc) {
        return `
            <div class="ms-popup">
                <div class="ms-popup-title">📍 ${loc.name}</div>
                <div class="ms-popup-row"><span>State</span><strong>${loc.state}</strong></div>
                <div class="ms-popup-row"><span>Open Requests</span><strong>${loc.open_requests}</strong></div>
                <div class="ms-popup-btn ms-open-record"
                     data-model="generic.location" data-id="${loc.id}">
                    View Location →
                </div>
            </div>`;
    }

    _vehiclePopup(v) {
        const statusLabel = {
            ok: '✅ OK', due_soon: '⚠️ Due Soon',
            overdue: '🔴 Overdue', no_schedule: '⚫ No Schedule'
        }[v.status] || v.status;
        return `
            <div class="ms-popup">
                <div class="ms-popup-title">🚗 ${v.name}</div>
                <div class="ms-popup-row"><span>Plate</span><strong>${v.plate || '—'}</strong></div>
                <div class="ms-popup-row"><span>Driver</span><strong>${v.driver || '—'}</strong></div>
                <div class="ms-popup-row"><span>Status</span><strong>${statusLabel}</strong></div>
                <div class="ms-popup-row"><span>Base</span><strong>${v.location}</strong></div>
                <div class="ms-popup-row"><span>State</span><strong>${v.state}</strong></div>
                <div class="ms-popup-btn ms-open-record"
                     data-model="fleet.vehicle" data-id="${v.id}">
                    View Vehicle →
                </div>
            </div>`;
    }

    openList(model, domain) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: model,
            view_mode: 'list,form',
            domain: domain,
            target: 'current',
        });
    }

    openRecord(model, id) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: model,
            res_id: id,
            view_mode: 'form',
            target: 'current',
        });
    }
}

// ── Register as client action ─────────────────────────────────────────
registry.category("actions").add("myservice_dashboard", MyServiceDashboard);
