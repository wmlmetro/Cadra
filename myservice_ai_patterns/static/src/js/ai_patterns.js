odoo.define('myservice_ai_patterns.dashboard', function(require) {
'use strict';
var rpc = require('web.rpc');

window.AiPanel = {

    loadAlerts: function(container, opts) {
        opts = opts || {};
        rpc.query({
            route: '/myservice/ai/alerts',
            params: { limit: opts.limit || 10, severity: opts.severity || null }
        }).then(function(alerts) {
            window.AiPanel._renderAlerts(container, alerts);
        }).catch(function(e) {
            console.warn('AI alerts load error:', e);
        });
    },

    loadSummary: function(callback) {
        rpc.query({ route: '/myservice/ai/summary', params: {} }).then(callback);
    },

    assessRoute: function(origin, dest, callback) {
        rpc.query({
            route: '/myservice/ai/route_risk',
            params: { origin: origin, destination: dest }
        }).then(callback);
    },

    runNow: function(callback) {
        rpc.query({ route: '/myservice/ai/run_now', params: {} }).then(callback);
    },

    _renderAlerts: function(container, alerts) {
        if (!container) return;
        if (!alerts || !alerts.length) {
            container.innerHTML = '<div style="padding:16px;text-align:center;' +
                'color:var(--color-text-secondary);font-size:13px">' +
                'No active AI pattern alerts.</div>';
            return;
        }
        var typeLabels = {
            cluster: 'Cluster', escalation: 'Escalation', actor: 'Actor',
            temporal: 'Temporal', route: 'Route Risk', watchlist: 'Watchlist'
        };
        var html = '';
        alerts.forEach(function(a) {
            html += '<div class="ai-alert-card ' + a.severity + '" ' +
                'onclick="window.AiPanel._openAlert(' + a.id + ')">' +
                '<div class="ai-alert-title">' + _esc(a.title) + '</div>' +
                '<div class="ai-alert-meta">' +
                    '<span class="ai-type-badge">' + (typeLabels[a.pattern_type]||a.pattern_type) + '</span>' +
                    '<span style="color:' + _severityColor(a.severity) + ';font-weight:700">' +
                        a.severity.toUpperCase() + '</span>' +
                    ' · ' + _esc(a.states) +
                    ' · ' + _esc(a.created) +
                    ' · Confidence: ' + a.confidence + '%' +
                '</div>' +
                (a.summary ? '<div class="ai-alert-summary">' + _esc(a.summary.substring(0,200)) +
                    (a.summary.length > 200 ? '…' : '') + '</div>' : '') +
                '<div class="ai-confidence-bar">' +
                    '<div class="ai-confidence-fill" style="width:' + a.confidence + '%;' +
                    'background:' + _severityColor(a.severity) + '"></div>' +
                '</div>' +
            '</div>';
        });
        container.innerHTML = html;
    },

    _openAlert: function(id) {
        window.location.href = '/web#id=' + id +
            '&model=ai.pattern.alert&view_type=form';
    }
};

function _esc(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function _severityColor(s) {
    return {critical:'#dc3545',high:'#E85426',medium:'#ffc107',low:'#28a745'}[s] || '#888';
}

});
