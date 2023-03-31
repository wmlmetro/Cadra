odoo.define('crnd_wsd_resource.tour_request_new_with_resource', function (require) {
    'use strict';

    var tour = require('web_tour.tour');

    // Start this tour directly from step 'type' to avoid service selection if
    // 'crnd_wsd_service' addon is installed
    tour.register('crnd_wsd_resource_tour_request_new_with_resource', {
        test: true,
        url: '/requests/new/step/category',
    }, [
        {
            content: "Check that we in req creation process on step 'type'",
            trigger: ".wsd_request_new form#request_category",
        },
        {
            content: "Select request category SaAS / General",
            trigger: "h4:has(label:containsExact('SaAS / General'))" +
                ":contains() input[name='category_id']",
        },
        {
            content: "Click 'Next' button",
            trigger: "button[type='submit']",
        },
        {
            content: "Check that we in req creation process on step 'type'",
            trigger: ".wsd_request_new form#request_type",
        },
        {
            content: "Select request type Resource Question",
            trigger: "h4:has(label:containsExact('Resource Question'))" +
                ":contains() input[name='type_id']",
        },
        {
            content: "Click 'Next' button",
            trigger: "button[type='submit']",
        },
        {
            content: "Write name resource",
            trigger: "#resource_id_autocomplete",
            run: "text Printer",
        },
        {
            content: "Select resource Printer Canon i569",
            trigger: "a:containsRegex(" +
                "/Printer Canon i569 \\[SR-\\d+\\]/g)",
        },
        {
            content: "Write request text",
            trigger: "#request_text",
            run: function () {
                $("#request_text").trumbowyg(
                    'html', "<h1>Test request with resource</h1>");
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
            content: "Check that there resource type 'Default'",
            trigger: "div#request-head-right > div > " +
                "span:containsExact('Default')",
        },
        {
            content: "Check that there resource 'Printer Canon i569 '",
            trigger: "div#request-head-right > div >" +
                " span:containsRegex(/Printer Canon i569 \\[SR-\\d+\\]/g)",
        },
    ]);
    return {};
});
