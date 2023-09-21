from odoo import http
from odoo.addons.portal.controllers.mail import (
    _message_post_helper,
    PortalChatter,
)


# We have to inherit this controller from http.Controller,
# or, at least, http.Controller have to be available in globals,
# to ensure that this controller is registered, otherwise,
# chatter may not work because Odoo cannot find this route
class PortalRequestChatter(PortalChatter, http.Controller):

    # Based on /mail/chatter_post
    # implemented to avoid html escapes
    @http.route(['/mail/request_chatter_post'], type='json',
                methods=['POST'], auth='public', website=True)
    def portal_chatter_post(self, res_model, res_id, message,
                            attachment_ids=None, attachment_tokens=None, **kw):
        """Create a new `mail.message` with the given `message` and/or
        `attachment_ids` and return new message values.

        The message will be associated to the record `res_id` of the model
        `res_model`. The user must have access rights on this target
        document or must provide valid identifiers through `kw`.
        See `_message_post_helper`.
        """
        res_id = int(res_id)

        self._portal_post_check_attachments(attachment_ids, attachment_tokens)

        if message or attachment_ids:
            result = {'default_message': message}
            # message is received in plaintext and saved in html
            # if message:
            #     message = plaintext2html(message)

            if kw.get('pid'):
                # Enforce covertion of 'pid' param to int if present
                # This is needed to bypass bug in odoo code, that try to
                # browse partner record with string ID. So, this way,
                # we can ensure that everything will work fine.
                kw = dict(kw, pid=int(kw['pid']))

            post_values = {
                'res_model': res_model,
                'res_id': res_id,
                'message': message,
                'send_after_commit': False,
                'attachment_ids': False,  # will be added afterward
            }
            post_values.update(
                (fname, kw.get(fname))
                for fname in self._portal_post_filter_params()
            )
            post_values['_hash'] = kw.get('hash')
            message = _message_post_helper(**post_values)
            result.update({'default_message_id': message.id})

            if attachment_ids:
                # sudo write the attachment to bypass the read access
                # verification in mail message
                record = http.request.env[res_model].browse(res_id)
                message_values = {'res_id': res_id, 'model': res_model}
                attachments = record._message_post_process_attachments(
                    [], attachment_ids, message_values)

                if attachments.get('attachment_ids'):
                    message.sudo().write(attachments)

                result.update({
                    'default_attachment_ids': (
                        message.attachment_ids.sudo().read([
                            'id', 'name', 'mimetype',
                            'file_size', 'access_token']))})
            return result
        return {}
