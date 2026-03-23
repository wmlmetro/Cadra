"""
Patches dashboard.js to add:
1. Tab switching logic
2. Fleet Command data loading + rendering
3. CSS injection for fleet command styles
"""

JS = '/opt/odoo/myservicenrs/myservice_dashboard/static/src/js/dashboard.js'
with open(JS) as f:
    js = f.read()

# ── CSS injection ─────────────────────────────────────────────────────
CSS_INJECT = """
        // Fleet Command styles
        if (!document.getElementById('ms-fleet-style')) {
            var fst = document.createElement('style');
            fst.id = 'ms-fleet-style';
            fst.textContent = [
                '.ms-tab-bar{display:flex;gap:6px;padding:0 0 14px;border-bottom:1px solid #e0e0e0;margin-bottom:16px}',
                '.ms-tab{padding:7px 18px;border-radius:20px;border:1px solid #ddd;background:#fff;cursor:pointer;font-size:13px;color:#555;transition:all .2s}',
                '.ms-tab.active{background:#E85426;color:#fff;border-color:#E85426}',
                '.ms-tab-panel{display:block}',
                '.ms-fleet-kpis{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:10px;margin-bottom:16px}',
                '.ms-fleet-kpi{background:#fff;border-radius:8px;border:1px solid #e8e8e8;padding:12px 14px;text-align:center}',
                '.ms-fleet-kpi.red .ms-fleet-kval{color:#dc3545}',
                '.ms-fleet-kpi.orange .ms-fleet-kval{color:#E85426}',
                '.ms-fleet-kpi.green .ms-fleet-kval{color:#28a745}',
                '.ms-fleet-kpi.blue .ms-fleet-kval{color:#007bff}',
                '.ms-fleet-kpi.gray .ms-fleet-kval{color:#555}',
                '.ms-fleet-kval{font-size:24px;font-weight:700;line-height:1.2}',
                '.ms-fleet-klbl{font-size:11px;color:#888;margin-top:4px}',
                '.ms-fleet-grid{display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px}',
                '.ms-fleet-card{background:#fff;border-radius:8px;border:1px solid #e8e8e8;padding:14px 16px;overflow:hidden}',
                '.ms-fleet-card.wide{grid-column:span 2}',
                '.ms-fleet-card-hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;font-size:13px;font-weight:600;color:#333}',
                '.ms-fleet-card-sub{font-size:11px;color:#888;font-weight:400}',
                '.ms-fleet-empty{font-size:12px;color:#aaa;padding:12px 0;text-align:center}',
                '.ms-fleet-bar-row{display:flex;align-items:center;gap:8px;margin-bottom:7px}',
                '.ms-fleet-bar-label{font-size:11px;color:#555;width:130px;flex-shrink:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
                '.ms-fleet-bar-track{flex:1;height:8px;background:#f0f0f0;border-radius:4px;overflow:hidden}',
                '.ms-fleet-bar-fill{height:100%;border-radius:4px;transition:width .4s ease}',
                '.ms-fleet-bar-val{font-size:11px;color:#888;width:32px;text-align:right;flex-shrink:0}',
                '.ms-fleet-status-row{display:flex;align-items:center;justify-content:space-between;padding:7px 0;border-bottom:1px solid #f5f5f5;font-size:12px}',
                '.ms-fleet-status-row:last-child{border-bottom:none}',
                '.ms-fleet-dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px;flex-shrink:0}',
                '.ms-fleet-badge{padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600}',
                '.ms-fleet-badge-red{background:#fde8e8;color:#dc3545}',
                '.ms-fleet-badge-orange{background:#fff3cd;color:#E85426}',
                '.ms-fleet-badge-green{background:#e8f5e9;color:#28a745}',
                '.ms-fleet-badge-gray{background:#f5f5f5;color:#555}',
                '.ms-fleet-vendor-row{display:flex;align-items:center;justify-content:space-between;padding:7px 0;border-bottom:1px solid #f5f5f5;font-size:12px}',
                '.ms-fleet-vendor-row:last-child{border-bottom:none}',
                '.ms-fleet-maint-row{display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid #f5f5f5;font-size:12px}',
                '.ms-fleet-maint-row:last-child{border-bottom:none}',
                '.ms-fleet-maint-plate{font-weight:600;min-width:80px;color:#333}',
                '.ms-fleet-maint-info{flex:1;color:#555;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
                '.ms-fleet-maint-cost{color:#E85426;font-weight:600;min-width:70px;text-align:right}',
                '.ms-fleet-maint-date{color:#aaa;font-size:10px;min-width:70px;text-align:right}',
            ].join('');
            document.head.appendChild(fst);
        }"""

# ── Tab switching + fleet load ────────────────────────────────────────
TAB_JS = """
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
        },"""

# Inject CSS into existing style injection block
if 'ms-fleet-style' not in js:
    js = js.replace(
        "    if (!document.getElementById('soc-spin-style')) {",
        CSS_INJECT + "\n    if (!document.getElementById('soc-spin-style')) {"
    )
    print("CSS injected")

# Add _fleetLoaded flag to init
if '_fleetLoaded' not in js:
    js = js.replace(
        "this.map = null; this.locationLayer = null; this.fleetLayer = null;",
        "this.map = null; this.locationLayer = null; this.fleetLayer = null; this._fleetLoaded = false;"
    )

# Add _initTabs call to start
if '_initTabs' not in js:
    js = js.replace(
        "await this._loadData();",
        "this._initTabs();\n            await this._loadData();"
    )

# Add tab/fleet methods before the closing of the widget
if '_loadFleetCommand' not in js:
    # Find a good insertion point — after _renderLocationStats
    js = js.replace(
        "        _onKpiClick: function(ev) {",
        TAB_JS + "\n\n        _onKpiClick: function(ev) {"
    )
    print("Tab + fleet JS added")

with open(JS, 'w') as f:
    f.write(js)

print("dashboard.js updated")
