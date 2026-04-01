odoo.define('myservice_security.SecurityTabs', function (require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var rpc = require('web.rpc');

    // ─── Shared helpers ──────────────────────────────────────────────
    function fmtDate(d) { return d ? d.substring(0, 10) : '—'; }

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
    // Security Command Center — 8 tabs
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
                var html = '<div class="nrs-kpi-strip">';
                var kpis = [
                    { label: 'Open Incidents',  val: d.open_incidents || 0,  cls: 'red' },
                    { label: 'Critical',        val: d.critical || 0,        cls: 'red' },
                    { label: 'Today',           val: d.today_incidents || 0, cls: 'orange' },
                    { label: 'Guards on Duty',  val: d.guards_on_duty || 0,  cls: 'green' },
                    { label: 'Access Today',    val: d.access_today || 0,    cls: 'blue' },
                    { label: 'Watchlist',       val: d.watchlist_count || 0,  cls: 'purple' },
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
        _load_guards: function () {
            var self = this;
            rpc.query({
                model: 'security.guard', method: 'search_read', args: [[]],
                kwargs: {
                    fields: ['name', 'phone', 'location_id', 'on_duty',
                             'shift_start', 'shift_end'],
                    limit: 50, order: 'name',
                },
            }).then(function (recs) {
                renderTable(self.$('.nrs-tab-body-guards'), recs, [
                    { f: 'name',        l: 'Name',      w: '180px' },
                    { f: 'phone',       l: 'Phone',     w: '120px' },
                    { f: 'location_id', l: 'Location',  w: '1fr',   fmt: 'm2o' },
                    { f: 'on_duty',     l: 'On Duty',   w: '80px',  fmt: 'bool' },
                    { f: 'shift_start', l: 'Shift Start',w: '100px' },
                    { f: 'shift_end',   l: 'Shift End',  w: '100px' },
                ], 'security.guard');
            });
        },

        // ── Access Logs tab ──────────────────────────────────────────
        _load_access_logs: function () {
            var self = this;
            rpc.query({
                model: 'security.access.log', method: 'search_read', args: [[]],
                kwargs: {
                    fields: ['name', 'visitor_name', 'location_id', 'entry_time',
                             'exit_time', 'authorized', 'purpose'],
                    limit: 50, order: 'entry_time desc',
                },
            }).then(function (recs) {
                renderTable(self.$('.nrs-tab-body-access_logs'), recs, [
                    { f: 'name',         l: 'Reference',  w: '120px' },
                    { f: 'visitor_name', l: 'Visitor',    w: '160px' },
                    { f: 'location_id',  l: 'Location',   w: '1fr',   fmt: 'm2o' },
                    { f: 'entry_time',   l: 'Entry',      w: '130px', fmt: 'date' },
                    { f: 'exit_time',    l: 'Exit',       w: '130px', fmt: 'date' },
                    { f: 'authorized',   l: 'Auth',       w: '60px',  fmt: 'bool' },
                ], 'security.access.log');
            });
        },

        // ── Duty Roster tab ──────────────────────────────────────────
        _load_duty_roster: function () {
            var self = this;
            rpc.query({
                model: 'security.duty.roster', method: 'search_read', args: [[]],
                kwargs: {
                    fields: ['name', 'guard_id', 'location_id', 'date',
                             'shift_type', 'status'],
                    limit: 50, order: 'date desc',
                },
            }).then(function (recs) {
                renderTable(self.$('.nrs-tab-body-duty_roster'), recs, [
                    { f: 'name',        l: 'Reference', w: '120px' },
                    { f: 'guard_id',    l: 'Guard',     w: '160px', fmt: 'm2o' },
                    { f: 'location_id', l: 'Location',  w: '1fr',   fmt: 'm2o' },
                    { f: 'date',        l: 'Date',      w: '100px', fmt: 'date' },
                    { f: 'shift_type',  l: 'Shift',     w: '90px' },
                    { f: 'status',      l: 'Status',    w: '90px',  fmt: 'state' },
                ], 'security.duty.roster');
            });
        },

        // ── Intelligence tab ─────────────────────────────────────────
        _load_intelligence: function () {
            var self = this;
            rpc.query({
                model: 'osint.feed.entry', method: 'search_read', args: [[]],
                kwargs: {
                    fields: ['name', 'source_id', 'threat_level', 'summary',
                             'published_date', 'state'],
                    limit: 50, order: 'published_date desc',
                },
            }).then(function (recs) {
                renderTable(self.$('.nrs-tab-body-intelligence'), recs, [
                    { f: 'name',           l: 'Title',     w: '1fr' },
                    { f: 'source_id',      l: 'Source',    w: '120px', fmt: 'm2o' },
                    { f: 'threat_level',   l: 'Threat',    w: '90px',  fmt: 'sev' },
                    { f: 'published_date', l: 'Published', w: '100px', fmt: 'date' },
                    { f: 'state',          l: 'Status',    w: '90px',  fmt: 'state' },
                ], 'osint.feed.entry');
            });
        },

        // ── Daily Briefs tab ─────────────────────────────────────────
        _load_daily_briefs: function () {
            var self = this;
            rpc.query({
                model: 'ai.daily.brief', method: 'search_read', args: [[]],
                kwargs: {
                    fields: ['brief_date', 'subject', 'headline', 'critical_alerts', 'high_alerts', 'states_elevated'],
                    limit: 50, order: 'brief_date desc',
                },
            }).then(function (recs) {
                renderTable(self.$('.nrs-tab-body-daily_briefs'), recs, [
                    { f: 'brief_date',      l: 'Date',     w: '110px', fmt: 'date' },
                    { f: 'subject',         l: 'Subject',  w: 'auto' },
                    { f: 'critical_alerts', l: 'Critical', w: '80px' },
                    { f: 'high_alerts',     l: 'High',     w: '70px' },
                    { f: 'states_elevated', l: 'States',   w: '180px' },
                ], 'ai.daily.brief');
            });
        },

        // ── State Threats tab ─────────────────────────────────────────
        _load_threats: function () {
            var self = this;
            rpc.query({
                model: 'security.state.threat', method: 'search_read', args: [[]],
                kwargs: {
                    fields: ['name', 'threat_level', 'state_id',
                             'last_updated', 'notes'],
                    limit: 50, order: 'threat_level desc, name',
                },
            }).then(function (recs) {
                renderTable(self.$('.nrs-tab-body-threats'), recs, [
                    { f: 'name',         l: 'Region',       w: '180px' },
                    { f: 'state_id',     l: 'State',        w: '140px', fmt: 'm2o' },
                    { f: 'threat_level', l: 'Threat Level', w: '100px', fmt: 'sev' },
                    { f: 'last_updated', l: 'Updated',      w: '100px', fmt: 'date' },
                    { f: 'notes',        l: 'Notes',        w: '1fr' },
                ], 'security.state.threat');
            });
        },

        // ── AI Patterns tab ──────────────────────────────────────────
        _load_ai_patterns: function () {
            var self = this;
            rpc.query({
                model: 'ai.pattern.alert', method: 'search_read', args: [[]],
                kwargs: {
                    fields: ['name', 'pattern_type', 'severity', 'state',
                             'detection_date', 'description'],
                    limit: 50, order: 'detection_date desc',
                },
            }).then(function (recs) {
                renderTable(self.$('.nrs-tab-body-ai_patterns'), recs, [
                    { f: 'name',           l: 'Alert',    w: '1fr' },
                    { f: 'pattern_type',   l: 'Pattern',  w: '120px' },
                    { f: 'severity',       l: 'Severity', w: '90px',  fmt: 'sev' },
                    { f: 'state',          l: 'Status',   w: '90px',  fmt: 'state' },
                    { f: 'detection_date', l: 'Detected', w: '100px', fmt: 'date' },
                ], 'ai.pattern.alert');
            });
        },
    });

    // ═══════════════════════════════════════════════════════════════════
    // Case Management — 3 tabs
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
        _load_watchlist: function () {
            var self = this;
            rpc.query({
                model: 'security.watchlist', method: 'search_read', args: [[]],
                kwargs: {
                    fields: ['name', 'threat_level', 'reason', 'state',
                             'last_seen_date'],
                    limit: 50, order: 'create_date desc',
                },
            }).then(function (recs) {
                renderTable(self.$('.nrs-tab-body-watchlist'), recs, [
                    { f: 'name',           l: 'Subject',   w: '180px' },
                    { f: 'threat_level',   l: 'Threat',    w: '90px',  fmt: 'sev' },
                    { f: 'reason',         l: 'Reason',    w: '1fr' },
                    { f: 'state',          l: 'Status',    w: '90px',  fmt: 'state' },
                    { f: 'last_seen_date', l: 'Last Seen', w: '100px', fmt: 'date' },
                ], 'security.watchlist');
            });
        },
        _load_threats: function () {
            var self = this;
            rpc.query({
                model: 'security.state.threat', method: 'search_read', args: [[]],
                kwargs: {
                    fields: ['name', 'threat_level', 'state_id',
                             'last_updated', 'notes'],
                    limit: 50, order: 'threat_level desc, name',
                },
            }).then(function (recs) {
                renderTable(self.$('.nrs-tab-body-threats'), recs, [
                    { f: 'name',         l: 'Region',       w: '180px' },
                    { f: 'state_id',     l: 'State',        w: '140px', fmt: 'm2o' },
                    { f: 'threat_level', l: 'Threat Level', w: '100px', fmt: 'sev' },
                    { f: 'last_updated', l: 'Updated',      w: '100px', fmt: 'date' },
                    { f: 'notes',        l: 'Notes',        w: '1fr' },
                ], 'security.state.threat');
            });
        },
    });

    // ═══════════════════════════════════════════════════════════════════
    // OSINT — 3 tabs
    // ═══════════════════════════════════════════════════════════════════
    var OsintPage = AbstractAction.extend(TabMixin, {
        template: 'myservice_security.OsintPage',
        events: { 'click .nrs-row': '_onRowClick', 'click .nrs-view-all': '_onViewAll' },
        start: async function () {
            await this._super.apply(this, arguments);
            this._initTabs();
            this._load_feed();
        },
        _load_feed: function () {
            var self = this;
            rpc.query({
                model: 'osint.feed.entry', method: 'search_read', args: [[]],
                kwargs: {
                    fields: ['name', 'source_id', 'threat_level', 'summary',
                             'published_date', 'state'],
                    limit: 50, order: 'published_date desc',
                },
            }).then(function (recs) {
                renderTable(self.$('.nrs-tab-body-feed'), recs, [
                    { f: 'name',           l: 'Title',     w: '1fr' },
                    { f: 'source_id',      l: 'Source',    w: '120px', fmt: 'm2o' },
                    { f: 'threat_level',   l: 'Threat',    w: '90px',  fmt: 'sev' },
                    { f: 'published_date', l: 'Published', w: '100px', fmt: 'date' },
                    { f: 'state',          l: 'Status',    w: '90px',  fmt: 'state' },
                ], 'osint.feed.entry');
            });
        },
        _load_sources: function () {
            var self = this;
            rpc.query({
                model: 'osint.source.config', method: 'search_read', args: [[]],
                kwargs: {
                    fields: ['name', 'source_type', 'active',
                             'last_fetch_date', 'feed_url'],
                    limit: 50, order: 'name',
                },
            }).then(function (recs) {
                renderTable(self.$('.nrs-tab-body-sources'), recs, [
                    { f: 'name',            l: 'Source',     w: '200px' },
                    { f: 'source_type',     l: 'Type',       w: '120px' },
                    { f: 'feed_url',        l: 'URL',        w: '1fr' },
                    { f: 'last_fetch_date', l: 'Last Fetch', w: '120px', fmt: 'date' },
                    { f: 'active',          l: 'Active',     w: '70px',  fmt: 'bool' },
                ], 'osint.source.config');
            });
        },
        _load_osint: function () {
            var self = this;
            rpc.query({
                model: 'security.osint.feed', method: 'search_read', args: [[]],
                kwargs: {
                    fields: ['name', 'source', 'threat_level', 'summary',
                             'date_published'],
                    limit: 50, order: 'date_published desc',
                },
            }).then(function (recs) {
                renderTable(self.$('.nrs-tab-body-osint'), recs, [
                    { f: 'name',           l: 'Title',  w: '1fr' },
                    { f: 'source',         l: 'Source', w: '120px' },
                    { f: 'threat_level',   l: 'Threat', w: '90px',  fmt: 'sev' },
                    { f: 'date_published', l: 'Date',   w: '100px', fmt: 'date' },
                ], 'security.osint.feed');
            });
        },
    });

    // ═══════════════════════════════════════════════════════════════════
    // AI Patterns — 2 tabs
    // ═══════════════════════════════════════════════════════════════════
    var AiPatternsPage = AbstractAction.extend(TabMixin, {
        template: 'myservice_security.AiPatternsPage',
        events: { 'click .nrs-row': '_onRowClick', 'click .nrs-view-all': '_onViewAll' },
        start: async function () {
            await this._super.apply(this, arguments);
            this._initTabs();
            this._load_alerts();
        },
        _load_alerts: function () {
            var self = this;
            rpc.query({
                model: 'ai.pattern.alert', method: 'search_read', args: [[]],
                kwargs: {
                    fields: ['name', 'pattern_type', 'severity', 'state',
                             'detection_date'],
                    limit: 50, order: 'detection_date desc',
                },
            }).then(function (recs) {
                renderTable(self.$('.nrs-tab-body-alerts'), recs, [
                    { f: 'name',           l: 'Alert',    w: '1fr' },
                    { f: 'pattern_type',   l: 'Pattern',  w: '120px' },
                    { f: 'severity',       l: 'Severity', w: '90px',  fmt: 'sev' },
                    { f: 'state',          l: 'Status',   w: '90px',  fmt: 'state' },
                    { f: 'detection_date', l: 'Detected', w: '100px', fmt: 'date' },
                ], 'ai.pattern.alert');
            });
        },
        _load_briefs: function () {
            var self = this;
            rpc.query({
                model: 'ai.daily.brief', method: 'search_read', args: [[]],
                kwargs: {
                    fields: ['brief_date', 'subject', 'headline', 'critical_alerts', 'high_alerts', 'states_elevated'],
                    limit: 50, order: 'brief_date desc',
                },
            }).then(function (recs) {
                renderTable(self.$('.nrs-tab-body-briefs'), recs, [
                    { f: 'brief_date',      l: 'Date',     w: '110px', fmt: 'date' },
                    { f: 'subject',         l: 'Subject',  w: 'auto' },
                    { f: 'critical_alerts', l: 'Critical', w: '80px' },
                    { f: 'high_alerts',     l: 'High',     w: '70px' },
                    { f: 'states_elevated', l: 'States',   w: '180px' },
                ], 'ai.daily.brief');
            });
        },
    });

    // ═══════════════════════════════════════════════════════════════════
    // Daily Brief — standalone
    // ═══════════════════════════════════════════════════════════════════
    var DailyBriefPage = AbstractAction.extend(TabMixin, {
        template: 'myservice_security.DailyBriefPage',
        events: { 'click .nrs-row': '_onRowClick', 'click .nrs-view-all': '_onViewAll' },
        start: async function () {
            await this._super.apply(this, arguments);
            this._initTabs();
            this._load_briefs();
        },
        _load_briefs: AiPatternsPage.prototype._load_briefs,
    });

    // Register all actions
    core.action_registry.add('nrs_security_command_center', SecurityCommandCenter);
    core.action_registry.add('nrs_case_management', CaseManagement);
    core.action_registry.add('nrs_osint', OsintPage);
    core.action_registry.add('nrs_ai_patterns', AiPatternsPage);
    core.action_registry.add('nrs_daily_brief', DailyBriefPage);

    return {
        SecurityCommandCenter: SecurityCommandCenter,
        CaseManagement: CaseManagement,
        OsintPage: OsintPage,
        AiPatternsPage: AiPatternsPage,
        DailyBriefPage: DailyBriefPage,
    };
});
