odoo.define('crnd_wsd.star_priority_selection', function (require) {
    'use strict';

    var snippet_animation = require('website.content.snippets.animation');
    var snippet_registry = snippet_animation.registry;

    var RequestSelectPriorityComplex = snippet_animation.Class.extend({
        selector: '#request-data-priority',

        events: {
            'mousemove .priority_group label': '_onMovePriority',
            'mouseleave .priority_group' : '_onMouseLeavePriorityGroup',
            'change .priority_group input': '_onChangePriority',
            'click .priority_group input': '_onClickFirstElement',
            'change .selection_container select': '_onChangeSelection',
        },

        start: function () {
            var def = this._super.apply(this, arguments);

            if ($('#star_priority_group')[0]) {
                this.impact_priority_group = $('#impact_priority_group')[0];
                this.urgency_priority_group = $('#urgency_priority_group')[0];
                this.priority_group = $('#priority_group')[0];

                if ($('#request-data-priority').data('complex')) {
                    this.complex_priority = true;

                    this.impact_priority_checked_value =
                        $("input[name='request_impact_priority']:checked")
                            .val();
                    this._setPriority(this.impact_priority_group,
                        this.impact_priority_checked_value);

                    this.urgency_priority_checked_value =
                        $("input[name='request_urgency_priority']:checked")
                            .val();
                    this._setPriority(this.urgency_priority_group,
                        this.urgency_priority_checked_value);
                } else {
                    this.complex_priority = false;
                }

                this.priority_checked_value =
                    $("input[name='request_priority']:checked").val();
                this._setPriority(this.priority_group,
                    this.priority_checked_value);
            }

            return def;
        },

        _setPriority: function (priority_group, priority) {
            var elements = priority_group.getElementsByTagName('i');
            for (var index = 0; index < elements.length; index++) {
                if (index < priority) {
                    elements[index].setAttribute('class', 'fa fa-star');
                } else {
                    elements[index].setAttribute('class', 'fa fa-star-o');
                }
            }
        },

        _onMovePriority: function (ev) {
            var input = ev.currentTarget.control;

            if (input.parentElement === this.impact_priority_group) {
                this._setPriority(this.impact_priority_group, input.value);
            } else if (input.parentElement === this.urgency_priority_group) {
                this._setPriority(this.urgency_priority_group, input.value);
            } else if (input.parentElement === this.priority_group &&
                !this.complex_priority) {
                this._setPriority(this.priority_group, input.value);
            }
        },

        _onMouseLeavePriorityGroup: function (ev) {
            if (ev.currentTarget === this.impact_priority_group) {
                this._setPriority(this.impact_priority_group,
                    this.impact_priority_checked_value);
            } else if (ev.currentTarget === this.urgency_priority_group) {
                this._setPriority(this.urgency_priority_group,
                    this.urgency_priority_checked_value);
            } else if (ev.currentTarget === this.priority_group &&
                !this.complex_priority) {
                this._setPriority(this.priority_group,
                    this.priority_checked_value);
            }
        },

        _onChangePriority: function (ev) {
            var input = ev.currentTarget;
            var value = parseInt(input.value, 10);

            if (input.parentElement === this.impact_priority_group) {
                this.impact_priority_checked_value = value;
                this._setPriority(this.impact_priority_group, value);
            } else if (input.parentElement === this.urgency_priority_group) {
                this.urgency_priority_checked_value = value;
                this._setPriority(this.urgency_priority_group, value);
            } else if (input.parentElement === this.priority_group &&
                !this.complex_priority) {
                this.priority_checked_value = value;
                this._setPriority(this.priority_group, value);
            }

            if (this.complex_priority) {
                this._showComplexPriority();
            }
        },

        // Function for change priority to 'Not set', when click on first star
        // priority bar
        _onClickFirstElement: function (ev) {
            var input = ev.currentTarget;
            var value = parseInt(input.value, 10);

            if (value === 1) {
                if (input.parentElement === this.impact_priority_group &&
                    value === this.impact_priority_checked_value) {
                    this.impact_priority_checked_value = 0;
                    this._setPriority(this.impact_priority_group, 0);

                    input.previousElementSibling.checked = true;
                } else if (
                    input.parentElement === this.urgency_priority_group &&
                    value === this.urgency_priority_checked_value) {
                    this.urgency_priority_checked_value = 0;
                    this._setPriority(this.urgency_priority_group, 0);

                    input.previousElementSibling.checked = true;
                } else if (input.parentElement === this.priority_group &&
                    !this.complex_priority &&
                    value === this.priority_checked_value) {
                    this.priority_checked_value = 0;
                    this._setPriority(this.priority_group, 0);

                    input.previousElementSibling.checked = true;
                }

                if (this.complex_priority) {
                    this._showComplexPriority();
                }
            }
        },

        _showComplexPriority: function () {
            var complex_priority_value =
                this._calcComplexPriority(this.impact_priority_checked_value,
                    this.urgency_priority_checked_value);
            this.priority_checked_value = complex_priority_value;
            this._setPriority(this.priority_group, this.priority_checked_value);
            $('#priority_' + this.priority_checked_value).prop('checked', true);
        },

        _onChangeSelection: function () {
            $('#request_priority').val(this._calcComplexPriority(
                $('#request_impact_priority').val(),
                $('#request_urgency_priority').val()));
        },

        _calcComplexPriority: function (i, j) {
            var priority_map = [
                [0, 1, 2, 3],
                [1, 1, 2, 3],
                [2, 2, 3, 4],
                [3, 3, 4, 5]];

            return priority_map[i][j];
        },

    });

    snippet_registry.RequestSelectPriorityComplex =
        RequestSelectPriorityComplex;

});
