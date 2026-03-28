/** @odoo-module **/
/* NRS Theme v5 — Left Sidebar Navigation */

import {WebClient} from "@web/webclient/webclient";
import {useService} from "@web/core/utils/hooks";
import {patch} from "web.utils";

const COLLAPSED_KEY = "nrs_sidebar_collapsed";

const NRS_GROUPS = [
    {
        label: "Service Desk",
        apps: ["Requests", "Discuss"],
    },
    {
        label: "Operations",
        apps: ["Services", "Locations", "Teams"],
    },
    {
        label: "Configuration",
        apps: ["Tags", "Rules"],
    },
    {
        label: "Administration",
        apps: ["Settings", "Apps", "Dashboards", "Link Tracker"],
    },
];

patch(WebClient.prototype, "myservice_theme_v5.NRSSidebar", {
    setup() {
        this._super(...arguments);
        this._nrsMenuService = useService("menu");
    },

    mounted() {
        this._super(...arguments);
        this._nrsInitSidebar();
        this.env.bus.on("ACTION_MANAGER:UI-UPDATED", this, () => {
            this._nrsSetActiveItem();
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

        // Logo — company logo + MyService brand
        var logo = document.createElement("div");
        logo.className = "nrs-sidebar-logo";
        logo.innerHTML =
            '<a href="/web" class="nrs-logo-link">' +
                '<img class="nrs-logo-img" src="/web/image/res.company/1/logo" alt="Company"/>' +
                '<div class="nrs-logo-brand">' +
                    '<span class="nrs-logo-name">My<span>Service</span></span>' +
                '</div>' +
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
                if (group.apps.indexOf(apps[a].name) !== -1 && !assigned[apps[a].id]) {
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

        // Catch-all
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
            "Locations": '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/>',
            "Teams": '<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/>',
            "Tags": '<path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/>',
            "Rules": '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
            "Apps": '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>',
            "Settings": '<circle cx="12" cy="12" r="3"/><path d="M19.07 4.93l-1.41 1.41M4.93 4.93l1.41 1.41M12 2v2M12 20v2M2 12h2M20 12h2M19.07 19.07l-1.41-1.41M4.93 19.07l1.41-1.41"/>',
            "Fleet": '<rect x="1" y="3" width="15" height="13" rx="2"/><path d="M16 8h4l3 3v5h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/>',
            "Staff Bus": '<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/>',
            "FM Dashboard": '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>',
            "Asset Register": '<path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/>',
            "Security Ops": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
            "OSINT": '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
            "AI Patterns": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
            "Barcode Station": '<path d="M3 9V6a1 1 0 011-1h3M3 15v3a1 1 0 001 1h3M21 9V6a1 1 0 00-1-1h-3M21 15v3a1 1 0 01-1 1h-3"/>',
            "Dashboards": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/>',
            "Link Tracker": '<path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/>',
            "Tests": '<path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/>',
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
