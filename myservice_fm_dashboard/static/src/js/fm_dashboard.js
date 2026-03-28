odoo.define('myservice_fm_dashboard.FMDashboard', function (require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var ajax = require('web.ajax');

    var STAGE_CLASS = {
        'Draft':          'stage-draft',
        'New':            'stage-new',
        'Classification': 'stage-classification',
        'Progress':       'stage-progress',
        'Done':           'stage-done',
        'Rejected':       'stage-rejected',
    };

    var PRIO_CONFIG = {
        '0': { label: 'Normal',   color: '#6A737D' },
        '1': { label: 'Low',      color: '#15803D' },
        '2': { label: 'High',     color: '#B45309' },
        '3': { label: 'Critical', color: '#C8102E' },
    };

    var FMDashboard = AbstractAction.extend({
        template: 'myservice_fm_dashboard.FMDashboard',
        hasControlPanel: false,

        start: function () {
            var self = this;
            this._stageFilter = 'all';
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
            if (this._map) {
                this._map.remove();
                this._map = null;
            }
            this._super.apply(this, arguments);
        },

        refresh: function () {
            this._loadData();
        },

        _bindEvents: function () {
            var self = this;
            this.$('.ms-fm-tab-btn').on('click', function () {
                self.$('.ms-fm-tab-btn').removeClass('active');
                $(this).addClass('active');
                self._stageFilter = $(this).data('stage');
                self._renderRequestList();
            });
        },

        _loadData: function () {
            var self = this;
            ajax.jsonRpc('/myservice/fm_dashboard/data', 'call', {}).then(function (data) {
                self._data = data;
                self._renderKpis();
                self._renderSlaTable();
                self._renderRequestList();
                self._renderTeamWorkload();
                self._renderOverdue();
                self._renderMap();

                var now = new Date();
                var ts = now.toLocaleTimeString('en-GB', {hour: '2-digit', minute: '2-digit'});
                var el = self.$('#fm-last-updated');
                if (el.length) {
                    el.text('Last updated: ' + ts + ' \u2014 ' + (data.kpis.open || 0) + ' open requests');
                }
            }).guardedCatch(function (err) {
                console.error('FM Dashboard load error:', err);
            });
        },

        _renderKpis: function () {
            var k = this._data.kpis || {};
            var set = function (id, val) {
                var el = document.getElementById(id);
                if (el) el.textContent = val;
            };
            set('kpi-total-open', k.open || 0);
            set('kpi-overdue', k.overdue || 0);
            set('kpi-escalated', k.escalated || 0);
            set('kpi-in-progress', k.in_progress || 0);
            set('kpi-resolved-today', k.resolved_today || 0);
            set('overdue-badge', k.overdue || 0);
        },

        _renderSlaTable: function () {
            var rows = this._data.sla_data || [];
            var $el = this.$('#fm-sla-table');
            $el.empty();

            var html = '<table class="ms-fm-sla-table">';
            html += '<tr><th>Domain</th><th>Open</th><th>Overdue</th><th>Escalated</th><th>SLA</th></tr>';

            rows.forEach(function (row) {
                var slaClass = row.sla_pct >= 90 ? 'ok' : row.sla_pct >= 70 ? 'warn' : 'breach';
                html += '<tr>' +
                    '<td><strong>' + row.domain + '</strong></td>' +
                    '<td>' + row.open + '</td>' +
                    '<td>' + (row.overdue ? '<span class="ms-fm-val-red">' + row.overdue + '</span>' : '0') + '</td>' +
                    '<td>' + (row.escalated ? '<span class="ms-fm-val-amber">' + row.escalated + '</span>' : '0') + '</td>' +
                    '<td><span class="ms-fm-sla-pill ' + slaClass + '">' + row.sla_pct + '%</span></td>' +
                    '</tr>';
            });
            html += '</table>';
            $el.html(html);
        },

        _renderRequestList: function () {
            var self = this;
            var reqs = this._data.recent_requests || [];
            var filter = this._stageFilter;

            var filtered = reqs.filter(function (r) {
                if (filter === 'all') return true;
                if (filter === 'Overdue') return r.is_overdue;
                return r.stage === filter;
            });

            var $list = this.$('#fm-request-list');
            $list.empty();

            if (!filtered.length) {
                $list.html('<div class="ms-fm-empty">No requests found.</div>');
                return;
            }

            filtered.slice(0, 30).forEach(function (r) {
                var stageClass = STAGE_CLASS[r.stage] || '';
                var prioColor = (PRIO_CONFIG[r.priority] || PRIO_CONFIG['0']).color;
                var deadline = r.deadline ? r.deadline.substring(0, 10) : '';

                $list.append(
                    '<div class="ms-fm-req-item" data-id="' + r.id + '">' +
                    '<div class="ms-fm-req-dot" style="background:' + prioColor + '"></div>' +
                    '<div style="flex:1;min-width:0">' +
                    '<div class="ms-fm-req-name">' + _.escape(r.name) +
                    (r.is_overdue ? ' <span class="ms-fm-overdue-tag">OVERDUE</span>' : '') +
                    '</div>' +
                    '<div class="ms-fm-req-meta">' + _.escape(r.category || 'General') +
                    (r.location ? ' \u00b7 ' + _.escape(r.location) : '') +
                    (deadline ? ' \u00b7 Due: ' + deadline : '') +
                    '</div></div>' +
                    '<span class="ms-fm-req-stage ' + stageClass + '">' + _.escape(r.stage) + '</span>' +
                    '</div>'
                );
            });

            this.$('.ms-fm-req-item').on('click', function () {
                var id = parseInt($(this).data('id'));
                self.do_action({
                    type: 'ir.actions.act_window',
                    res_model: 'request.request',
                    res_id: id,
                    views: [[false, 'form']],
                    target: 'current',
                });
            });
        },

        _renderTeamWorkload: function () {
            var items = this._data.team_workload || [];
            var $el = this.$('#fm-team-workload');
            $el.empty();

            if (!items.length) {
                $el.html('<div class="ms-fm-empty">No open requests.</div>');
                return;
            }

            var max = items[0].count || 1;
            items.forEach(function (item) {
                var pct = Math.round(item.count / max * 100);
                $el.append(
                    '<div class="ms-fm-team-row">' +
                    '<div class="ms-fm-team-name" title="' + _.escape(item.name) + '">' + _.escape(item.name) + '</div>' +
                    '<div class="ms-fm-team-bar-track">' +
                    '<div class="ms-fm-team-bar-fill" style="width:' + pct + '%;background:#C8102E"></div>' +
                    '</div>' +
                    '<div class="ms-fm-team-count">' + item.count + '</div>' +
                    '</div>'
                );
            });
        },

        _renderOverdue: function () {
            var items = this._data.overdue_list || [];
            var $el = this.$('#fm-overdue-list');
            $el.empty();

            if (!items.length) {
                $el.html('<div class="ms-fm-empty ms-fm-empty-ok">No overdue requests</div>');
                return;
            }

            items.slice(0, 10).forEach(function (r) {
                $el.append(
                    '<div class="ms-fm-overdue-item">' +
                    '<div class="ms-fm-overdue-name">' + _.escape(r.name) + '</div>' +
                    '<div class="ms-fm-overdue-meta">' +
                    _.escape(r.category || 'General') + ' \u00b7 ' +
                    r.days_overdue + ' day(s) overdue \u00b7 Due: ' + r.deadline +
                    '</div></div>'
                );
            });

            if (items.length > 10) {
                $el.append('<div class="ms-fm-more">+ ' + (items.length - 10) + ' more overdue</div>');
            }
        },

        _renderMap: function () {
            var locations = this._data.map_locations || [];
            var $container = this.$('#fm-map');
            if (!$container.length) return;

            if (!window.L) {
                this._loadLeaflet(locations);
                return;
            }
            this._initMap(locations);
        },

        _loadLeaflet: function (locations) {
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
                script.onload = function () {
                    self._initMap(locations);
                };
                document.head.appendChild(script);
            }
        },

        _initMap: function (locations) {
            var $container = this.$('#fm-map');
            if (!$container.length || !window.L) return;

            if (this._map) {
                this._map.remove();
                this._map = null;
            }

            var map = L.map($container[0], {
                scrollWheelZoom: false,
            }).setView([55.945, -3.19], 13);

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 18,
                attribution: '\u00a9 OpenStreetMap contributors',
            }).addTo(map);

            var redIcon = L.divIcon({
                className: 'ms-fm-map-pin',
                html: '<div class="ms-fm-pin-inner"></div>',
                iconSize: [14, 14],
                iconAnchor: [7, 7],
            });

            locations.forEach(function (loc) {
                var marker = L.marker([loc.lat, loc.lng], {icon: redIcon}).addTo(map);
                marker.bindPopup(
                    '<strong>' + loc.name + '</strong><br>' +
                    'Open requests: <strong>' + loc.request_count + '</strong>'
                );
            });

            this._map = map;
            setTimeout(function () { map.invalidateSize(); }, 300);
        },
    });

    core.action_registry.add('myservice_fm_dashboard', FMDashboard);
    return FMDashboard;
});
