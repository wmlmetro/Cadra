odoo.define('myservice_asset_register.AssetDashboard', ['web.AbstractAction', 'web.core', 'web.rpc'], function (require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var rpc = require('web.rpc');

    var CONDITION_LABELS = {
        'new': 'New', 'good': 'Good', 'fair': 'Fair',
        'poor': 'Poor', 'condemned': 'Condemned', 'missing': 'Missing',
    };

    var STATE_LABELS = {
        'active': 'Active', 'in_repair': 'Under Repair',
        'disposed': 'Disposed', 'transferred': 'Transferred', 'missing': 'Missing',
    };

    var AssetDashboard = AbstractAction.extend({
        template: 'myservice_asset_register.AssetDashboard',
        hasControlPanel: false,

        start: function () {
            var self = this;
            this._mapFilter = 'all';
            this._data = {};
            return this._super.apply(this, arguments).then(function () {
                self._bindEvents();
                self._loadData();
                self._refreshTimer = setInterval(function () {
                    self._loadData();
                }, 180000);
            });
        },

        destroy: function () {
            if (this._refreshTimer) clearInterval(this._refreshTimer);
            if (this._map) { this._map.remove(); this._map = null; }
            this._super.apply(this, arguments);
        },

        _bindEvents: function () {
            var self = this;

            // Header buttons
            this.$('.ms-ar-btn-export').on('click', function () {
                self._exportAssets();
            });
            this.$('.ms-ar-btn-new').on('click', function () {
                self._openNewAsset();
            });
            this.$('.ms-ar-btn-all').on('click', function () {
                self._openAll();
            });

            // Map filter buttons
            this.$('.ms-ar-map-filter-btn').on('click', function () {
                self.$('.ms-ar-map-filter-btn').removeClass('active');
                $(this).addClass('active');
                self._mapFilter = $(this).data('filter');
                self._renderMap();
            });

            // Barcode scan
            this.$('#ar-scan-input').on('input', function () {
                self._onScan($(this).val().trim());
            });

            // KPI clicks
            this.$('.ms-ar-kpi').on('click', function () {
                var filter = $(this).data('filter');
                if (filter) self._openFiltered(filter);
            });
        },

        // ── Data loading ────────────────────────────────────────

        _loadData: function () {
            var self = this;
            $.when(
                self._loadStats(),
                self._loadCategories(),
                self._loadPmDue(),
                self._loadRecent(),
                self._loadLocations()
            ).then(function () {
                self._renderAll();
            });
        },

        _loadStats: function () {
            var self = this;
            return $.when(
                rpc.query({ model: 'nrs.asset', method: 'search_count', args: [[]] }),
                rpc.query({ model: 'nrs.asset', method: 'search_count', args: [[['state', '=', 'active']]] }),
                rpc.query({ model: 'nrs.asset', method: 'search_count', args: [[['state', '=', 'in_repair']]] }),
                rpc.query({ model: 'nrs.asset', method: 'search_count', args: [[['is_verified', '=', false]]] }),
                rpc.query({ model: 'nrs.asset', method: 'search_count', args: [[['condition', '=', 'condemned']]] }),
                rpc.query({ model: 'nrs.asset.pm', method: 'search_count', args: [[
                    ['next_due_date', '<', self._today()], ['active', '=', true]
                ]] })
            ).then(function (total, active, repair, unverified, condemned, pm_overdue) {
                self._data.stats = {
                    total: total, active: active, repair: repair,
                    unverified: unverified, condemned: condemned, pm_overdue: pm_overdue,
                };
            });
        },

        _loadCategories: function () {
            var self = this;
            return rpc.query({
                model: 'nrs.asset',
                method: 'read_group',
                domain: [],
                fields: ['category_id'],
                groupBy: ['category_id'],
                order: 'category_id_count desc',
                limit: 8,
            }).then(function (groups) {
                self._data.categories = groups.map(function (g) {
                    return { name: g.category_id ? g.category_id[1] : 'Uncategorized', count: g.category_id_count };
                });
            });
        },

        _loadPmDue: function () {
            var self = this;
            var future = self._futureDate(14);
            return rpc.query({
                model: 'nrs.asset.pm',
                method: 'search_read',
                domain: [['next_due_date', '<=', future], ['active', '=', true]],
                fields: ['asset_id', 'next_due_date', 'name'],
                order: 'next_due_date asc',
                limit: 6,
            }).then(function (pms) {
                var today = self._today();
                var soon = self._futureDate(3);
                self._data.pm_due = pms.map(function (p) {
                    return {
                        id: p.id,
                        asset_id: p.asset_id,
                        name: p.name,
                        asset_name: p.asset_id ? p.asset_id[1] : '',
                        next_due_date: p.next_due_date,
                        overdue: p.next_due_date < today,
                        soon: p.next_due_date <= soon && p.next_due_date >= today,
                    };
                });
            });
        },

        _loadRecent: function () {
            var self = this;
            return rpc.query({
                model: 'nrs.asset',
                method: 'search_read',
                domain: [],
                fields: ['name', 'asset_tag', 'asset_code', 'location_id', 'state', 'create_date'],
                order: 'create_date desc',
                limit: 5,
            }).then(function (assets) {
                self._data.recent = assets;
            });
        },

        _loadLocations: function () {
            var self = this;
            return rpc.query({
                model: 'nrs.asset',
                method: 'read_group',
                domain: [],
                fields: ['location_id'],
                groupBy: ['location_id'],
            }).then(function (locGroups) {
                var counts = {};
                var locIds = [];
                locGroups.forEach(function (g) {
                    if (g.location_id) {
                        var lid = g.location_id[0];
                        counts[lid] = { name: g.location_id[1], count: g.location_id_count };
                        locIds.push(lid);
                    }
                });
                self._data.locations = counts;

                var stateList = [];
                for (var id in counts) {
                    stateList.push(counts[id]);
                }
                stateList.sort(function (a, b) { return b.count - a.count; });
                self._data.top_locations = stateList.slice(0, 6);

                if (!locIds.length) {
                    self._data.map_points = [];
                    return;
                }
                return rpc.query({
                    model: 'generic.location',
                    method: 'search_read',
                    domain: [['id', 'in', locIds]],
                    fields: ['id', 'name', 'latitude', 'longitude', 'parent_path'],
                }).then(function (locRecs) {
                    var ancestorIds = {};
                    locRecs.forEach(function (r) {
                        if (!r.parent_path) return;
                        r.parent_path.split('/').forEach(function (s) {
                            if (s) ancestorIds[parseInt(s)] = true;
                        });
                    });
                    var ancestorList = Object.keys(ancestorIds).map(function (k) { return parseInt(k); });
                    return rpc.query({
                        model: 'generic.location',
                        method: 'search_read',
                        domain: [['id', 'in', ancestorList], '|', ['latitude', '!=', 0], ['longitude', '!=', 0]],
                        fields: ['id', 'name', 'latitude', 'longitude'],
                    }).then(function (geoRecs) {
                        var geoMap = {};
                        geoRecs.forEach(function (r) {
                            geoMap[r.id] = r;
                        });
                        var aggregated = {};
                        locRecs.forEach(function (r) {
                            var count = counts[r.id] ? counts[r.id].count : 0;
                            if (!count) return;
                            var resolved = null;
                            if ((r.latitude || r.longitude) && geoMap[r.id]) {
                                resolved = geoMap[r.id];
                            } else if (r.parent_path) {
                                var chain = r.parent_path.split('/').filter(Boolean).map(Number);
                                for (var i = chain.length - 1; i >= 0; i--) {
                                    if (geoMap[chain[i]]) { resolved = geoMap[chain[i]]; break; }
                                }
                            }
                            if (!resolved) return;
                            var key = resolved.id;
                            if (!aggregated[key]) {
                                aggregated[key] = {
                                    id: key, name: resolved.name,
                                    lat: resolved.latitude, lng: resolved.longitude, count: 0,
                                };
                            }
                            aggregated[key].count += count;
                        });
                        self._data.map_points = Object.keys(aggregated).map(function (k) { return aggregated[k]; });
                    });
                });
            });
        },

        // ── Rendering ───────────────────────────────────────────

        _renderAll: function () {
            this._renderKpis();
            this._renderCategories();
            this._renderPmDue();
            this._renderRecent();
            this._renderMap();

            var ts = new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
            this.$('#ar-last-updated').text('Last updated: ' + ts);
        },

        _renderKpis: function () {
            var s = this._data.stats || {};
            this._setVal('kpi-ar-total', s.total);
            this._setVal('kpi-ar-active', s.active);
            this._setVal('kpi-ar-repair', s.repair);
            this._setVal('kpi-ar-unverified', s.unverified);
            this._setVal('kpi-ar-condemned', s.condemned);
            this._setVal('kpi-ar-pm-overdue', s.pm_overdue);
        },

        _renderCategories: function () {
            var cats = this._data.categories || [];
            var $el = this.$('#ar-categories');
            $el.empty();

            if (!cats.length) {
                $el.html('<div class="ms-ar-empty">No categories found</div>');
                return;
            }

            var max = cats[0].count || 1;
            cats.forEach(function (c) {
                var pct = Math.round(c.count / max * 100);
                $el.append(
                    '<div class="ms-ar-cat-row">' +
                    '<div class="ms-ar-cat-label" title="' + _.escape(c.name) + '">' + _.escape(c.name) + '</div>' +
                    '<div class="ms-ar-cat-bar-track">' +
                    '<div class="ms-ar-cat-bar-fill" style="width:' + pct + '%"></div>' +
                    '</div>' +
                    '<div class="ms-ar-cat-count">' + c.count + '</div>' +
                    '</div>'
                );
            });
        },

        _renderPmDue: function () {
            var pms = this._data.pm_due || [];
            var $el = this.$('#ar-pm-list');
            $el.empty();

            if (!pms.length) {
                $el.html('<div class="ms-ar-empty">No upcoming PM schedules</div>');
                return;
            }

            pms.forEach(function (p) {
                var dotClass = p.overdue ? 'overdue' : p.soon ? 'soon' : 'upcoming';
                $el.append(
                    '<div class="ms-ar-pm-row">' +
                    '<div class="ms-ar-pm-dot ' + dotClass + '"></div>' +
                    '<div class="ms-ar-pm-name" title="' + _.escape(p.asset_name) + '">' +
                    _.escape(p.asset_name || p.name) + '</div>' +
                    '<div class="ms-ar-pm-date">' + (p.next_due_date || '') + '</div>' +
                    '</div>'
                );
            });
        },

        _renderRecent: function () {
            var self = this;
            var assets = this._data.recent || [];
            var $el = this.$('#ar-recent-list');
            $el.empty();

            if (!assets.length) {
                $el.html('<div class="ms-ar-empty">No assets registered yet</div>');
                return;
            }

            assets.forEach(function (a) {
                var loc = a.location_id ? a.location_id[1] : '';
                var stateLabel = STATE_LABELS[a.state] || a.state;
                var badgeClass = a.state || 'active';

                $el.append(
                    '<div class="ms-ar-recent-row" data-id="' + a.id + '">' +
                    '<div class="ms-ar-recent-icon">&#x2750;</div>' +
                    '<div class="ms-ar-recent-info">' +
                    '<div class="ms-ar-recent-name">' + _.escape(a.name) + '</div>' +
                    '<div class="ms-ar-recent-meta">' +
                    (a.asset_tag ? _.escape(a.asset_tag) : _.escape(a.asset_code || '')) +
                    (loc ? ' &middot; ' + _.escape(loc) : '') +
                    '</div></div>' +
                    '<span class="ms-ar-badge ' + badgeClass + '">' + _.escape(stateLabel) + '</span>' +
                    '</div>'
                );
            });

            this.$('.ms-ar-recent-row').on('click', function () {
                var id = parseInt($(this).data('id'));
                self._openAsset(id);
            });
        },

        _renderMap: function () {
            var $container = this.$('#ar-map');
            if (!$container.length) return;

            if (!window.L) {
                this._loadLeaflet();
                return;
            }
            this._initMap();
        },

        _loadLeaflet: function () {
            var self = this;
            if (!document.getElementById('leaflet-css')) {
                var link = document.createElement('link');
                link.id = 'leaflet-css';
                link.rel = 'stylesheet';
                link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
                document.head.appendChild(link);
            }
            if (!document.getElementById('leaflet-js')) {
                var script = document.createElement('script');
                script.id = 'leaflet-js';
                script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
                script.onload = function () { self._initMap(); };
                document.head.appendChild(script);
            } else if (window.L) {
                self._initMap();
            }
        },

        _initMap: function () {
            var $container = this.$('#ar-map');
            if (!$container.length || !window.L) return;

            if (this._map) { this._map.remove(); this._map = null; }

            // Center on Nigeria (Abuja)
            var map = L.map($container[0], { scrollWheelZoom: false }).setView([9.06, 7.49], 6);

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 18,
                attribution: '\u00a9 OpenStreetMap contributors',
            }).addTo(map);

            var points = this._data.map_points || [];
            var filter = this._mapFilter;

            var pinClass = '';
            if (filter === 'active') pinClass = 'active';
            else if (filter === 'repair') pinClass = 'repair';
            else if (filter === 'unverified') pinClass = 'unverified';

            var topLocs = this._data.top_locations || [];
            var $grid = this.$('#ar-state-grid');
            $grid.empty();
            topLocs.forEach(function (loc) {
                $grid.append(
                    '<div class="ms-ar-state-cell">' +
                    '<span class="ms-ar-state-label">' + _.escape(loc.name) + '</span>' +
                    '<span class="ms-ar-state-val">' + loc.count + '</span>' +
                    '</div>'
                );
            });

            var bounds = [];
            points.forEach(function (p) {
                var icon = L.divIcon({
                    className: 'ms-ar-map-pin',
                    html: '<div class="ms-ar-pin-inner ' + pinClass + '"></div>',
                    iconSize: [14, 14],
                    iconAnchor: [7, 7],
                });
                var marker = L.marker([p.lat, p.lng], { icon: icon }).addTo(map);
                marker.bindPopup(
                    '<strong>' + _.escape(p.name) + '</strong><br>Assets: <strong>' + p.count + '</strong>'
                );
                bounds.push([p.lat, p.lng]);
            });
            if (bounds.length > 1) {
                map.fitBounds(bounds, { padding: [30, 30], maxZoom: 8 });
            }

            this._map = map;
            setTimeout(function () { map.invalidateSize(); }, 300);
        },

        // ── Barcode scan ────────────────────────────────────────

        _onScan: function (val) {
            var self = this;
            if (val.length < 4) {
                this.$('#ar-scan-result').hide();
                return;
            }

            rpc.query({
                model: 'nrs.asset',
                method: 'search_read',
                domain: ['|', ['asset_tag', '=', val], ['asset_code', '=', val]],
                fields: ['name', 'asset_code', 'asset_tag', 'location_id', 'custodian_id',
                         'condition', 'last_verified_date', 'state'],
                limit: 1,
            }).then(function (assets) {
                var $result = self.$('#ar-scan-result');
                if (!assets.length) {
                    $result.html(
                        '<div class="ms-ar-scan-row"><span class="ms-ar-scan-label">No asset found</span></div>'
                    ).show();
                    self.$('#ar-scan-actions').hide();
                    return;
                }

                var a = assets[0];
                self._scanAssetId = a.id;
                var html = '';
                html += self._scanRow('Name', a.name);
                html += self._scanRow('Code', a.asset_code || '-');
                html += self._scanRow('Tag', a.asset_tag || '-');
                html += self._scanRow('Location', a.location_id ? a.location_id[1] : '-');
                html += self._scanRow('Custodian', a.custodian_id ? a.custodian_id[1] : '-');
                html += self._scanRow('Condition', CONDITION_LABELS[a.condition] || a.condition);
                html += self._scanRow('Last Verified', a.last_verified_date || 'Never');
                html += self._scanRow('Status', STATE_LABELS[a.state] || a.state);

                $result.html(html).show();
                self.$('#ar-scan-actions').show();

                // Bind action buttons
                self.$('#ar-action-open').off('click').on('click', function () { self._openAsset(a.id); });
                self.$('#ar-action-verify').off('click').on('click', function () { self._verifyAsset(a.id); });
                self.$('#ar-action-transfer').off('click').on('click', function () { self._transferAsset(a.id); });
            });
        },

        _scanRow: function (label, value) {
            return '<div class="ms-ar-scan-row">' +
                '<span class="ms-ar-scan-label">' + _.escape(label) + '</span>' +
                '<span class="ms-ar-scan-value">' + _.escape(value || '') + '</span></div>';
        },

        // ── Actions ─────────────────────────────────────────────

        _openAsset: function (id) {
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: 'nrs.asset',
                res_id: id,
                views: [[false, 'form']],
                target: 'current',
            });
        },

        _openAll: function () {
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: 'nrs.asset',
                views: [[false, 'list'], [false, 'form']],
                target: 'current',
            });
        },

        _openNewAsset: function () {
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: 'nrs.asset',
                views: [[false, 'form']],
                target: 'new',
            });
        },

        _openFiltered: function (filter) {
            var domain = [];
            if (filter === 'active') domain = [['state', '=', 'active']];
            else if (filter === 'repair') domain = [['state', '=', 'in_repair']];
            else if (filter === 'unverified') domain = [['is_verified', '=', false]];
            else if (filter === 'condemned') domain = [['condition', '=', 'condemned']];
            else if (filter === 'pm_overdue') {
                this.do_action({
                    type: 'ir.actions.act_window',
                    res_model: 'nrs.asset.pm',
                    views: [[false, 'list'], [false, 'form']],
                    domain: [['next_due_date', '<', this._today()], ['active', '=', true]],
                    target: 'current',
                });
                return;
            }

            this.do_action({
                type: 'ir.actions.act_window',
                res_model: 'nrs.asset',
                views: [[false, 'list'], [false, 'form']],
                domain: domain,
                target: 'current',
            });
        },

        _exportAssets: function () {
            // Export via standard Odoo list view
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: 'nrs.asset',
                views: [[false, 'list'], [false, 'form']],
                target: 'current',
            });
        },

        _verifyAsset: function (id) {
            var self = this;
            rpc.query({
                model: 'nrs.asset',
                method: 'write',
                args: [[id], {
                    last_verified_date: self._today(),
                    last_verified_by: odoo.session_info.uid,
                }],
            }).then(function () {
                self._onScan(self.$('#ar-scan-input').val().trim());
                self._loadData();
            });
        },

        _transferAsset: function (id) {
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: 'nrs.asset.transfer',
                views: [[false, 'form']],
                target: 'new',
                context: { default_asset_id: id },
            });
        },

        // ── Helpers ─────────────────────────────────────────────

        _today: function () {
            return new Date().toISOString().slice(0, 10);
        },

        _futureDate: function (days) {
            return new Date(Date.now() + days * 864e5).toISOString().slice(0, 10);
        },

        _setVal: function (id, val) {
            var el = document.getElementById(id);
            if (el) el.textContent = (val !== undefined && val !== null) ? val : 0;
        },
    });

    core.action_registry.add('nrs_asset_dashboard', AssetDashboard);
    return AssetDashboard;
});
