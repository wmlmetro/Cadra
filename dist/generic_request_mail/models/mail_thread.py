from odoo import models, api


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    @api.model
    def message_process(self, model, message, custom_values=None,
                        save_original=False, strip_attachments=False,
                        thread_id=None):
        # Overridden to apply request creation template
        # Request creation template used if following conditions met:
        # - models is 'request.request'
        # - there is 'fetchmail_server_id' in context
        # - fetchmail server has request creation template
        # - custom_values not provided
        #
        # Otherwise - use standard behavior
        if model != 'request.request':
            return super(MailThread, self).message_process(
                model, message, custom_values=custom_values,
                save_original=save_original,
                strip_attachments=strip_attachments,
                thread_id=thread_id)
        if not self.env.context.get('default_fetchmail_server_id'):
            return super(MailThread, self).message_process(
                model, message, custom_values=custom_values,
                save_original=save_original,
                strip_attachments=strip_attachments,
                thread_id=thread_id)

        fetchmail_srv = self.env['fetchmail.server'].browse(
            self.env.context.get('default_fetchmail_server_id'))
        request_tmpl = fetchmail_srv.request_creation_template_id
        if request_tmpl and not custom_values:
            custom_values = request_tmpl.prepare_request_data(custom_values)

        return super(MailThread, self).message_process(
            model, message, custom_values=custom_values,
            save_original=save_original,
            strip_attachments=strip_attachments,
            thread_id=thread_id)

    @api.model
    def message_route(self, message, message_dict, model=None, thread_id=None,
                      custom_values=None):
        # Overridden to attach mail to existing request by mail subject
        # Mail will be attached to request if following conditions met:
        # - 'request_attach_messages_to_request_by_subject' set to True
        # - there is only the one request name mention in subject
        # - there is no reply to other mail
        # Otherwise - used standard behavior
        company = self.env.user.company_id
        try:
            result = super(MailThread, self).message_route(
                message,
                message_dict,
                model=model,
                thread_id=thread_id,
                custom_values=custom_values)
        except ValueError:
            # if no route has been found standard way
            # will try to find the request name in mail subject
            # and set the mail route
            # Otherwise - raising error by standard behavior
            if not company.request_attach_messages_to_request_by_subject:
                raise

            request = self._request__find_request_from_message_subject(
                message_dict)
            if not request:
                raise
            return [('request.request', request.id, None, self._uid, None)]

        if not company.request_attach_messages_to_request_by_subject:
            return result

        routes = []
        for r_model, r_thread_id, r_custom_vals, r_uid, r_alias in result:
            if r_model == 'request.request' and not r_thread_id:
                # Instead of creating new request, we have to check,
                # may be we could link message to existing request
                # (mentioned in subject) instead of creating new one.
                request = self._request__find_request_from_message_subject(
                    message_dict)

                if request:
                    r_thread_id = request.id

            routes += [(r_model, r_thread_id, r_custom_vals, r_uid, r_alias)]

        return routes

    def _request__find_request_from_message_subject(self, message_dict):
        """ Find routes for requests in message subject.
            This method, will check if there is name or request present in
            mail message subject, and if such name found, it will
            return the route to link the message to already existing request.

            :param dict message_dict: Dictionary with message data
            :return: Recordset with request found or empty recordset
        """
        words = message_dict.get('subject', '').split(' ')

        requests = self.env['request.request'].browse()
        for word in words:
            # TODO: add some regex to check the format of the work.
            #       for example, name of request must have numbers.
            if len(word) > 3:
                # Skip words that are too short
                # because, usually names of requests have more than 3 symbols
                requests += self.env['request.request'].search(
                    [('name', '=', word)], limit=2)

        if len(requests) == 1:
            return requests
        return self.env['request.request'].browse()
