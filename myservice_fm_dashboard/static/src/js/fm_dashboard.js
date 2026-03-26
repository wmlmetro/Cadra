odoo.define('myservice_fm_dashboard.FMDashboard', function(require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var rpc = require('web.rpc');

    var DOMAIN_CONFIG = {
        'Facilities Helpdesk': { cls: 'helpdesk', color: '#28a745' },
        'Building Services':   { cls: 'building',  color: '#007bff' },
        'Plant & Machinery':   { cls: 'plant',     color: '#E85426' },
        'Plumbing & Drainage': { cls: 'plumbing',  color: '#17a2b8' },
        'Fleet Management':    { cls: 'fleet',     color: '#6f42c1' },
        'Security & Safety':   { cls: 'security',  color: '#dc3545' },
    };

    var STAGE_CLASS = {
        'New':         'stage-new',
        'Assigned':    'stage-assigned',
        'In Progress': 'stage-progress',
        'Pending':     'stage-pending',
        'Escalated':   'stage-escalated',
        'Resolved':    'stage-resolved',
        'Closed':      'stage-closed',
    };

    var PRIO_CONFIG = {
        '0': { label: 'Normal',   color: '#888' },
        '1': { label: 'Low',      color: '#28a745' },
        '2': { label: 'High',     color: '#f0a500' },
        '3': { label: 'Critical', color: '#dc3545' },
    };

    var FMDashboard = AbstractAction.extend({
        template: 'myservice_fm_dashboard.FMDashboard',
        hasControlPanel: true,

        start: function() {
            var self = this;
            this._stageFilter = 'all';
            this._allRequests = [];
            return this._super.apply(this, arguments).then(function() {
                self._loadData();
                self._refreshTimer = setInterval(function() {
                    self._loadData();
                }, 180000); // 3 min

                // Tab filter buttons
                self.$('.ms-fm-tab-btn').on('click', function() {
                    self.$('.ms-fm-tab-btn').removeClass('active');
                    $(this).addClass('active');
                    self._stageFilter = $(this).data('stage');
                    self._renderRequestList();
                });
            });
        },

        destroy: function() {
            if (this._refreshTimer) clearInterval(this._refreshTimer);
            this._super.apply(this, arguments);
        },

        refresh: function() {
            this._loadData();
        },

        // ── Load all data ────────────────────────────────────────
        _loadData: function() {
            var self = this;
            var today = new Date().toISOString().split('T')[0];

            // All open requests (not closed/resolved)
            rpc.query({
                model: 'request.request',
                method: 'search_read',
                args: [[['stage_id.name', 'not in', ['Closed']]]],
                kwargs: {
                    fields: ['name', 'stage_id', 'team_id', 'service_id',
                             'priority', 'deadline_date', 'generic_location_id',
                             'type_id', 'create_date'],
                    limit: 500,
                    order: 'create_date desc',
                }
            }).then(function(reqs) {
                self._allRequests = reqs || [];
                self._renderKpis(today);
                self._renderDomainRow();
                self._renderRequestList();
                self._renderTeamWorkload();
                self._renderPriority();
                self._renderOverdue(today);
                self._renderSlaTable();

                // Update timestamp
                var now = new Date();
                var timeStr = now.toLocaleTimeString('en-GB', {hour:'2-digit', minute:'2-digit'});
                var el = document.getElementById('fm-last-updated');
                if (el) el.textContent = 'Last updated: ' + timeStr + ' — ' + (reqs.length) + ' open requests';
            });

            // Load locations for filter
            rpc.query({
                model: 'generic.location',
                method: 'search_read',
                args: [[]],
                kwargs: { fields: ['name'], limit: 100, order: 'name asc' }
            }).then(function(locs) {
                var sel = document.getElementById('fm-location-filter');
                if (!sel || sel.options.length > 1) return;
                (locs || []).forEach(function(l) {
                    var opt = document.createElement('option');
                    opt.value = l.id;
                    opt.textContent = l.name;
                    sel.appendChild(opt);
                });
            });
        },

        // ── KPIs ─────────────────────────────────────────────────
        _renderKpis: function(today) {
            var reqs = this._allRequests;
            var open      = reqs.filter(function(r) { return !['Closed','Resolved'].includes(r.stage_id && r.stage_id[1]); }).length;
            var overdue   = reqs.filter(function(r) { return r.deadline_date && r.deadline_date < today && !['Closed','Resolved'].includes(r.stage_id && r.stage_id[1]); }).length;
            var escalated = reqs.filter(function(r) { return r.stage_id && r.stage_id[1] === 'Escalated'; }).length;
            var inprog    = reqs.filter(function(r) { return r.stage_id && r.stage_id[1] === 'In Progress'; }).length;
            var resolved  = reqs.filter(function(r) {
                return r.stage_id && r.stage_id[1] === 'Resolved' &&
                       r.create_date && r.create_date.substring(0,10) === today;
            }).length;
            var unassigned = reqs.filter(function(r) { return !r.team_id; }).length;

            var set = function(id, val) {
                var el = document.getElementById(id);
                if (el) el.textContent = val;
            };
            set('kpi-total-open',    open);
            set('kpi-overdue',       overdue);
            set('kpi-escalated',     escalated);
            set('kpi-in-progress',   inprog);
            set('kpi-resolved-today',resolved);
            set('kpi-unassigned',    unassigned);
            set('overdue-badge',     overdue);
        },

        // ── Domain breakdown row ─────────────────────────────────
        _renderDomainRow: function() {
            var reqs = this._allRequests;
            var $row = this.$('#fm-domain-row');
            $row.empty();

            Object.keys(DOMAIN_CONFIG).forEach(function(domain) {
                var cfg = DOMAIN_CONFIG[domain];
                var domReqs = reqs.filter(function(r) {
                    return r.team_id && r.team_id[1] === domain;
                });
                var total    = domReqs.length;
                var critical = domReqs.filter(function(r) { return r.priority === '3'; }).length;
                var escalated = domReqs.filter(function(r) { return r.stage_id && r.stage_id[1] === 'Escalated'; }).length;

                $row.append(
                    '<div class="ms-fm-domain-card ' + cfg.cls + '">' +
                    '<div class="ms-fm-domain-name">' + domain + '</div>' +
                    '<div class="ms-fm-domain-count">' + total + '</div>' +
                    '<div class="ms-fm-domain-sub">' +
                    (critical ? critical + ' critical' : '') +
                    (critical && escalated ? ' · ' : '') +
                    (escalated ? escalated + ' escalated' : '') +
                    (!critical && !escalated ? 'No critical issues' : '') +
                    '</div></div>'
                );
            });
        },

        // ── SLA table ────────────────────────────────────────────
        _renderSlaTable: function() {
            var reqs = this._allRequests;
            var today = new Date().toISOString().split('T')[0];
            var $el = this.$('#fm-sla-table');
            $el.empty();

            var html = '<table class="ms-fm-sla-table">';
            html += '<tr><th>Domain</th><th>Open</th><th>Overdue</th><th>Escalated</th><th>SLA</th></tr>';

            Object.keys(DOMAIN_CONFIG).forEach(function(domain) {
                var domReqs = reqs.filter(function(r) {
                    return r.team_id && r.team_id[1] === domain &&
                           !['Closed','Resolved'].includes(r.stage_id && r.stage_id[1]);
                });
                var total    = domReqs.length;
                var overdue  = domReqs.filter(function(r) { return r.deadline_date && r.deadline_date < today; }).length;
                var escalated = domReqs.filter(function(r) { return r.stage_id && r.stage_id[1] === 'Escalated'; }).length;

                var slaPct = total ? Math.round((1 - overdue/total) * 100) : 100;
                var slaClass = slaPct >= 90 ? 'ok' : slaPct >= 70 ? 'warn' : 'breach';

                html += '<tr>' +
                    '<td><strong>' + domain + '</strong></td>' +
                    '<td>' + total + '</td>' +
                    '<td>' + (overdue ? '<span style="color:#dc3545;font-weight:600">' + overdue + '</span>' : '0') + '</td>' +
                    '<td>' + (escalated ? '<span style="color:#f0a500;font-weight:600">' + escalated + '</span>' : '0') + '</td>' +
                    '<td><span class="ms-fm-sla-pill ' + slaClass + '">' + slaPct + '%</span></td>' +
                    '</tr>';
            });
            html += '</table>';
            $el.html(html);
        },

        // ── Request list ─────────────────────────────────────────
        _renderRequestList: function() {
            var self = this;
            var today = new Date().toISOString().split('T')[0];
            var reqs = this._allRequests;
            var filter = this._stageFilter;

            var filtered = reqs.filter(function(r) {
                if (filter === 'all')      return !['Closed'].includes(r.stage_id && r.stage_id[1]);
                if (filter === 'Overdue')  return r.deadline_date && r.deadline_date < today;
                return r.stage_id && r.stage_id[1] === filter;
            });

            var $list = this.$('#fm-request-list');
            $list.empty();

            if (!filtered.length) {
                $list.html('<div class="ms-fm-empty">No requests found.</div>');
                return;
            }

            filtered.slice(0, 30).forEach(function(r) {
                var stage     = r.stage_id ? r.stage_id[1] : '';
                var stageClass = STAGE_CLASS[stage] || '';
                var team      = r.team_id ? r.team_id[1] : 'Unassigned';
                var loc       = r.generic_location_id ? r.generic_location_id[1] : '';
                var isOverdue = r.deadline_date && r.deadline_date < today;
                var prio      = r.priority || '0';
                var prioColor = PRIO_CONFIG[prio] ? PRIO_CONFIG[prio].color : '#888';
                var deadline  = r.deadline_date ? r.deadline_date.substring(0,10) : '';

                $list.append(
                    '<div class="ms-fm-req-item" data-id="' + r.id + '">' +
                    '<div class="ms-fm-req-dot" style="background:' + prioColor + '"></div>' +
                    '<div style="flex:1;min-width:0">' +
                    '<div class="ms-fm-req-name">' + r.name +
                    (isOverdue ? ' <span style="color:#dc3545;font-size:10px;font-weight:700">OVERDUE</span>' : '') +
                    '</div>' +
                    '<div class="ms-fm-req-meta">' + team +
                    (loc ? ' · ' + loc : '') +
                    (deadline ? ' · Due: ' + deadline : '') +
                    '</div></div>' +
                    '<span class="ms-fm-req-stage ' + stageClass + '">' + stage + '</span>' +
                    '</div>'
                );
            });

            // Click to open request
            this.$('.ms-fm-req-item').on('click', function() {
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

        // ── Team workload ────────────────────────────────────────
        _renderTeamWorkload: function() {
            var reqs = this._allRequests.filter(function(r) {
                return !['Closed','Resolved'].includes(r.stage_id && r.stage_id[1]);
            });
            var $el = this.$('#fm-team-workload');
            $el.empty();

            var teams = {};
            reqs.forEach(function(r) {
                var name = r.team_id ? r.team_id[1] : 'Unassigned';
                teams[name] = (teams[name] || 0) + 1;
            });

            var sorted = Object.entries(teams).sort(function(a,b) { return b[1]-a[1]; });
            var max = sorted.length ? sorted[0][1] : 1;

            sorted.forEach(function(entry) {
                var name = entry[0], count = entry[1];
                var pct = Math.round(count / max * 100);
                var cfg = DOMAIN_CONFIG[name];
                var color = cfg ? cfg.color : '#E85426';
                $el.append(
                    '<div class="ms-fm-team-row">' +
                    '<div class="ms-fm-team-name" title="' + name + '">' + name + '</div>' +
                    '<div class="ms-fm-team-bar-track">' +
                    '<div class="ms-fm-team-bar-fill" style="width:' + pct + '%;background:' + color + '"></div>' +
                    '</div>' +
                    '<div class="ms-fm-team-count">' + count + '</div>' +
                    '</div>'
                );
            });

            if (!sorted.length) {
                $el.html('<div class="ms-fm-empty">No open requests.</div>');
            }
        },

        // ── Priority breakdown ───────────────────────────────────
        _renderPriority: function() {
            var reqs = this._allRequests.filter(function(r) {
                return !['Closed','Resolved'].includes(r.stage_id && r.stage_id[1]);
            });
            var $el = this.$('#fm-priority-breakdown');
            $el.empty();

            var counts = {'3':0, '2':0, '1':0, '0':0};
            reqs.forEach(function(r) { counts[r.priority || '0']++; });

            [['3','Critical'],['2','High'],['1','Low'],['0','Normal']].forEach(function(p) {
                var key = p[0], label = p[1];
                var cfg = PRIO_CONFIG[key];
                $el.append(
                    '<div class="ms-fm-prio-row">' +
                    '<div class="ms-fm-prio-dot" style="background:' + cfg.color + '"></div>' +
                    '<div class="ms-fm-prio-label">' + label + '</div>' +
                    '<div class="ms-fm-prio-count">' + counts[key] + '</div>' +
                    '</div>'
                );
            });
        },

        // ── Overdue list ─────────────────────────────────────────
        _renderOverdue: function(today) {
            var reqs = this._allRequests.filter(function(r) {
                return r.deadline_date && r.deadline_date < today &&
                       !['Closed','Resolved'].includes(r.stage_id && r.stage_id[1]);
            }).sort(function(a,b) {
                return a.deadline_date < b.deadline_date ? -1 : 1;
            });

            var $el = this.$('#fm-overdue-list');
            $el.empty();

            if (!reqs.length) {
                $el.html('<div class="ms-fm-empty" style="color:#28a745">✓ No overdue requests</div>');
                return;
            }

            reqs.slice(0, 10).forEach(function(r) {
                var team = r.team_id ? r.team_id[1] : 'Unassigned';
                var daysOverdue = Math.floor((new Date(today) - new Date(r.deadline_date)) / 86400000);
                $el.append(
                    '<div class="ms-fm-overdue-item">' +
                    '<div class="ms-fm-overdue-name">' + r.name + '</div>' +
                    '<div class="ms-fm-overdue-meta">' + team + ' · ' + daysOverdue + ' day(s) overdue · Due: ' + r.deadline_date + '</div>' +
                    '</div>'
                );
            });

            if (reqs.length > 10) {
                $el.append('<div style="padding:8px 14px;font-size:11px;color:#888;text-align:center">+ ' + (reqs.length-10) + ' more overdue</div>');
            }
        },
    });

    core.action_registry.add('fm_dashboard', FMDashboard);
    return FMDashboard;
});
