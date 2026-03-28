/** @odoo-module **/
/* NRS Theme v5 — Grouped apps menu replacing web_responsive default grid */

import {AppsMenu} from "@web_responsive/components/apps_menu/apps_menu.esm";
import {patch} from "web.utils";

const {useState} = owl.hooks;

// Define app groups: key = group label, value = list of app names
const APP_GROUPS = [
    {
        label: "Service Desk",
        names: ["Requests", "Discuss"],
        featured: true,
    },
    {
        label: "Operations",
        names: ["Services", "Locations", "Teams"],
    },
    {
        label: "Configuration",
        names: ["Tags", "Rules"],
    },
    {
        label: "Administration",
        names: ["Settings", "Apps", "Dashboards", "Link Tracker"],
    },
];

patch(AppsMenu.prototype, "myservice_theme_v5.GroupedAppsMenu", {
    setup() {
        this._super();
        this.appGroups = APP_GROUPS;
    },

    /**
     * Group apps into the defined categories.
     * Apps not in any group go into "Other".
     */
    groupApps(apps) {
        const grouped = [];
        const assigned = new Set();

        for (const group of this.appGroups) {
            const items = [];
            for (const app of apps) {
                if (group.names.includes(app.name)) {
                    items.push(app);
                    assigned.add(app.id);
                }
            }
            if (items.length) {
                grouped.push({
                    label: group.label,
                    featured: group.featured || false,
                    apps: items,
                });
            }
        }

        // Collect ungrouped apps
        const other = apps.filter((app) => !assigned.has(app.id));
        if (other.length) {
            grouped.push({
                label: "Other",
                featured: false,
                apps: other,
            });
        }

        return grouped;
    },
});
