odoo.define('generic_request_mail.ChatThread', function (require) {
    "use strict";

    var Thread = require('mail.widget.Thread');

    Thread.include({
        events: _.extend({}, Thread.prototype.events, {
            "click .o_thread_message_request": 'on_request_create',

        }),

        on_request_create: function (event) {
            event.preventDefault();
            var message = this.call(
                'mail_service',
                'getMessage',
                $(event.currentTarget).data('message-id')
            );
            var subject =
                message._subject ? "<h2>" + message._subject + "<h2/>" : '';
            var author_id = message._serverAuthorID[0];
            var context = {
                'default_request_text': subject + message._body,
                'from_message_id': message._id,
            };
            if (author_id !== 0) {
                context.default_author_id = author_id;
            }
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: "request.request",
                views: [[false, 'form']],
                context: context,
                target: 'current',
            });
        },

    });

    return Thread;

});
