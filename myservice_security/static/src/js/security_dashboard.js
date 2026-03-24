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

    if (!document.getElementById('soc-tab-style')) {
        var ts = document.createElement('style');
        ts.id = 'soc-tab-style';
        ts.textContent = [
            '.ms-soc-tab-bar{display:flex;gap:6px;padding:10px 0;border-bottom:1px solid #21262d;margin-bottom:14px}',
            '.ms-soc-tab{padding:7px 16px;border-radius:16px;border:1px solid #30363d;background:transparent;cursor:pointer;font-size:12px;color:#8b949e;transition:all .2s;font-family:inherit}',
            '.ms-soc-tab.active{background:#E85426;color:#fff;border-color:#E85426}',
            '.ms-soc-tab:hover:not(.active){background:#21262d;color:#e6edf3}',
            '.ms-intel-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px;flex-wrap:wrap}',
            '.ms-intel-filters{display:flex;gap:4px}',
            '.ms-intel-filter{padding:4px 12px;border-radius:12px;border:1px solid #30363d;background:transparent;cursor:pointer;font-size:11px;color:#8b949e;font-family:inherit}',
            '.ms-intel-filter.active{background:#21262d;color:#e6edf3;border-color:#58a6ff}',
            '.ms-intel-source-filters{display:flex;gap:4px;flex-wrap:wrap}',
            '.ms-intel-src{padding:4px 10px;border-radius:12px;border:1px solid #30363d;background:transparent;cursor:pointer;font-size:10px;color:#7d8590;font-family:inherit}',
            '.ms-intel-src.active{background:#161b22;color:#e6edf3;border-color:#30363d}',
            '.ms-intel-count{font-size:11px;color:#7d8590;white-space:nowrap}',
            '.ms-intel-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}',
            '.ms-intel-card{background:#161b22;border-radius:8px;border:1px solid #21262d;padding:14px;cursor:pointer;transition:border-color .2s}',
            '.ms-intel-card:hover{border-color:#E85426}',
            '.ms-intel-card-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}',
            '.ms-intel-source{font-size:10px;color:#7d8590;text-transform:uppercase;letter-spacing:.5px}',
            '.ms-intel-threat{font-size:10px;font-weight:700;padding:2px 8px;border-radius:8px}',
            '.ms-intel-threat.critical{background:rgba(248,81,73,.15);color:#f85149}',
            '.ms-intel-threat.high{background:rgba(232,84,38,.15);color:#E85426}',
            '.ms-intel-threat.medium{background:rgba(210,153,34,.15);color:#d29922}',
            '.ms-intel-threat.low{background:rgba(63,185,80,.15);color:#3fb950}',
            '.ms-intel-threat.info{background:rgba(88,166,255,.15);color:#58a6ff}',
            '.ms-intel-title{font-size:13px;font-weight:600;color:#e6edf3;margin-bottom:6px;line-height:1.4}',
            '.ms-intel-summary{font-size:11px;color:#8b949e;line-height:1.5;margin-bottom:8px}',
            '.ms-intel-footer{display:flex;align-items:center;justify-content:space-between;font-size:10px;color:#7d8590}',
            '.ms-intel-verified{color:#3fb950}',
            '.ms-wlb-toolbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;flex-wrap:wrap;gap:10px}',
            '.ms-wlb-filters{display:flex;gap:4px}',
            '.ms-wlb-filter{padding:4px 12px;border-radius:12px;border:1px solid #30363d;background:transparent;cursor:pointer;font-size:11px;color:#8b949e;font-family:inherit}',
            '.ms-wlb-filter.active{background:#E85426;color:#fff;border-color:#E85426}',
            '.ms-wlb-count{font-size:11px;color:#7d8590}',
            '.ms-wlb-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px}',
            '.ms-wlb-card{background:#161b22;border-radius:10px;overflow:hidden;border-top:3px solid #30363d;transition:transform .2s,box-shadow .2s;cursor:pointer}',
            '.ms-wlb-card:hover{transform:translateY(-3px);box-shadow:0 8px 24px rgba(0,0,0,.4)}',
            '.ms-wlb-card.critical{border-top-color:#f85149}',
            '.ms-wlb-card.high{border-top-color:#E85426}',
            '.ms-wlb-card.medium{border-top-color:#d29922}',
            '.ms-wlb-card.low{border-top-color:#3fb950}',
            '.ms-wlb-photo{width:100%;height:180px;object-fit:cover;object-position:top center;display:block}',
            '.ms-wlb-placeholder{width:100%;height:180px;background:#0d1117;display:flex;align-items:center;justify-content:center;font-size:52px;font-weight:700;color:#30363d}',
            '.ms-wlb-body{padding:10px 12px 12px}',
            '.ms-wlb-name{font-size:13px;font-weight:700;color:#e6edf3;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
            '.ms-wlb-cat{font-size:10px;color:#7d8590;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}',
            '.ms-wlb-meta{font-size:10px;color:#7d8590;margin-bottom:4px}',
            '.ms-wlb-ribbon{display:inline-block;font-size:9px;font-weight:700;padding:2px 7px;border-radius:8px;text-transform:uppercase;margin-top:4px}',
            '.ms-wlb-ribbon.critical{background:#f85149;color:#fff}',
            '.ms-wlb-ribbon.high{background:#E85426;color:#fff}',
            '.ms-wlb-ribbon.medium{background:#d29922;color:#0d1117}',
            '.ms-wlb-ribbon.low{background:#3fb950;color:#0d1117}',
            '.ms-wlb-status{font-size:9px;float:right;margin-top:4px}',
            '.ms-wlb-status.approved{color:#3fb950}',
            '.ms-wlb-status.pending{color:#d29922}',
            '.ms-rpt-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}',
            '.ms-rpt-card{background:#161b22;border-radius:8px;border:1px solid #21262d;padding:14px 16px}',
            '.ms-rpt-card-hdr{font-size:12px;font-weight:600;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:12px}',
            '.ms-rpt-bar-row{display:flex;align-items:center;gap:8px;margin-bottom:7px}',
            '.ms-rpt-bar-label{font-size:11px;color:#8b949e;width:110px;flex-shrink:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
            '.ms-rpt-bar-track{flex:1;height:7px;background:#21262d;border-radius:4px;overflow:hidden}',
            '.ms-rpt-bar-fill{height:100%;border-radius:4px}',
            '.ms-rpt-bar-val{font-size:11px;color:#7d8590;width:28px;text-align:right;flex-shrink:0}',
            '.ms-rpt-stat-row{display:flex;align-items:center;justify-content:space-between;padding:7px 0;border-bottom:1px solid #21262d;font-size:12px;color:#8b949e}',
            '.ms-rpt-stat-row:last-child{border-bottom:none}',
            '.ms-rpt-stat-val{font-weight:600;color:#e6edf3}',
            '.ms-rpt-alert-row{display:flex;align-items:flex-start;gap:8px;padding:7px 0;border-bottom:1px solid #21262d}',
            '.ms-rpt-alert-row:last-child{border-bottom:none}',
            '.ms-rpt-alert-name{font-size:11px;color:#e6edf3;font-weight:600}',
            '.ms-rpt-alert-type{font-size:10px;color:#7d8590}',
        ].join('');
        document.head.appendChild(ts);
    }

    // Overflow fix — ensure OSINT and state threat sections are visible
    if (!document.getElementById('soc-overflow-fix')) {
        var sf = document.createElement('style');
        sf.id = 'soc-overflow-fix';
        sf.textContent =
            '.ms-soc{overflow-y:auto!important;height:auto!important;min-height:100%;}' +
            '.o_action_manager,.o_action,.o_client_action_container{overflow-y:auto!important;height:auto!important;}' +
            '.ms-soc-osint-section{display:block!important;width:100%;padding:16px 20px;box-sizing:border-box;}' +
            '.ms-soc-state-bar{display:block!important;width:100%;padding:12px 20px 24px;box-sizing:border-box;}' +
            '.ms-soc-osint-grid{display:grid!important;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;margin-top:10px;}' +
            '.ms-soc-states{display:flex!important;flex-wrap:wrap;gap:6px;margin-top:8px;}';
        document.head.appendChild(sf);
    }
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
            'click .ms-soc-tab': '_onTabClick',
            'click .ms-soc-kpi':         '_onKpiClick',
            'click .ms-soc-mf':          '_onFilterClick',
            'click .ms-soc-inc-item':    '_onIncidentClick',
            'click .ms-soc-osint-card':  '_onOsintClick',
        },
        init: function(parent, action) {
            this._super.apply(this, arguments);
            this.map = null; this.incLayer = null; this.guardLayer = null; this.locLayer = null;
            this.kpis = {}; this.mapData = {}; this.osint = []; this.states = [];
            this._intelLoaded = false; this._wlbLoaded = false; this._reportsLoaded = false; this._allOsint = []; this._wlbData = [];
            this.currentFilter = 'all'; this._clockTimer = null; this._refreshTimer = null;
        },
        start: async function() {
            await this._super.apply(this, arguments);
            var self = this;
            self._startClock();
            // Load Leaflet in background, data immediately
            loadStyle(L_CSS); loadStyle(CL_CSS); loadStyle(CL_DEF);
            loadScript(L_JS).then(function() {
                return loadScript(CL_JS);
            }).then(function() {
                self._renderMap();
            }).catch(function(e) {
                console.warn('Leaflet CDN failed:', e);
            });
            await self._loadData();
            self._refreshTimer = setInterval(self._loadData.bind(self), 300000);
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
                self.osint   = results[3]; self._allOsint = results[3];
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
            if (!window.L || !window.L.map) {
                // Leaflet not ready yet — retry in 300ms
                setTimeout(function() { self._renderMap(); }, 300);
                return;
            }
            var container = document.getElementById('ms-soc-map');
            if (!container) return;
            if (!this.map) {
                container.innerHTML = '';
                this.map = window.L.map('ms-soc-map', {
                    center:[9.0,8.5], zoom:6, minZoom:5,
                    maxBounds:[[3.5,2.0],[14.5,16.0]],
                    maxBoundsViscosity:0.8
                });
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

            // Location layer (FIRS offices)
            this.locLayer = window.L.markerClusterGroup({ maxClusterRadius:30,
                iconCreateFunction: function(c) {
                    return window.L.divIcon({
                        html:'<div style="background:#58a6ff;color:#0d1117;border-radius:50%;width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:10px;border:2px solid #0d1117">'+c.getChildCount()+'</div>',
                        className:'', iconSize:[24,24]
                    });
                }
            });
            (self.mapData.locations||[]).forEach(function(loc) {
                var color = loc.open_incidents > 0 ? '#E85426' : '#58a6ff';
                var m = window.L.circleMarker([loc.lat, loc.lng], {
                    radius:5, fillColor:color, color:'#0d1117',
                    weight:1, opacity:1, fillOpacity:0.85
                });
                m.bindPopup(
                    '<div style="font-family:Outfit,sans-serif;min-width:160px">'+
                    '<div style="font-weight:700;font-size:12px;color:#e6edf3;border-bottom:1px solid #58a6ff;padding-bottom:3px;margin-bottom:6px">'+loc.name+'</div>'+
                    '<div style="font-size:11px;color:#8b949e">State: <b style="color:#e6edf3">'+loc.state+'</b></div>'+
                    '<div style="font-size:11px;color:#8b949e">Open incidents: <b style="color:'+(loc.open_incidents>0?'#E85426':'#3fb950')+'">'+loc.open_incidents+'</b></div>'+
                    '</div>'
                );
                self.locLayer.addLayer(m);
            });

            this.map.addLayer(this.incLayer);
            this.map.addLayer(this.guardLayer);
            this.map.addLayer(this.locLayer);
            this._applyFilter();
            setTimeout(function(){
                if (self.map) {
                    self.map.invalidateSize();
                    // Force re-center on Nigeria if no markers visible
                    if ((self.mapData.incidents||[]).length === 0 && (self.mapData.guards||[]).length === 0) {
                        self.map.setView([9.5, 8.0], 6);
                    }
                }
            }, 500);
        },
        _applyFilter: function() {
            if (!this.map) return;
            var f = this.currentFilter;
            var addL = function(l) { if (l && !this.map.hasLayer(l)) this.map.addLayer(l); }.bind(this);
            var remL = function(l) { if (l && this.map.hasLayer(l)) this.map.removeLayer(l); }.bind(this);
            if (f==='all') {
                addL(this.incLayer); addL(this.guardLayer); addL(this.locLayer);
            } else if (f==='incidents') {
                addL(this.incLayer); remL(this.guardLayer); addL(this.locLayer);
            } else if (f==='guards') {
                remL(this.incLayer); addL(this.guardLayer); addL(this.locLayer);
            }
        },
        _renderWatchlist: function() {
            var self = this;
            var w = this.kpis.watchlist || {};
            this.$('.soc-watch-count').text((w.total||0)+' active');
            // Fetch actual watchlist entries
            rpc.query({
                model: 'security.watchlist',
                method: 'search_read',
                args: [[['approval_state', '=', 'approved']]],
                kwargs: {
                    fields: ['name', 'threat_level', 'category', 'last_sighted',
                             'last_sighted_location_id', 'vehicle_plate', 'photo'],
                    limit: 8,
                }
            }).then(function(entries) {
                console.log('SOC watchlist entries:', entries ? entries.length : 'null', entries);
                var $list = self.$('.soc-watch-list');
                $list.empty();
                if (!entries || !entries.length) {
                    $list.append('<div style="padding:10px 12px;font-size:11px;color:#7d8590">No approved watchlist entries</div>');
                    return;
                }
                entries.forEach(function(e) {
                    var tl = e.threat_level || 'medium';
                    var initials = (e.name||'?').split(' ').map(function(w){return (w||'')[0]||'';}).join('').substring(0,2).toUpperCase();
                    var lastSeen = e.last_sighted ? String(e.last_sighted).substring(0,10) : '';
                    var avatarHtml = e.photo
                        ? '<div class="ms-soc-avatar '+tl+'" style="background:none;padding:0;overflow:hidden"><img src="data:image/png;base64,'+e.photo+'" style="width:100%;height:100%;object-fit:cover;border-radius:50%"></div>'
                        : '<div class="ms-soc-avatar '+tl+'">'+initials+'</div>';
                    $list.append('<div class="ms-soc-watch-item" data-id="'+e.id+'">' +
                        avatarHtml+
                        '<div style="flex:1;min-width:0">'+
                        '<div class="ms-soc-wname">'+e.name+'</div>'+
                        '<div class="ms-soc-wmeta">'+(e.category||'')+(lastSeen?' • '+lastSeen:'')+'</div>'+
                        '</div>'+
                        '<span class="ms-soc-tbadge '+tl+'">'+tl+'</span>'+
                        '</div>');
                });
            });
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
                    '<div class="ms-soc-osint-summary">'+(item.summary||'').replace(/<[^>]*>/g,'').substring(0,160)+'</div>'+
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
        _onTabClick: function(ev) {
            var tab = $(ev.currentTarget).data('tab');
            this.$('.ms-soc-tab').removeClass('active');
            $(ev.currentTarget).addClass('active');
            this.$('.ms-soc-tab-panel').hide();
            this.$('.ms-soc-tab-panel[data-panel="' + tab + '"]').show();
            if (tab === 'intel' && !this._intelLoaded) { this._renderIntelFull(); this._intelLoaded = true; }
            if (tab === 'watchlist' && !this._wlbLoaded) { this._renderWatchlistBoard(); this._wlbLoaded = true; }
            if (tab === 'reports' && !this._reportsLoaded) { this._renderReports(); this._reportsLoaded = true; }
        },

        _renderIntelFull: function() {
            var self = this;
            var threatFilter = 'all', srcFilter = 'all';
            function render() {
                var items = self._allOsint || [];
                var filtered = items.filter(function(i) {
                    return (threatFilter === 'all' || i.threat === threatFilter) &&
                           (srcFilter === 'all' || i.source_type === srcFilter);
                });
                self.$('#intel-count').text(filtered.length + ' entries');
                var $g = self.$('.soc-intel-grid');
                $g.empty();
                if (!filtered.length) { $g.append('<div class="ms-soc-osint-empty">No entries match.</div>'); return; }
                filtered.forEach(function(i) {
                    var v = i.verified ? '<span class="ms-intel-verified">&#10003; Verified</span>' : '';
                    $g.append('<div class="ms-intel-card" data-id="' + i.id + '">' +
                        '<div class="ms-intel-card-top"><span class="ms-intel-source">' + (i.source_name||i.source_type||'') + '</span>' +
                        '<span class="ms-intel-threat ' + (i.threat||'info') + '">' + (i.threat||'info').toUpperCase() + '</span></div>' +
                        '<div class="ms-intel-title">' + (i.title||'') + '</div>' +
                        '<div class="ms-intel-summary">' + (i.summary||'').replace(/<[^>]*>/g,'').substring(0,200) + '</div>' +
                        '<div class="ms-intel-footer"><span>' + (i.location||'') + '</span><span>' + v + ' ' + (i.date||'') + '</span></div></div>');
                });
            }
            if (!this._allOsint || !this._allOsint.length) {
                var rpc = require('web.rpc');
                rpc.query({ route: '/myservice/security/osint', params: {} }).then(function(d) {
                    self._allOsint = d || [];
                    render();
                });
            } else { render(); }
            this.$('.ms-intel-filter').off('click').on('click', function() {
                self.$('.ms-intel-filter').removeClass('active');
                $(this).addClass('active');
                threatFilter = $(this).data('threat');
                render();
            });
            this.$('.ms-intel-src').off('click').on('click', function() {
                self.$('.ms-intel-src').removeClass('active');
                $(this).addClass('active');
                srcFilter = $(this).data('source');
                render();
            });
        },

        _renderWatchlistBoard: function() {
            var self = this;
            var threatFilter = 'all';
            var rpc = require('web.rpc');
            rpc.query({ model:'security.watchlist', method:'search_read',
                args:[[['approval_state','=','approved']]],
                kwargs:{ fields:['name','threat_level','category','last_sighted',
                    'vehicle_plate','approval_state','last_sighted_location_id','photo'],
                    limit:100 }
            }).then(function(data) {
                self._wlbData = data || [];
                self.$('#wlb-count').text(data.length + ' subjects');
                self._renderWlbCards(threatFilter);
            });
            this.$('.ms-wlb-filter').off('click').on('click', function() {
                self.$('.ms-wlb-filter').removeClass('active');
                $(this).addClass('active');
                threatFilter = $(this).data('threat');
                self._renderWlbCards(threatFilter);
            });
            this.$('.ms-wlb-fullscreen-btn').off('click').on('click', function() {
                var el = self.$('.ms-soc-tab-panel[data-panel="watchlist"]')[0];
                if (el && el.requestFullscreen) el.requestFullscreen();
            });
            var _auto = null;
            this.$('.ms-wlb-autoplay-btn').off('click').on('click', function() {
                if (_auto) { clearInterval(_auto); _auto = null; $(this).text('Play Auto-cycle'); return; }
                var filters = ['all','critical','high','medium','low'], idx = 0;
                _auto = setInterval(function() {
                    idx = (idx+1) % filters.length;
                    threatFilter = filters[idx];
                    self.$('.ms-wlb-filter').removeClass('active');
                    self.$('.ms-wlb-filter[data-threat="'+threatFilter+'"]').addClass('active');
                    self._renderWlbCards(threatFilter);
                }, 5000);
                $(this).text('Stop');
            });
        },

        _renderWlbCards: function(threatFilter) {
            var ORDER = {critical:0,high:1,medium:2,low:3};
            var data = (this._wlbData||[]).filter(function(w) {
                return threatFilter === 'all' || w.threat_level === threatFilter;
            }).sort(function(a,b) {
                return (ORDER[a.threat_level]||9) - (ORDER[b.threat_level]||9);
            });
            var $g = this.$('.soc-wlb-grid');
            $g.empty();
            if (!data.length) { $g.append('<div class="ms-soc-osint-empty">No subjects match.</div>'); return; }
            data.forEach(function(w) {
                var photo = w.photo ?
                    '<img class="ms-wlb-photo" src="data:image/png;base64,' + w.photo + '" alt=""/>' :
                    '<div class="ms-wlb-placeholder">' + (w.name||'?')[0].toUpperCase() + '</div>';
                var loc = w.last_sighted_location_id ? w.last_sighted_location_id[1] : 'Unknown';
                var inc = '';
                var plate = w.vehicle_plate ? '<div class="ms-wlb-meta">Plate: ' + w.vehicle_plate + '</div>' : '';
                $g.append('<div class="ms-wlb-card ' + (w.threat_level||'') + '" data-id="' + w.id + '">' +
                    photo + '<div class="ms-wlb-body">' +
                    '<div class="ms-wlb-name">' + w.name + '</div>' +
                    '<div class="ms-wlb-cat">' + (w.category||'') + '</div>' +
                    '<div class="ms-wlb-meta">Last seen: ' + loc + '</div>' +
                    inc + plate +
                    '<span class="ms-wlb-ribbon ' + (w.threat_level||'') + '">' + (w.threat_level||'').toUpperCase() + '</span>' +
                    '</div></div>');
            });
        },

        _renderReports: function() {
            var self = this;
            var rpc = require('web.rpc');
            rpc.query({ model:'security.incident', method:'read_group',
                args:[[],['incident_type'],['incident_type']], kwargs:{lazy:false} })
            .then(function(data) {
                var $c = self.$('.soc-rpt-by-type'); $c.empty();
                var max = Math.max.apply(null, data.map(function(d){return d.incident_type_count||0;})) || 1;
                data.sort(function(a,b){return (b.incident_type_count||0)-(a.incident_type_count||0);});
                data.forEach(function(d) {
                    var pct = Math.round(((d.incident_type_count||0)/max)*100);
                    $c.append('<div class="ms-rpt-bar-row"><div class="ms-rpt-bar-label">'+(d.incident_type||'Unknown')+'</div>' +
                        '<div class="ms-rpt-bar-track"><div class="ms-rpt-bar-fill" style="width:'+pct+'%;background:#E85426"></div></div>' +
                        '<div class="ms-rpt-bar-val">'+(d.incident_type_count||0)+'</div></div>');
                });
            });
            rpc.query({ model:'security.incident', method:'read_group',
                args:[[],['severity'],['severity']], kwargs:{lazy:false} })
            .then(function(data) {
                var $c = self.$('.soc-rpt-by-severity'); $c.empty();
                var colors = {critical:'#f85149',high:'#E85426',medium:'#d29922',low:'#3fb950'};
                var max = Math.max.apply(null, data.map(function(d){return d.severity_count||0;})) || 1;
                data.forEach(function(d) {
                    var pct = Math.round(((d.severity_count||0)/max)*100);
                    $c.append('<div class="ms-rpt-bar-row"><div class="ms-rpt-bar-label">'+(d.severity||'Unknown')+'</div>' +
                        '<div class="ms-rpt-bar-track"><div class="ms-rpt-bar-fill" style="width:'+pct+'%;background:'+(colors[d.severity]||'#7d8590')+'"></div></div>' +
                        '<div class="ms-rpt-bar-val">'+(d.severity_count||0)+'</div></div>');
                });
            });
            rpc.query({ model:'security.watchlist', method:'read_group',
                args:[[],['category'],['category']], kwargs:{lazy:false} })
            .then(function(data) {
                var $c = self.$('.soc-rpt-wl-cat'); $c.empty();
                var max = Math.max.apply(null, data.map(function(d){return d.category_count||0;})) || 1;
                data.sort(function(a,b){return (b.category_count||0)-(a.category_count||0);});
                data.forEach(function(d) {
                    var pct = Math.round(((d.category_count||0)/max)*100);
                    $c.append('<div class="ms-rpt-bar-row"><div class="ms-rpt-bar-label">'+(d.category||'Unknown')+'</div>' +
                        '<div class="ms-rpt-bar-track"><div class="ms-rpt-bar-fill" style="width:'+pct+'%;background:#58a6ff"></div></div>' +
                        '<div class="ms-rpt-bar-val">'+(d.category_count||0)+'</div></div>');
                });
            });
            rpc.query({ model:'ai.pattern.alert', method:'search_read', args:[[]],
                kwargs:{fields:['name','pattern_type','severity','title','create_date'],
                    order:'create_date desc', limit:10} })
            .then(function(data) {
                var $c = self.$('.soc-rpt-ai-alerts'); $c.empty();
                if (!data||!data.length) { $c.html('<div class="ms-soc-osint-empty">No AI alerts yet.</div>'); return; }
                var colors = {critical:'#f85149',high:'#E85426',medium:'#d29922',low:'#3fb950'};
                data.forEach(function(a) {
                    $c.append('<div class="ms-rpt-alert-row">' +
                        '<div style="width:6px;height:6px;border-radius:50%;background:'+(colors[a.severity]||'#7d8590')+';margin-top:4px;flex-shrink:0"></div>' +
                        '<div><div class="ms-rpt-alert-name">'+a.name+' — '+(a.title||'')+'</div>' +
                        '<div class="ms-rpt-alert-type">'+(a.pattern_type||'')+' · '+(a.severity||'')+'</div></div></div>');
                });
            }).catch(function() {
                self.$('.soc-rpt-ai-alerts').html('<div class="ms-soc-osint-empty">AI alerts unavailable.</div>');
            });
            self.$('.soc-rpt-access').html('<div class="ms-soc-osint-empty">Access log summary coming soon.</div>');
        },

        _onKpiClick: function(ev) {
            var model=$(ev.currentTarget).data('model');
            if (!model) return;
            this.do_action({
                type:'ir.actions.act_window',
                res_model:model,
                views:[[false,'list'],[false,'form']],
                view_mode:'list,form',
                domain:[],
                target:'current'
            });
        },
        _onFilterClick: function(ev) {
            this.$('.ms-soc-mf').removeClass('active');
            $(ev.currentTarget).addClass('active');
            this.currentFilter=$(ev.currentTarget).data('filter');
            this._applyFilter();
        },
        _onIncidentClick: function(ev) {
            var id=parseInt($(ev.currentTarget).data('id'));
            if (!id) return;
            this.do_action({
                type:'ir.actions.act_window',
                res_model:'security.incident',
                res_id:id,
                views:[[false,'form']],
                view_mode:'form',
                target:'current'
            });
        },
        _onOsintClick: function(ev) {
            var id=parseInt($(ev.currentTarget).data('id'));
            if (!id) return;
            this.do_action({
                type:'ir.actions.act_window',
                res_model:'security.osint.feed',
                res_id:id,
                views:[[false,'form']],
                view_mode:'form',
                target:'current'
            });
        },
    });

    core.action_registry.add('myservice_security_dashboard', SecurityDashboard);
    return SecurityDashboard;
});
