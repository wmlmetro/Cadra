from odoo import models


class RequestRequest(models.Model):
    _inherit = 'request.request'

    def _hook_can_change_request_text(self):
        if self.sudo().type_id.change_request_text_condition_ids:
            return (
                self.sudo().type_id.change_request_text_condition_ids.
                with_user(self.env.user).check(self))
        return super(RequestRequest, self)._hook_can_change_request_text()

    def _hook_can_change_assignee(self):
        if self.sudo().type_id.change_assignee_condition_ids:
            return self.sudo().type_id.change_assignee_condition_ids.with_user(
                self.env.user).check(self)
        return super(RequestRequest, self)._hook_can_change_assignee()

    def _hook_can_change_category(self):
        if self.sudo().type_id.change_category_condition_ids:
            return self.sudo().type_id.change_category_condition_ids.with_user(
                self.env.user).check(self)
        return super(RequestRequest, self)._hook_can_change_category()

    def _hook_can_change_deadline(self):
        if self.sudo().type_id.change_deadline_condition_ids:
            return self.sudo().type_id.change_deadline_condition_ids.with_user(
                self.env.user).check(self)
        return super(RequestRequest, self)._hook_can_change_deadline()

    def _hook_can_change_author(self):
        if self.sudo().type_id.change_author_condition_ids:
            return self.sudo().type_id.change_author_condition_ids.with_user(
                self.env.user).check(self)
        return super(RequestRequest, self)._hook_can_change_author()

    def _hook_can_change_service(self):
        if self.sudo().type_id.change_service_condition_ids:
            return self.sudo().type_id.change_service_condition_ids.with_user(
                self.env.user).check(self)
        return super(RequestRequest, self)._hook_can_change_service()
