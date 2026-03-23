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
            'click .ms-soc-kpi':         '_onKpiClick',
            'click .ms-soc-mf':          '_onFilterClick',
            'click .ms-soc-inc-item':    '_onIncidentClick',
            'click .ms-soc-osint-card':  '_onOsintClick',
        },
        init: function(parent, action) {
            this._super.apply(this, arguments);
            this.map = null; this.incLayer = null; this.guardLayer = null; this.locLayer = null;
            this.kpis = {}; this.mapData = {}; this.osint = []; this.states = [];
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
                args: [[['approval_state','=','approved']]],
                kwargs: {
                    fields: ['name','threat_level','category','last_sighted'],
                    limit: 8,
                    order: 'threat_level desc',
                }
            }).then(function(entries) {
                var $list = self.$('.soc-watch-list');
                $list.empty();
                if (!entries.length) {
                    $list.append('<div style="padding:10px 12px;font-size:11px;color:#7d8590">No approved watchlist entries</div>');
                    return;
                }
                entries.forEach(function(e) {
                    var tl = e.threat_level || 'medium';
                    var initials = e.name.split(' ').map(function(w){return w[0]}).join('').substring(0,2).toUpperCase();
                    $list.append($('<div class="ms-soc-watch-item" data-id="'+e.id+'">' +
                        '<div class="ms-soc-avatar '+tl+'">'+initials+'</div>'+
                        '<div style="flex:1;min-width:0">'+
                        '<div class="ms-soc-wname">'+e.name+'</div>'+
                        '<div class="ms-soc-wmeta">'+(e.category||'')+(e.last_sighted?' • Last seen: '+e.last_sighted:'')+'</div>'+
                        '</div>'+
                        '<span class="ms-soc-tbadge '+tl+'">'+tl+'</span>'+
                        '</div>'));
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
