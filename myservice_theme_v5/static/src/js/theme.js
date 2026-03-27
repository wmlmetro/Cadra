odoo.define('myservice_theme_v5.Theme', function(require) {
    'use strict';

    var core = require('web.core');

    // Inject NRS logo text into the menu brand after render
    function injectNRSBrand() {
        var brand = document.querySelector('.o_menu_brand');
        if (brand && brand.textContent && !brand.dataset.nrsInjected) {
            // Wrap content — NRS mark + app name
            var appName = brand.textContent.trim();
            brand.innerHTML = '<span style="color:#C8102E;font-family:Syne,sans-serif;font-weight:800;letter-spacing:2px;font-size:14px">NRS</span>' +
                              '<span style="color:#555;font-size:9px;letter-spacing:2px;text-transform:uppercase;margin-left:6px;font-family:DM Mono,monospace">' +
                              appName + '</span>';
            brand.dataset.nrsInjected = '1';
        }
    }

    // Run on load and watch for DOM changes
    document.addEventListener('DOMContentLoaded', function() {
        setTimeout(injectNRSBrand, 500);
        setTimeout(injectNRSBrand, 1500);
    });

    // Watch for navigation changes (OWL re-renders)
    if (typeof MutationObserver !== 'undefined') {
        var observer = new MutationObserver(function(mutations) {
            var hasNav = mutations.some(function(m) {
                return Array.from(m.addedNodes).some(function(n) {
                    return n.nodeType === 1 && (
                        n.classList && (n.classList.contains('o_main_navbar') ||
                        n.classList.contains('o_menu_brand')) ||
                        n.querySelector && n.querySelector('.o_menu_brand')
                    );
                });
            });
            if (hasNav) {
                setTimeout(injectNRSBrand, 100);
            }
        });

        // Start observing once body is available
        function startObserving() {
            if (document.body) {
                observer.observe(document.body, { childList: true, subtree: true });
            } else {
                setTimeout(startObserving, 100);
            }
        }
        startObserving();
    }

    return { injectNRSBrand: injectNRSBrand };
});
