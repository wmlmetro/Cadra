odoo.define('crnd_wsd_resource.tour_request_new_with_resource_public_user_create_req', function (require) {
    'use strict';

    var tour = require('web_tour.tour');

    // Start this tour directly from step 'type' to avoid service selection if
    // 'crnd_wsd_service' addon is installed
    tour.register('crnd_wsd_resource_tour_request_public_user_create_req', {
        test: true,
        url: '/requests/new',
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
            content: "Enter user's name (with email to avoid errors)",
            trigger: "input#request_author_email",
            run: "text John Doe <john@doe.net>",
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
