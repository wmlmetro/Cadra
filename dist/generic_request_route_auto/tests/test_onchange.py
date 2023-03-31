from odoo.tests.common import TransactionCase


class TestRouteTriggerOnchanges(TransactionCase):

    def test_onchange(self):
        req = self.env['request.stage.route.trigger'].new()
        req.onchange_gen_trigger_name()
        self.assertEqual(req.name, "")

        req.route_id = self.env.ref(
            'generic_request_route_auto.'
            'request_stage_route_type_auto_draft_to_sent')
        req.onchange_gen_trigger_name()
        self.assertEqual(req.name, "Send")

        req.trigger = "auto_on_write"
        req.onchange_gen_trigger_name()
        self.assertEqual(req.name, "Auto: On write | Send")

        req.route_id = False
        req.onchange_gen_trigger_name()
        self.assertEqual(req.name, "Auto: On write")

        req.trigger = False
        req.onchange_gen_trigger_name()
        self.assertEqual(req.name, "")
