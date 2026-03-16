odoo.define('myservice_security_dashboard.SecurityDashboard', function(require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var rpc  = require('web.rpc');

    var LEAFLET_CSS  = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
    var LEAFLET_JS   = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    var CLUSTER_CSS  = 'https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css';
    var CLUSTER_DEF  = 'https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css';
    var CLUSTER_JS   = 'https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js';

    function loadStyle(href) {
        if (document.querySelector('link[href="'+href+'"]')) return;
        var l = document.createElement('link'); l.rel='stylesheet'; l.href=href;
        document.head.appendChild(l);
    }
    function loadScript(src) {
        return new Promise(function(resolve, reject) {
            if (document.querySelector('script[src="'+src+'"]')) { resolve(); return; }
            var s = document.createElement('script'); s.src=src;
            s.onload=resolve; s.onerror=reject; document.head.appendChild(s);
        });
    }

    var SEV_COLOR = { critical:'#dc3545', high:'#E85426', medium:'#ffc107', low:'#28a745' };

    var SecurityDashboard = AbstractAction.extend({
        template: 'myservice_security_dashboard.Dashboard',
        events: {
            'click .ms-sec-refresh':    '_onRefresh',
            'click .ms-sec-kpi':        '_onKpiClick',
            'click .ms-sec-filter-btn': '_onFilterClick',
            'click .ms-sec-inc-item':   '_onIncidentClick',
        },
        init: function(parent, action) {
            this._super.apply(this, arguments);
            this.map = null; this.incLayer = null; this.guardLayer = null;
            this.kpis = {}; this.mapData = {}; this.currentFilter = 'all';
        },
        start: async function() {
            await this._super.apply(this, arguments);
            loadStyle(LEAFLET_CSS); loadStyle(CLUSTER_CSS); loadStyle(CLUSTER_DEF);
            await loadScript(LEAFLET_JS); await loadScript(CLUSTER_JS);
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
                    rpc.query({ route: '/myservice/security/kpis',    params: {} }),
                    rpc.query({ route: '/myservice/security/map_data',params: {} }),
                    rpc.query({ route: '/myservice/security/recent',  params: {} }),
                ]);
                self.kpis    = results[0];
                self.mapData = results[1];
                self.recent  = results[2];
                self._updateKpis();
                self._renderMap();
                self._renderSidePanel();
                self._renderRecentIncidents();
            } catch(e) { console.error('Security dashboard error:', e); }
        },
        _updateKpis: function() {
            var i=this.kpis.incidents||{}, g=this.kpis.guards||{},
                a=this.kpis.access||{}, w=this.kpis.watchlist||{};
            this.$('.sec-kpi-open').text(i.open||0);
            this.$('.sec-kpi-critical').text(i.critical||0);
            this.$('.sec-kpi-today').text(i.today||0);
            this.$('.sec-kpi-onduty').text(g.on_duty||0);
            this.$('.sec-kpi-access').text(a.today_in||0);
            this.$('.sec-kpi-watchlist').text(w.total||0);
        },
        _renderSidePanel: function() {
            var i=this.kpis.incidents||{}, g=this.kpis.guards||{},
                a=this.kpis.access||{}, w=this.kpis.watchlist||{};
            this.$('.sec-sev-critical').text(i.critical||0);
            this.$('.sec-sev-high').text(i.high||0);
            this.$('.sec-sev-medium').text(
                (i.open||0) - (i.critical||0) - (i.high||0) > 0 ?
                (i.open||0) - (i.critical||0) - (i.high||0) : 0);
            this.$('.sec-sev-low').text(0);
            this.$('.sec-guards-total').text(g.total||0);
            this.$('.sec-guards-duty').text(g.on_duty||0);
            this.$('.sec-access-flagged').text(a.flagged||0);
            this.$('.sec-watch-critical').text(w.critical||0);
            this.$('.sec-watch-high').text(w.high||0);
            this.$('.sec-watch-total').text(w.total||0);
        },
        _renderMap: function() {
            var self = this;
            if (!window.L) return;
            var container = document.getElementById('ms-sec-map');
            if (!container) return;
            container.innerHTML = '';

            if (!this.map) {
                this.map = window.L.map('ms-sec-map', { center:[9.5,8.0], zoom:6 });
                window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                    { attribution:'© OpenStreetMap contributors', maxZoom:18 }).addTo(this.map);
            } else {
                if (this.incLayer)   this.map.removeLayer(this.incLayer);
                if (this.guardLayer) this.map.removeLayer(this.guardLayer);
            }

            // Incident markers
            this.incLayer = window.L.markerClusterGroup({ maxClusterRadius:50 });
            (this.mapData.incidents||[]).forEach(function(inc) {
                var color = SEV_COLOR[inc.severity] || '#888';
                var m = window.L.circleMarker([inc.lat, inc.lng], {
                    radius:10, fillColor:color, color:'#fff', weight:2,
                    opacity:1, fillOpacity:0.9
                });
                m.bindPopup(
                    '<div class="ms-popup">' +
                    '<div class="ms-popup-title">🚨 '+inc.name+'</div>' +
                    '<div class="ms-popup-row"><span>Type</span><strong>'+inc.type+'</strong></div>' +
                    '<div class="ms-popup-row"><span>Severity</span><strong>'+inc.severity.toUpperCase()+'</strong></div>' +
                    '<div class="ms-popup-row"><span>Location</span><strong>'+inc.location+'</strong></div>' +
                    '<div class="ms-popup-row"><span>Date</span><strong>'+inc.date+'</strong></div>' +
                    '</div>'
                );
                self.incLayer.addLayer(m);
            });

            // Guard markers
            this.guardLayer = window.L.layerGroup();
            (this.mapData.guards||[]).forEach(function(g) {
                var icon = window.L.divIcon({
                    html: '<div style="background:#007bff;color:#fff;border-radius:50%;width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-size:12px;border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,0.3)">G</div>',
                    className: '', iconSize:[24,24]
                });
                var m = window.L.marker([g.lat, g.lng], { icon:icon });
                m.bindPopup(
                    '<div class="ms-popup">' +
                    '<div class="ms-popup-title">🛡️ '+g.name+'</div>' +
                    '<div class="ms-popup-row"><span>Badge</span><strong>'+g.badge+'</strong></div>' +
                    '<div class="ms-popup-row"><span>Location</span><strong>'+g.location+'</strong></div>' +
                    '<div class="ms-popup-row"><span>Shift</span><strong>'+g.shift+'</strong></div>' +
                    '</div>'
                );
                self.guardLayer.addLayer(m);
            });

            this.map.addLayer(this.incLayer);
            this.map.addLayer(this.guardLayer);
            this._updateLayerVisibility();
            setTimeout(function(){ self.map && self.map.invalidateSize(); }, 200);
        },
        _updateLayerVisibility: function() {
            if (!this.map) return;
            var f = this.currentFilter;
            if (f==='all') {
                if (this.incLayer)   this.map.addLayer(this.incLayer);
                if (this.guardLayer) this.map.addLayer(this.guardLayer);
            } else if (f==='incidents') {
                if (this.incLayer)   this.map.addLayer(this.incLayer);
                if (this.guardLayer && this.map.hasLayer(this.guardLayer)) this.map.removeLayer(this.guardLayer);
            } else if (f==='guards') {
                if (this.incLayer && this.map.hasLayer(this.incLayer)) this.map.removeLayer(this.incLayer);
                if (this.guardLayer) this.map.addLayer(this.guardLayer);
            }
        },
        _renderRecentIncidents: function() {
            var self = this, $list = this.$('.ms-sec-inc-list');
            $list.empty();
            var items = this.recent || [];
            if (!items.length) {
                $list.append('<div style="padding:16px;text-align:center;color:#888;font-size:13px;">No open incidents</div>');
                return;
            }
            items.forEach(function(inc) {
                var badge = '<span class="ms-sec-badge '+inc.severity+'">'+inc.severity.toUpperCase()+'</span>';
                $list.append($(
                    '<div class="ms-sec-inc-item '+inc.severity+'" data-id="'+inc.id+'">' +
                    '<div class="ms-sec-inc-name">'+inc.name+badge+'</div>' +
                    '<div class="ms-sec-inc-meta">'+inc.type+' • '+(inc.location||'No location')+' • '+inc.date+'</div>' +
                    '</div>'
                ));
            });
        },
        _onRefresh: function() { this._loadData(); },
        _onKpiClick: function(ev) {
            var model = $(ev.currentTarget).data('model');
            if (!model) return;
            this.do_action({ type:'ir.actions.act_window', res_model:model, view_mode:'list,form', domain:[], target:'current' });
        },
        _onFilterClick: function(ev) {
            this.$('.ms-sec-filter-btn').removeClass('active');
            $(ev.currentTarget).addClass('active');
            this.currentFilter = $(ev.currentTarget).data('filter');
            this._updateLayerVisibility();
        },
        _onIncidentClick: function(ev) {
            var id = parseInt($(ev.currentTarget).data('id'));
            this.do_action({ type:'ir.actions.act_window', res_model:'security.incident', res_id:id, view_mode:'form', target:'current' });
        },
    });

    core.action_registry.add('myservice_security_dashboard', SecurityDashboard);
    return SecurityDashboard;
});
