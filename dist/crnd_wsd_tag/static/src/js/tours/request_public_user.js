odoo.define('crnd_wsd_tag.tour_request_new_with_tags_public_user', function (require) {
    'use strict';

    var tour = require('web_tour.tour');

    // Start this tour directly from step 'type' to avoid service selection if
    // 'crnd_wsd_service' addon is installed
    tour.register('crnd_wsd_tag_tour_request_public_user', {
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
            content: "Check 'Sign Up or Sign In inscription'",
            trigger: "div div p:contains(" +
                "'to be able to view and create requests.')",
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
            content: "Set serverity High",
            trigger: "div.request-data-tag-category:has(" +
                "label.control-label:containsExact('Severity')):contains()" +
                " > div.request-data-tag-tag >" +
                " input[disabled='disabled']",
        },
        {
            content: "Set priority Medium",
            trigger: "div.request-data-tag-category:has(" +
                "label.control-label:containsExact('Priority')):contains()" +
                " > div.request-data-tag-tag > " +
                " input[disabled='disabled']",
        },
        {
            content: "Set platform Linux",
            trigger: "div.request-data-tag-category:has(" +
                "label.control-label:containsExact('Platform')):contains()" +
                " > div.request-data-tag-tag > " +
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
            content: "Set serverity High",
            trigger: "div.request-data-tag-category:has(" +
                "label.control-label:containsExact('Severity')):contains()" +
                " > div.request-data-tag-tag:has(" +
                "label:containsExact('High')):contains()" +
                " > input[name^='tag_id_']",
        },
        {
            content: "Set priority Medium",
            trigger: "div.request-data-tag-category:has(" +
                "label.control-label:containsExact('Priority')):contains()" +
                " > div.request-data-tag-tag:has(" +
                "label:containsExact('Medium')):contains()" +
                " > input[name^='tag_id_']",
        },
        {
            content: "Set platform Linux",
            trigger: "div.request-data-tag-category:has(" +
                "label.control-label:containsExact('Platform')):contains()" +
                " > div.request-data-tag-tag:has(" +
                "label:containsExact('Linux')):contains() >" +
                " input[name^='tag_id_']",
        },
        {
            content: "Set platform Mac OS",
            trigger: "div.request-data-tag-category:has(" +
                "label.control-label:containsExact('Platform')):contains()" +
                " > div.request-data-tag-tag:has(" +
                "label:containsExact('Mac OS')):contains()" +
                " > input[name^='tag_id_']",
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
