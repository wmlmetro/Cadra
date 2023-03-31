odoo.define('crnd_wsd_service_resource.tour_request_new', function (require) {
    'use strict';

    var tour = require('web_tour.tour');

    // Start this tour directly from step 'type' to avoid service selection if
    // 'crnd_wsd_service' addon is installed
    tour.register('crnd_wsd_service_resource_tour_request_new', {
        test: true,
        url: '/requests/new',
    }, [
        {
            content: "Select service 'Default'",
            trigger: "h4:has(label:containsExact('Default'))" +
                ":contains() input[name='service_id']",
        },
        {
            content: "Click 'Next' button",
            trigger: "button[type='submit']",
        },
        {
            content: "Select request category Demo / Resource",
            trigger: "h4:has(label:containsExact('Demo / Resource'))" +
                ":contains() input[name='category_id']",
        },
        {
            content: "Click 'Next' button",
            trigger: "button[type='submit']",
        },
        {
            content: "Check service selected",
            trigger: "#request-selection-box #request-service" +
                " span:containsExact('Default')",
        },
        {
            content: "Check category selected",
            trigger: "#request-selection-box #request-category" +
                " span:containsExact('Demo / Resource')",
        },
        {
            content: "Check type selected",
            trigger: "#request-selection-box #request-type" +
                " span:containsExact('Printer Request')",
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
            content: "Check that there resource type 'Default'",
            trigger: "div#request-head-right > div >" +
                " span:containsExact('Default')",
        },
        {
            content: "Check that there resource 'Printer Canon i569 '",
            trigger: "div#request-head-right > div >" +
                " span:containsRegex(/Printer Canon i569 \\[SR-\\d+\\]/g)",
        },
        {
            content: "Check that request have service 'Default'",
            trigger: "#request-head-left div#request-service" +
                " span:containsExact('Default')",
        },
    ]);
    return {};
});
