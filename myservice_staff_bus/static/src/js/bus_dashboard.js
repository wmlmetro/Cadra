odoo.define('myservice_staff_bus.BusDashboard', function(require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var rpc = require('web.rpc');

    var L_CSS = '/myservice_staff_bus/static/lib/leaflet/leaflet.css';
    var L_JS  = '/myservice_staff_bus/static/lib/leaflet/leaflet.js';

    var STATE_COLOR = {
        scheduled: '#888',
        boarding:  '#007bff',
        departed:  '#E85426',
        completed: '#28a745',
        cancelled: '#ccc',
    };

    var BusDashboard = AbstractAction.extend({
        template: 'myservice_staff_bus.BusDashboard',
        hasControlPanel: true,

        start: function() {
            var self = this;
            return this._super.apply(this, arguments).then(function() {
                self._loadLeaflet(function() {
                    self._initMap();
                });
                self._loadData();
                self._refreshTimer = setInterval(function() {
                    self._loadData();
                }, 120000); // refresh every 2 minutes
            });
        },

        destroy: function() {
            if (this._refreshTimer) clearInterval(this._refreshTimer);
            this._super.apply(this, arguments);
        },

        refresh: function() {
            this._loadData();
            if (this.map) {
                this.map.invalidateSize();
            }
        },

        // ── Leaflet loader ──────────────────────────────────────
        _loadLeaflet: function(cb) {
            var self = this;
            if (window.L && window.L.map) { cb(); return; }
            var link = document.createElement('link');
            link.rel = 'stylesheet'; link.href = L_CSS;
            document.head.appendChild(link);
            var script = document.createElement('script');
            script.src = L_JS;
            script.onload = function() { cb(); };
            document.head.appendChild(script);
        },

        // ── Map init ────────────────────────────────────────────
        _initMap: function() {
            var self = this;
            var container = document.getElementById('ms-bus-map');
            if (!container || !window.L) return;
            container.innerHTML = '';
            if (this.map) {
                try { this.map.remove(); } catch(e) {}
                this.map = null;
            }
            this.map = window.L.map('ms-bus-map', {
                center: [9.0, 8.5], zoom: 6, minZoom: 6, maxZoom: 12,
                maxBounds: [[4.0, 2.5], [14.0, 15.5]],
                maxBoundsViscosity: 1.0,
            });
            this.map.fitBounds([[4.0, 2.5], [14.0, 15.5]]);
            window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap contributors', maxZoom: 18,
            }).addTo(this.map);
            setTimeout(function() {
                if (self.map) self.map.invalidateSize();
            }, 200);
            // Filter buttons
            var self2 = this;
            this.$('.ms-bus-filter-btn').off('click').on('click', function() {
                self2.$('.ms-bus-filter-btn').removeClass('active');
                $(this).addClass('active');
                self2._renderMapMarkers($(this).data('filter'));
            });
        },

        // ── Load all data ───────────────────────────────────────
        _loadData: function() {
            var self = this;
            var today = new Date().toISOString().split('T')[0];

            // Today's schedules
            rpc.query({
                model: 'bus.schedule',
                method: 'search_read',
                args: [[['date', '=', today]]],
                kwargs: {
                    fields: ['name', 'route_id', 'vehicle_id', 'driver_id',
                             'departure_time', 'capacity', 'booked_seats',
                             'occupancy_pct', 'state', 'direction'],
                    order: 'departure_time asc',
                    limit: 50,
                }
            }).then(function(schedules) {
                self._schedules = schedules || [];
                self._renderSchedules();
                self._renderKpis();
                self._renderMapMarkers('all');
            });

            // Compliance — buses expiring soon or expired
            rpc.query({
                model: 'fleet.vehicle',
                method: 'search_read',
                args: [[['is_staff_bus', '=', true]]],
                kwargs: {
                    fields: ['name', 'license_plate', 'is_roadworthy',
                             'is_insured', 'roadworthy_expiry', 'insurance_expiry',
                             'current_route_id', 'home_location_id'],
                    limit: 200,
                }
            }).then(function(buses) {
                self._buses = buses || [];
                // Fetch GPS coords for all home locations
                var locIds = [];
                (buses || []).forEach(function(b) {
                    if (b.home_location_id && b.home_location_id[0]) {
                        locIds.push(b.home_location_id[0]);
                    }
                });
                if (locIds.length) {
                    rpc.query({
                        model: 'generic.location',
                        method: 'search_read',
                        args: [[['id', 'in', locIds]]],
                        kwargs: { fields: ['id', 'latitude', 'longitude'], limit: 500 }
                    }).then(function(locs) {
                        var locMap = {};
                        (locs || []).forEach(function(l) { locMap[l.id] = l; });
                        self._buses.forEach(function(b) {
                            if (b.home_location_id && locMap[b.home_location_id[0]]) {
                                var l = locMap[b.home_location_id[0]];
                                b.home_lat = l.latitude;
                                b.home_lng = l.longitude;
                            }
                        });
                        self._renderCompliance();
                        self._renderKpis();
                        self._renderMapMarkers('all');
                    });
                } else {
                    self._renderCompliance();
                    self._renderKpis();
                }
            });

            // Fuel MTD
            var firstOfMonth = today.substring(0, 8) + '01';
            rpc.query({
                model: 'bus.fuel.log',
                method: 'search_read',
                args: [[['date', '>=', firstOfMonth], ['state', '=', 'approved']]],
                kwargs: {
                    fields: ['vehicle_id', 'total_cost', 'litres', 'date'],
                    limit: 500,
                }
            }).then(function(fuels) {
                self._fuels = fuels || [];
                self._renderFuel();
                self._renderKpis();
            });

            // Active routes
            rpc.query({
                model: 'bus.route',
                method: 'search_read',
                args: [[['state', '=', 'active']]],
                kwargs: {
                    fields: ['name', 'code', 'direction', 'stop_ids'],
                    limit: 100,
                }
            }).then(function(routes) {
                self._routes = routes || [];
                self._renderKpis();
            });
        },

        // ── KPIs ────────────────────────────────────────────────
        _renderKpis: function() {
            var schedules = this._schedules || [];
            var buses = this._buses || [];
            var fuels = this._fuels || [];
            var routes = this._routes || [];

            var activeBuses = schedules.filter(function(s) {
                return s.state !== 'cancelled' && s.state !== 'completed';
            }).length;
            var totalBooked = schedules.reduce(function(acc, s) {
                return acc + (s.booked_seats || 0);
            }, 0);
            var fuelMtd = fuels.reduce(function(acc, f) {
                return acc + (f.total_cost || 0);
            }, 0);
            var complianceIssues = buses.filter(function(b) {
                return !b.is_roadworthy || !b.is_insured;
            }).length;

            var el = function(id) { return document.getElementById(id); };
            if (el('kpi-buses-active')) el('kpi-buses-active').textContent = activeBuses;
            if (el('kpi-seats-booked')) el('kpi-seats-booked').textContent = totalBooked;
            if (el('kpi-routes-active')) el('kpi-routes-active').textContent = routes.length;
            if (el('kpi-fuel-mtd')) el('kpi-fuel-mtd').textContent = '₦' + Math.round(fuelMtd).toLocaleString();
            if (el('kpi-compliance')) el('kpi-compliance').textContent = complianceIssues;
            if (el('sched-count')) el('sched-count').textContent = schedules.filter(function(s) { return s.state !== 'cancelled'; }).length;
            if (el('compliance-count')) el('compliance-count').textContent = complianceIssues;
        },

        // ── Schedules list ──────────────────────────────────────
        _renderSchedules: function() {
            var schedules = this._schedules || [];
            var $list = this.$('#ms-bus-sched-list');
            $list.empty();
            if (!schedules.length) {
                $list.html('<div class="ms-bus-empty">No schedules for today.</div>');
                return;
            }
            var active = schedules.filter(function(s) { return s.state !== 'cancelled'; });
            active.forEach(function(s) {
                var color = STATE_COLOR[s.state] || '#888';
                var occ = Math.round(s.occupancy_pct || 0);
                var occClass = occ >= 90 ? 'high' : occ >= 60 ? 'med' : '';
                var h = Math.floor(s.departure_time || 0);
                var m = Math.round(((s.departure_time || 0) - h) * 60);
                var time = ('0' + h).slice(-2) + ':' + ('0' + m).slice(-2);
                var dir = s.direction === 'morning' ? '→ Office' :
                          s.direction === 'evening' ? '← Home' : '↔';
                $list.append(
                    '<div class="ms-bus-sched-item">' +
                    '<div class="ms-bus-sched-dot" style="background:' + color + '"></div>' +
                    '<div class="ms-bus-sched-info">' +
                    '<div class="ms-bus-sched-route">' + (s.route_id ? s.route_id[1] : '—') + '</div>' +
                    '<div class="ms-bus-sched-meta">' + time + ' ' + dir +
                    (s.vehicle_id ? ' · ' + s.vehicle_id[1] : '') + '</div>' +
                    '</div>' +
                    '<div>' +
                    '<div class="ms-bus-occ-bar"><div class="ms-bus-occ-fill ' + occClass + '" style="width:' + occ + '%"></div></div>' +
                    '<div style="font-size:10px;color:#888;text-align:right;margin-top:2px">' + (s.booked_seats || 0) + '/' + (s.capacity || 0) + '</div>' +
                    '</div>' +
                    '</div>'
                );
            });
        },

        // ── Compliance list ─────────────────────────────────────
        _renderCompliance: function() {
            var buses = this._buses || [];
            var $list = this.$('#ms-bus-compliance-list');
            $list.empty();
            var issues = buses.filter(function(b) {
                return !b.is_roadworthy || !b.is_insured;
            });
            if (!issues.length) {
                $list.html('<div class="ms-bus-empty" style="color:#28a745">✓ All buses compliant</div>');
                return;
            }
            issues.slice(0, 10).forEach(function(b) {
                var problems = [];
                if (!b.is_roadworthy) problems.push('Roadworthiness expired');
                if (!b.is_insured) problems.push('Insurance expired');
                $list.append(
                    '<div class="ms-bus-alert-item">' +
                    '<div class="ms-bus-alert-dot" style="background:#E85426"></div>' +
                    '<div class="ms-bus-alert-name">' + (b.license_plate || b.name) + '</div>' +
                    '<div class="ms-bus-alert-issue">' + problems.join(', ') + '</div>' +
                    '</div>'
                );
            });
        },

        // ── Fuel summary ────────────────────────────────────────
        _renderFuel: function() {
            var fuels = this._fuels || [];
            var $list = this.$('#ms-bus-fuel-list');
            $list.empty();
            if (!fuels.length) {
                $list.html('<div class="ms-bus-empty">No fuel logs this month.</div>');
                return;
            }
            // Group by vehicle
            var byVehicle = {};
            fuels.forEach(function(f) {
                var key = f.vehicle_id ? f.vehicle_id[0] : 0;
                var name = f.vehicle_id ? f.vehicle_id[1] : 'Unknown';
                if (!byVehicle[key]) byVehicle[key] = { name: name, total: 0, litres: 0, fills: 0 };
                byVehicle[key].total += f.total_cost || 0;
                byVehicle[key].litres += f.litres || 0;
                byVehicle[key].fills++;
            });
            var sorted = Object.values(byVehicle).sort(function(a, b) { return b.total - a.total; });
            sorted.slice(0, 8).forEach(function(v) {
                $list.append(
                    '<div class="ms-bus-alert-item">' +
                    '<div class="ms-bus-alert-dot" style="background:#007bff"></div>' +
                    '<div class="ms-bus-alert-name">' + v.name + '</div>' +
                    '<div class="ms-bus-alert-issue">₦' + Math.round(v.total).toLocaleString() +
                    ' · ' + Math.round(v.litres) + 'L</div>' +
                    '</div>'
                );
            });
            var total = sorted.reduce(function(a, v) { return a + v.total; }, 0);
            $list.append(
                '<div style="padding:8px 14px;font-size:11px;font-weight:600;color:#1A1A1A;border-top:1px solid #eee">' +
                'Total: ₦' + Math.round(total).toLocaleString() + '</div>'
            );
        },

        // ── Map markers ─────────────────────────────────────────
        _renderMapMarkers: function(filter) {
            if (!this.map || !window.L) return;
            if (this._busLayer) this.map.removeLayer(this._busLayer);
            this._busLayer = window.L.layerGroup();

            var buses = this._buses || [];
            var schedules = this._schedules || [];

            buses.forEach(function(b) {
                // Use real GPS from home_location_id
                var lat = b.home_lat || 0;
                var lng = b.home_lng || 0;
                if (!lat || !lng) return;

                var active = schedules.some(function(s) {
                    return s.vehicle_id && s.vehicle_id[0] === b.id &&
                           s.state !== 'cancelled' && s.state !== 'completed';
                });
                if (filter === 'active' && !active) return;

                var color = active ? '#E85426' : '#888';
                var icon = window.L.divIcon({
                    html: '<div style="background:' + color + ';color:#fff;border-radius:50%;' +
                          'width:24px;height:24px;display:flex;align-items:center;justify-content:center;' +
                          'font-size:12px;font-weight:700;border:2px solid #fff;' +
                          'box-shadow:0 2px 6px rgba(0,0,0,0.3)">B</div>',
                    className: '', iconSize: [24, 24],
                });
                var marker = window.L.marker([lat, lng], { icon: icon });
                var routeName = b.current_route_id ? b.current_route_id[1] : '—';
                marker.bindPopup(
                    '<div style="font-family:Outfit,sans-serif;min-width:160px">' +
                    '<div style="font-weight:700;font-size:13px;border-bottom:2px solid #E85426;padding-bottom:4px;margin-bottom:8px">' +
                    (b.license_plate || b.name) + '</div>' +
                    '<div style="font-size:11px;color:#555;line-height:1.8">' +
                    '<b>Route:</b> ' + routeName + '<br>' +
                    '<b>Status:</b> ' + (active ? 'In Service' : 'Standby') + '<br>' +
                    '<b>Roadworthy:</b> ' + (b.is_roadworthy ? '✓' : '✗ EXPIRED') + '<br>' +
                    '<b>Insured:</b> ' + (b.is_insured ? '✓' : '✗ EXPIRED') +
                    '</div></div>'
                );
                this._busLayer.addLayer(marker);
            }, this);

            this._busLayer.addTo(this.map);
        },
    });

    core.action_registry.add('bus_dashboard', BusDashboard);
    return BusDashboard;
});
