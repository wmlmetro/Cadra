odoo.define('myservice_osint.dashboard', function(require) {
'use strict';
var rpc = require('web.rpc');

// Expose refresh functions for the security dashboard to call
window.OsintPanel = {

    _currentSource: 'all',
    _currentThreat: 'all',

    loadFeed: function(container, opts) {
        opts = opts || {};
        var self = this;
        var params = { limit: opts.limit || 30 };
        if (opts.source && opts.source !== 'all') params.source_type = opts.source;
        if (opts.threat && opts.threat !== 'all') params.threat_level = opts.threat;
        if (opts.state) params.state = opts.state;

        rpc.query({ route: '/myservice/osint/feed', params: params }).then(function(entries) {
            self._renderFeed(container, entries);
        }).catch(function(e) {
            console.warn('OSINT feed load error:', e);
        });
    },

    loadStateScores: function(container) {
        rpc.query({ route: '/myservice/osint/state_scores', params: {} })
        .then(function(states) {
            window.OsintPanel._renderThreatMatrix(container, states);
        });
    },

    loadSummary: function(callback) {
        rpc.query({ route: '/myservice/osint/summary', params: {} })
        .then(callback);
    },

    _renderFeed: function(container, entries) {
        if (!container) return;
        if (!entries.length) {
            container.innerHTML = '<div style="padding:20px;text-align:center;color:var(--color-text-secondary);font-size:13px">No intelligence entries matching current filters.</div>';
            return;
        }
        var html = '';
        entries.forEach(function(e) {
            var icon = { acled:'⚔️', gdelt:'📡', rss:'📰', reliefweb:'🌐',
                         manual:'✏️', watchlist:'👁️', twitter:'🐦' };
            html += '<div class="osint-feed-card ' + e.threat_level + '" ' +
                    'onclick="window.OsintPanel._openEntry(' + e.id + ')">' +
                '<div class="card-title">' + _escHtml(e.title) + '</div>' +
                '<div class="card-meta">' +
                    '<span class="osint-badge ' + e.threat_level + '">' + e.threat_level + '</span> ' +
                    (icon[e.source_type] || '📌') + ' ' + _escHtml(e.source_name) + ' · ' +
                    _escHtml(e.state) + ' · ' + _escHtml(e.event_date) +
                    (e.fatalities > 0 ? ' · <strong>' + e.fatalities + ' fatalities</strong>' : '') +
                    (e.verified ? ' ✓' : '') +
                '</div>' +
                (e.summary ? '<div style="font-size:11px;color:var(--color-text-secondary);margin-top:4px;line-height:1.4">' + _escHtml(e.summary.substring(0,200)) + (e.summary.length>200?'…':'') + '</div>' : '') +
            '</div>';
        });
        container.innerHTML = html;
    },

    _renderThreatMatrix: function(container, states) {
        if (!container || !states.length) return;
        var levelColors = { red:'#dc3545', orange:'#E85426', yellow:'#ffc107', green:'#28a745' };
        var sorted = states.slice().sort(function(a,b){ return (b.score||0)-(a.score||0); });
        var html = '<div style="padding:8px">';
        sorted.forEach(function(s) {
            var color = levelColors[s.level] || '#888';
            var score = Math.round(s.score || 0);
            var delta = s.delta || 0;
            var deltaClass = delta > 2 ? 'delta-up' : delta < -2 ? 'delta-down' : 'delta-same';
            var deltaText = delta > 0 ? '+' + delta.toFixed(1) : delta.toFixed(1);
            html += '<div class="threat-matrix-row">' +
                '<div class="state-label">' + _escHtml(s.name) + '</div>' +
                '<div class="threat-bar-track">' +
                    '<div class="threat-bar-fill" style="width:' + score + '%;background:' + color + '"></div>' +
                '</div>' +
                '<span style="font-size:11px;min-width:32px;color:var(--color-text-secondary)">' + score + '</span>' +
                '<span class="delta-badge ' + deltaClass + '">' + deltaText + '</span>' +
            '</div>';
        });
        html += '</div>';
        container.innerHTML = html;
    },

    _openEntry: function(id) {
        window.location.href = '/web#id=' + id + '&model=osint.feed.entry&view_type=form';
    },

    buildSourceTabs: function(container, callback) {
        var sources = [
            {key:'all',   label:'All Sources'},
            {key:'acled', label:'ACLED'},
            {key:'gdelt', label:'GDELT'},
            {key:'rss',   label:'News RSS'},
            {key:'reliefweb', label:'ReliefWeb'},
            {key:'manual', label:'Manual'},
        ];
        var self = this;
        var html = '';
        sources.forEach(function(s) {
            html += '<span class="osint-source-tab' + (s.key==='all'?' active':'') + '" ' +
                    'data-source="' + s.key + '">' + s.label + '</span>';
        });
        container.innerHTML = html;
        container.querySelectorAll('.osint-source-tab').forEach(function(tab) {
            tab.addEventListener('click', function() {
                container.querySelectorAll('.osint-source-tab').forEach(function(t){ t.classList.remove('active'); });
                tab.classList.add('active');
                if (callback) callback(tab.dataset.source);
            });
        });
    }
};

function _escHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

});
