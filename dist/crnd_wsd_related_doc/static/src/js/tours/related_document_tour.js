odoo.define('crnd_wsd_related_document.tour_crnd_wsd_related_document',
    function (require) {
        'use strict';

        var tour = require('web_tour.tour');

        tour.register('tour_crnd_wsd_related_document', {
            test: true,
            url: '/requests',
        }, [
            {
                content: "Search for request with related document'",
                trigger: ".wsd_request:has(div:contains(" +
                    "'Cannot confirm sale order')):contains()"+
                    " .request_top .request-shortcuts "+
                    "a[title='Related documents']",
            },
            {
                content: "Check related documents section",
                trigger: "h4 span:containsExact('Related documents')",
            },
            {
                content: "Search related request",
                trigger: "span:contains('Wood Corner')",
            },

        ]);
        return {};
    });
