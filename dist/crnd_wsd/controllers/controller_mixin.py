from odoo import http
from odoo.tools import consteq
from odoo.exceptions import UserError, AccessError, ValidationError


class WSDControllerMixin(http.Controller):

    def _id_to_record(self, model, record_id, no_raise=False,
                      access_token=None):
        """ Get record by it's id.
            Optionally, do not raise error if record not found.
            If access_token is provided, then return record wrapped with sudo.

            :param str model: Name of model to look for record in
            :param int record_id: Int or convertable to int ID of record to
                read
            :param bool no_raise: If set to True, then no error will be raise.
                In this case, if error caught, then just empty recordset will
                be returned.
            :param str access_token: access token to validate access with
            :return: Recordset with record of specified model.
                If access_token provided and current user has no access
                to record, then record will be wrapped with sudo.
        """
        # pylint: disable=too-many-return-statements
        Model = http.request.env[model]
        if not record_id:
            return Model.browse()

        try:
            record = Model.browse(int(record_id))
        except (TypeError, ValueError):
            # If it is not possible to convert record_id to int
            if no_raise:
                return Model.browse()
            raise

        if not record.sudo().exists():
            return Model.browse()

        try:
            record.check_access_rights('read')
            record.check_access_rule('read')
        except AccessError:
            # Try to find access record as sudo
            if (access_token and
                    'access_token' in Model._fields and
                    consteq(record.sudo().access_token, access_token)):
                return record.sudo()
            if no_raise:
                return Model.browse()
            raise
        except (UserError, ValidationError):
            if no_raise:
                return http.request.env[model].browse()
            raise
        return record

    def _is_view_active(self, xmlid):
        """ Check if view is active or not
            :param str xmlid: external ID of view
            :return bool: True if view is active, otherwise False
        """
        view = http.request.env(su=True).ref(xmlid, raise_if_not_found=False)
        if view:
            return view.active
        return False
