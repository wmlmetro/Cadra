odoo.define('crnd_wsd.tour_crnd_wsd_subrequest_additional',
    function (require) {
        'use strict';

        var tour = require('web_tour.tour');

        tour.register('tour_crnd_wsd_subrequest_additional', {
            test: true,
            url: '/requests',
        }, [
            {
                content: "Search for related request'",
                trigger: ".wsd_request:has(div:contains(" +
                    "'Demo parent request')):contains()"+
                    " .request_top .request-title "+
                    "a.request-name",
            },
            {
                content: "Check subrequests section",
                trigger: "h4 span:containsExact('Subrequests')",
            },
            {
                content: "Search subrequest",
                trigger: "span:contains('Demo subrequest')",
            },
            {
                content: "Check subrequest name",
                trigger: ".wsd_request .request_top " +
                    "span.request-title",
            },

        ]);
        return {};
    });
