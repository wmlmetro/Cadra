odoo.define('myservice_dashboard.Dashboard', function (require) {
    'use strict';

    const AbstractAction = require('web.AbstractAction');
    const core = require('web.core');
    const rpc = require('web.rpc');
    const session = require('web.session');

    const LEAFLET_CSS = '/myservice_dashboard/static/lib/leaflet/leaflet.css';
    const LEAFLET_JS  = '/myservice_dashboard/static/lib/leaflet/leaflet.js';
    const CLUSTER_CSS = '/myservice_dashboard/static/lib/leaflet/MarkerCluster.css';
    const CLUSTER_DEF = '/myservice_dashboard/static/lib/leaflet/MarkerCluster.Default.css';
    const CLUSTER_JS  = '/myservice_dashboard/static/lib/leaflet/leaflet.markercluster.js';

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

        // Fleet Command + Tab styles
    if (!document.getElementById('ms-fleet-style')) {
        var fst = document.createElement('style');
        fst.id = 'ms-fleet-style';
        fst.textContent = '.ms-tab-bar{display:flex;gap:6px;padding:0 0 12px;border-bottom:2px solid #f0f0f0;margin-bottom:14px}' +
            '.ms-tab{padding:7px 18px;border-radius:20px;border:1px solid #ddd;background:#fff;cursor:pointer;font-size:13px;color:#555;transition:all .2s}' +
            '.ms-tab.active{background:#E85426;color:#fff;border-color:#E85426}' +
            '.ms-fleet-kpis{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:10px;margin-bottom:14px}' +
            '.ms-fleet-kpi{background:#fff;border-radius:8px;border:1px solid #e8e8e8;padding:12px 14px;text-align:center}' +
            '.ms-fleet-kpi.red .ms-fleet-kval{color:#dc3545}' +
            '.ms-fleet-kpi.orange .ms-fleet-kval{color:#E85426}' +
            '.ms-fleet-kpi.green .ms-fleet-kval{color:#28a745}' +
            '.ms-fleet-kpi.blue .ms-fleet-kval{color:#007bff}' +
            '.ms-fleet-kpi.gray .ms-fleet-kval{color:#555}' +
            '.ms-fleet-kval{font-size:24px;font-weight:700;line-height:1.2}' +
            '.ms-fleet-klbl{font-size:11px;color:#888;margin-top:4px}' +
            '.ms-fleet-grid{display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px}' +
            '.ms-fleet-card{background:#fff;border-radius:8px;border:1px solid #e8e8e8;padding:14px 16px;overflow:hidden}' +
            '.ms-fleet-card.wide{grid-column:span 2}' +
            '.ms-fleet-card-hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;font-size:13px;font-weight:600;color:#333}' +
            '.ms-fleet-card-sub{font-size:11px;color:#888;font-weight:400}' +
            '.ms-fleet-empty{font-size:12px;color:#aaa;padding:12px 0;text-align:center}' +
            '.ms-fleet-bar-row{display:flex;align-items:center;gap:8px;margin-bottom:7px}' +
            '.ms-fleet-bar-label{font-size:11px;color:#555;width:140px;flex-shrink:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}' +
            '.ms-fleet-bar-track{flex:1;height:8px;background:#f0f0f0;border-radius:4px;overflow:hidden}' +
            '.ms-fleet-bar-fill{height:100%;border-radius:4px;transition:width .4s ease}' +
            '.ms-fleet-bar-val{font-size:11px;color:#888;width:32px;text-align:right;flex-shrink:0}' +
            '.ms-fleet-status-row{display:flex;align-items:center;justify-content:space-between;padding:7px 0;border-bottom:1px solid #f5f5f5;font-size:12px}' +
            '.ms-fleet-status-row:last-child{border-bottom:none}' +
            '.ms-fleet-dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px}' +
            '.ms-fleet-badge{padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600}' +
            '.ms-fleet-badge-red{background:#fde8e8;color:#dc3545}' +
            '.ms-fleet-badge-orange{background:#fff3cd;color:#E85426}' +
            '.ms-fleet-badge-green{background:#e8f5e9;color:#28a745}' +
            '.ms-fleet-badge-gray{background:#f5f5f5;color:#555}' +
            '.ms-fleet-vendor-row{display:flex;align-items:center;justify-content:space-between;padding:7px 0;border-bottom:1px solid #f5f5f5;font-size:12px}' +
            '.ms-fleet-vendor-row:last-child{border-bottom:none}' +
            '.ms-fleet-maint-row{display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid #f5f5f5;font-size:12px}' +
            '.ms-fleet-maint-row:last-child{border-bottom:none}' +
            '.ms-fleet-maint-plate{font-weight:600;min-width:80px;color:#333}' +
            '.ms-fleet-maint-info{flex:1;color:#555;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
            '.ms-fleet-maint-cost{color:#E85426;font-weight:600;min-width:70px;text-align:right}' +
            '.ms-fleet-maint-date{color:#aaa;font-size:10px;min-width:70px;text-align:right}';
        document.head.appendChild(fst);
    }

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
            this.map = null; this.locationLayer = null; this.fleetLayer = null; this._fleetLoaded = false;
            this.kpis = {}; this.mapData = { locations:[], fleet:[], recent_requests:[] };
            this.currentFilter = 'all';
        },
        start: async function() {
            await this._super.apply(this, arguments);
            if (session.brand_short_name) {
                this.$('.o_brand_code').text(session.brand_short_name);
            }
            await loadLeaflet();
            this._initTabs();
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

        _showLoadingProgress: function() {
            var self = this;
            self._loadPct = 0;
            var container = document.getElementById('ms-map');
            if (container) {
                container.innerHTML = '<div id="ms-map-loader" style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:12px">' +
                    '<div style="font-size:13px;color:#888">Loading map...</div>' +
                    '<div style="width:200px;height:4px;background:#e0e0e0;border-radius:2px;overflow:hidden">' +
                    '<div id="ms-map-bar" style="height:100%;width:0%;background:#E85426;border-radius:2px;transition:width 0.3s ease"></div>' +
                    '</div>' +
                    '<div id="ms-map-pct" style="font-size:11px;color:#aaa">0%</div>' +
                    '</div>';
            }
            // Animate progress bar to show activity
            self._progressTimer = setInterval(function() {
                self._loadPct = Math.min(self._loadPct + Math.random() * 8, 85);
                var bar = document.getElementById('ms-map-bar');
                var pct = document.getElementById('ms-map-pct');
                if (bar) bar.style.width = self._loadPct.toFixed(0) + '%';
                if (pct) pct.textContent = self._loadPct.toFixed(0) + '%';
            }, 200);
        },

        _hideLoadingProgress: function() {
            if (this._progressTimer) clearInterval(this._progressTimer);
            var bar = document.getElementById('ms-map-bar');
            var pct = document.getElementById('ms-map-pct');
            var lbl = document.querySelector('#ms-map-loader > div:first-child');
            if (bar) bar.style.width = '100%';
            if (pct) pct.textContent = '100%';
            if (lbl) lbl.textContent = 'Map ready';
        },

        _initEmptyMap: function() {
            var self = this;
            var container = document.getElementById('ms-map');
            if (!container || !window.L || !window.L.map) return;
            if (container._leaflet_id) return; // already initialised
            // Clear loader
            container.innerHTML = '';
            if (!this.map) {
                if (container.clientWidth === 0 || container.clientHeight === 0) {
                    setTimeout(function(){ self._initEmptyMap(); }, 200);
                    return;
                }
                this.map = window.L.map(container, {
                    center:[9.0,8.5], zoom:6, minZoom:5,
                    maxBounds:[[3.5,2.0],[14.5,16.0]],
                    maxBoundsViscosity:0.8
                });
                window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                    {attribution:'© OpenStreetMap contributors', maxZoom:18}).addTo(this.map);
                setTimeout(function(){ if(self.map) self.map.invalidateSize(); }, 300);
            }
        },

        _renderMap: function() {
            var self = this;
            if (!window.L || !window.L.map) {
                // Leaflet not ready yet — retry in 300ms
                setTimeout(function() { self._renderMap(); }, 300);
                return;
            }
            var container = document.getElementById('ms-map');
            if (!container) return;
            if (!this.map) {
                // Container not yet sized by DOM layout — retry
                if (container.clientWidth === 0 || container.clientHeight === 0) {
                    setTimeout(function() { self._renderMap(); }, 200);
                    return;
                }
                // Guard against double init
                if (container._leaflet_id) return;
                container.innerHTML = '';
                this.map = window.L.map(container, {
                    center:[9.0,8.5], zoom:6, minZoom:5,
                    maxBounds:[[3.5,2.0],[14.5,16.0]],
                    maxBoundsViscosity:0.8
                });
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

        _initTabs: function() {
            var self = this;
            this.$('.ms-tab').on('click', function() {
                var tab = $(this).data('tab');
                self.$('.ms-tab').removeClass('active');
                $(this).addClass('active');
                self.$('.ms-tab-panel').hide();
                self.$('.ms-tab-panel[data-panel="' + tab + '"]').show();
                if (tab === 'fleet' && !self._fleetLoaded) {
                    self._loadFleetCommand();
                }
            });
        },

        _loadFleetCommand: function() {
            var self = this;
            rpc.query({ route: '/myservice/dashboard/fleet_command', params: {} })
            .then(function(d) {
                self._fleetLoaded = true;
                self._renderFleetKpis(d.kpis);
                self._renderFleetLocBars(d.by_location);
                self._renderFleetStatusList(d.by_status);
                self._renderFleetMakeBars(d.by_make);
                self._renderFleetVendors(d.vendors);
                self._renderFleetCompliance(d.compliance);
                self._renderFleetMaint(d.recent_maint);
            }).catch(function(e) {
                console.warn('Fleet command load error:', e);
            });
        },

        _renderFleetKpis: function(k) {
            if (!k) return;
            this.$('.fk-overdue').text(k.overdue || 0);
            this.$('.fk-due-soon').text(k.due_soon || 0);
            this.$('.fk-ok').text(k.ok || 0);
            this.$('.fk-idle').text(k.idle || 0);
            this.$('.fk-unassigned').text(k.unassigned || 0);
            this.$('.fk-no-location').text(k.no_location || 0);
            this.$('.fk-vendors').text(k.vendors || 0);
        },

        _renderFleetLocBars: function(locs) {
            var $c = this.$('.ms-fleet-loc-bars');
            if (!locs || !locs.length) { $c.html('<div class="ms-fleet-empty">No location data yet.</div>'); return; }
            var max = locs[0].count || 1;
            var colors = ['#E85426','#E85426','#378ADD','#378ADD','#1D9E75','#1D9E75','#1D9E75','#BA7517','#BA7517','#888'];
            var html = '';
            locs.forEach(function(l, i) {
                var pct = Math.round((l.count / max) * 100);
                html += '<div class="ms-fleet-bar-row">' +
                    '<div class="ms-fleet-bar-label" title="' + l.name + '">' + l.name + '</div>' +
                    '<div class="ms-fleet-bar-track"><div class="ms-fleet-bar-fill" style="width:' + pct + '%;background:' + (colors[i]||'#888') + '"></div></div>' +
                    '<div class="ms-fleet-bar-val">' + l.count + '</div>' +
                    '</div>';
            });
            $c.html(html);
        },

        _renderFleetStatusList: function(statuses) {
            var $c = this.$('.ms-fleet-status-list');
            if (!statuses || !statuses.length) { $c.html('<div class="ms-fleet-empty">No data.</div>'); return; }
            var total = statuses.reduce(function(a,b){ return a + b.count; }, 0) || 1;
            var html = '';
            statuses.forEach(function(s) {
                var pct = Math.round((s.count / total) * 100);
                html += '<div class="ms-fleet-status-row">' +
                    '<span><span class="ms-fleet-dot" style="background:' + s.color + '"></span>' + s.status + '</span>' +
                    '<span><strong>' + s.count + '</strong> <span style="color:#aaa;font-size:10px">(' + pct + '%)</span></span>' +
                    '</div>';
            });
            $c.html(html);
        },

        _renderFleetMakeBars: function(makes) {
            var $c = this.$('.ms-fleet-make-bars');
            if (!makes || !makes.length) { $c.html('<div class="ms-fleet-empty">No data.</div>'); return; }
            var max = makes[0].count || 1;
            var html = '';
            makes.forEach(function(m) {
                var pct = Math.round((m.count / max) * 100);
                html += '<div class="ms-fleet-bar-row">' +
                    '<div class="ms-fleet-bar-label">' + m.make + '</div>' +
                    '<div class="ms-fleet-bar-track"><div class="ms-fleet-bar-fill" style="width:' + pct + '%;background:#378ADD"></div></div>' +
                    '<div class="ms-fleet-bar-val">' + m.count + '</div>' +
                    '</div>';
            });
            $c.html(html);
        },

        _renderFleetVendors: function(vendors) {
            var $c = this.$('.ms-fleet-vendor-list');
            if (!vendors || !vendors.length) {
                $c.html('<div class="ms-fleet-empty">No approved vendors yet.<br>Add via Fleet → Vendors.</div>');
                return;
            }
            var html = '';
            vendors.forEach(function(v) {
                html += '<div class="ms-fleet-vendor-row">' +
                    '<div>' +
                    '<div style="font-weight:600;color:#333;font-size:12px">' + v.name + '</div>' +
                    '<div style="font-size:10px;color:#888">' + (v.specialisation||'General') + (v.state ? ' · ' + v.state : '') + '</div>' +
                    '</div>' +
                    '<span class="ms-fleet-badge ms-fleet-badge-green">Approved</span>' +
                    '</div>';
            });
            $c.html(html);
        },

        _renderFleetCompliance: function(items) {
            var $c = this.$('.ms-fleet-compliance-list');
            if (!items || !items.length) {
                $c.html('<div class="ms-fleet-empty" style="color:#28a745">No compliance alerts.</div>');
                return;
            }
            var html = '';
            items.forEach(function(c) {
                var cls = c.level === 'critical' ? 'ms-fleet-badge-red' : 'ms-fleet-badge-orange';
                html += '<div class="ms-fleet-status-row">' +
                    '<span style="font-size:12px">' + c.type + '</span>' +
                    '<span class="ms-fleet-badge ' + cls + '">' + c.count + ' vehicles</span>' +
                    '</div>';
            });
            $c.html(html);
        },

        _renderFleetMaint: function(logs) {
            var $c = this.$('.ms-fleet-maint-list');
            if (!logs || !logs.length) {
                $c.html('<div class="ms-fleet-empty">No maintenance records yet.</div>');
                return;
            }
            var html = '';
            logs.forEach(function(l) {
                var cost = l.cost ? '₦' + Number(l.cost).toLocaleString() : '—';
                html += '<div class="ms-fleet-maint-row">' +
                    '<div class="ms-fleet-maint-plate">' + (l.plate||l.vehicle||'—') + '</div>' +
                    '<div class="ms-fleet-maint-info">' + (l.service||'Service') +
                    (l.vendor ? ' · ' + l.vendor : '') +
                    (l.location ? ' · ' + l.location : '') + '</div>' +
                    '<div class="ms-fleet-maint-cost">' + cost + '</div>' +
                    '<div class="ms-fleet-maint-date">' + (l.date||'') + '</div>' +
                    '</div>';
            });
            $c.html(html);
        },

        _onKpiClick: function(ev) {
            var $c=$(ev.currentTarget), model=$c.data('model'), domain=$c.data('domain')||'[]';
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
            this.$('.ms-filter-btn').removeClass('active');
            $(ev.currentTarget).addClass('active');
            this.currentFilter=$(ev.currentTarget).data('filter');
            this._updateLayerVisibility();
        },
        _onRequestClick: function(ev) {
            var id=parseInt($(ev.currentTarget).data('id'));
            this.do_action({
                type:'ir.actions.act_window',
                res_model:'request.request',
                res_id:id,
                views:[[false,'form']],
                view_mode:'form',
                target:'current'
            });
        },
    });

    core.action_registry.add('myservice_dashboard', MyServiceDashboard);
    return MyServiceDashboard;
});
