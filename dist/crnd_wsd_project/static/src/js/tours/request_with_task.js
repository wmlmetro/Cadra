odoo.define('crnd_wsd.tour_request_with_task', function (require) {
    'use strict';

    var tour = require('web_tour.tour');

    tour.register('crnd_wsd_project_request_with_task', {
        test: true,
        url: '/requests',
    }, [
        {
            content: "Click request with task",
            trigger: "td.wsd_request:has(div:containsExact("+
            "'This is demo request with task')):contains() div.request_top "+
             "span.request-title a.request-name",
        },
        {
            content: "Click task",
            trigger: "a:containsExact('Demo task related to request')",
        },
        {
            content: "Click request",
            trigger: "div.card-body div.row.mb-4 div:has("+
            ">strong:containsExact('Request:')):contains() a",
        },
        {
            content: "Check request page",
            trigger: "div#request-body-text-content",
        },
    ]);
    return {};
});
