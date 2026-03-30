odoo.define('myservice_fleet_maintenance.FleetDashboard', function (require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var ajax = require('web.ajax');

    var MAINT_BADGE = {
        ok:          { label: 'OK',          bg: '#ECFDF5', fg: '#065F46' },
        due_soon:    { label: 'Due Soon',    bg: '#FFFBEB', fg: '#92400E' },
        overdue:     { label: 'Overdue',     bg: '#FEF2F2', fg: '#991B1B' },
        no_schedule: { label: 'No Schedule', bg: '#F3F4F6', fg: '#6B7280' },
    };

    function maintBadge(status) {
        var cfg = MAINT_BADGE[status] || MAINT_BADGE.no_schedule;
        return '<span class="flt-badge" style="background:' + cfg.bg +
               ';color:' + cfg.fg + '">' + cfg.label + '</span>';
    }

    function fmtDate(d) { return d ? d.substring(0, 10) : '\u2014'; }
    function fmtOdo(v) { return v ? v.toLocaleString() + ' km' : '\u2014'; }

    var FleetDashboard = AbstractAction.extend({
        template: 'myservice_fleet_maintenance.FleetDashboard',
        hasControlPanel: false,

        start: function () {
            var self = this;
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

        _bindEvents: function () {
            var self = this;
            this.$('.flt-refresh').on('click', function () {
                self._loadData();
            });
        },

        _loadData: function () {
            var self = this;
            this.$('.flt-loading').show();
            ajax.jsonRpc('/myservice/fleet_dashboard/data', 'call', {})
                .then(function (data) {
                    self._data = data;
                    self._renderKpis(data.kpis || {});
                    self._renderStatePills(data.state_counts || {});
                    self._renderVehicleTable(data.vehicles || []);
                    self._renderMaintenanceTable(data.maintenance || []);
                    self._renderMap();
                    self.$('.flt-loading').hide();
                    var now = new Date();
                    self.$('#flt-timestamp').text(
                        now.toLocaleTimeString('en-GB',
                            { hour: '2-digit', minute: '2-digit' }) +
                        '  |  ' + (data.kpis.total || 0) + ' vehicles registered'
                    );
                })
                .catch(function (err) {
                    console.error('Fleet dashboard error:', err);
                    self.$('.flt-loading').hide();
                    self.$('#flt-vehicle-body, #flt-maint-body').html(
                        '<tr><td colspan="7" class="flt-empty">' +
                        'Unable to load fleet data</td></tr>');
                });
        },

        // ── KPI cards ────────────────────────────────────────────────
        _renderKpis: function (k) {
            var kpis = [
                { id: 'total',     label: 'TOTAL FLEET',         val: k.total || 0,     color: '#1A1A1A' },
                { id: 'active',    label: 'ACTIVE',              val: k.active || 0,    color: '#059669' },
                { id: 'ok',        label: 'SERVICE OK',          val: k.ok || 0,        color: '#2563EB' },
                { id: 'due_soon',  label: 'MAINTENANCE DUE',     val: k.due_soon || 0,  color: '#D97706' },
                { id: 'overdue',   label: 'OVERDUE',             val: k.overdue || 0,   color: '#C8102E' },
                { id: 'docs',      label: 'DOCS EXPIRING',       val: (k.expiring_insurance || 0) + (k.expiring_roadworthy || 0), color: '#7C3AED' },
                { id: 'vendors',   label: 'SERVICE VENDORS',     val: k.vendors || 0,   color: '#0891B2' },
            ];
            var html = '';
            kpis.forEach(function (kpi) {
                html += '<div class="flt-kpi">' +
                    '<div class="flt-kpi-label">' + kpi.label + '</div>' +
                    '<div class="flt-kpi-value" style="color:' + kpi.color + '">' +
                    kpi.val + '</div></div>';
            });
            this.$('#flt-kpi-row').html(html);
        },

        // ── State pills ─────────────────────────────────────────────
        _renderStatePills: function (counts) {
            var html = '';
            var keys = Object.keys(counts).sort();
            if (!keys.length) {
                html = '<span style="color:#9CA3AF">No vehicles found</span>';
            }
            keys.forEach(function (state) {
                html += '<span class="flt-state-pill">' + state +
                    ': <strong>' + counts[state] + '</strong></span>';
            });
            this.$('#flt-state-bar').html(html);
        },

        // ── Vehicle register table ──────────────────────────────────
        _renderVehicleTable: function (vehicles) {
            var self = this;
            this.$('#flt-vehicle-count').text(vehicles.length + ' vehicles');
            if (!vehicles.length) {
                this.$('#flt-vehicle-body').html(
                    '<tr><td colspan="7" class="flt-empty">' +
                    'No vehicles registered. Add vehicles via Fleet menu.</td></tr>');
                return;
            }
            var html = '';
            vehicles.forEach(function (v) {
                html += '<tr class="flt-row" data-id="' + v.id + '">' +
                    '<td class="flt-name">' +
                        (v.brand ? v.brand + ' ' : '') + v.model +
                        (v.is_staff_bus ? ' <span class="flt-bus-tag">BUS</span>' : '') +
                    '</td>' +
                    '<td><span class="flt-plate">' + (v.license || '\u2014') + '</span></td>' +
                    '<td>' + (v.driver || '\u2014') + '</td>' +
                    '<td>' + (v.location || '\u2014') + '</td>' +
                    '<td>' + maintBadge(v.maint_status) + '</td>' +
                    '<td>' + fmtDate(v.next_service) + '</td>' +
                    '<td>' + (v.fuel_type || '\u2014') + '</td>' +
                    '</tr>';
            });
            this.$('#flt-vehicle-body').html(html);

            // Row click → open vehicle form
            this.$('#flt-vehicle-body .flt-row').on('click', function () {
                var id = parseInt($(this).data('id'));
                if (id) {
                    self.do_action({
                        type: 'ir.actions.act_window',
                        res_model: 'fleet.vehicle',
                        res_id: id,
                        views: [[false, 'form']],
                        target: 'current',
                    });
                }
            });
        },

        // ── Maintenance schedule table ──────────────────────────────
        _renderMaintenanceTable: function (maint) {
            var self = this;
            var overdueCount = 0;
            maint.forEach(function (m) {
                if (m.status === 'overdue') overdueCount++;
            });
            this.$('#flt-maint-overdue').text(overdueCount + ' overdue')
                .css('color', overdueCount > 0 ? '#C8102E' : '#059669');

            if (!maint.length) {
                this.$('#flt-maint-body').html(
                    '<tr><td colspan="6" class="flt-empty">' +
                    'No pending maintenance.</td></tr>');
                return;
            }
            var html = '';
            maint.forEach(function (m) {
                html += '<tr class="flt-row' +
                    (m.status === 'overdue' ? ' flt-overdue' : '') +
                    '" data-id="' + m.id + '">' +
                    '<td class="flt-name">' + m.name + '</td>' +
                    '<td><span class="flt-plate">' + (m.license || '\u2014') + '</span></td>' +
                    '<td>' + maintBadge(m.status) + '</td>' +
                    '<td style="font-weight:' +
                        (m.status === 'overdue' ? '600' : '400') + '">' +
                        fmtDate(m.next_service) + '</td>' +
                    '<td>' + fmtOdo(m.next_odo) + '</td>' +
                    '<td>' + (m.vendor || '\u2014') + '</td>' +
                    '</tr>';
            });
            this.$('#flt-maint-body').html(html);

            this.$('#flt-maint-body .flt-row').on('click', function () {
                var id = parseInt($(this).data('id'));
                if (id) {
                    self.do_action({
                        type: 'ir.actions.act_window',
                        res_model: 'fleet.vehicle',
                        res_id: id,
                        views: [[false, 'form']],
                        target: 'current',
                    });
                }
            });
        },

        // ── Leaflet map ─────────────────────────────────────────────
        _renderMap: function () {
            if (this._map) return;   // only init once
            var el = this.$('#fleet-map')[0];
            if (!el) return;

            if (typeof L === 'undefined') {
                var self = this;
                var link = document.createElement('link');
                link.rel = 'stylesheet';
                link.href = '/myservice_security/static/lib/leaflet/leaflet.css';
                document.head.appendChild(link);
                var script = document.createElement('script');
                script.src = '/myservice_security/static/lib/leaflet/leaflet.js';
                script.onload = function () { self._initMap(el); };
                document.body.appendChild(script);
            } else {
                this._initMap(el);
            }
        },

        _initMap: function (el) {
            try {
                this._map = L.map(el, {
                    center: [9.06, 7.50],
                    zoom: 6,
                    zoomControl: true,
                    scrollWheelZoom: false,
                });

                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    attribution: '\u00a9 OpenStreetMap',
                    maxZoom: 18,
                }).addTo(this._map);

                var redIcon = L.divIcon({
                    className: '',
                    html: '<div style="width:12px;height:12px;background:#C8102E;' +
                          'border-radius:50%;border:2px solid #fff;' +
                          'box-shadow:0 1px 4px rgba(0,0,0,.3);"></div>',
                    iconSize: [12, 12],
                    iconAnchor: [6, 6],
                });

                var offices = [
                    { name: 'FCT HQ \u2014 Abuja',    lat: 9.0579,  lng: 7.4951 },
                    { name: 'Lagos Island MSTO',       lat: 6.4541,  lng: 3.3947 },
                    { name: 'Port Harcourt MSTO',      lat: 4.8156,  lng: 7.0498 },
                    { name: 'Kano MSTO',               lat: 12.0022, lng: 8.5920 },
                    { name: 'Enugu MSTO',              lat: 6.4584,  lng: 7.5464 },
                    { name: 'Ibadan MSTO',             lat: 7.3775,  lng: 3.9470 },
                    { name: 'Kaduna MSTO',             lat: 10.5222, lng: 7.4383 },
                    { name: 'Benin City MSTO',         lat: 6.3350,  lng: 5.6037 },
                    { name: 'Uyo MSTO',               lat: 5.0510,  lng: 7.9328 },
                ];

                var map = this._map;
                offices.forEach(function (o) {
                    L.marker([o.lat, o.lng], { icon: redIcon })
                     .addTo(map)
                     .bindPopup('<strong>' + o.name + '</strong>');
                });

                setTimeout(function () { map.invalidateSize(); }, 300);
            } catch (e) {
                console.error('Fleet map init error:', e);
            }
        },
    });

    core.action_registry.add('myservice_fleet_dashboard', FleetDashboard);
    return FleetDashboard;
});
