from dateutil.relativedelta import relativedelta


def get_recurring_next_date(date_start, recurring_type, recurring_period):
    """ Generate next recurring date starting from 'date_start'

        :param Date date_start: starting date for recurrence
        :param str recurring_type: One of predefined values.
                                   See below for details.
        :param int recurring_period: Recurring interval.

        Following recurring types available:
            - 'dayly'
            - 'weekly'
            - 'monthly'
            - 'monthly-last-day'
            - 'yearly'
    """
    if recurring_type == 'daily':
        delta = relativedelta(days=recurring_period)
    elif recurring_type == 'weekly':
        delta = relativedelta(weeks=recurring_period)
    elif recurring_type == 'monthly':
        delta = relativedelta(months=recurring_period)
    elif recurring_type == 'monthly-last-day':
        if date_start.month == (date_start + relativedelta(days=1)).month:
            # date start is not last day of month
            # (if we can add 1 day and month will not be changed)
            # In this case we have to use same month for next recurring date
            delta = relativedelta(months=recurring_period - 1, day=31)
        else:
            delta = relativedelta(months=recurring_period, day=31)
    elif recurring_type == 'yearly':
        delta = relativedelta(years=recurring_period)
    else:
        delta = relativedelta()

    return date_start + delta
