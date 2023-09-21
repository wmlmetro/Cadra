odoo.define('crnd_wsd.tour_response_attachments', function (require) {
    'use strict';

    var tour = require('web_tour.tour');

    tour.register('tour_response_attachments', {
        test: true,
        url: '/requests',
    }, [
        {
            content: "Check page loaded",
            trigger: ".wsd_requests",
        },
        {
            content: "Search for request with attachments",
            trigger: ".wsd_requests form#wsd-request-search" +
                " input[name='search']",
            run:     "text Test response attachments",
        },
        {
            content: "Click on 'search' button",
            trigger: ".wsd_requests form#wsd-request-search " +
                "button[type='submit']",
        },
        {
            content: "Wait for page loaded",
            trigger: ".wsd_requests",
        },
        {
            content: "Go to closed page",
            trigger: ".wsd_requests " +
            "a[href='/requests/closed?search=Test+response+attachments']",
        },
        {
            content: "Click on first selected request",
            trigger: ".wsd_requests .wsd_request:first a.request-name",
        },
        {
            content: "Check request opened",
            trigger: "#request-body-text-content:contains(" +
                "'Test response attachments')",
        },
        {
            content: "Check attachment1",
            trigger: "#request-body-response-attachments" +
                " ul > li > a:containsExact('sample_attachment1.txt')",
        },
        {
            content: "Check attachment2",
            trigger: "#request-body-response-attachments" +
                " ul > li > a:containsExact('sample_attachment2.txt')",
        },
    ]);
    return {};
});
