/** @odoo-module **/
/* NRS Theme v5 — Left Sidebar Navigation */

import {WebClient} from "@web/webclient/webclient";
import {useService} from "@web/core/utils/hooks";
import {patch} from "@web/core/utils/patch";
import {onMounted} from "@odoo/owl";

const COLLAPSED_KEY = "nrs_sidebar_collapsed";

const NRS_GROUPS = [
    {
        label: "DASHBOARDS",
        apps: ["Facility Command Center"],
    },
    {
        label: "SERVICE DESK",
        apps: ["Discuss", "Requests", "Triage Inbox", "All Requests", "Overdue", "My Jobs"],
    },
    {
        label: "OPERATIONS",
        apps: ["Operations Command Center", "Services", "Resources", "Locations", "Teams"],
    },
    {
        label: "FACILITIES",
        apps: ["Building Services", "Plumbing & Drainage", "Plant & Machinery"],
    },
    {
        label: "SECURITY & SAFETY",
        apps: ["Security Command Center", "Security & Safety", "Case Management", "OSINT", "AI Patterns", "Daily Brief"],
    },
    {
        label: "FLEET & TRANSPORT",
        apps: ["Fleet Command Center", "Fleet", "Fuel Card", "Staff Bus"],
    },
    {
        label: "ASSET REGISTER",
        apps: ["Asset Register", "Barcode Station"],
    },
    {
        label: "HR & STAFF",
        apps: ["Identity", "Employees"],
    },
    {
        label: "CONFIGURATION",
        apps: ["Tags", "Rules"],
    },
    {
        label: "ADMINISTRATION",
        apps: ["Website", "Apps", "Settings"],
    },
];

