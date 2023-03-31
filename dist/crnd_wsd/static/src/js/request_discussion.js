/* global Promise */
odoo.define('crnd_wsd.discussion', function (require) {
    'use strict';

    var trumbowyg = require('crnd_wsd.trumbowyg');
    var portal_chatter = require('portal.chatter');
    var portal_composer = require('portal.composer');
    var publicWidget = require('web.public.widget');


    var RequestComposer = portal_composer.PortalComposer.extend({
        start: function () {
            var self = this;
            var defs = [];
            defs.push(this._super.apply(this, arguments));
            return Promise.all(defs).then(function () {
                self.$(
                    '.o_portal_chatter_composer_body textarea[name="message"]'
                ).each(function () {
                    var $textarea = $(this);
                    $textarea.trumbowyg(trumbowyg.trumbowygOptions);
                });
                self.$(
                    '.o_portal_chatter_composer_body ' +
                    'button.o_portal_chatter_composer_btn'
                ).each(function () {
                    $(this).attr('data-action', '/mail/request_chatter_post');
                });
            });
        },
    });

    // Extend mail thread widget
    var RequestChatter = portal_chatter.PortalChatter.extend({

        _createComposerWidget: function () {
            return new RequestComposer(this, this.options);
        },

    });

    var requestChatter = publicWidget.Widget.extend({
        selector: '.request_comments_chatter',

        /**
         * @override
         */

        start: function () {
            var self = this;
            var defs = [this._super.apply(this, arguments)];
            var chatter = new RequestChatter(this, this.$el.data());
            defs.push(chatter.appendTo(this.$el));
            return Promise.all(defs).then(function () {
                // Scroll to the right place after chatter loaded
                if (window.location.hash === '#' + self.$el.attr('id')) {
                    $('html, body').scrollTop(self.$el.offset().top);
                }
            });
        },
    });

    // Register widget
    publicWidget.registry.requestChatter = requestChatter;

    return {
        RequestChatter: RequestChatter,
        requestChatter: requestChatter,
    };

});
