odoo.define('crnd_wsd_resource.tour_request_new_with_resource_service_http_parameter', function (require) {
    'use strict';

    var tour = require('web_tour.tour');

    tour.register(
        'crnd_wsd_service_resource_tour_request_new_with_res_parameter', {
            test: true,
        }, [
            {
                content: "Check that we in request creation process" +
                    " on step 'service'",
                trigger: ".wsd_request_new form#request_service",
            },
            {
                content: "Check service Support / Configuration",
                trigger: "section.row h4:has(label:containsExact" +
                    "('Support / Configuration')):contains()",
            },
            {
                content: "Check and select service Default",
                trigger: "h4:has(label:containsExact('Default'))" +
                    ":contains() input[name='service_id']",
            },
            {
                content: "Click 'Next' button",
                trigger: "button[type='submit']",
            },
            {
                content: "Check that we in request creation process on step" +
                    " category'",
                trigger: ".wsd_request_new form#request_category",
            },
            {
                content: "Check service selected",
                trigger: "#request-selection-box #request-service" +
                    " span:containsExact('Default')",
            },
            {
                content: "Check category Demo / Resource",
                trigger: "section.row h4:has(label:containsExact" +
                    "('Demo / Resource')):contains()",
            },
            {
                content: "Check category SaAS / Technical",
                trigger: "section.row h4:has(label:containsExact" +
                    "('SaAS / Technical')):contains()",
            },
            {
                content: "Check and select request category SaAS / Support",
                trigger: "h4:has(label:containsExact('SaAS / Support'))" +
                    ":contains() input[name='category_id']",
            },
            {
                content: "Click 'Next' button",
                trigger: "button[type='submit']",
            },
            {
                content: "Check that we in request creation process " +
                    "on step 'type'",
                trigger: ".wsd_request_new form#request_type",
            },
            {
                content: "Check category selected",
                trigger: "#request-selection-box #request-category" +
                    " span:containsExact('SaAS / Support')",
            },
            {
                content: "Check type Generic Question",
                trigger: "section.row h4:has(label:containsExact" +
                    "('Generic Question')):contains()",
            },
            {
                content: "Check and select request type Resource Question",
                trigger: "h4:has(label:containsExact('Resource Question'))" +
                    ":contains() input[name='type_id']",
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
                    " span:containsExact('SaAS / Support')",
            },
            {
                content: "Check type selected",
                trigger: "#request-selection-box #request-type" +
                    " span:containsExact('Resource Question')",
            },
            {
                content: "Check selected resource",
                trigger: "input[id='resource_id_autocomplete']:propValue" +
                    "(\"Desktop Computer [SR-0002]\")",
            },
        ]);
    return {};
});
