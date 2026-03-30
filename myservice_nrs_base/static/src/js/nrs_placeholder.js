odoo.define('myservice_nrs_base.NrsPlaceholder', function (require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');

    var NrsPlaceholder = AbstractAction.extend({
        hasControlPanel: false,

        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                var action = self.action || {};
                var params = action.params || {};
                var title = params.title || action.display_name || action.name || 'Coming Soon';
                var subtitle = params.subtitle || 'This module is under development.';

                self.$el.html(
                    '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;' +
                    'min-height:70vh;padding:40px;text-align:center;">' +
                    '<div style="width:64px;height:64px;border-radius:16px;background:#FBE9EC;' +
                    'display:flex;align-items:center;justify-content:center;margin-bottom:24px;">' +
                    '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" ' +
                    'stroke="#C8102E" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' +
                    '<path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>' +
                    '<polyline points="9 22 9 12 15 12 15 22"/>' +
                    '</svg></div>' +
                    '<h2 style="font-size:22px;font-weight:600;color:#1A1A1A;margin:0 0 8px;">' +
                    _.escape(title) + '</h2>' +
                    '<p style="font-size:15px;color:#6B7280;max-width:400px;margin:0 0 32px;line-height:1.6;">' +
                    _.escape(subtitle) + '</p>' +
                    '<div style="display:inline-flex;align-items:center;gap:8px;background:#FBE9EC;' +
                    'border:1px solid #F0C0C8;border-radius:20px;padding:8px 20px;">' +
                    '<div style="width:8px;height:8px;border-radius:50%;background:#C8102E;"></div>' +
                    '<span style="font-size:13px;font-weight:500;color:#C8102E;">Content in development</span>' +
                    '</div></div>'
                );
            });
        },
    });

    core.action_registry.add('nrs_placeholder', NrsPlaceholder);
    return NrsPlaceholder;
});
