/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
const { Component, useState, onMounted, onWillUnmount, useRef } = owl;

// ── Tier / Status helpers ────────────────────────────────────────────────────
const TIER_LABEL  = { delta: 'DELTA', charlie: 'CHARLIE', bravo: 'BRAVO' };
const TIER_COLOR  = { delta: '#c8102e', charlie: '#f59e0b', bravo: '#3b82f6' };
const STATUS_LABEL = { active: 'ACTIVE', detained: 'DETAINED', cleared: 'CLEARED', pending: 'PENDING' };

// ── Subject Card ─────────────────────────────────────────────────────────────
class WatchlistCard extends Component {
    setup() {
        this.tierLabel  = TIER_LABEL[this.props.subject.tier]  || this.props.subject.tier.toUpperCase();
        this.statusLabel = STATUS_LABEL[this.props.subject.status] || this.props.subject.status.toUpperCase();
        this.tierColor  = TIER_COLOR[this.props.subject.tier]  || '#64748b';
        this.initials   = this.props.subject.name.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase();
    }
    get chargeShort() {
        const c = this.props.subject.charge || '';
        return c.length > 60 ? c.substring(0, 60) + '…' : c;
    }
    get locShort() {
        return (this.props.subject.location || '').replace('Last seen: ', '');
    }
    onCardClick() {
        this.props.onSelect(this.props.subject);
    }
}
WatchlistCard.template = 'nrs_watchlist.WatchlistCard';
WatchlistCard.props    = ['subject', 'onSelect'];

// ── Detail Overlay ────────────────────────────────────────────────────────────
class WatchlistDetail extends Component {
    setup() {
        this.orm = useService('orm');
        this.notification = useService('notification');
    }
    get subject() { return this.props.subject; }
    get tierLabel()  { return TIER_LABEL[this.subject.tier]   || this.subject.tier; }
    get statusLabel(){ return STATUS_LABEL[this.subject.status]|| this.subject.status; }
    get tierColor()  { return TIER_COLOR[this.subject.tier]   || '#64748b'; }
    get initials()   { return this.subject.name.split(' ').slice(0,2).map(w=>w[0]).join('').toUpperCase(); }

    async flagActive() {
        await this.orm.call('nrs.watchlist.subject', 'action_flag_active', [[this.subject.id]]);
        this.notification.add('Subject flagged as ACTIVE', { type: 'warning' });
        this.props.onClose();
        this.props.onRefresh();
    }
    async raiseAlert() {
        await this.orm.call('nrs.watchlist.subject', 'action_raise_alert', [[this.subject.id]]);
        this.notification.add('Alert raised for ' + this.subject.name, { type: 'danger' });
        this.props.onClose();
    }
    async markCleared() {
        await this.orm.call('nrs.watchlist.subject', 'action_mark_cleared', [[this.subject.id]]);
        this.notification.add('Subject marked CLEARED', { type: 'success' });
        this.props.onClose();
        this.props.onRefresh();
    }
}
WatchlistDetail.template = 'nrs_watchlist.WatchlistDetail';
WatchlistDetail.props    = ['subject', 'onClose', 'onRefresh'];

// ── Main Board ────────────────────────────────────────────────────────────────
class NrsWatchlistBoard extends Component {
    setup() {
        this.orm = useService('orm');
        this.boardRef = useRef('board');

        this.state = useState({
            subjects:  [],
            filtered:  [],
            selected:  null,
            search:    '',
            filters:   { delta: true, charlie: true, bravo: true, active: true, detained: true, cleared: true },
            kiosk:     true,
            loading:   true,
            clock:     '--:--:--',
        });

        this._scrollTimer  = null;
        this._clockTimer   = null;
        this._scrollPos    = 0;

        onMounted(async () => {
            await this.loadData();
            this.startClock();
            setTimeout(() => this.startKiosk(), 1000);
        });

        onWillUnmount(() => {
            this.stopKiosk();
            if (this._clockTimer) clearInterval(this._clockTimer);
        });
    }

    // ── Data ─────────────────────────────────────────────────────────────────
    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call('nrs.watchlist.subject', 'get_board_data', []);
            this.state.subjects = data;
            this.applyFilters();
        } catch (e) {
            console.error('Watchlist load error:', e);
        }
        this.state.loading = false;
    }

    // ── Filters ───────────────────────────────────────────────────────────────
    toggleFilter(key) {
        this.state.filters[key] = !this.state.filters[key];
        this.applyFilters();
    }

    applyFilters() {
        const q = this.state.search.toLowerCase();
        const f = this.state.filters;
        this.state.filtered = this.state.subjects.filter(s =>
            f[s.tier] && f[s.status] &&
            (!q || s.name.toLowerCase().includes(q) ||
                   (s.alias||'').toLowerCase().includes(q) ||
                   (s.charge||'').toLowerCase().includes(q))
        );
        this._scrollPos = 0;
    }

    onSearch(ev) {
        this.state.search = ev.target.value;
        this.applyFilters();
    }

    // ── Kiosk scroll ──────────────────────────────────────────────────────────
    startKiosk() {
        this.stopKiosk();
        this._scrollTimer = setInterval(() => {
            const el = this.boardRef.el;
            if (!el) return;
            this._scrollPos += 1;
            if (this._scrollPos >= el.scrollHeight - el.clientHeight + 10) {
                this._scrollPos = 0;
            }
            el.scrollTop = this._scrollPos;
        }, 30);
    }

    stopKiosk() {
        if (this._scrollTimer) { clearInterval(this._scrollTimer); this._scrollTimer = null; }
    }

    toggleKiosk() {
        this.state.kiosk = !this.state.kiosk;
        this.state.kiosk ? this.startKiosk() : this.stopKiosk();
    }

    onBoardMouseEnter() { if (this.state.kiosk) this.stopKiosk(); }
    onBoardMouseLeave() { if (this.state.kiosk) this.startKiosk(); }

    // ── Detail ────────────────────────────────────────────────────────────────
    selectSubject(subject) { this.stopKiosk(); this.state.selected = subject; }
    closeDetail()          { this.state.selected = null; if (this.state.kiosk) this.startKiosk(); }

    // ── Clock ─────────────────────────────────────────────────────────────────
    startClock() {
        const tick = () => {
            this.state.clock = new Date().toLocaleTimeString('en-GB', {
                timeZone: 'Africa/Lagos', hour12: false
            }) + ' WAT';
        };
        tick();
        this._clockTimer = setInterval(tick, 1000);
    }

    // ── KPIs ──────────────────────────────────────────────────────────────────
    get kpiTotal()    { return this.state.subjects.length; }
    get kpiDelta()    { return this.state.subjects.filter(s=>s.tier==='delta').length; }
    get kpiCharlie()  { return this.state.subjects.filter(s=>s.tier==='charlie').length; }
    get kpiBravo()    { return this.state.subjects.filter(s=>s.tier==='bravo').length; }
    get kpiDetained() { return this.state.subjects.filter(s=>s.status==='detained').length; }
}
NrsWatchlistBoard.template    = 'nrs_watchlist.WatchlistBoard';
NrsWatchlistBoard.components  = { WatchlistCard, WatchlistDetail };

registry.category('actions').add('nrs_watchlist_board', NrsWatchlistBoard);
