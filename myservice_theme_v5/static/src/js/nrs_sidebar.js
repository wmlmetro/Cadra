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

        // Logo
        var logo = document.createElement("div");
        logo.className = "nrs-sidebar-logo";
        logo.innerHTML =
            '<div style="display:flex;flex-direction:column">' +
                '<div style="display:flex;align-items:center;gap:5px">' +
                    '<div class="nrs-logo-nrs">NR<span>S</span></div>' +
                    '<div class="nrs-logo-pipe"></div>' +
                    '<div class="nrs-logo-tag">Nigeria<br>Revenue<br>Service</div>' +
                '</div>' +
                '<span class="nrs-logo-sub">myservice</span>' +
            '</div>';
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

    _nrsCreateNavItem(app) {
        var self = this;
        var item = document.createElement("a");
        item.className = "nrs-nav-item";
        item.dataset.appId = app.id;
        item.href = "#";

        var icon = document.createElement("img");
        icon.className = "nrs-nav-icon";
        if (app.webIconData) {
            icon.src = "data:image/png;base64," + app.webIconData;
        } else {
            icon.src = "/web/static/img/logo.png";
        }
        icon.alt = app.name;

        var label = document.createElement("span");
        label.className = "nrs-nav-label";
        label.textContent = app.name;

        var tooltip = document.createElement("span");
        tooltip.className = "nrs-tooltip";
        tooltip.textContent = app.name;

        item.appendChild(icon);
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
