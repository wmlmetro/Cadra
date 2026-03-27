odoo.define('myservice_theme.Theme', function(require) {
    'use strict';

    var core = require('web.core');

    // Replace all #E85426 orange references with NRS red in inline styles
    // This runs after each page navigation
    function applyNRSColors() {
        // Fix inline style colors on our custom dashboards
        document.querySelectorAll('[style*="E85426"]').forEach(function(el) {
            el.style.cssText = el.style.cssText.replace(/#E85426/gi, '#C8102E');
        });
        document.querySelectorAll('[style*="e85426"]').forEach(function(el) {
            el.style.cssText = el.style.cssText.replace(/e85426/gi, 'C8102E');
        });
        document.querySelectorAll('[style*="c94820"]').forEach(function(el) {
            el.style.cssText = el.style.cssText.replace(/c94820/gi, 'A50D24');
        });
    }

    // Run on load and after DOM mutations
    document.addEventListener('DOMContentLoaded', applyNRSColors);

    // Watch for dynamic content
    if (typeof MutationObserver !== 'undefined') {
        var observer = new MutationObserver(function(mutations) {
            var hasNewNodes = mutations.some(function(m) {
                return m.addedNodes.length > 0;
            });
            if (hasNewNodes) {
                applyNRSColors();
            }
        });
        observer.observe(document.body, {
            childList: true,
            subtree: true,
        });
    }

    return { applyNRSColors: applyNRSColors };
});
