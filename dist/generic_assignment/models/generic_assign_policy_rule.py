import random
import logging

import dateutil

from odoo import models, fields, api
from odoo.tools.safe_eval import safe_eval, wrap_module


from ..debug_logger import DebugLogger

_logger = logging.getLogger(__name__)


class GenericAssignPolicyRule(models.Model):
    _name = 'generic.assign.policy.rule'
    _inherit = [
        'mail.thread',
    ]
    _description = 'Assignment Policy Rule'
    _order = 'sequence ASC, name ASC'

    name = fields.Char(required=True, index=True, translate=True)
    sequence = fields.Integer(
        string="Priority", index=True, default=5,
        help="Specify here priority for this assignment rule. "
             "Rules with less priority will be executed first. ",
        tracking=True)
    active = fields.Boolean(
        index=True, default=True, tracking=True)
    policy_id = fields.Many2one(
        'generic.assign.policy', required=True, index=True,
        ondelete='cascade', tracking=True)
    model_id = fields.Many2one(
        'ir.model', related='policy_id.model_id',
        string="Odoo Model", readonly=True, store=True, index=True)
    model_name = fields.Char(
        related='policy_id.model_id.model', readonly=True, store=True,
        index=True)
    condition_ids = fields.Many2many(
        'generic.condition', tracking=True)
    assign_type = fields.Selection(
        [('eval', 'Python expression'),
         ('user', 'User'),
         ('user_field', 'User field'),
         ('policy', 'Policy'),
         ('related_policy', 'Related policy')],
        'Type', required=True, index=True,
        default='user', tracking=True)
    assign_eval = fields.Text(
        help="""Python expression that evaluates to False or dict with keys:
         user_id. If False is returned, than next rule in chain
          will be triggered.
           For example: '{"user_id": record.create_uid}' or 'False'""",
        tracking=True)
    assign_user_id = fields.Many2one(
        'res.users', ondelete='restrict',
        help='User to be assigned to this request.',
        tracking=True)
    assign_user_field_id = fields.Many2one(
        'ir.model.fields', ondelete='cascade',
        domain="[('ttype', 'in', ('many2one', 'many2many', 'one2many')),"
               " ('relation', '=', 'res.users')]",
        help="Field to get user from.", tracking=True)
    assign_policy_id = fields.Many2one(
        'generic.assign.policy', ondelete='restrict',
        tracking=True)
    assign_related_policy_field_id = fields.Many2one(
        'ir.model.fields', ondelete='cascade',
        domain="[('ttype', 'in', ('many2one',))]",
        help="Field that points to record to run related policy.",
        tracking=True)
    assign_related_policy_field_model_id = fields.Char(
        related='assign_related_policy_field_id.relation',
        readonly=True, tracking=True)
    assign_related_policy_field_type = fields.Selection(
        related='assign_related_policy_field_id.ttype',
        readonly=True, tracking=True)
    assign_related_policy_choice_type = fields.Selection(
        selection=[
            ('first', 'First'),
            ('random', 'Random')],
        string='Choice type',
        tracking=True)
    assign_related_policy_choice_condition_ids = fields.Many2many(
        'generic.condition',
        'generic_assign_policy_rel_policy_choice_cond_rel',
        tracking=True)
    assign_related_policy_id = fields.Many2one(
        'generic.assign.policy',
        ondelete='restrict',
        tracking=True,
        domain="[('id', '!=', policy_id),"
               "('model_name', '=', assign_related_policy_field_model_id)]"
    )
    assign_related_policy_sort_field_id = fields.Many2one(
        'ir.model.fields', ondelete='cascade',
        domain="[('store', '=', True)]",
        tracking=True)
    assign_related_policy_sort_direction = fields.Selection(
        selection=[
            ('asc', 'Ascending'),
            ('desc', 'Descending')])
    assign_user_field_type = fields.Selection(
        related='assign_user_field_id.ttype')
    assign_user_field_sort_field_id = fields.Many2one(
        'ir.model.fields', ondelete='cascade',
        domain="[('model', '=', 'res.users'),"
               " ('store', '=', True)]",
        tracking=True)
    assign_user_field_sort_direction = fields.Selection(
        selection=[
            ('asc', 'Ascending'),
            ('desc', 'Descending')])
    assign_user_field_choice_type = fields.Selection(
        selection=[
            ('first', 'First'),
            ('random', 'Random')],
        default='random')
    assign_user_field_choice_condition_ids = fields.Many2many(
        comodel_name='generic.condition',
        relation='generic_assign_policy_rel_user_field_choice_cond_rel')

    description = fields.Text(translate=True)

    @api.onchange('model_id')
    def _onchange_model_id(self):
        for rec in self:
            rec.assign_eval = False
            rec.assign_user_id = False
            rec.assign_user_field_id = False
            rec.assign_policy_id = False
            rec.assign_related_policy_field_id = False
            rec.assign_related_policy_field_model_id = False
            rec.assign_related_policy_id = False

    @api.onchange('assign_related_policy_field_id')
    def _onchange_assign_related_policy_field_id(self):
        for rec in self:
            rec.assign_related_policy_id = False
            rec.assign_related_policy_choice_type = False
            rec.assign_related_policy_choice_condition_ids = False

    @api.model
    def _choose_record(self, records, choice_type, order=None):
        """ Choose record from list using specified choice type

            :param Recordset records: Recordset to choice record from
            :return: False or choosen record
        """
        if not records:
            return False
        if not order:
            order = None
        if choice_type == 'first':
            return records.search(
                [('id', 'in', records.ids)], order=order, limit=1)
        if choice_type == 'random':
            indexes = list(range(len(records)))
            random.SystemRandom().shuffle(indexes)
            index = random.SystemRandom().choice(indexes)
            return records[index]
        return False

    def _get_assignee_eval(self, record, debug_log=None):
        self.ensure_one()

        mods = ['parser', 'relativedelta', 'rrule', 'tz']
        for mod in mods:
            __import__('dateutil.%s' % mod)
        _datetime = wrap_module(
            __import__('datetime'),
            ['date', 'datetime', 'time', 'timedelta', 'timezone',
             'tzinfo', 'MAXYEAR', 'MINYEAR'])
        _dateutil = wrap_module(dateutil, {
            mod: getattr(dateutil, mod).__all__
            for mod in mods
        })

        eval_context = dict(self.env.context)
        eval_context.update({
            'record': record,
            'env': self.env,
            'model': self.env[self.sudo().model_id.model],
            'uid': self.env.uid,
            'user': self.env.user,
            'date': _datetime.date,
            'time': _datetime.time,
            'datetime': _datetime.datetime,
            'dateutil': _dateutil,
            'timezone': _datetime.timezone,
            'timedelta': _datetime.timedelta,
            'logger': _logger,
        })
        assign_data = safe_eval(self.assign_eval, eval_context)
        if isinstance(assign_data, dict):
            return dict(assign_data)
        if assign_data is not False:
            _logger.warning(
                "Possible wrong computation of Assignment Policy Rule"
                " (%s)[%s]", self.name, self.id)
        return False

    def _get_assignee_user(self, record, debug_log=None):
        self.ensure_one()
        if self.assign_user_id:
            return {'user_id': self.assign_user_id}
        return False

    def _get_assignee_user_field__get_users(self, record):
        """Return recordset of res.users model that are assigned to a field
           self.assign_user_field_id.
        """
        users = record[self.sudo().assign_user_field_id.name]
        if users and self.assign_user_field_choice_condition_ids:
            conditions = self.assign_user_field_choice_condition_ids
            users = users.filtered(conditions.check)

        return users

    def _get_assignee_user_field(self, record, debug_log=None):
        self.ensure_one()
        if not self.sudo().assign_user_field_id:
            return False
        if self.sudo().assign_user_field_id.ttype == 'many2one':
            return {'user_id': record[self.sudo().assign_user_field_id.name]}

        if self.sudo().assign_user_field_id.ttype in (
                'many2many', 'one2many'):
            users = self._get_assignee_user_field__get_users(record)
            if not users:
                self._debug_log(
                    debug_log, record,
                    "no users to call related policy on")
                return False

            # TODO: it may make sense to remove this line of code
            # and add/leave a default value to the field attributes
            choice_type = self.assign_user_field_choice_type or 'first'
            order = None
            if self.sudo().assign_user_field_sort_field_id:
                order = ("%s %s" % (
                    self.sudo().assign_user_field_sort_field_id.name,
                    self.sudo().assign_user_field_sort_direction))
            user = self._choose_record(
                users, choice_type, order)
            return {'user_id': user.id}
        return False

    def _get_assignee_policy(self, record, debug_log=None):
        self.ensure_one()
        if self.assign_policy_id:
            return self.assign_policy_id.get_assign_data(
                record, debug_log=debug_log)
        return False

    def _get_assignee_related_policy(self, record, debug_log=None):
        self.ensure_one()
        if not self.assign_related_policy_id:
            self._debug_log(
                debug_log, record,
                "no related policy selected")

        related_policy_field = self.sudo().assign_related_policy_field_id.name
        related_records = record[related_policy_field]

        self._debug_log(
            debug_log, record,
            "Related records count %s" % len(related_records))

        # Filter related records by condition
        if related_records and self.assign_related_policy_choice_condition_ids:
            conditions = self.assign_related_policy_choice_condition_ids
            related_records = related_records.filtered(conditions.check)
            self._debug_log(
                debug_log, record,
                "Filtered records count %s" % len(related_records))

        if not related_records:
            self._debug_log(
                debug_log, record,
                "no related records to call related policy on")
            return False

        # TODO: it may make sense to remove this line of code
        # and add/leave a default value to the field attributes
        choice_type = self.assign_related_policy_choice_type or 'first'
        order = None
        if self.sudo().assign_related_policy_sort_field_id:
            order = ("%s %s" % (
                self.sudo().assign_related_policy_sort_field_id.name,
                self.sudo().assign_related_policy_sort_direction))
        related_records = self._choose_record(
            related_records, choice_type, order)
        if not related_records:
            self._debug_log(
                debug_log, record,
                "no records selected from related records")
            return False
        return self.assign_related_policy_id.get_assign_data(
            related_records, debug_log=debug_log)

    def _normalize_assign_data(self, assign_data):
        """ This method normalized 'assign_data' produced by '_get_assignee_*'
            methods. Normalication means:
                - Ensure that 'user_id' (if provided) is Integer,
                  that represents valid ID of user in 'res.users' model.
                - If provided 'user_id' is not Integer, then try to convert it
                  to Integer
                - If result is empty dict, then convert it to False

            :return dict: dictionary same as `assign_data` but with fixed
                          `user_id`.
        """
        self.ensure_one()
        if assign_data is False:
            return assign_data

        res = {}

        assignment_info = self.policy_id.get_assignment_fields_info()
        # atype = user_id
        # ainfo = {'field_name': field_name, 'model': 'res.users'}
        for atype, ainfo in assignment_info.items():
            if atype not in assign_data:
                continue
            if isinstance(assign_data[atype], int):
                if self.env[ainfo['model']].browse(
                        assign_data[atype]).exists():
                    res[atype] = assign_data[atype]
            if (isinstance(assign_data[atype], models.BaseModel) and
                    assign_data[atype]._name == ainfo['model']):
                res[atype] = assign_data[atype].id
        if not res:
            return False
        return res

    def _debug_log(self, debug_log, record, msg):
        self.ensure_one()
        if isinstance(debug_log, DebugLogger):
            debug_log.log(self, record, msg)

    def get_assign_data(self, record, debug_log=None):
        """ Compute assign data for specifid record by this assigment policy
        """
        self.ensure_one()
        self._debug_log(debug_log, record, "Computing...")

        assign_method_name = '_get_assignee_%s' % self.assign_type
        try:
            assign_method = getattr(self, assign_method_name)
        except AttributeError:
            _logger.error(
                "Error caught while getting assignment data %s[%d]",
                self.name, self.id, exc_info=True)
            raise

        res = assign_method(record, debug_log=debug_log)

        self._debug_log(
            debug_log, record,
            "Result before normalizing: %s" % res)
        normalized_res = self._normalize_assign_data(res)
        self._debug_log(
            debug_log, record,
            "Computed result: %s" % normalized_res)
        return normalized_res
