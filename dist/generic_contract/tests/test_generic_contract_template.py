import logging

from .common import TestGenericContractCommon

_logger = logging.getLogger(__name__)


class TestGenericContractTemplate(TestGenericContractCommon):

    def test_action_view_template_contracts(self):
        res = self.supplier_template.action_view_template_contracts()
        self.assertEqual(
            res['domain'],
            [('template_id', '=', self.supplier_template.id)])
        self.assertEqual(
            res['context']['default_template_id'], self.supplier_template.id)
