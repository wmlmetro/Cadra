/** @odoo-module **/
/* NRS Theme v5 — Left sidebar navigation */

import {WebClient} from "@web/webclient/webclient";
import {useService} from "@web/core/utils/hooks";
import {patch} from "web.utils";

const SIDEBAR_COLLAPSED_KEY = "nrs_sidebar_collapsed";

patch(WebClient.prototype, "myservice_theme_v5.NRSSidebar", {
    setup() {
        this._super(...arguments);
        this._nrsMenuService = useService("menu");
        this._nrsSidebarCollapsed =
            localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
    },

    mounted() {
        this._super(...arguments);
        this._nrsBuildSidebar();
        // Listen for app changes to update active state
        this.env.bus.on("ACTION_MANAGER:UI-UPDATED", this, () => {
            this._nrsUpdateActive();
        });
    },

    _nrsBuildSidebar() {
        if (this.el.querySelector(".nrs-sidebar")) return;

        const apps = this._nrsMenuService.getApps();
        const sidebar = document.createElement("div");
        sidebar.className = "nrs-sidebar" +
            (this._nrsSidebarCollapsed ? " nrs-sidebar-collapsed" : "");

        // Toggle button
        const toggle = document.createElement("div");
        toggle.className = "nrs-sidebar-toggle";
        toggle.innerHTML = '<i class="fa fa-bars"></i>';
        toggle.addEventListener("click", () => this._nrsToggleSidebar());
        sidebar.appendChild(toggle);

        // App list
        const nav = document.createElement("nav");
        nav.className = "nrs-sidebar-nav";

        apps.forEach((app) => {
            const item = document.createElement("a");
            item.className = "nrs-sidebar-item";
            item.dataset.menuId = app.id;
            item.href = "#";
            item.title = app.name;

            // Icon
            const icon = document.createElement("span");
            icon.className = "nrs-sidebar-icon";
            if (app.webIconData) {
                const img = document.createElement("img");
                img.src = "data:image/png;base64," + app.webIconData;
                img.alt = app.name;
                icon.appendChild(img);
            } else {
                icon.innerHTML = '<i class="fa fa-cube"></i>';
            }
            item.appendChild(icon);

            // Label
            const label = document.createElement("span");
            label.className = "nrs-sidebar-label";
            label.textContent = app.name;
            item.appendChild(label);

            item.addEventListener("click", (ev) => {
                ev.preventDefault();
                this._nrsMenuService.selectMenu(app);
            });

            nav.appendChild(item);
        });

        sidebar.appendChild(nav);

        // Insert sidebar before the action manager
        this.el.prepend(sidebar);

        // Add layout class to body
        this.el.classList.add("nrs-has-sidebar");
        if (this._nrsSidebarCollapsed) {
            this.el.classList.add("nrs-sidebar-is-collapsed");
        }

        this._nrsUpdateActive();
    },

    _nrsToggleSidebar() {
        const sidebar = this.el.querySelector(".nrs-sidebar");
        if (!sidebar) return;

        this._nrsSidebarCollapsed = !this._nrsSidebarCollapsed;
        sidebar.classList.toggle("nrs-sidebar-collapsed", this._nrsSidebarCollapsed);
        this.el.classList.toggle("nrs-sidebar-is-collapsed", this._nrsSidebarCollapsed);
        localStorage.setItem(
            SIDEBAR_COLLAPSED_KEY,
            this._nrsSidebarCollapsed ? "1" : "0"
        );
    },

    _nrsUpdateActive() {
        const sidebar = this.el.querySelector(".nrs-sidebar");
        if (!sidebar) return;

        const currentApp = this._nrsMenuService.getCurrentApp();
        sidebar.querySelectorAll(".nrs-sidebar-item").forEach((item) => {
            const isActive =
                currentApp && item.dataset.menuId === String(currentApp.id);
            item.classList.toggle("active", isActive);
        });
    },
});
