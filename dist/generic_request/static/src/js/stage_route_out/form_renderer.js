odoo.define('generic_request.FormRenderer', function (require) {
    "use strict";

    var FormRenderer = require('web.FormRenderer');

    FormRenderer.include({
        // This code is needed to display the stage_route_out_widget
        // in the form header button block
        _renderTagHeader: function (node) {
            var $statusbar = this._super.apply(this, arguments);

            var self = this;
            _.each(node.children, function (child) {
                if (child.tag === 'div' &&
                    child.attrs.class === 'stage_route_out_widget') {

                    var fields = child.children.filter(function (e) {
                        return e.tag === 'field' &&
                            e.attrs.widget === 'stage_route_out_widget';
                    });

                    if (fields.length) {
                        var $el = self._renderFieldWidget(
                            fields[0], self.state);
                        $statusbar.prepend($el);
                    }
                }
            });

            return $statusbar;
        },
    });

});
