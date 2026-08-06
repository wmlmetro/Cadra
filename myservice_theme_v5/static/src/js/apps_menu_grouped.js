/** @odoo-module **/
/* NRS Theme v5 — Grouped apps menu replacing web_responsive default grid */

import {AppsMenu} from "@web_responsive/components/apps_menu/apps_menu.esm";
import {patch} from "@web/core/utils/patch";
import {onMounted, onPatched} from "@odoo/owl";

const APP_GROUPS = [
    {label: "Service Desk", names: ["Requests", "Discuss"], featured: true},
    {label: "Operations", names: ["Services", "Locations", "Teams"]},
    {label: "Configuration", names: ["Tags", "Rules"]},
    {label: "Administration", names: ["Settings", "Apps", "Dashboards", "Link Tracker"]},
];

patch(AppsMenu.prototype, {
    setup() {
        super.setup(...arguments);
        // Odoo 19: OWL2 lifecycle via hooks, not mounted()/patched() methods.
        onMounted(() => this._nrsGroupApps());
        onPatched(() => this._nrsGroupApps());
    },
    _nrsGroupApps() {
        if (!this.state.open) return;
        const menu = this.el && this.el.querySelector(".dropdown-menu");
        if (!menu || menu.querySelector(".nrs-apps-grid")) return;

        // Collect all app tiles
        const tiles = Array.from(menu.querySelectorAll(":scope > .o_app"));
        if (!tiles.length) return;

        // Build a map of app name -> tile element
        const tileMap = {};
        tiles.forEach((tile) => {
            const nameEl = tile.querySelector("a > div");
            if (nameEl) {
                tileMap[nameEl.textContent.trim()] = tile;
            }
        });

        // Build the grouped grid
        const grid = document.createElement("div");
        grid.className = "nrs-apps-grid";

        const assigned = new Set();

        APP_GROUPS.forEach((group) => {
            const groupApps = group.names.filter((n) => tileMap[n]);
            if (!groupApps.length) return;

            const section = document.createElement("div");
            section.className = "nrs-app-group";

            const label = document.createElement("div");
            label.className = "nrs-app-group-label";
            label.textContent = group.label;
            section.appendChild(label);

            const row = document.createElement("div");
            row.className = "nrs-app-group-row";

            groupApps.forEach((name) => {
                const tile = tileMap[name];
                tile.classList.add("nrs-app-tile");
                if (group.featured) tile.classList.add("nrs-app-tile-featured");
                row.appendChild(tile);
                assigned.add(name);
            });

            section.appendChild(row);
            grid.appendChild(section);
        });

        // Other — unmatched apps
        const otherApps = Object.keys(tileMap).filter((n) => !assigned.has(n));
        if (otherApps.length) {
            const section = document.createElement("div");
            section.className = "nrs-app-group";

            const label = document.createElement("div");
            label.className = "nrs-app-group-label";
            label.textContent = "Other";
            section.appendChild(label);

            const row = document.createElement("div");
            row.className = "nrs-app-group-row";

            otherApps.forEach((name) => {
                const tile = tileMap[name];
                tile.classList.add("nrs-app-tile");
                row.appendChild(tile);
            });

            section.appendChild(row);
            grid.appendChild(section);
        }

        // Insert grid before the search container (or at the end)
        const search = menu.querySelector(".search-container");
        if (search) {
            menu.insertBefore(grid, search);
        } else {
            menu.appendChild(grid);
        }
    },
});
