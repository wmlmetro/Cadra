odoo.define('crnd_wsd.tour_request_new_with_service_group', function (require) {
    'use strict';

    var tour = require('web_tour.tour');

    tour.register('crnd_wsd_tour_request_new_with_service_group', {
        test: true,
        url: '/requests/new',
    }, [
        {
            content: "Check that we in request creation" +
                " process on step 'service group'",
            trigger: ".wsd_request_new form#request_service_group",
        },
        {
            content: "Check service group 'Rent' is on page",
            trigger: "h4:has(label:containsExact('Rent'))" +
                ":contains()",
        },
        {
            content: "Select service group 'Test service group'",
            trigger: "h4:has(label:containsExact('Test service group'))" +
                ":contains() input[name='service_group_id']",
        },
        {
            content: "Click 'Next' button",
            trigger: "button[type='submit']",
        },
        {
            content: "Check that we in request creation process" +
                " on step 'category'",
            trigger: ".wsd_request_new form#request_category",
        },
        {
            content: "Select request category SaAS / Support",
            trigger: "h4:has(label:containsExact('SaAS / Support'))" +
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
            content: "Select request type Incident",
            trigger: "h4:has(label:containsExact('Incident'))" +
                ":contains() input[name='type_id']",
        },
        {
            content: "Click 'Next' button",
            trigger: "button[type='submit']",
        },
        {
            content: "Write request text",
            trigger: "#request_text",
            run: function () {
                $("#request_text").trumbowyg(
                    'html', "<h1>Test service groups</h1>");
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
            trigger: "#wrap:has(h3:contains('INCIDENT-')):contains()",
        },
        {
            content: "Check that request have service 'Default'",
            trigger: "#request-head-left div#request-service" +
                " span:containsExact('Default')",
        },
    ]);
    return {};
});
