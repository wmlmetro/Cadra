from odoo import models, fields


class RequestEventAction(models.Model):
    _inherit = "request.event.action"

    act_type = fields.Selection(
        selection_add=[('invoice', 'Generate Invoice')],
        ondelete={'invoice': 'cascade'}
    )
    invoice_auto_validate = fields.Boolean()

    def _run_invoice(self, request, event):
        invoice = request._action_generate_invoice(no_raise=True)
        if invoice and self.invoice_auto_validate:
            invoice = self.env['account.move'].browse(invoice.id)
            invoice.action_post()

    def _dispatch(self, request, event):
        """ Dispatch action and run corresponding method
        """
        if self.act_type == 'invoice':
            return self._run_invoice(request, event)
        return super(RequestEventAction, self)._dispatch(request, event)
