odoo.define('crnd_wsd_tag.tour_request_new_with_tags', function (require) {
    'use strict';

    var tour = require('web_tour.tour');

    // Start this tour directly from step 'type' to avoid service selection if
    // 'crnd_wsd_service' addon is installed
    tour.register('crnd_wsd_tag_tour_request_new_with_tags', {
        test: true,
        url: '/requests/new',
    }, [
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
            trigger: "div.request-data-tag-category:has(label.control-label:" +
                "containsExact('Severity')):contains()" +
                " > div.request-data-tag-tag:" +
                "has(label:containsExact('High')):contains()" +
                " > input[name^='tag_id_']",
        },
        {
            content: "Set priority Medium",
            trigger: "div.request-data-tag-category:has(label.control-label:" +
                "containsExact('Priority')):contains()" +
                " > div.request-data-tag-tag:" +
                "has(label:containsExact('Medium')):contains()" +
                " > input[name^='tag_id_']",
        },
        {
            content: "Set platform Linux",
            trigger: "div.request-data-tag-category:has(label.control-label:" +
                "containsExact('Platform')):contains()" +
                " > div.request-data-tag-tag:" +
                "has(label:containsExact('Linux')):contains()" +
                " > input[name^='tag_id_']",
        },
        {
            content: "Set platform Mac OS",
            trigger: "div.request-data-tag-category:has(label.control-label:" +
                "containsExact('Platform')):contains()" +
                " > div.request-data-tag-tag:" +
                "has(label:containsExact('Mac OS')):contains()" +
                " > input[name^='tag_id_']",
        },
        {
            content: "Write request text",
            trigger: "#request_text",
            run: function () {
                $("#request_text").trumbowyg(
                    'html', "<h1>Test request with tags</h1>");
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
            content: "Check that there is tag 'Platform / Linux'",
            trigger: "td.wsd_request > div.request_tags >" +
                " div > span:containsExact('Platform / Linux')",
        },
        {
            content: "Check that there is tag 'Platform / Mac OS'",
            trigger: "td.wsd_request > div.request_tags >" +
                " div > span:containsExact('Platform / Mac OS')",
        },
        {
            content: "Check that there is tag 'Priority / Medium'",
            trigger: "td.wsd_request > div.request_tags > div >" +
                " span:containsExact('Priority / Medium')",
        },
        {
            content: "Check that there is tag 'Severity / High'",
            trigger: "td.wsd_request > div.request_tags >" +
                " div > span:containsExact('Severity / High')",
        },
        {
            content: "Click on request name ot open it",
            trigger: ".wsd_request a.request-name",
        },
        {
            content: "Wait for request page loaded",
            trigger: "#wrap:has(h3:contains('Req-')):contains()",
        },
        {
            content: "Check that there is tag 'Platform / Linux'",
            trigger: "div#request-head-tags > div >" +
                " span:containsExact('Platform / Linux')",
        },
        {
            content: "Check that there is tag 'Platform / Mac OS'",
            trigger: "div#request-head-tags > div >" +
                " span:containsExact('Platform / Mac OS')",
        },
        {
            content: "Check that there is tag 'Priority / Medium'",
            trigger: "div#request-head-tags > div >" +
                " span:containsExact('Priority / Medium')",
        },
        {
            content: "Check that there is tag 'Severity / High'",
            trigger: "div#request-head-tags > div >" +
                " span:containsExact('Severity / High')",
        },
    ]);
    return {};
});
