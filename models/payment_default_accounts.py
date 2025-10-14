from odoo import api, models, fields, _
from odoo.exceptions import ValidationError, UserError
from num2words import num2words
import logging

_logger = logging.getLogger(__name__)

class PaymentsDefaultAccounts(models.Model):
    _name = 'payment.default.accounts'
    _description = 'Default Accounts Payments'

    payment_type = fields.Selection([
        ('po_entry_rfp', 'PO Journal Entry'),
        ('po_reg_payment', 'PO Regular Payment'),
        ('po_adv_payment', 'PO Advance Payment')
    ], required=True)
    debit_account_ids = fields.Many2many(
        'account.account',
        relation='payment_default_accounts_debit_rel',  
        column1='payment_default_accounts_id',   
        column2='account_id',              
        string='Debit Accounts',
        readonly=False
    )
    credit_account_ids = fields.Many2many(
        'account.account',
        relation='payment_default_accounts_credit_rel',
        column1='payment_default_accounts_id',
        column2='account_id',
        string='Credit Accounts',
        readonly=False
    )