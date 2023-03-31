odoo.define('crnd_wsd_resource.tour_request_new_with_resource_http_parameter', function (require) {
    'use strict';

    var tour = require('web_tour.tour');

    tour.register(
        'crnd_wsd_resource_tour_request_new_with_resource_parameter', {
            test: true,
        }, [
            {
                content: "Check that we in request creation process" +
                    " on step 'category'",
                trigger: ".wsd_request_new form#request_category",
            },
            {
                content: "Check category SaAS / Technical",
                trigger: "section.row h4:has(label:containsExact" +
                    "('SaAS / Technical')):contains()",
            },
            {
                content: "Check and select request category SaAS / General",
                trigger: "h4:has(label:containsExact('SaAS / General'))" +
                    ":contains() input[name='category_id']",
            },
            {
                content: "Click 'Next' button",
                trigger: "button[type='submit']",
            },
            // TODO: It seems that category already selected here.
            //       Thus, may be it have sense to remove this commented code
            // {
            //     content: "Check that we in request creation process" +
            //         "on step 'type'",
            //     trigger: ".wsd_request_new form#request_type",
            // },
            // {
            //     content: "Check category selected",
            //     trigger: "#request-selection-box #request-category" +
            //         " span:containsExact('SaAS / General')",
            // },
            // {
            //     content: "Check type is Generic Question",
            //     trigger: "section.row h4:has(label:containsExact" +
            //         "('Generic Question')):contains()",
            // },
            // {
            //     content: "Check and select request type Resource Question",
            //     trigger: "h4:has(label:containsExact('Resource Question'))" +
            //         ":contains() input[name='type_id']",
            // },
            // {
            //     content: "Click 'Next' button",
            //     trigger: "button[type='submit']",
            // },
            {
                content: "Check category selected",
                trigger: "#request-selection-box #request-category" +
                    " span:containsExact('SaAS / General')",
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
            {
                content: "Write request text",
                trigger: "#request_text",
                run: function () {
                    $("#request_text").trumbowyg('html', "New request text");
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
                content: "Check request text",
                trigger: "div:containsExact('New request text')",
            },
        ]);
    return {};
});
