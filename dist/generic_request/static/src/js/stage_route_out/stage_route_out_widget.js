odoo.define('generic_request.RequestStageRouteOutWidget', function (require) {
    "use strict";

    var fieldRegistry = require('web.field_registry');
    var AbstractField = require('web.AbstractField');

    var RequestStageRouteOutWidget = AbstractField.extend({

        _renderWidget: function () {
            var self = this;
            var value_json = JSON.parse(this.value);

            if (!value_json.routes || !this.res_id) {
                return;
            }

            this.$el.addClass('o_statusbar_buttons');
            this.$el.addClass('stage_route_out_widget');
            this.$el.addClass('pr-1');

            _.each(value_json.routes, function (route) {
                var btn_style = route.btn_style === 'default'
                    ? 'btn-primary'
                    : 'btn-' + route.btn_style;

                var $route_btn = $('<button>')
                    .text(route.name)
                    .addClass('btn')
                    .addClass(btn_style)
                    .appendTo(self.$el);

                $route_btn.on('click', self._onBtnClick.bind(self, route));
            });
        },

        _renderEdit: function () {
            this._renderWidget();
        },

        _renderReadonly: function () {
            this._renderWidget();
        },

        _onBtnClick: function (route) {
            this.trigger_up('move_request', {
                route: route,
            });
        },
    });

    fieldRegistry.add('stage_route_out_widget', RequestStageRouteOutWidget);

    return RequestStageRouteOutWidget;
});
