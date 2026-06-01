/** @odoo-module **/

/*
 * Odoo 15 keeps `bus_service` as a *legacy* service (registered on
 * `core.serviceRegistry`). It is never copied into the new "wowl" env, so any
 * native component that calls `useService("bus_service")` blows up with
 *   "Service bus_service is not available"
 * during WebClient.setup(). Because the WebClient is the root component, that
 * exception aborts the whole mount and /web renders a blank page after login.
 *
 * OCA's generic_mixin (a dependency of generic_request / generic_location, which
 * this project relies on) ships exactly such a patch
 * (generic_mixin/static/src/js/web_client.js), which is what triggers the crash.
 *
 * Fix: register a thin wowl `bus_service` that proxies every call to the legacy
 * bus instance. The legacy services are deployed onto `owl.Component.env` before
 * the WebClient is mounted, and the proxy resolves the real instance lazily at
 * call time, so it works regardless of service start ordering.
 */

import {registry} from "@web/core/registry";

const {Component} = owl;

function legacyBus() {
    const env = Component.env;
    return (env && env.services && env.services.bus_service) || null;
}

const busServiceCompat = {
    start() {
        return new Proxy(
            {},
            {
                get(target, prop) {
                    const bus = legacyBus();
                    if (!bus) {
                        // Bus not deployed yet — return a harmless no-op so that
                        // early/defensive access never throws.
                        return () => undefined;
                    }
                    const value = bus[prop];
                    return typeof value === "function" ? value.bind(bus) : value;
                },
            }
        );
    },
};

// Only register if nothing else already provides a wowl bus_service.
if (!registry.category("services").contains("bus_service")) {
    registry.category("services").add("bus_service", busServiceCompat);
}
