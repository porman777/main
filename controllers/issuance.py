from odoo import http
from odoo.http import request
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)

class IssuanceConfirmController(http.Controller):
    # Confirm issuance form when it's triggered
    @http.route('/issuance/confirm', type='http', auth='public', website=True, methods=['GET'], csrf=False)
    def confirm_issuance(self, token=None, **kwargs):
        if not token:
            return http.request.not_found()
            
        record = request.env['issuance.form'].sudo().search([('state','=','sent'),('confirmation_token', '=', token)], limit=1)
        if not record:
            return http.request.not_found()

        # Expired Token
        if record.token_expiry and record.token_expiry < datetime.now():
            return http.request.not_found()

        # Run validate button - to deduct stock
        record.sudo().button_approve()
        
        # Mark confirmation
        record.sudo().write({
            'confirmation_token': False, 
            'token_expiry': False, 
            'state': 'done'
        })
        return request.render('ml_development.confirmation_template', {'issuance': record})