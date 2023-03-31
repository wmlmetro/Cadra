odoo.define('crnd_wsd_field.tour_request_public_user_redirect_with_fields', function (require) {
    'use strict';

    var tour = require('web_tour.tour');

    tour.register('crnd_wsd_fields_tour_request_public_user_redirect', {
        test: true,
        url: '/requests/new',
    }, [
        {
            content: "Check that we redirected to login page",
            trigger: "div:has(label:containsExact('Email')):contains()",
        },
        {
            content: "Enter login",
            trigger: "input#login",
            run:     "text demo-sd-website",
        },
        {
            content: "Enter password",
            trigger: "input#password",
            run:     "text demo-sd-website",
        },
        {
            content: "Press submit",
            trigger: "button[type='submit']",
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
