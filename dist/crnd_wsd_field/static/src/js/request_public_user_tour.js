odoo.define('crnd_wsd_field.tour_request_public_user_with_fields', function (require) {
    'use strict';

    var tour = require('web_tour.tour');

    tour.register('crnd_wsd_fields_tour_request_public_user', {
        test: true,
        url: '/requests/new',
    }, [
        {
            content: "Check 'Sign Up or Sign In inscription'",
            trigger: "div div p:contains(" +
                "'to be able to view and create requests.')",
        },
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
            content: "Check 'Sign Up or Sign In inscription'",
            trigger: "div div p:contains(" +
                "'to be able to view and create requests.')",
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
            content: "Check that input fields disabled",
            trigger: "#request-data-fields-top " +
                " input[disabled='disabled']",
        },
        {
            content: "Check request text is disabled",
            trigger: "#request_text[disabled='disabled']",
        },
        {
            content: "Click 'Sign in' link",
            trigger: "div.alert-warning div div p a:containsExact('Sign In')",
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
