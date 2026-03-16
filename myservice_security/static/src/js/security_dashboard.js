odoo.define('myservice_security_dashboard.SecurityDashboard', function(require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var rpc  = require('web.rpc');

    var L_CSS  = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
    var L_JS   = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    var CL_CSS = 'https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css';
    var CL_DEF = 'https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css';
    var CL_JS  = 'https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js';

    function loadStyle(href) {
        if (document.querySelector('link[href="'+href+'"]')) return;
        var l = document.createElement('link'); l.rel='stylesheet'; l.href=href;
        document.head.appendChild(l);
    }
    function loadScript(src) {
        return new Promise(function(res, rej) {
            if (document.querySelector('script[src="'+src+'"]')) { res(); return; }
            var s = document.createElement('script'); s.src=src;
            s.onload=res; s.onerror=rej; document.head.appendChild(s);
        });
    }

    // Add spin keyframe for loading spinner
    if (!document.getElementById('soc-spin-style')) {
        var st = document.createElement('style');
        st.id = 'soc-spin-style';
        st.textContent = '@keyframes soc-spin{to{transform:rotate(360deg)}}';
        document.head.appendChild(st);
    }

    var SEV_COLOR = { critical:'#f85149', high:'#E85426', medium:'#d29922', low:'#3fb950' };

    var NIG_STATES = [
        'Abia','Adamawa','Akwa Ibom','Anambra','Bauchi','Bayelsa','Benue','Borno',
        'Cross River','Delta','Ebonyi','Edo','Ekiti','Enugu','FCT','Gombe','Imo',
        'Jigawa','Kaduna','Kano','Katsina','Kebbi','Kogi','Kwara','Lagos','Nasarawa',
        'Niger','Ogun','Ondo','Osun','Oyo','Plateau','Rivers','Sokoto','Taraba',
        'Yobe','Zamfara'
    ];

    var SecurityDashboard = AbstractAction.extend({
        template: 'myservice_security_dashboard.Dashboard',
        events: {
            'click .ms-soc-refresh-btn': '_onRefresh',
            'click .ms-soc-kpi':         '_onKpiClick',
            'click .ms-soc-mf':          '_onFilterClick',
            'click .ms-soc-inc-item':    '_onIncidentClick',
            'click .ms-soc-osint-card':  '_onOsintClick',
        },
        init: function(parent, action) {
            this._super.apply(this, arguments);
            this.map = null; this.incLayer = null; this.guardLayer = null;
            this.kpis = {}; this.mapData = {}; this.osint = []; this.states = [];
            this.currentFilter = 'all'; this._clockTimer = null; this._refreshTimer = null;
        },
        start: async function() {
            await this._super.apply(this, arguments);
            loadStyle(L_CSS); loadStyle(CL_CSS); loadStyle(CL_DEF);
            await loadScript(L_JS); await loadScript(CL_JS);
            this._startClock();
            await this._loadData();
            this._refreshTimer = setInterval(this._loadData.bind(this), 300000);
        },
        destroy: function() {
            if (this._clockTimer)   clearInterval(this._clockTimer);
            if (this._refreshTimer) clearInterval(this._refreshTimer);
            if (this.map) { this.map.remove(); this.map = null; }
            this._super.apply(this, arguments);
        },
        _startClock: function() {
            var self = this;
            function tick() {
                var el = document.getElementById('soc-clock');
                if (el) el.textContent = new Date().toLocaleTimeString('en-GB');
            }
            tick();
            this._clockTimer = setInterval(tick, 1000);
        },
        _loadData: async function() {
            var self = this;
            try {
                var results = await Promise.all([
                    rpc.query({ route: '/myservice/security/kpis',         params: {} }),
                    rpc.query({ route: '/myservice/security/map_data',     params: {} }),
                    rpc.query({ route: '/myservice/security/recent',       params: {} }),
                    rpc.query({ route: '/myservice/security/osint',        params: {} }),
                    rpc.query({ route: '/myservice/security/state_threats',params: {} }),
                ]);
                self.kpis    = results[0];
                self.mapData = results[1];
                self.recent  = results[2];
                self.osint   = results[3];
                self.states  = results[4];
                self._updateKpis();
                self._renderMap();
                self._renderWatchlist();
                self._renderSeverityBars();
                self._renderGuardStats();
                self._renderRecentIncidents();
                self._renderOsint();
                self._renderStateThreatBar();
            } catch(e) { console.error('SOC Dashboard error:', e); }
        },
        _updateKpis: function() {
            var i=this.kpis.incidents||{}, g=this.kpis.guards||{},
                a=this.kpis.access||{}, w=this.kpis.watchlist||{};
            this.$('.soc-kpi-open').text(i.open||0);
            this.$('.soc-kpi-critical').text(i.critical||0);
            this.$('.soc-kpi-today').text(i.today||0);
            this.$('.soc-kpi-guards').text(g.on_duty||0);
            this.$('.soc-kpi-access').text(a.today_in||0);
            this.$('.soc-kpi-watchlist').text(w.total||0);
        },
        _renderMap: function() {
            var self = this;
            if (!window.L) return;
            var container = document.getElementById('ms-soc-map');
            if (!container) return;
            container.innerHTML = '';

            if (!this.map) {
                this.map = window.L.map('ms-soc-map', { center:[9.5,8.0], zoom:6 });
                window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                    { attribution:'© OpenStreetMap', maxZoom:18 }).addTo(this.map);
            } else {
                if (this.incLayer)   this.map.removeLayer(this.incLayer);
                if (this.guardLayer) this.map.removeLayer(this.guardLayer);
            }

            this.incLayer = window.L.markerClusterGroup({ maxClusterRadius:40,
                iconCreateFunction: function(c) {
                    return window.L.divIcon({
                        html:'<div style="background:#E85426;color:#fff;border-radius:50%;width:28px;height:28px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:11px;border:2px solid #0d1117;box-shadow:0 0 8px rgba(232,84,38,.5)">'+c.getChildCount()+'</div>',
                        className:'', iconSize:[28,28]
                    });
                }
            });

            (this.mapData.incidents||[]).forEach(function(inc) {
                var color = SEV_COLOR[inc.severity] || '#888';
                var isPulse = inc.severity === 'critical';
                var m = window.L.circleMarker([inc.lat, inc.lng], {
                    radius: isPulse ? 10 : 7,
                    fillColor: color, color: isPulse ? '#fff' : 'rgba(0,0,0,0.3)',
                    weight: isPulse ? 2 : 1, opacity:1, fillOpacity:0.9
                });
                m.bindPopup(
                    '<div style="font-family:Outfit,sans-serif;min-width:180px">' +
                    '<div style="font-weight:700;font-size:13px;color:#e6edf3;border-bottom:2px solid '+color+';padding-bottom:4px;margin-bottom:8px">'+inc.name+'</div>' +
                    '<div style="font-size:11px;color:#8b949e;line-height:1.8">'+
                    '<b style="color:#e6edf3">Type:</b> '+inc.type+'<br>'+
                    '<b style="color:#e6edf3">Severity:</b> <span style="color:'+color+'">'+inc.severity.toUpperCase()+'</span><br>'+
                    '<b style="color:#e6edf3">Location:</b> '+inc.location+'<br>'+
                    '<b style="color:#e6edf3">Date:</b> '+inc.date+
                    '</div></div>'
                );
                self.incLayer.addLayer(m);
            });

            this.guardLayer = window.L.layerGroup();
            (this.mapData.guards||[]).forEach(function(g) {
                var icon = window.L.divIcon({
                    html:'<div style="background:#3fb950;color:#0d1117;border-radius:50%;width:22px;height:22px;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;border:2px solid #0d1117;box-shadow:0 0 6px rgba(63,185,80,.4)">G</div>',
                    className:'', iconSize:[22,22]
                });
                var m = window.L.marker([g.lat,g.lng],{icon:icon});
                m.bindPopup('<div style="font-family:Outfit,sans-serif"><b style="color:#3fb950">'+g.name+'</b><br><span style="font-size:11px;color:#8b949e">'+g.location+' • '+g.shift+' shift</span></div>');
                self.guardLayer.addLayer(m);
            });

            this.map.addLayer(this.incLayer);
            this.map.addLayer(this.guardLayer);
            this._applyFilter();
            setTimeout(function(){ self.map && self.map.invalidateSize(); }, 200);
        },
        _applyFilter: function() {
            if (!this.map || !this.incLayer || !this.guardLayer) return;
            var f = this.currentFilter;
            if (f==='all') {
                this.map.addLayer(this.incLayer); this.map.addLayer(this.guardLayer);
            } else if (f==='incidents') {
                this.map.addLayer(this.incLayer);
                if (this.map.hasLayer(this.guardLayer)) this.map.removeLayer(this.guardLayer);
            } else if (f==='guards') {
                if (this.map.hasLayer(this.incLayer)) this.map.removeLayer(this.incLayer);
                this.map.addLayer(this.guardLayer);
            }
        },
        _renderWatchlist: function() {
            var w = this.kpis.watchlist || {};
            this.$('.soc-watch-count').text((w.total||0)+' active');
        },
        _renderSeverityBars: function() {
            var i = this.kpis.incidents || {};
            var total = (i.open||0) || 1;
            var vals = { critical: i.critical||0, high: i.high||0, medium: Math.max(0,(i.open||0)-(i.critical||0)-(i.high||0)), low: 0 };
            var self = this;
            ['critical','high','medium','low'].forEach(function(sev) {
                var pct = Math.round(vals[sev] / total * 100);
                self.$('.soc-bar-'+sev).css('width', pct+'%');
                self.$('#soc-sev-'+sev).text(vals[sev]);
            });
        },
        _renderGuardStats: function() {
            var g=this.kpis.guards||{}, a=this.kpis.access||{};
            this.$('#soc-g-duty').text(g.on_duty||0);
            this.$('#soc-g-total').text(g.total||0);
            this.$('#soc-g-access').text(a.today_in||0);
            this.$('#soc-g-flagged').text(a.flagged||0);
        },
        _renderRecentIncidents: function() {
            var self=this, $feed=this.$('.soc-inc-feed');
            $feed.empty();
            var items = this.recent || [];
            this.$('.soc-inc-count').text((this.kpis.incidents&&this.kpis.incidents.open||0)+' open');
            if (!items.length) {
                $feed.append('<div style="padding:14px;text-align:center;color:#7d8590;font-size:12px">No open incidents</div>');
                return;
            }
            items.forEach(function(inc) {
                $feed.append($('<div class="ms-soc-inc-item" data-id="'+inc.id+'">'+
                    '<div class="ms-soc-inc-strip '+inc.severity+'"></div>'+
                    '<div><div class="ms-soc-inc-name">'+inc.name+'</div>'+
                    '<div class="ms-soc-inc-meta">'+(inc.type||'')+' • '+(inc.location||'—')+' • '+inc.date+'</div></div>'+
                    '<span class="ms-soc-tag">'+inc.state.toUpperCase()+'</span>'+
                    '</div>'));
            });
        },
        _renderOsint: function() {
            var self=this, $grid=this.$('.soc-osint-grid');
            $grid.empty();
            var items = this.osint || [];
            this.$('#soc-osint-count').text(items.length+' entr'+(items.length===1?'y':'ies'));
            if (!items.length) {
                $grid.append('<div class="ms-soc-osint-empty">No OSINT entries yet. Add via Security menu → OSINT Feed.</div>');
                return;
            }
            items.forEach(function(item) {
                var verified = item.verified ? '<span class="ms-soc-verified">✓ Verified</span>' : '';
                $grid.append($('<div class="ms-soc-osint-card '+item.threat+'" data-id="'+item.id+'">'+
                    '<div class="ms-soc-osint-meta">'+
                    '<span class="ms-soc-src-badge '+item.source_type+'">'+item.source_type.replace('_',' ')+'</span>'+
                    '<span class="ms-soc-threat-badge '+item.threat+'">'+item.threat+'</span>'+
                    (item.source_name ? '<span style="font-size:10px;color:#7d8590">'+item.source_name+'</span>' : '')+
                    '</div>'+
                    '<div class="ms-soc-osint-headline">'+item.title+'</div>'+
                    '<div class="ms-soc-osint-summary">'+(item.summary||'')+'</div>'+
                    '<div class="ms-soc-osint-footer">'+
                    '<div class="ms-soc-osint-loc"><svg width="10" height="10" viewBox="0 0 10 10"><circle cx="5" cy="4" r="2" stroke="#7d8590" stroke-width="1" fill="none"/><path d="M5 6 Q5 9 5 9" stroke="#7d8590" stroke-width="1"/></svg>'+(item.location||'—')+'</div>'+
                    '<div style="display:flex;align-items:center;gap:6px">'+verified+'<span>'+item.date+'</span></div>'+
                    '</div></div>'));
            });
        },
        _renderStateThreatBar: function() {
            var self=this, $grid=this.$('.soc-states-grid');
            $grid.empty();
            var stateMap = {};
            (this.states||[]).forEach(function(s){ stateMap[s.name]=s.level; });
            NIG_STATES.forEach(function(name) {
                var level = stateMap[name] || 'green';
                $grid.append($('<span class="ms-soc-state '+level+'" title="'+name+'">'+(name==='Cross River'?'X.River':name==='Akwa Ibom'?'A.Ibom':name)+'</span>'));
            });
        },
        _onRefresh: function() { this._loadData(); },
        _onKpiClick: function(ev) {
            var model=$(ev.currentTarget).data('model');
            if (!model) return;
            this.do_action({ type:'ir.actions.act_window', res_model:model, view_mode:'list,form', domain:[], target:'current' });
        },
        _onFilterClick: function(ev) {
            this.$('.ms-soc-mf').removeClass('active');
            $(ev.currentTarget).addClass('active');
            this.currentFilter=$(ev.currentTarget).data('filter');
            this._applyFilter();
        },
        _onIncidentClick: function(ev) {
            var id=parseInt($(ev.currentTarget).data('id'));
            this.do_action({ type:'ir.actions.act_window', res_model:'security.incident', res_id:id, view_mode:'form', target:'current' });
        },
        _onOsintClick: function(ev) {
            var id=parseInt($(ev.currentTarget).data('id'));
            if (id) this.do_action({ type:'ir.actions.act_window', res_model:'security.osint.feed', res_id:id, view_mode:'form', target:'current' });
        },
    });

    core.action_registry.add('myservice_security_dashboard', SecurityDashboard);
    return SecurityDashboard;
});
