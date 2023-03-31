import collections

from odoo import http
from odoo.addons.crnd_wsd.controllers.main import WebsiteRequest
from odoo.addons.project.controllers.portal import (
    ProjectCustomerPortal as CustomerPortal
)
from odoo.exceptions import AccessError


class RequestRequest(WebsiteRequest):
    def _request_page_get_extra_context(self, req_id, **kw):
        res = super(RequestRequest, self)._request_page_get_extra_context(
            req_id, **kw)
        request = http.request.env['request.request'].search(
            [('id', '=', req_id)])
        tasks_grouped = collections.defaultdict(
            http.request.env['project.task'].browse)
        for task in request.project_task_ids:
            tasks_grouped[task.project_id] += task
        res.update({'request_tasks_grouped': tasks_grouped})
        return res


class ProjectCustomerPortal(CustomerPortal):
    @http.route()
    def portal_my_task(self, task_id=None, **kw):
        res = super(ProjectCustomerPortal, self).portal_my_task(task_id, **kw)
        task = res.qcontext['task']
        if task.request_id:
            try:
                task.request_id.check_access_rights('read')
                task.request_id.check_access_rule('read')
            except AccessError:
                res.qcontext['request_access_denied'] = True
        return res
