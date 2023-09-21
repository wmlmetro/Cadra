import logging

from odoo.tests.common import TransactionCase
from odoo.addons.generic_mixin.tests.common import ReduceLoggingMixin
from odoo.addons.generic_request.tests.common import (
    RequestClassifierUtilsMixin)

_logger = logging.getLogger(__name__)


class TestRequestFieldCase(ReduceLoggingMixin,
                           RequestClassifierUtilsMixin,
                           TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestRequestFieldCase, cls).setUpClass()

        cls.simple_type = cls.env.ref(
            'generic_request.request_type_simple')
        cls.field_type = cls.env.ref(
            'generic_request_field.request_type_field')
        cls.stage_field_new = cls.env.ref(
            'generic_request_field.request_stage_type_field_new')

        cls.request_field_memory = cls.env.ref(
            'generic_request_field.request_stage_field_memory')
        cls.request_field_cpu = cls.env.ref(
            'generic_request_field.request_stage_field_cpu')
        cls.request_field_hdd = cls.env.ref(
            'generic_request_field.request_stage_field_hdd')
        cls.request_field_os = cls.env.ref(
            'generic_request_field.request_stage_field_os')
        cls.request_field_comment = cls.env.ref(
            'generic_request_field.request_stage_field_comment')

        # Fields for request type Create LXC container
        cls.request_field_lxc_cpu = cls.env.ref(
            'generic_request_field.request__create_lxc_field_cpu')
        cls.request_field_lxc_memory = cls.env.ref(
            'generic_request_field.request__create_lxc_field_memory')
        cls.request_field_lxc_hdd = cls.env.ref(
            'generic_request_field.request__create_lxc_field_hdd')
        cls.request_field_lxc_priviledged = cls.env.ref(
            'generic_request_field.request__create_lxc_field_priviledged')
        cls.request_field_lxc_container_name = cls.env.ref(
            'generic_request_field.request__create_lxc_field_container_name')
        cls.request_field_lxc_domain_name = cls.env.ref(
            'generic_request_field.request__create_lxc_field_domain_name')
        cls.request_field_lxc_expose_port = cls.env.ref(
            'generic_request_field.request__create_lxc_field_expose_port')

        cls.request_category_demo = cls.env.ref(
            'generic_request.request_category_demo')
        cls.request_category_demo_technical = cls.env.ref(
            'generic_request.request_category_demo_technical')

    def _enable_use_services_setting(self):
        (
            self.env.ref('base.group_user') +
            self.env.ref('base.group_portal') +
            self.env.ref('base.group_public')
        ).write({
            'implied_ids': [
                (4,
                 self.env.ref(
                     'generic_request.group_request_use_services').id),
            ]
        })
