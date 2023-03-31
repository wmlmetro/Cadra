odoo.define('crnd_wsd.tour_request_public_user_create_request_to_request', function (require) {
    'use strict';

    var tour = require('web_tour.tour');

    tour.register('crnd_wsd_tour_request_public_user_create_req_to_request', {
        test: true,
        url: '/requests',
    }, [
        {
            content: "Click 'Create request' button",
            trigger: "a:containsExact('Create request')",
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
            content: "Check category selected",
            trigger: "#request-selection-box #request-category" +
                " span:containsExact('SaAS / Support')",
        },
        {
            content: "Select request type Generic Question",
            trigger: "h4:has(label:containsExact('Generic Question'))" +
                ":contains() input[name='type_id']",
        },
        {
            content: "Click 'Next' button",
            trigger: "button[type='submit']",
        },
        {
            content: "Enter user's name (without email)",
            trigger: "input#request_author_email",
            run: "text John",
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
            content: "Check that error message show",
            trigger: "section#request-error-list",
        },
        {
            content: "Check that author's email marked as invalid",
            trigger: "input#request_author_email.is-invalid",
        },
        {
            content: "Close error message",
            trigger: "section#request-error-list button.close",
        },
        {
            content: "Enter user's name (with email to avoid errors)",
            trigger: "input#request_author_email",
            run: "text John Doe <john@doe.net>",
        },
        {
            content: "Click 'Create' button",
            trigger: "button[type='submit']",
        },
        {
            content: "Wait for congratulation message loaded",
            trigger: "#wrap:has(div.alert-success h3:contains(" +
                "'Your request has been submitted')):contains()",
        },
        {
            content: "Check request text",
            trigger: "#wrap:has(#request-body-text-content " +
                "p:containsExact('New request text')):contains()",
        },
        {
            content: "Check 'Requests' link",
            trigger: "a:containsExact('Requests')",
        },
        {
            content: "Wait for requests page loaded",
            trigger: "#wrap:has(h3:contains(" +
                "'There are currently no requests.')):contains()",
        },
    ]);
    return {};
});

