odoo.define('crnd_wsd_resource.new_request', function (require) {
    'use strict';
    var core = require('web.core');
    var ajax = require('web.ajax');
    var request_new = require('crnd_wsd.new_request');
    var RequestCreateWidget = request_new.RequestCreateWidget;

    var _t = core._t;

    RequestCreateWidget.include({
        start: function () {
            var self = this;

            self._super.apply(self, arguments);
            self.$form_resource_sel_status_icon = self.$target.find(
                '#check_resource_label');

            self.$form_resource = self.$target.find('input#resource_id');

            self.$form_resource_auto = self.$target.find(
                'input#resource_id_autocomplete');
            self.resource_types = self._get_resource_types();
            $.widget('custom.catcomplete', $.ui.autocomplete,
                self._get_catcomplete_menu_params());

            self.$form_resource_auto.catcomplete(
                self._get_catcomplete_params());
            self._add_input_toggle();
            self._set_default_resource_from_query();
        },

        _set_default_resource_from_query: function () {
            var self = this;
            var resource_id = parseInt(self.$form_resource.val(), 10);

            if (resource_id) {
                ajax.jsonRpc(
                    '/crnd_wsd/api/resource_name',
                    'call',
                    {
                        'lang': self._get_lang(),
                        'resource_id': resource_id,
                    }
                ).then(function (data) {
                    self.$form_resource_auto.val(data.resource_name);
                });
                self.$form_resource_sel_status_icon.removeClass(
                    'fa-times text-danger');
                self.$form_resource_sel_status_icon.addClass(
                    'fa-check text-success');
            }
        },

        _get_catcomplete_menu_params: function () {
            return {
                _renderMenu: function (ul, items) {
                    var that = this;

                    $.each(items, function (index, item) {

                        var li = that._renderItemData(ul, item);
                        if (item.is_category_more_info) {
                            $(li).addClass('item-category-more-info');
                        }
                        if (item.is_resource_type_name) {
                            $(li).addClass('ui-autocomplete-category');
                        }
                    });
                },
            };
        },

        _get_catcomplete_params: function () {
            var self = this;
            // Docs on catcomplete:
            // https://jqueryui.com/autocomplete/#categories
            // Docs on autocomplete api:
            // https://api.jqueryui.com/autocomplete/
            return {
                minLength: 0,
                source: function (request, response) {
                    self._update_resources_selection(request, response);
                },
                change: function (event, ui) {
                    if (ui.item && ui.item.id) {
                        self.$form_resource_sel_status_icon.removeClass(
                            'fa-times text-danger');
                        self.$form_resource_sel_status_icon.addClass(
                            'fa-check text-success');
                    } else {
                        self.$form_resource.val('');
                        self.$form_resource_sel_status_icon.val('');
                        self.$form_resource_sel_status_icon.removeClass(
                            'fa-check text-success');
                        self.$form_resource_sel_status_icon.addClass(
                            'fa-times text-danger');
                    }
                },
                response: function (event, ui) {
                    var _content_copy = ui.content.slice();
                    var allowed_count = _content_copy.shift().settings
                        .allowed_count;

                    ui.content.length = 0;
                    $.each(_content_copy, function (index, res_type) {
                        ui.content.push({
                            'label': res_type.resource_type_name,
                            'value': res_type.resource_type_name,
                            'is_resource_type_name': true,
                        });
                        $.each(res_type.resources,
                            function (index_res, resource) {
                                ui.content.push({
                                    'label': resource.value,
                                    'value': resource.value,
                                    'id': resource.id,
                                });
                            });
                        if (res_type.resources_count > allowed_count) {
                            var label = _t('More...');
                            ui.content.push({
                                'label': label,
                                'value': label,
                                'is_category_more_info': true,
                            });
                        }
                    });
                },
                select: function (event, ui) {
                    if (ui.item.is_resource_type_name) {
                        event.preventDefault();
                        return false;
                    } else if (ui.item.is_category_more_info) {
                        event.preventDefault();
                        return false;
                    } else if (ui.item.id) {
                        self.$form_resource.val(ui.item.id);
                        self.$form_resource_sel_status_icon.removeClass(
                            'fa-times text-danger');
                        self.$form_resource_sel_status_icon.addClass(
                            'fa-check text-success');
                    } else {
                        self.$form_resource_sel_status_icon.removeClass(
                            'fa-check text-success');
                        self.$form_resource_sel_status_icon.addClass(
                            'fa-times text-danger');
                    }
                },
            };
        },

        _add_input_toggle: function () {
            var self = this;
            var input_autocomplete = $('input#resource_id_autocomplete');
            input_autocomplete.on('click', function () {
                self.$form_resource_auto.trigger('focus');
                self.$form_resource_auto.catcomplete(
                    'search', input_autocomplete.val());
            });
        },

        _get_resource_types: function () {
            var self = this;
            var t = [];
            self.$target.find(
                "input[name^=resource_type]"
            ).each(function (index, value) {
                var $res_type = value;
                if ($res_type.checked === true) {
                    t.push(parseInt($res_type.value, 10));
                }
            });
            return t;
        },

        _get_lang: function () {
            // Determine lang of website
            // TODO: Try to do in on python level
            var lang = $('html');
            lang = lang.attr('lang').replace('-', '_');
            return lang;
        },

        _update_resources_selection: function (request, response) {
            var self = this;
            var term = request.term;
            var lang = self._get_lang();
            var resource_types = self._get_resource_types();
            var request_type_id = parseInt(
                self.$target.find('input[name="type_id"]').val(), 10);
            var resource_search_params = self._get_resource_search_params(
                term, request_type_id, lang, resource_types);

            ajax.jsonRpc(
                '/crnd_wsd/api/resources',
                'call',
                resource_search_params
            ).then(function (data) {
                response(data);
            });
        },

        _get_resource_search_params: function (
            term, request_type_id, lang, resource_types) {
            var $service = this.$target.find('input[name="service_id"]');
            var service_id = parseInt($service.val(), 10);
            return {
                'term': term,
                'request_type_id': request_type_id,
                'lang': lang,
                'resource_types': resource_types,
                'service_id': service_id,
            };
        },
    });
});
