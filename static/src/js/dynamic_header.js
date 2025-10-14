odoo.define('ml_development.dynamic_header', function (require) {
    'use strict';

    $(document).ready(function () {
        // Add a custom header dynamically if it doesn't already exist
        var header = '<div class="dynamic-header" style="text-align: center; font-size: 24px; margin-bottom: 20px;">' +
            '<h1>Dynamic Header Text</h1>' +
            '</div>';

        $('.page').each(function () {
            if (!$(this).find('.dynamic-header').length) {
                $(this).prepend(header);
            }
        });
    });
});
