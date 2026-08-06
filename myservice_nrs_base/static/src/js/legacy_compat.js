/**
 * NRS legacy compatibility shim for Odoo 19.
 *
 * Odoo 17+ removed the legacy JS modules our client-action dashboards rely on
 * (web.core, web.rpc, web.ajax, web.session, web.AbstractAction) and dropped
 * jQuery auto-loading. Rewriting ~4k LOC of jQuery dashboards to native OWL is
 * a large effort; instead we re-provide those module names — backed by the real
 * Odoo 19 services — so the existing dashboards run with only a one-line
 * `odoo.define(...)` dependency-array fix each.
 *
 * This file is NOT an @odoo-module ESM file: it uses raw
 * `odoo.define(name, [deps], factory)` (the loader's native form) so it can
 * register legacy module *names* that the dashboards import via `require(...)`.
 */

// Legacy Odoo added Deferred/Promise.prototype.guardedCatch (a .catch() that
// ignores "unloaded widget" rejections). Native promises lack it; re-add a
// simple alias so legacy dashboards' rpc chains keep working.
if (!Promise.prototype.guardedCatch) {
    // eslint-disable-next-line no-extend-native
    Promise.prototype.guardedCatch = function (onRejected) {
        return this.catch(onRejected);
    };
}

// ── web.session → @web/session ──────────────────────────────────────────────
odoo.define("web.session", ["@web/session"], function (require) {
    "use strict";
    return require("@web/session").session;
});

// ── web.core → _t + an action_registry.add() shim ───────────────────────────
odoo.define("web.core", ["@web/core/registry", "@web/core/l10n/translation"], function (require) {
    "use strict";
    const { registry } = require("@web/core/registry");
    const { _t } = require("@web/core/l10n/translation");
    return {
        _t,
        // Legacy code did core.action_registry.add(tag, ActionClass).
        action_registry: {
            add: (tag, ActionClass) =>
                registry.category("actions").add(tag, ActionClass, { force: true }),
        },
        qweb: {},
    };
});

// ── web.rpc → rpc.query({model, method, args, kwargs}) / ({route, params}) ───
odoo.define("web.rpc", ["@web/core/network/rpc"], function (require) {
    "use strict";
    const { rpc } = require("@web/core/network/rpc");
    return {
        query(params) {
            if (params && params.route) {
                return rpc(params.route, params.params || {});
            }
            return rpc("/web/dataset/call_kw", {
                model: params.model,
                method: params.method,
                args: params.args || [],
                kwargs: params.kwargs || {},
            });
        },
    };
});

// ── web.ajax → jsonRpc(route, 'call', params) ───────────────────────────────
odoo.define("web.ajax", ["@web/core/network/rpc"], function (require) {
    "use strict";
    const { rpc } = require("@web/core/network/rpc");
    return {
        jsonRpc: (route, _method, params) => rpc(route, params || {}),
        rpc: (route, params) => rpc(route, params || {}),
    };
});

// ── web.AbstractAction → an OWL Component adapter with a Widget-ish API ──────
odoo.define(
    "web.AbstractAction",
    ["@odoo/owl", "@web/core/utils/hooks", "@web/core/utils/render"],
    function (require) {
        "use strict";
        const { Component, xml, onMounted, onWillUnmount, useRef } = require("@odoo/owl");
        const { useService } = require("@web/core/utils/hooks");
        const { renderToElement } = require("@web/core/utils/render");

        class LegacyAction extends Component {
            setup() {
                this.__ref = useRef("root");
                this.actionService = useService("action");
                this.ormService = useService("orm");
                // Widget-era props the dashboards may read.
                this.action = this.props.action || {};
                this.options = this.props.options || {};
                if (typeof this.init === "function") {
                    try {
                        this.init(null, this.props.action, this.props.options || {});
                    } catch (e) {
                        console.warn("[nrs-legacy] init() failed", e);
                    }
                }
                onMounted(async () => {
                    this.el = this.__ref.el;
                    // Legacy AbstractAction rendered `this.template` (a QWeb
                    // template name) into $el before start(); reproduce that so
                    // start()'s this.$('.selector') lookups resolve.
                    if (this.template) {
                        try {
                            const rendered = renderToElement(this.template, { widget: this });
                            this.el.appendChild(rendered);
                        } catch (e) {
                            console.error("[nrs-legacy] template render failed:", this.template, e);
                        }
                    }
                    this.$el = window.$(this.el);
                    this._bindLegacyEvents();
                    try {
                        if (typeof this.start === "function") {
                            await this.start();
                        }
                    } catch (e) {
                        console.error("[nrs-legacy] start() failed", e);
                    }
                });
                onWillUnmount(() => {
                    try {
                        if (typeof this.destroy === "function") {
                            this.destroy();
                        }
                    } catch (e) {
                        /* ignore */
                    }
                });
            }

            // Widget.prototype._super was a no-op-ish chain; dashboards call it
            // from start()/init() and rely on a thenable return.
            _super() {
                return Promise.resolve();
            }

            // Scoped jQuery find, as Widget.prototype.$.
            $(selector) {
                return this.$el.find(selector);
            }

            do_action(action, options) {
                return this.actionService.doAction(action, options);
            }

            _bindLegacyEvents() {
                const events = this.events || {};
                for (const key of Object.keys(events)) {
                    const spaceIdx = key.indexOf(" ");
                    const type = spaceIdx === -1 ? key : key.slice(0, spaceIdx);
                    const selector = spaceIdx === -1 ? null : key.slice(spaceIdx + 1);
                    const raw = events[key];
                    const handler = typeof raw === "string" ? this[raw] : raw;
                    if (typeof handler !== "function") {
                        continue;
                    }
                    const bound = (ev) => handler.call(this, ev);
                    if (selector) {
                        this.$el.on(type, selector, bound);
                    } else {
                        this.$el.on(type, bound);
                    }
                }
            }

            // Widget.extend({...}) → subclass with the prototype merged in.
            static extend(proto) {
                const Base = this;
                class Extended extends Base {}
                Object.assign(Extended.prototype, proto);
                return Extended;
            }
        }
        LegacyAction.template = xml`<div t-ref="root" class="o_client_action o_nrs_legacy_action" style="height:100%; overflow:auto;"/>`;
        // Client-action components must accept the standard action props.
        LegacyAction.props = ["*"];
        return LegacyAction;
    }
);
