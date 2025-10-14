from odoo import api, models, fields, _
from odoo.exceptions import ValidationError, UserError
from num2words import num2words
import logging

_logger = logging.getLogger(__name__)

class RequestViewPayment(models.Model):
    _name = 'request.view.payments'
    _description = 'View Payments'
    _rec_name = "name"

    rfp_line_id = fields.Many2one('request.payments.line', string="RFP Lines")
    purchase_order_ids = fields.Many2one('purchase.order')
    name = fields.Char(string="Reference Number")
    tax_type = fields.Selection([
        ('vatable','Vatable'),
        ('exempt','Exempt'),
        ('zero','Zero Rated'),
        ('non_vat','NONVAT'),
    ])
    po_amount = fields.Float(string="PO Amount", compute="_auto_compute_po_amount", store=True, readonly=True, related='rfp_line_id.po_amount')
    rr_amount = fields.Float(string="RR Amount", store=True, readonly=True, related='rfp_line_id.rr_amount')
    paid_amount = fields.Float(string="Amount Paid", store=True, related='rfp_line_id.paid_amount')
    payable_amount = fields.Float(string="To be Paid", store=True, related='rfp_line_id.payable_amount')
    balance = fields.Float(string="Balance", store=True)
    terms = fields.Many2one('account.payment.term', related='rfp_line_id.terms')
    terms_by_text = fields.Char(string="Terms", related='rfp_line_id.terms_by_text')
    state = fields.Selection([
        ('process', 'On-process'),
        ('done', 'Approved'),
    ], string='Status', readonly=True, copy=False)