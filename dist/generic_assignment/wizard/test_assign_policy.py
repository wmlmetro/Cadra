import logging

from odoo import models, fields, tools, exceptions, _

from ..models.generic_assign_policy_rule import DebugLogger

_logger = logging.getLogger(__name__)


class TestGenericAssignPolicy(models.TransientModel):
    _name = 'generic.assign.policy.test_assign_policy'
    _description = "Wizard: Test generic assign policy"

    assign_policy_id = fields.Many2one(
        'generic.assign.policy', 'Policy',
        required=True, ondelete='cascade')
    assign_user_field_id = fields.Many2one(
        'ir.model.fields', related='assign_policy_id.assign_user_field_id',
        readonly=True, ondelete='cascade')
    res_model = fields.Char(
        string='Object Model',
        related='assign_policy_id.model_id.model',
        readonly=True)
    res_id = fields.Many2oneReference(
        'Object ID', help='ID of object to test assign policy on',
        model_field='res_model')
    test_as_user_id = fields.Many2one('res.users')

    result_get = fields.Text(readonly=True)
    result_convert = fields.Text(readonly=True)
    debug_log = fields.Html(readonly=True)
    result_user_id = fields.Many2one('res.users', readonly=True)

    def get_record(self):
        self.ensure_one()
        TestModel = self.env[self.assign_policy_id.sudo().model_id.model]
        record = TestModel.search([('id', '=', self.res_id)], limit=1)

        if not record:
            raise exceptions.ValidationError(_(
                'Object (model: %(model)s; id: %(res_id)s) not found'
            ) % {
                'model': self.assign_policy_id.sudo().model_id.model,
                'res_id': self.res_id,
            })
        return record

    def _get_assign_data(self, debug_log):
        record = self.get_record()
        if self.test_as_user_id:
            return self.assign_policy_id.with_user(
                self.test_as_user_id,
            ).get_assign_data(
                record.with_user(self.test_as_user_id),
                debug_log=debug_log)
        return self.assign_policy_id.get_assign_data(
            record, debug_log=debug_log)

    def _convert_data(self, assign_data, debug_log):
        if self.test_as_user_id:
            return self.assign_policy_id.with_user(
                self.test_as_user_id
            ).convert_assign_data(
                assign_data, debug_log=debug_log)

        return self.assign_policy_id.convert_assign_data(
            assign_data)

    def run_test_get(self):
        self.ensure_one()
        debug_log = DebugLogger()
        result_get = self._get_assign_data(debug_log)
        vals = {
            'result_get': tools.ustr(result_get),
            'result_user_id': (
                result_get.get('user_id', False) if result_get else False),
        }
        if self.assign_user_field_id:
            result_convert = self._convert_data(result_get, debug_log)
            vals['result_convert'] = tools.ustr(result_convert)
        vals['debug_log'] = debug_log.get_log_html()
        self.write(vals)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'generic.assign.policy.test_assign_policy',
            'view_mode': 'form',
            'res_id': self.id,
            'views': [(False, 'form')],
            'target': 'new',
        }
