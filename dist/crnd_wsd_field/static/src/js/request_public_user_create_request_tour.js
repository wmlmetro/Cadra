odoo.define('crnd_wsd_field.tour_request_public_user_with_fields_create_req', function (require) {
    'use strict';

    var tour = require('web_tour.tour');

    tour.register('crnd_wsd_fields_tour_request_public_user_create_request', {
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
            content: "Enter user's name (with email to avoid errors)",
            trigger: "input#request_author_email",
            run: "text John Doe <john@doe.net>",
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
