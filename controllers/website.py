from odoo import http
from odoo.http import request

class CustomRedirectController(http.Controller):
    @http.route('/web/database/selector', type='http', auth="public")
    def redirect_database_selector(self, **kwargs):
        return request.redirect('/web/login')

    @http.route('/', type='http', auth="public")
    def redirect_home_route(self, **kwargs):
        return request.redirect('/web/login')