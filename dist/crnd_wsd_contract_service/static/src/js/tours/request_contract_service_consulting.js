odoo.define('crnd_wsd_contract_service.tour_request_contract_service_consulting', function (require) {
    'use strict';

    var tour = require('web_tour.tour');

    tour.register(
        'crnd_wsd_contract_service_tour_request_contract_service_consulting', {
            test: true,
            url: '/requests/new',
        }, [
            {
                content: "Check that we in request creation" +
                    " process on step 'service'",
                trigger: ".wsd_request_new form#request_service",
            },
            {
                content: "Check if there is service 'Rent of notebook'" +
                    " is not in the list of services",
                trigger: ".wsd_request_new form#request_service:" +
                    "not(:has(span:containsExact('Rent of notebook'))" +
                    ":contains())",
            },
            {
                content: "Select service 'Support / Consulting'",
                trigger: "h4:has(label:containsExact('Support / Consulting'))" +
                    ":contains() input[name='service_id']",
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
                        'html',
                        "<h1>Test incident request support consulting</h1>");
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
                content: "Check that request have service " +
                    "'Support / Consulting'",
                trigger: "#request-head-left div#request-service" +
                    " span:containsExact('Support / Consulting')",
            },
        ]);
    return {};
});
