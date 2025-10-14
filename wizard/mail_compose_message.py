import logging
from odoo import api, models

_logger = logging.getLogger(__name__)

class MailComposeMessage(models.TransientModel):
    _inherit = 'mail.compose.message'

    def action_send_mail(self, auto_commit=False):
        _logger.info("send_mail method called")  # Debug Log

        res = super(MailComposeMessage, self).action_send_mail()
        tracking_po_id = self._context.get('tracking_po_id')
        _logger.info(f"Tracking PO ID from context: {tracking_po_id}")  # Debug Log

        if tracking_po_id:
            purchase_order = self.env['purchase.order'].browse(tracking_po_id)
            if purchase_order.exists():
                _logger.info(f"Updating PO {tracking_po_id} to 'po_sent'")  # Debug Log
                purchase_order.state = 'po_sent'
            else:
                _logger.warning(f"Purchase Order with ID {tracking_po_id} not found!")  # Debug Log
        else:
            _logger.warning("No tracking_po_id found in context")  # Debug Log

        return res
