odoo.define('crnd_wsd_related_request.tour_crnd_wsd_related_request',
    function (require) {
        'use strict';

        var tour = require('web_tour.tour');

        tour.register('tour_crnd_wsd_related_request', {
            test: true,
            url: '/requests',
        }, [
            {
                content: "Search for related request'",
                trigger: ".wsd_request:has(div:contains(" +
                    "'ERP: Sale order creation access request')):contains()"+
                    " .request_top .request-shortcuts "+
                    "a[title='Related requests']",
            },
            {
                content: "Check related requests section",
                trigger: "h4 span:containsExact('Related requests')",
            },
            {
                content: "Search related request",
                trigger: "span:contains(" +
                    "'Demo request with related requests and big text')",
            },
            {
                content: "Check related request name is not link",
                trigger: ".wsd_request .request_top " +
                    "span.request-title",
            },

        ]);
        return {};
    });
