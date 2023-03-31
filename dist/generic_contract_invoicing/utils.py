import logging

import dateutil
import pytz

from odoo.tools.safe_eval import safe_eval, wrap_module
from odoo.addons.generic_mixin import render_jinja_string
from odoo.addons.generic_mixin.tools.utils import removeprefix

_logger = logging.getLogger(__name__)

mods = ['parser', 'relativedelta', 'rrule', 'tz']
_datetime = wrap_module(
    __import__('datetime'),
    ['date', 'datetime', 'time', 'timedelta', 'timezone',
     'tzinfo', 'MAXYEAR', 'MINYEAR'])
_dateutil = wrap_module(dateutil, {
    mod: getattr(dateutil, mod).__all__
    for mod in mods
})
_relativedelta = dateutil.relativedelta.relativedelta

_time = wrap_module(
    __import__('time'), ['time', 'strptime', 'strftime'])
_timezone = pytz.timezone


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
        delta = _relativedelta(days=recurring_period)
    elif recurring_type == 'weekly':
        delta = _relativedelta(weeks=recurring_period)
    elif recurring_type == 'monthly':
        delta = _relativedelta(months=recurring_period)
    elif recurring_type == 'monthly-last-day':
        if date_start.month == (date_start + _relativedelta(days=1)).month:
            # date start is not last day of month
            # (if we can add 1 day and month will not be changed)
            # In this case we have to use same month for next recurring date
            delta = _relativedelta(months=recurring_period - 1, day=31)
        else:
            delta = _relativedelta(months=recurring_period, day=31)
    elif recurring_type == 'yearly':
        delta = _relativedelta(years=recurring_period)
    else:
        delta = _relativedelta()

    return date_start + delta


# TODO: move to separate module and add documentation
class StackStatement:
    def __init__(self, *args, **kwargs):
        self._stack = []

    def add_statement(self, stm):
        """ Add statement to the stack.
            Return added statement
        """
        if not isinstance(stm, StackStatement):
            raise TypeError("Must be instance of StackStatement")

        if isinstance(stm, (StackIfBranch, StackIfElse)):
            raise ValueError(
                "ELIF and ELSE could be added only into IF statement")

        self._stack.append(stm)
        return stm

    def run(self, context):
        """ Must return list of processed data lines
        """
        result = []
        for stm in self._stack:
            res = stm.run(context)
            result += res
        return result


class StackFor(StackStatement):

    def __init__(self, expr, varname, index_varname=None):
        super(StackFor, self).__init__()

        self._expr = expr
        self._varname = varname
        self._index_varname = index_varname

    def run(self, context):
        result = []
        for index, value in enumerate(safe_eval(self._expr, context)):
            ctx = dict(context)
            ctx[self._varname] = value
            if self._index_varname:
                ctx[self._index_varname] = index

            result += super(StackFor, self).run(ctx)
        return result


class StackSubStatement(StackStatement):
    pass


class StackIfBranch(StackSubStatement):
    def __init__(self, expr):
        super(StackIfBranch, self).__init__()
        self._expr = expr

    def if_test(self, context):
        return bool(safe_eval(self._expr, context))


class StackIfElse(StackSubStatement):
    pass


class StackIfMulty(StackStatement):
    """ Represents IF/ELIF/ELSE in stack
    """

    def __init__(self, expr):
        super(StackIfMulty, self).__init__()
        self._checks = [StackIfBranch(expr)]
        self._else = None

    def add_statement(self, stm):
        if isinstance(stm, StackIfBranch):
            if self._else is not None:
                raise ValueError(
                    "Could not add ELIF after Else branch defined")
            self._checks.append(stm)
            return stm
        if isinstance(stm, StackIfElse):
            if self._else is not None:
                raise ValueError("Else branch already defined")
            self._else = stm
            return stm
        if isinstance(stm, StackStatement):
            if self._else:
                return self._else.add_statement(stm)
            return self._checks[-1].add_statement(stm)
        raise TypeError("Must be instance of StackStatement")

    def run(self, context):
        for check in self._checks:
            if check.if_test(context):
                return check.run(context)
        if self._else:
            return self._else.run(context)
        return []


class StackData(StackStatement):
    """ This statement have to be used to wrap single data lement

        :param dict data: dictionary with data to be pre-processed
        :param dict preprocess_fields: dictionary that mapps data field to
                                       template engine that must be used to
                                       process it.
    """
    def __init__(self, data, preprocess_fields):
        super(StackData, self).__init__()
        self._data = data
        self._preprocess_fields = preprocess_fields

    def render_template(self, field_name, engine, context):
        value = self._data[field_name]
        if engine == 'jinja2':
            return render_jinja_string(
                value, context, 'raw')
        if engine == 'python':
            if not value:
                return False
            return safe_eval(value, context)

        raise ValueError(
            "Unsupported template engine %s!\n"
            "Supported engined: jinja2, python")

    def run(self, context):
        res = dict(self._data)
        for field_name, engine in self._preprocess_fields.items():
            res[field_name] = self.render_template(field_name, engine, context)
        return [res]


class StackProcessor(StackStatement):
    """ Process list of data

        :param string code_field: name of field to look for code in
        :param dict preprocess_fields: dictionary that mapps data field to
                                       template engine that must be used to
                                       process it.
        :param dict extra_context: dictionary with extra context for processing
    """

    _stm_start = "%>CODE->"
    _stm_end = "%>END"

    def __init__(self, code_field, preprocess_fields, extra_context=None):
        super(StackProcessor, self).__init__()

        self._extra_context = {} if extra_context is None else extra_context
        self._code_field = code_field
        self._preprocess_fields = preprocess_fields
        self._open_statements = []

    def _prepare_context(self, extra_context=None):
        res = dict(self._extra_context)

        res.update({
            'time': _time,
            'datetime': _datetime,
            'dateutil': _dateutil,
            'relativedelta': _relativedelta,
            'timezone': _timezone,
        })
        if extra_context:
            res.update(extra_context)
        return res

    def add_statement(self, stm):
        if self._open_statements:
            root = self._open_statements[-1]
        else:
            root = super(StackProcessor, self)

        stm = root.add_statement(stm)
        return stm

    def open_statement(self, stm):
        self.add_statement(stm)
        self._open_statements.append(stm)

    def close_statement(self):
        if not self._open_statements:
            raise ValueError("There is no open statements")
        self._open_statements.pop(-1)

    def parse_line(self, data_line):
        """ data_line is dictionary and convert it into statement.
            Add created statement to stack
        """
        code = data_line.get(self._code_field)
        if code and code.startswith(self._stm_start):
            code = removeprefix(code, self._stm_start)
            ctx = self._prepare_context({
                'FOR': StackFor,
                'IF': StackIfMulty,
                'ELIF': StackIfBranch,
                'ELSE': StackIfElse,
            })
            stm = safe_eval(code, ctx)
            if not isinstance(stm, StackStatement):
                raise ValueError(
                    "Expression must return instance of StackStatement")

            if isinstance(stm, StackSubStatement):
                self._open_statements[-1].add_statement(stm)
            else:
                self.open_statement(stm)
        elif code and code.startswith(self._stm_end):
            self.close_statement()
        else:
            self.add_statement(StackData(data_line, self._preprocess_fields))

    # TODO: Add validation step
    # TODO: Save context in stack, add ability to modify
    #       context via SET var=val
    def run(self, context=None):
        ctx = self._prepare_context(context)
        return super(StackProcessor, self).run(ctx)
