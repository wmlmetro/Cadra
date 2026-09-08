odoo.define('myservice_security.SecurityTabs', ['web.AbstractAction', 'web.core', 'web.rpc'], function (require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var rpc = require('web.rpc');

    // Every `fields:` list below names columns that exist on the model in
    // the same call. That is not a style rule — a search_read naming one
    // absent field raises for the WHOLE call, so the tab renders nothing at
    // all rather than rendering that column blank. The guarantee is enforced
    // by myservice_security/tests/test_security_tabs_fields.py, which reads
    // this file and resolves every name against a live registry.

    // ─── Shared helpers ──────────────────────────────────────────────
    function fmtDate(d) { return d ? d.substring(0, 10) : '—'; }

    // Access-log rows are events, not days: the time is the point of the
    // record, so a Datetime column keeps its minutes.
    function fmtDateTime(d) { return d ? d.substring(0, 16).replace('T', ' ') : '—'; }

    function sevBadge(sev) {
        var c = {
            critical: '#fde8e8;color:#dc3545',
            high:     '#fff3cd;color:#E85426',
            medium:   '#fff8e1;color:#d29922',
            low:      '#e8f5e9;color:#28a745',
            info:     '#e8f4fd;color:#1a73e8',
        };
        var s = (sev || 'low').toLowerCase();
        return '<span class="nrs-sev-badge" style="background:' +
            (c[s] || c.low) + '">' + s.charAt(0).toUpperCase() + s.slice(1) + '</span>';
    }

    function stateBadge(st) {
        var s = (st || '').toLowerCase();
        var cls = s === 'open' || s === 'new' ? 'nrs-state-open'
                : s === 'closed' || s === 'done' ? 'nrs-state-closed'
                : 'nrs-state-default';
        return '<span class="nrs-state-badge ' + cls + '">' + (st || '—') + '</span>';
    }

    function renderTable($el, recs, cols, model) {
        if (!recs.length) {
            $el.html('<div class="nrs-empty">No records found</div>');
            return;
        }
        var gridCols = cols.map(function (c) { return c.w; }).join(' ');
        var html = '<div class="nrs-tbl" style="grid-template-columns:' + gridCols + '">';
        cols.forEach(function (c) {
            html += '<div class="nrs-th">' + c.l + '</div>';
        });
        recs.forEach(function (r) {
            cols.forEach(function (c, i) {
                var val = r[c.f];
                if (c.fmt === 'date') val = fmtDate(val);
                else if (c.fmt === 'datetime') val = fmtDateTime(val);
                else if (c.fmt === 'sev') val = sevBadge(val);
                else if (c.fmt === 'state') val = stateBadge(val);
                else if (c.fmt === 'm2o') val = val ? val[1] : '—';
                else if (c.fmt === 'bool') val = val ? '✓' : '—';
                else val = (val != null && val !== false) ? String(val) : '—';
                var cls = i === 0 ? ' nrs-td-name' : '';
                html += '<div class="nrs-td' + cls + ' nrs-row" data-model="' +
                    model + '" data-id="' + r.id + '">' + val + '</div>';
            });
        });
        html += '</div>';
        $el.html(html);
    }

    var TabMixin = {
        _initTabs: function () {
            var self = this;
            this.$('.nrs-tab').on('click', function () {
                var tab = $(this).data('tab');
                self.$('.nrs-tab').removeClass('active');
                $(this).addClass('active');
                self.$('.nrs-tab-panel').hide();
                self.$('.nrs-tab-panel[data-panel="' + tab + '"]').show();
                if (self['_load_' + tab]) self['_load_' + tab]();
            });
        },
        _onRowClick: function (ev) {
            var $t = $(ev.currentTarget);
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: $t.data('model'),
                res_id: $t.data('id'),
                views: [[false, 'form']],
                target: 'current',
            });
        },
        _onViewAll: function (ev) {
            this.do_action(parseInt($(ev.currentTarget).data('action')));
        },
    };

    // ═══════════════════════════════════════════════════════════════════
    // Security Command Center — 5 tabs
    // ═══════════════════════════════════════════════════════════════════
    var SecurityCommandCenter = AbstractAction.extend(TabMixin, {
        template: 'myservice_security.SecurityCommandCenter',
        events: {
            'click .nrs-row': '_onRowClick',
            'click .nrs-view-all': '_onViewAll',
        },
        start: async function () {
            await this._super.apply(this, arguments);
            this._initTabs();
            this._load_dashboard();
        },

        // ── Dashboard tab ────────────────────────────────────────────
        _load_dashboard: function () {
            var self = this;
            rpc.query({ route: '/myservice/security/kpis', params: {} })
            .then(function (d) {
                var $p = self.$('.nrs-tab-body-dashboard');
                // /myservice/security/kpis answers three NESTED groups —
                // incidents / guards / access. This strip used to read six
                // flat top-level keys that the controller has never
                // returned, so every card fell through `|| 0` and the
                // dashboard reported a quiet, confident zero for everything.
                var inc = d.incidents || {}, grd = d.guards || {}, acc = d.access || {};
                var html = '<div class="nrs-kpi-strip">';
                var kpis = [
                    { label: 'Open Incidents', val: inc.open || 0,      cls: 'red' },
                    { label: 'Critical',       val: inc.critical || 0,  cls: 'red' },
                    { label: 'Today',          val: inc.today || 0,     cls: 'orange' },
                    { label: 'Guards on Duty', val: grd.on_duty || 0,   cls: 'green' },
                    { label: 'Entries Today',  val: acc.today_in || 0,  cls: 'blue' },
                    { label: 'Flagged Today',  val: acc.flagged || 0,   cls: 'purple' },
                ];
                kpis.forEach(function (k) {
                    html += '<div class="nrs-kpi-card nrs-kpi-' + k.cls + '">' +
                        '<div class="nrs-kpi-val">' + k.val + '</div>' +
                        '<div class="nrs-kpi-lbl">' + k.label + '</div></div>';
                });
                html += '</div>';

                // Recent incidents table
                html += '<div class="nrs-section-hdr">Recent Incidents</div>';
                $p.html(html + '<div class="nrs-dash-incidents"></div>');

                rpc.query({ route: '/myservice/security/recent', params: {} })
                .then(function (recs) {
                    var incidents = recs.incidents || recs || [];
                    renderTable(self.$('.nrs-dash-incidents'), incidents, [
                        { f: 'name',      l: 'Reference',  w: '140px' },
                        { f: 'type',      l: 'Type',       w: '120px' },
                        { f: 'severity',  l: 'Severity',   w: '90px',  fmt: 'sev' },
                        { f: 'state',     l: 'Status',     w: '90px',  fmt: 'state' },
                        { f: 'location',  l: 'Location',   w: '1fr' },
                        { f: 'date',      l: 'Date',       w: '100px', fmt: 'date' },
                    ], 'security.incident');
                }).catch(function () {
                    // Fallback: load via search_read
                    self._load_incidents_rpc(self.$('.nrs-dash-incidents'), 10);
                });
            }).catch(function () {
                self.$('.nrs-tab-body-dashboard').html(
                    '<div class="nrs-empty">Dashboard data unavailable</div>');
            });
        },

        _load_incidents_rpc: function ($el, limit) {
            rpc.query({
                model: 'security.incident', method: 'search_read',
                args: [[['state', '!=', 'closed']]],
                kwargs: {
                    fields: ['name', 'incident_type', 'severity', 'state',
                             'location_id', 'date_reported'],
                    limit: limit || 50, order: 'date_reported desc',
                },
            }).then(function (recs) {
                renderTable($el, recs, [
                    { f: 'name',          l: 'Reference',  w: '140px' },
                    { f: 'incident_type', l: 'Type',       w: '120px' },
                    { f: 'severity',      l: 'Severity',   w: '90px',  fmt: 'sev' },
                    { f: 'state',         l: 'Status',     w: '90px',  fmt: 'state' },
                    { f: 'location_id',   l: 'Location',   w: '1fr',   fmt: 'm2o' },
                    { f: 'date_reported', l: 'Date',       w: '100px', fmt: 'date' },
                ], 'security.incident');
            });
        },

        // ── Incidents tab ────────────────────────────────────────────
        _load_incidents: function () {
            this._load_incidents_rpc(this.$('.nrs-tab-body-incidents'), 50);
        },

        // ── Guards tab ───────────────────────────────────────────────
        // A shift belongs to a security.duty.roster row, not to a guard:
        // there are no shift_start/shift_end fields on security.guard and
        // there never were. The Duty Roster tab is where a shift is shown;
        // this tab is the guard register, so it carries what identifies a
        // guard — badge, base location, specialisation — plus the stored
        // on_duty flag, which is the one thing here that answers "now".
        _load_guards: function () {
            var self = this;
            rpc.query({
                model: 'security.guard', method: 'search_read', args: [[]],
                kwargs: {
                    fields: ['name', 'badge_number', 'phone', 'home_location_id',
                             'specialisation', 'on_duty'],
                    limit: 50, order: 'name',
                },
            }).then(function (recs) {
                renderTable(self.$('.nrs-tab-body-guards'), recs, [
                    { f: 'name',             l: 'Name',           w: '180px' },
                    { f: 'badge_number',     l: 'Badge',          w: '110px' },
                    { f: 'phone',            l: 'Phone',          w: '120px' },
                    { f: 'home_location_id', l: 'Base Location',  w: '1fr',   fmt: 'm2o' },
                    { f: 'specialisation',   l: 'Specialisation', w: '130px' },
                    { f: 'on_duty',          l: 'On Duty',        w: '80px',  fmt: 'bool' },
                ], 'security.guard');
            });
        },

        // ── Access Logs tab ──────────────────────────────────────────
        // One row is one movement through a gate, stamped with a direction
        // — not an entry/exit pair — so there is no entry_time/exit_time to
        // read, and the person is person_name. The model has no `name`
        // either: the Reference column had nothing behind it.
        _load_access_logs: function () {
            var self = this;
            rpc.query({
                model: 'security.access.log', method: 'search_read', args: [[]],
                kwargs: {
                    fields: ['person_name', 'location_id', 'direction', 'datetime',
                             'purpose', 'authorized'],
                    limit: 50, order: 'datetime desc',
                },
            }).then(function (recs) {
                renderTable(self.$('.nrs-tab-body-access_logs'), recs, [
                    { f: 'person_name', l: 'Person',    w: '160px' },
                    { f: 'location_id', l: 'Location',  w: '1fr',   fmt: 'm2o' },
                    { f: 'direction',   l: 'Direction', w: '80px' },
                    { f: 'datetime',    l: 'Date/Time', w: '140px', fmt: 'datetime' },
                    { f: 'purpose',     l: 'Purpose',   w: '160px' },
                    { f: 'authorized',  l: 'Auth',      w: '60px',  fmt: 'bool' },
                ], 'security.access.log');
            });
        },

        // ── Duty Roster tab ──────────────────────────────────────────
        // The shift field is `shift`, not `shift_type`, and the model has
        // no `name` — a roster row is identified by guard + date + shift,
        // which is why its display_name is a bare "model,id".
        _load_duty_roster: function () {
            var self = this;
            rpc.query({
                model: 'security.duty.roster', method: 'search_read', args: [[]],
                kwargs: {
                    fields: ['guard_id', 'location_id', 'date', 'shift', 'status'],
                    limit: 50, order: 'date desc',
                },
            }).then(function (recs) {
                renderTable(self.$('.nrs-tab-body-duty_roster'), recs, [
                    { f: 'guard_id',    l: 'Guard',     w: '180px', fmt: 'm2o' },
                    { f: 'location_id', l: 'Location',  w: '1fr',   fmt: 'm2o' },
                    { f: 'date',        l: 'Date',      w: '100px', fmt: 'date' },
                    { f: 'shift',       l: 'Shift',     w: '110px' },
                    { f: 'status',      l: 'Status',    w: '100px', fmt: 'state' },
                ], 'security.duty.roster');
            });
        },
    });

    // ═══════════════════════════════════════════════════════════════════
    // Case Management
    // ═══════════════════════════════════════════════════════════════════
    var CaseManagement = AbstractAction.extend(TabMixin, {
        template: 'myservice_security.CaseManagement',
        events: { 'click .nrs-row': '_onRowClick', 'click .nrs-view-all': '_onViewAll' },
        start: async function () {
            await this._super.apply(this, arguments);
            this._initTabs();
            this._load_incidents();
        },
        _load_incidents: function () {
            var self = this;
            rpc.query({
                model: 'security.incident', method: 'search_read',
                args: [[['state', '!=', 'closed']]],
                kwargs: {
                    fields: ['name', 'incident_type', 'severity', 'state',
                             'location_id', 'date_reported'],
                    limit: 50, order: 'date_reported desc',
                },
            }).then(function (recs) {
                renderTable(self.$('.nrs-tab-body-incidents'), recs, [
                    { f: 'name',          l: 'Reference', w: '140px' },
                    { f: 'incident_type', l: 'Type',      w: '120px' },
                    { f: 'severity',      l: 'Severity',  w: '90px',  fmt: 'sev' },
                    { f: 'state',         l: 'Status',    w: '90px',  fmt: 'state' },
                    { f: 'location_id',   l: 'Location',  w: '1fr',   fmt: 'm2o' },
                    { f: 'date_reported', l: 'Date',      w: '100px', fmt: 'date' },
                ], 'security.incident');
            });
        },
    });

    // The OSINT, AI Patterns, Daily Brief and Watchlist / State Threat tabs
    // that used to live here were removed, not repaired. Every one of them
    // read a model this codebase does not define and no tenant carries —
    // osint.feed.entry, osint.source.config, ai.pattern.alert,
    // ai.daily.brief, security.watchlist, security.state.threat. They exist
    // only as CSV extracts of the retired Odoo 15 estate under
    // docs/upgrade/archive/. A tab whose RPC can only raise is not a
    // placeholder for one that will work; keeping it preserves the
    // appearance of a feature while removing anything that would make its
    // absence audible. Git history holds the markup if the models come back.

    // Register all actions
    core.action_registry.add('nrs_security_command_center', SecurityCommandCenter);
    core.action_registry.add('nrs_case_management', CaseManagement);

    return {
        SecurityCommandCenter: SecurityCommandCenter,
        CaseManagement: CaseManagement,
    };
});
