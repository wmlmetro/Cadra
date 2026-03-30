odoo.define('myservice_security.SecurityTabs', function (require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var rpc = require('web.rpc');

    // ─── Shared tab-switching logic ──────────────────────────────────
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
        _fmtDate: function (d) {
            if (!d) return '—';
            return d.substring(0, 10);
        },
        _sevBadge: function (sev) {
            var colors = {
                critical: 'background:#fde8e8;color:#dc3545',
                high: 'background:#fff3cd;color:#E85426',
                medium: 'background:#fff8e1;color:#d29922',
                low: 'background:#e8f5e9;color:#28a745',
            };
            var s = (sev || 'low').toLowerCase();
            return '<span class="nrs-sev-badge" style="' + (colors[s] || colors.low) + '">' +
                s.charAt(0).toUpperCase() + s.slice(1) + '</span>';
        },
        _openRecord: function (model, id) {
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: model,
                res_id: id,
                views: [[false, 'form']],
                target: 'current',
            });
        },
        _openList: function (actionId) {
            this.do_action(actionId);
        },
    };

    // ─── Case Management ─────────────────────────────────────────────
    var CaseManagement = AbstractAction.extend(TabMixin, {
        template: 'myservice_security.CaseManagement',
        events: {
            'click .nrs-row': '_onRowClick',
            'click .nrs-view-all': '_onViewAll',
        },
        start: async function () {
            await this._super.apply(this, arguments);
            this._initTabs();
            this._load_incidents();
        },
        _load_incidents: function () {
            var self = this;
            rpc.query({
                model: 'security.incident',
                method: 'search_read',
                args: [[['state', '!=', 'closed']]],
                kwargs: {
                    fields: ['name', 'incident_type', 'severity', 'state',
                             'location_id', 'date_reported', 'description'],
                    limit: 50,
                    order: 'date_reported desc',
                },
            }).then(function (recs) {
                self._renderTable(self.$('.nrs-tab-body-incidents'), recs, [
                    { f: 'name', l: 'Reference', w: '140px' },
                    { f: 'incident_type', l: 'Type', w: '120px' },
                    { f: 'severity', l: 'Severity', w: '90px', fmt: 'sev' },
                    { f: 'state', l: 'Status', w: '90px' },
                    { f: 'location_id', l: 'Location', w: '1fr', fmt: 'm2o' },
                    { f: 'date_reported', l: 'Date', w: '100px', fmt: 'date' },
                ], 'security.incident');
            });
        },
        _load_watchlist: function () {
            var self = this;
            rpc.query({
                model: 'security.watchlist',
                method: 'search_read',
                args: [[]],
                kwargs: {
                    fields: ['name', 'threat_level', 'reason', 'state',
                             'last_seen_date', 'notes'],
                    limit: 50,
                    order: 'create_date desc',
                },
            }).then(function (recs) {
                self._renderTable(self.$('.nrs-tab-body-watchlist'), recs, [
                    { f: 'name', l: 'Subject', w: '180px' },
                    { f: 'threat_level', l: 'Threat', w: '90px', fmt: 'sev' },
                    { f: 'reason', l: 'Reason', w: '1fr' },
                    { f: 'state', l: 'Status', w: '90px' },
                    { f: 'last_seen_date', l: 'Last Seen', w: '100px', fmt: 'date' },
                ], 'security.watchlist');
            });
        },
        _load_threats: function () {
            var self = this;
            rpc.query({
                model: 'security.state.threat',
                method: 'search_read',
                args: [[]],
                kwargs: {
                    fields: ['name', 'threat_level', 'state_id',
                             'last_updated', 'notes'],
                    limit: 50,
                    order: 'threat_level desc, name',
                },
            }).then(function (recs) {
                self._renderTable(self.$('.nrs-tab-body-threats'), recs, [
                    { f: 'name', l: 'Region', w: '180px' },
                    { f: 'state_id', l: 'State', w: '140px', fmt: 'm2o' },
                    { f: 'threat_level', l: 'Threat Level', w: '100px', fmt: 'sev' },
                    { f: 'last_updated', l: 'Updated', w: '100px', fmt: 'date' },
                    { f: 'notes', l: 'Notes', w: '1fr' },
                ], 'security.state.threat');
            });
        },
        _renderTable: function ($el, recs, cols, model) {
            if (!recs.length) {
                $el.html('<div class="nrs-empty">No records found</div>');
                return;
            }
            var self = this;
            var gridCols = cols.map(function (c) { return c.w; }).join(' ');
            var html = '<div class="nrs-tbl" style="grid-template-columns:' + gridCols + '">';
            cols.forEach(function (c) {
                html += '<div class="nrs-th">' + c.l + '</div>';
            });
            recs.forEach(function (r) {
                cols.forEach(function (c, i) {
                    var val = r[c.f];
                    if (c.fmt === 'date') val = self._fmtDate(val);
                    else if (c.fmt === 'sev') val = self._sevBadge(val);
                    else if (c.fmt === 'm2o') val = val ? val[1] : '—';
                    else val = val || '—';
                    var cls = i === 0 ? ' nrs-td-name' : '';
                    html += '<div class="nrs-td' + cls + ' nrs-row" data-model="' +
                        model + '" data-id="' + r.id + '">' + val + '</div>';
                });
            });
            html += '</div>';
            $el.html(html);
        },
        _onRowClick: function (ev) {
            var $t = $(ev.currentTarget);
            this._openRecord($t.data('model'), $t.data('id'));
        },
        _onViewAll: function (ev) {
            this._openList(parseInt($(ev.currentTarget).data('action')));
        },
    });

    // ─── OSINT ───────────────────────────────────────────────────────
    var OsintPage = AbstractAction.extend(TabMixin, {
        template: 'myservice_security.OsintPage',
        events: {
            'click .nrs-row': '_onRowClick',
            'click .nrs-view-all': '_onViewAll',
        },
        start: async function () {
            await this._super.apply(this, arguments);
            this._initTabs();
            this._load_feed();
        },
        _load_feed: function () {
            var self = this;
            rpc.query({
                model: 'osint.feed.entry',
                method: 'search_read',
                args: [[]],
                kwargs: {
                    fields: ['name', 'source_id', 'threat_level', 'summary',
                             'published_date', 'state'],
                    limit: 50,
                    order: 'published_date desc',
                },
            }).then(function (recs) {
                self._renderTable(self.$('.nrs-tab-body-feed'), recs, [
                    { f: 'name', l: 'Title', w: '1fr' },
                    { f: 'source_id', l: 'Source', w: '120px', fmt: 'm2o' },
                    { f: 'threat_level', l: 'Threat', w: '90px', fmt: 'sev' },
                    { f: 'published_date', l: 'Published', w: '100px', fmt: 'date' },
                    { f: 'state', l: 'Status', w: '90px' },
                ], 'osint.feed.entry');
            });
        },
        _load_sources: function () {
            var self = this;
            rpc.query({
                model: 'osint.source.config',
                method: 'search_read',
                args: [[]],
                kwargs: {
                    fields: ['name', 'source_type', 'active', 'last_fetch_date',
                             'feed_url'],
                    limit: 50,
                    order: 'name',
                },
            }).then(function (recs) {
                self._renderTable(self.$('.nrs-tab-body-sources'), recs, [
                    { f: 'name', l: 'Source Name', w: '200px' },
                    { f: 'source_type', l: 'Type', w: '120px' },
                    { f: 'feed_url', l: 'URL', w: '1fr' },
                    { f: 'last_fetch_date', l: 'Last Fetch', w: '120px', fmt: 'date' },
                    { f: 'active', l: 'Active', w: '70px' },
                ], 'osint.source.config');
            });
        },
        _load_osint: function () {
            var self = this;
            rpc.query({
                model: 'security.osint.feed',
                method: 'search_read',
                args: [[]],
                kwargs: {
                    fields: ['name', 'source', 'threat_level', 'summary',
                             'date_published'],
                    limit: 50,
                    order: 'date_published desc',
                },
            }).then(function (recs) {
                self._renderTable(self.$('.nrs-tab-body-osint'), recs, [
                    { f: 'name', l: 'Title', w: '1fr' },
                    { f: 'source', l: 'Source', w: '120px' },
                    { f: 'threat_level', l: 'Threat', w: '90px', fmt: 'sev' },
                    { f: 'date_published', l: 'Date', w: '100px', fmt: 'date' },
                ], 'security.osint.feed');
            });
        },
        _renderTable: CaseManagement.prototype._renderTable,
        _onRowClick: CaseManagement.prototype._onRowClick,
        _onViewAll: CaseManagement.prototype._onViewAll,
    });

    // ─── AI Patterns ─────────────────────────────────────────────────
    var AiPatternsPage = AbstractAction.extend(TabMixin, {
        template: 'myservice_security.AiPatternsPage',
        events: {
            'click .nrs-row': '_onRowClick',
            'click .nrs-view-all': '_onViewAll',
        },
        start: async function () {
            await this._super.apply(this, arguments);
            this._initTabs();
            this._load_alerts();
        },
        _load_alerts: function () {
            var self = this;
            rpc.query({
                model: 'ai.pattern.alert',
                method: 'search_read',
                args: [[]],
                kwargs: {
                    fields: ['name', 'pattern_type', 'severity', 'state',
                             'detection_date', 'description'],
                    limit: 50,
                    order: 'detection_date desc',
                },
            }).then(function (recs) {
                self._renderTable(self.$('.nrs-tab-body-alerts'), recs, [
                    { f: 'name', l: 'Alert', w: '1fr' },
                    { f: 'pattern_type', l: 'Pattern', w: '120px' },
                    { f: 'severity', l: 'Severity', w: '90px', fmt: 'sev' },
                    { f: 'state', l: 'Status', w: '90px' },
                    { f: 'detection_date', l: 'Detected', w: '100px', fmt: 'date' },
                ], 'ai.pattern.alert');
            });
        },
        _load_briefs: function () {
            var self = this;
            rpc.query({
                model: 'ai.daily.brief',
                method: 'search_read',
                args: [[]],
                kwargs: {
                    fields: ['name', 'date', 'threat_level', 'summary', 'state'],
                    limit: 50,
                    order: 'date desc',
                },
            }).then(function (recs) {
                self._renderTable(self.$('.nrs-tab-body-briefs'), recs, [
                    { f: 'name', l: 'Brief', w: '1fr' },
                    { f: 'date', l: 'Date', w: '100px', fmt: 'date' },
                    { f: 'threat_level', l: 'Threat', w: '90px', fmt: 'sev' },
                    { f: 'state', l: 'Status', w: '90px' },
                ], 'ai.daily.brief');
            });
        },
        _renderTable: CaseManagement.prototype._renderTable,
        _onRowClick: CaseManagement.prototype._onRowClick,
        _onViewAll: CaseManagement.prototype._onViewAll,
    });

    core.action_registry.add('nrs_case_management', CaseManagement);
    core.action_registry.add('nrs_osint', OsintPage);
    core.action_registry.add('nrs_ai_patterns', AiPatternsPage);

    return { CaseManagement: CaseManagement, OsintPage: OsintPage, AiPatternsPage: AiPatternsPage };
});
