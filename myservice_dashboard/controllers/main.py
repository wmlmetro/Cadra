from odoo import http
from odoo.http import request
import json


class MyServiceDashboardController(http.Controller):

    @http.route('/myservice/dashboard/kpis', type='json',
                auth='user', methods=['POST'])
    def get_kpis(self):
        return request.env['myservice.dashboard'].get_kpis()

    @http.route('/myservice/dashboard/map', type='json',
                auth='user', methods=['POST'])
    def get_map_data(self):
        return request.env['myservice.dashboard'].get_map_data()
