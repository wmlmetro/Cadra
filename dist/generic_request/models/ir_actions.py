import logging
from odoo import models

_logger = logging.getLogger(__name__)


class IrActionsActWindow(models.Model):
    _inherit = 'ir.actions.act_window'

    def _generic_request_fix_view_mode(self, views):
        """ Update views priority for requests according to company's settings
        """
        preferred_view_mode = \
            self.env.user.company_id.request_preferred_list_view_mode
        if not preferred_view_mode or preferred_view_mode == 'default':
            return views

        views_list = []
        for view_id, view_mode in views:
            if preferred_view_mode == 'list' and view_mode == 'tree':
                views_list.insert(0, (view_id, view_mode))
            elif preferred_view_mode == 'kanban' and view_mode == 'kanban':
                views_list.insert(0, (view_id, view_mode))
            else:
                views_list.append((view_id, view_mode))
        return views_list

    def read(self, fields=None, load='_classic_read'):
        """ changes default view for model 'request.request' depending of
         chosen option in request settings 'preferred view type'
        """
        result = super(IrActionsActWindow, self).read(fields=fields, load=load)
        request_act = self.env.ref(
            'generic_request.action_request_window',
            raise_if_not_found=False)
        if not request_act:
            return result

        # Modify only action global Requests menu
        for rec in result:
            if rec['id'] != request_act.id:
                continue
            if 'views' not in rec:
                continue
            rec['views'] = self._generic_request_fix_view_mode(rec['views'])

        return result