patch(WebClient.prototype, {
    setup() {
        super.setup(...arguments);
        this._nrsMenuService = useService("menu");
        // Odoo 19: OWL2 lifecycle via hooks, not a mounted() method.
        onMounted(() => {
            try {
                this._nrsInitSidebar();
                this.env.bus.addEventListener("ACTION_MANAGER:UI-UPDATED", () =>
                    this._nrsSetActiveItem()
                );
            } catch (e) {
                console.warn("[nrs-sidebar] init failed", e);
            }
        });
    },

    _nrsInitSidebar() {
        var existing = document.getElementById("nrs-sidebar");
        if (existing) existing.remove();

        var collapsed = localStorage.getItem(COLLAPSED_KEY) === "1";
        document.body.classList.toggle("nrs-sidebar-collapsed", collapsed);
        document.body.classList.toggle("nrs-sidebar-expanded", !collapsed);

        var sidebar = document.createElement("div");
        sidebar.id = "nrs-sidebar";
        if (collapsed) sidebar.classList.add("collapsed");

        // Logo
        var logo = document.createElement("div");
        logo.className = "nrs-sidebar-logo";
        logo.innerHTML =
            '<a href="/web" class="nrs-logo-link">' +
                '<img class="nrs-logo-img" src="/web/image/res.company/1/logo" alt="Company"/>' +
            '</a>';
        sidebar.appendChild(logo);

        // Toggle button
        var self = this;
        var toggle = document.createElement("div");
        toggle.className = "nrs-sidebar-toggle";
        toggle.innerHTML = '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M15 18l-6-6 6-6"/></svg>';
        toggle.addEventListener("click", function () {
            self._nrsToggleSidebar(sidebar);
        });
        sidebar.appendChild(toggle);

        // Nav inner
        var inner = document.createElement("div");
        inner.className = "nrs-nav-inner";

        var apps = this._nrsMenuService.getApps();
        var assigned = {};

        // Build grouped nav
        for (var g = 0; g < NRS_GROUPS.length; g++) {
            var group = NRS_GROUPS[g];
            var members = [];
            for (var a = 0; a < apps.length; a++) {
                if (group.apps.indexOf(apps[a].name) !== -1) {
                    members.push(apps[a]);
                    assigned[apps[a].id] = true;
                }
            }
            if (!members.length) continue;

            var sectionLabel = document.createElement("div");
            sectionLabel.className = "nrs-nav-section-label";
            sectionLabel.textContent = group.label;
            inner.appendChild(sectionLabel);

            for (var m = 0; m < members.length; m++) {
                inner.appendChild(this._nrsCreateNavItem(members[m]));
            }

            var divider = document.createElement("div");
            divider.className = "nrs-nav-divider";
            inner.appendChild(divider);
        }

        // Catch-all for any unmatched apps
        var others = [];
        for (var i = 0; i < apps.length; i++) {
            if (!assigned[apps[i].id]) others.push(apps[i]);
        }
        if (others.length) {
            var otherLabel = document.createElement("div");
            otherLabel.className = "nrs-nav-section-label";
            otherLabel.textContent = "Other";
            inner.appendChild(otherLabel);
            for (var o = 0; o < others.length; o++) {
                inner.appendChild(this._nrsCreateNavItem(others[o]));
            }
        }

        sidebar.appendChild(inner);

        // User info
        var initials = this._nrsGetInitials();
        var userDiv = document.createElement("div");
        userDiv.className = "nrs-sidebar-user";
        userDiv.innerHTML =
            '<div class="nrs-user-avatar">' + initials + '</div>' +
            '<div class="nrs-user-name">' + (this._nrsGetUserName()) + '</div>';
        sidebar.appendChild(userDiv);

        document.body.prepend(sidebar);
        this._nrsSetActiveItem();
    },

    _nrsGetIcon(appName) {
        var icons = {
            "Discuss": '<path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>',
            "Requests": '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/>',
            "Services": '<circle cx="12" cy="12" r="3"/><path d="M19.07 4.93l-1.41 1.41"/>',
            "Resources": '<path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/>',
            "Locations": '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/>',
            "Teams": '<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/>',
            "Tags": '<path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/>',
            "Rules": '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
            "Operations": '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>',
            "Facilities": '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>',
            "Security": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
            "Security & Safety": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
            "Daily Brief": '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
            "Fleet": '<rect x="1" y="3" width="15" height="13" rx="2"/><path d="M16 8h4l3 3v5h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/>',
            "Fleet Command Center": '<rect x="1" y="3" width="15" height="13" rx="2"/><path d="M16 8h4l3 3v5h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/>',
            "Operations Command Center": '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>',
            "Triage Inbox": '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z"/>',
            "All Requests": '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/>',
            "Overdue": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
            "My Jobs": '<path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="8.5" cy="7" r="4"/><polyline points="17 11 19 13 23 9"/>',
            "Employees": '<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/>',
            "Website": '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/>',
            "Apps": '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>',
            "Settings": '<circle cx="12" cy="12" r="3"/><path d="M19.07 4.93l-1.41 1.41M4.93 4.93l1.41 1.41M12 2v2M12 20v2M2 12h2M20 12h2M19.07 19.07l-1.41-1.41M4.93 19.07l1.41-1.41"/>',
            "FM Dashboard": '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>',
            "Facility Command Center": '<path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
            "Building Services": '<path d="M2 22h20"/><path d="M6 22V6l6-4 6 4v16"/><path d="M10 10h4"/><path d="M10 14h4"/>',
            "Plumbing & Drainage": '<path d="M12 2v6m0 4v10M5 8h14M5 8a3 3 0 00-3 3v2a3 3 0 003 3h14a3 3 0 003-3v-2a3 3 0 00-3-3"/>',
            "Plant & Machinery": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>',
            "Security Command Center": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
            "Security Brief": '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
            "Case Management": '<path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>',
            "OSINT": '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
            "AI Patterns": '<path d="M12 2a2 2 0 012 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 017 7h1.27c.34-.6.99-1 1.73-1a2 2 0 110 4c-.74 0-1.39-.4-1.73-1H20a7 7 0 01-7 7v1.27c.6.34 1 .99 1 1.73a2 2 0 11-4 0c0-.74.4-1.39 1-1.73V18a7 7 0 01-7-7H2.73c-.34.6-.99 1-1.73 1a2 2 0 110-4c.74 0 1.39.4 1.73 1H5a7 7 0 017-7V5.73c-.6-.34-1-.99-1-1.73a2 2 0 012-2z"/>',
            "Fuel Card": '<rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/>',
            "Staff Bus": '<path d="M5 17h14V5H5v12zM2 17h20M7 21l1-4M16 21l1-4"/><circle cx="7" cy="9" r="1"/><circle cx="17" cy="9" r="1"/>',
            "Asset Register": '<path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/>',
            "Barcode Station": '<path d="M3 5v14M7 5v14M10 5v14M13 5v14M17 5v14M21 5v14"/>',
            "Identity": '<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/>',
            "default": '<circle cx="12" cy="12" r="10"/>'
        };
        var path = icons[appName] || icons["default"];
        return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + path + '</svg>';
    },

    _nrsCreateNavItem(app) {
        var self = this;
        var item = document.createElement("a");
        item.className = "nrs-nav-item";
        item.dataset.appId = app.id;
        item.href = "#";

        var iconWrap = document.createElement("span");
        iconWrap.className = "nrs-nav-icon-wrap";
        iconWrap.innerHTML = this._nrsGetIcon(app.name);
        item.appendChild(iconWrap);

        var label = document.createElement("span");
        label.className = "nrs-nav-label";
        label.textContent = app.name;

        var tooltip = document.createElement("span");
        tooltip.className = "nrs-tooltip";
        tooltip.textContent = app.name;

        item.appendChild(label);
        item.appendChild(tooltip);

        item.addEventListener("click", function (e) {
            e.preventDefault();
            self._nrsMenuService.selectMenu(app);
            self._nrsSetActiveItem(app.id);
        });

        return item;
    },

    _nrsSetActiveItem(activeId) {
        var currentApp = this._nrsMenuService.getCurrentApp();
        var id = activeId || (currentApp && currentApp.id);
        var items = document.querySelectorAll("#nrs-sidebar .nrs-nav-item");
        for (var i = 0; i < items.length; i++) {
            var isActive = String(items[i].dataset.appId) === String(id);
            items[i].classList.toggle("active", isActive);
        }
    },

    _nrsToggleSidebar(sidebar) {
        var collapsed = sidebar.classList.toggle("collapsed");
        document.body.classList.toggle("nrs-sidebar-collapsed", collapsed);
        document.body.classList.toggle("nrs-sidebar-expanded", !collapsed);
        localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
    },

    _nrsGetInitials() {
        try {
            var info = odoo.__session_info__ || {};
            var name = info.name || info.username || "U";
            return name.split(" ").map(function (n) { return n[0]; }).slice(0, 2).join("").toUpperCase();
        } catch (e) {
            return "U";
        }
    },

    _nrsGetUserName() {
        try {
            var info = odoo.__session_info__ || {};
            return info.name || info.username || "User";
        } catch (e) {
            return "User";
        }
    },
});
