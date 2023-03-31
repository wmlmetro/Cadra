from odoo import fields, models


class Website(models.Model):
    _inherit = "website"

    request_create_step_layout = fields.Selection(
        [('standard', 'Standard'),
         ('tiles', 'Tiles')],
        default='standard',
        required=True)

    request_redirect_after_created_on_website = fields.Selection(
        selection=[('congrats_page', 'Redirect to congratulation page'),
                   ('req_page', 'Redirect to request page')],
        default='congrats_page',
        required=True
    )

    def get_request_public_ui(self):
        """ Get type of public UI for request
        """
        self.ensure_one()
        return self.company_id.request_wsd_public_ui_visibility

    def get_request_public_use_author_phone(self):
        """ Get for public UI use author phone for request
        """
        self.ensure_one()
        return self.company_id.request_wsd_public_use_author_phone

    def is_request_author_phone_required(self):
        self.ensure_one()
        if not self.is_public_user():
            return False
        if self.get_request_public_use_author_phone() == 'required-phone':
            return True
        return False

    def is_request_restricted_ui(self):
        """ Check if restricted UI set in configuration
        """
        self.ensure_one()
        if not self.is_public_user():
            return False
        if self.get_request_public_ui() == 'restrict':
            return True
        return False

    def is_request_create_public(self):
        """ Return True only if current user is public user and
            the system configured to allow public users to create requests
        """
        self.ensure_one()
        if not self.is_public_user():
            return False
        if self.get_request_public_ui() == 'create-request':
            return True
        return False
