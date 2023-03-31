odoo.define('crnd_wsd_field.tour_request_new_with_fields', function (require) {
    'use strict';

    var tour = require('web_tour.tour');

    tour.register('crnd_wsd_field_tour_request_new_with_fields', {
        test: true,
        url: '/requests/new',
    }, [
        {
            content: "Check that we in request creation process on step 'type'",
            trigger: ".wsd_request_new form#request_category",
        },
        {
            content: "Select request category SaAS / Technical",
            trigger: "h4:has(label:containsExact('SaAS / Technical'))" +
                ":contains() input[name='category_id']",
        },
        {
            content: "Click 'Next' button",
            trigger: "button[type='submit']",
        },
        {
            content: "Check that we in request creation process on step 'type'",
            trigger: ".wsd_request_new form#request_type",
        },
        {
            content: "Select request type Create VM",
            trigger: "h4:has(label:containsExact('Create VM'))" +
                ":contains() input[name='type_id']",
        },
        {
            content: "Click 'Next' button",
            trigger: "button[type='submit']",
        },
        {
            content: "Fill CPU Data",
            trigger: "#request-data-fields-top > div:has(" +
                "label:contains('CPU')):contains() > " +
                " input[name^='request_field_cpu']",
            run: "text 2 Cores",
        },
        {
            content: "Write request text",
            trigger: "#request_text",
            run: function () {
                $("#request_text").trumbowyg(
                    'html', "<h1>Test create-vm request</h1>");
            },
        },
        {
            content: "Click 'Create' button",
            trigger: "button[type='submit']",
        },
        {
            content: "Wait for congratulation page loaded",
            trigger: "#wrap:has(h3:contains(" +
                "'Your request has been submitted')):contains()",
        },
        {
            content: "Click on request name ot open it",
            trigger: ".wsd_request a.request-name",
        },
        {
            content: "Wait for request page loaded",
            trigger: "#wrap:has(h3:contains('Req-')):contains()",
        },
        {
            content: "Check field is displayed on request form",
            trigger: "#request-body-fields div:has(" +
                "strong:contains('CPU')):contains()" +
                " span:containsExact('2 Cores')",
        },
    ]);
    return {};
});
