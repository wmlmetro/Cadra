odoo.define('myservice_dashboard.Dashboard', function (require) {
    'use strict';

    const AbstractAction = require('web.AbstractAction');
    const core = require('web.core');
    const rpc = require('web.rpc');

    const LEAFLET_CSS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
    const LEAFLET_JS  = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    const CLUSTER_CSS = 'https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css';
    const CLUSTER_DEF = 'https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css';
    const CLUSTER_JS  = 'https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js';

    function loadStyle(href) {
        if (document.querySelector('link[href="' + href + '"]')) return;
        var l = document.createElement('link'); l.rel = 'stylesheet'; l.href = href;
        document.head.appendChild(l);
    }
    function loadScript(src) {
        return new Promise(function(resolve, reject) {
            if (document.querySelector('script[src="' + src + '"]')) { resolve(); return; }
            var s = document.createElement('script'); s.src = src;
            s.onload = resolve; s.onerror = reject;
            document.head.appendChild(s);
        });
    }
    async function loadLeaflet() {
        loadStyle(LEAFLET_CSS); loadStyle(CLUSTER_CSS); loadStyle(CLUSTER_DEF);
        await loadScript(LEAFLET_JS); await loadScript(CLUSTER_JS);
    }

    var STATUS_COLOR = { ok:'#28a745', due_soon:'#ffc107', overdue:'#dc3545', no_schedule:'#6c757d' };

    var MyServiceDashboard = AbstractAction.extend({
        template: 'myservice_dashboard.Dashboard',
        events: {
            'click .ms-dash-refresh': '_onRefresh',
            'click .ms-kpi-card':    '_onKpiClick',
            'click .ms-filter-btn':  '_onFilterClick',
            'click .ms-request-item':'_onRequestClick',
        },
        init: function(parent, action) {
            this._super.apply(this, arguments);
            this.map = null; this.locationLayer = null; this.fleetLayer = null;
            this.kpis = {}; this.mapData = { locations:[], fleet:[], recent_requests:[] };
            this.currentFilter = 'all';
        },
        start: async function() {
            await this._super.apply(this, arguments);
            await loadLeaflet();
            await this._loadData();
            this._refreshTimer = setInterval(this._loadData.bind(this), 300000);
        },
        destroy: function() {
            if (this._refreshTimer) clearInterval(this._refreshTimer);
            if (this.map) { this.map.remove(); this.map = null; }
            this._super.apply(this, arguments);
        },
        _loadData: async function() {
            var self = this;
            try {
                var results = await Promise.all([
                    rpc.query({ route: '/myservice/dashboard/kpis', params: {} }),
                    rpc.query({ route: '/myservice/dashboard/map',  params: {} }),
                ]);
                self.kpis = results[0]; self.mapData = results[1];
                self._updateKpis(); self._renderMap();
                self._renderRecentRequests(); self._renderFleetStatus();
                self._renderLocationStats();
            } catch(e) { console.error('Dashboard error:', e); }
        },
        _updateKpis: function() {
            var f=this.kpis.fleet||{}, l=this.kpis.locations||{}, r=this.kpis.requests||{}, v=this.kpis.vendors||{};
            this.$('.kpi-total-vehicles').text(f.total||0);
            this.$('.kpi-overdue').text(f.overdue||0);
            this.$('.kpi-due-soon').text(f.due_soon||0);
            this.$('.kpi-total-locations').text(l.total||0);
            this.$('.kpi-open-requests').text(r.open||0);
            this.$('.kpi-approved-vendors').text(v.approved||0);
        },
        _renderMap: function() {
            var self = this;
            if (!window.L) return;
            var container = document.getElementById('ms-map');
            if (!container) return;
            container.innerHTML = '';
            if (!this.map) {
                this.map = window.L.map('ms-map', { center:[9.5,8.0], zoom:7 });
                window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                    { attribution:'© OpenStreetMap contributors', maxZoom:18 }).addTo(this.map);
            } else {
                if (this.locationLayer) this.map.removeLayer(this.locationLayer);
                if (this.fleetLayer)    this.map.removeLayer(this.fleetLayer);
            }
            this.locationLayer = window.L.markerClusterGroup({ maxClusterRadius:40,
                iconCreateFunction: function(c) { return window.L.divIcon({
                    html:'<div style="background:#007bff;color:#fff;border-radius:50%;width:32px;height:32px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;border:2px solid #fff">'+c.getChildCount()+'</div>',
                    className:'', iconSize:[32,32] }); }
            });
            (this.mapData.locations||[]).forEach(function(loc) {
                var m = window.L.circleMarker([loc.lat,loc.lng],{radius:7,fillColor:'#007bff',color:'#fff',weight:1.5,opacity:1,fillOpacity:0.9});
                m.bindPopup('<div class="ms-popup"><div class="ms-popup-title">📍 '+loc.name+'</div><div class="ms-popup-row"><span>State</span><strong>'+(loc.state||'—')+'</strong></div><div class="ms-popup-row"><span>Open Requests</span><strong>'+loc.open_requests+'</strong></div></div>');
                self.locationLayer.addLayer(m);
            });
            this.fleetLayer = window.L.markerClusterGroup({ maxClusterRadius:40,
                iconCreateFunction: function(c) { return window.L.divIcon({
                    html:'<div style="background:#E85426;color:#fff;border-radius:50%;width:32px;height:32px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;border:2px solid #fff">'+c.getChildCount()+'</div>',
                    className:'', iconSize:[32,32] }); }
            });
            var statusLabel = {ok:'✅ OK',due_soon:'⚠️ Due Soon',overdue:'🔴 Overdue',no_schedule:'⚫ No Schedule'};
            (this.mapData.fleet||[]).forEach(function(v) {
                var color=STATUS_COLOR[v.status]||'#6c757d';
                var m=window.L.circleMarker([v.lat,v.lng],{radius:6,fillColor:color,color:'#fff',weight:1.5,opacity:1,fillOpacity:0.9});
                m.bindPopup('<div class="ms-popup"><div class="ms-popup-title">🚗 '+v.name+'</div><div class="ms-popup-row"><span>Plate</span><strong>'+(v.plate||'—')+'</strong></div><div class="ms-popup-row"><span>Status</span><strong>'+(statusLabel[v.status]||v.status)+'</strong></div><div class="ms-popup-row"><span>Base</span><strong>'+(v.location||'—')+'</strong></div></div>');
                self.fleetLayer.addLayer(m);
            });
            this.map.addLayer(this.locationLayer);
            this.map.addLayer(this.fleetLayer);
            this._updateLayerVisibility();
            setTimeout(function(){ self.map&&self.map.invalidateSize(); },200);
        },
        _updateLayerVisibility: function() {
            if (!this.map||!this.locationLayer||!this.fleetLayer) return;
            var f=this.currentFilter;
            if (f==='all') { this.map.addLayer(this.locationLayer); this.map.addLayer(this.fleetLayer); }
            else if (f==='location') { this.map.addLayer(this.locationLayer); if(this.map.hasLayer(this.fleetLayer))this.map.removeLayer(this.fleetLayer); }
            else if (f==='vehicle') { if(this.map.hasLayer(this.locationLayer))this.map.removeLayer(this.locationLayer); this.map.addLayer(this.fleetLayer); }
        },
        _renderFleetStatus: function() {
            var f=this.kpis.fleet||{};
            this.$('.fs-ok').text(f.ok||0); this.$('.fs-due-soon').text(f.due_soon||0);
            this.$('.fs-overdue').text(f.overdue||0); this.$('.fs-no-schedule').text(f.no_schedule||0);
        },
        _renderLocationStats: function() {
            var l=this.kpis.locations||{}, r=this.kpis.requests||{};
            this.$('.ls-total').text(l.total||0); this.$('.ls-mapped').text(l.mapped||0);
            this.$('.ls-open').text(r.open||0); this.$('.ls-today').text(r.today||0);
        },
        _renderRecentRequests: function() {
            var self=this, $list=this.$('.ms-request-list');
            $list.empty();
            var reqs=this.mapData.recent_requests||[];
            if (!reqs.length) { $list.append('<div style="padding:16px;text-align:center;color:#888;font-size:13px;">No open requests</div>'); return; }
            reqs.forEach(function(req) {
                var badge=req.is_maintenance?'<span class="ms-request-badge">MAINT</span>':'';
                $list.append($('<div class="ms-request-item" data-id="'+req.id+'"><div class="ms-request-name">'+req.name+badge+'</div><div class="ms-request-meta">'+(req.service||'')+' • '+(req.location||'No location')+' • '+(req.date||'')+'</div></div>'));
            });
        },
        _onRefresh: function() { this._loadData(); },
        _onKpiClick: function(ev) {
            var $c=$(ev.currentTarget), model=$c.data('model'), domain=$c.data('domain')||'[]';
            if (!model) return;
            this.do_action({ type:'ir.actions.act_window', res_model:model, view_mode:'list,form', domain:JSON.parse(domain), target:'current' });
        },
        _onFilterClick: function(ev) {
            this.$('.ms-filter-btn').removeClass('active');
            $(ev.currentTarget).addClass('active');
            this.currentFilter=$(ev.currentTarget).data('filter');
            this._updateLayerVisibility();
        },
        _onRequestClick: function(ev) {
            var id=parseInt($(ev.currentTarget).data('id'));
            this.do_action({ type:'ir.actions.act_window', res_model:'request.request', res_id:id, view_mode:'form', target:'current' });
        },
    });

    core.action_registry.add('myservice_dashboard', MyServiceDashboard);
    return MyServiceDashboard;
});
