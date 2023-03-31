odoo.define('generic_request.FormController', function (require) {
    "use strict";

    var FormController = require('web.FormController');

    FormController.include({
        custom_events: _.extend({}, FormController.prototype.custom_events, {
            move_request: '_moveRequest',
        }),

        _moveRequest: function (event) {
            var self = this;
            return this.saveRecord.apply(this).then(function () {
                return self._rpc({
                    model: event.target.model,
                    method: 'api_move_request',
                    args: [
                        [event.target.res_id],
                        event.data.route.id,
                    ],
                }).then(function (result) {
                    if (result) {
                        self.do_action(result, {
                            on_close: function () {
                                self.reload();
                            },
                        });
                    } else {
                        self.reload();
                    }
                });
            });
        },
    });

});
