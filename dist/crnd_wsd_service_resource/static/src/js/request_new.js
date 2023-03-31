odoo.define('crnd_wsd_service_resource.new_request', function (require) {
    'use strict';

    var request_new = require('crnd_wsd.new_request');
    var RequestCreateWidget = request_new.RequestCreateWidget;

    RequestCreateWidget.include({
        _get_resource_search_params: function () {
            var self = this;
            var res = self._super.apply(self, arguments);

            var $service = self.$target.find('input[name="service_id"]');
            var service_id = parseInt($service.val(), 10);
            return _.extend(res, {
                'service_id': service_id,
            });
        },
    });
});
