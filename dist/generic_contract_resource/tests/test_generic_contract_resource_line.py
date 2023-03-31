import logging

from .common import TestGenericContractResourceCommon

_logger = logging.getLogger(__name__)


class TestGenericContractResourceLine(TestGenericContractResourceCommon):

    def test_name_get(self):
        self.assertEqual(
            self.basic_support_guest_book_line.display_name,
            'Basic support contract '
            '[%s]-[Guest Book Application [%s]]' % (
                self.basic_support_guest_book_line.contract_id.number,
                self.env.ref(
                    'generic_contract_resource.simple_resource_guest_book'
                ).inv_number,
            )
        )
