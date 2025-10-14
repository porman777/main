from odoo import api, models, fields, _
from odoo.exceptions import ValidationError, UserError
from num2words import num2words
import logging

_logger = logging.getLogger(__name__)

class RequestPaymentLines(models.Model):
    _name = 'request.payments.line'
    _rec_name = "name"
    _description = 'RFP Lines'
    
    request_payment_id = fields.Many2one('request.payments', ondelete='cascade')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('manager', 'Submitted to Manager'),
        ('vpo', 'Submitted to VPO'),
        ('pres', 'Submitted to President'),
        ('iad', 'Submitted to IAD'),
        ('finance', 'Submitted to Finance'),
        ('done', 'Approved'),
    ], string='Status', readonly=True, copy=False, related='request_payment_id.state')
    name = fields.Char(related='request_payment_id.name', string="Reference Number")
    purchase_order_ids = fields.Many2one('purchase.order',  domain="[('state', '=', 'po_sent')]")
    tax_type = fields.Selection([
        ('vatable','Vatable'),
        ('exempt','Exempt'),
        ('zero','Zero Rated'),
        ('non_vat','NONVAT'),
    ])
    currency_id = fields.Many2one('res.currency', 'Currency', required=True, default=lambda self: self.env.company.currency_id.id)
    atc_code = fields. Many2one('account.tax', string="ATC Code")
    rate = fields. Float(related='atc_code.amount', digits=(16, 2))
    withholding_tax = fields.Float(store=True, compute="_onchange_purchase_order_tax")
    description = fields.Text(string="Description")
    amount_total = fields.Monetary(string="Untaxed", related="purchase_order_ids.amount_untaxed", store=True)
    vat_amount = fields.Monetary(string="VAT", related="purchase_order_ids.amount_tax", store=True, readonly=True)
    po_amount = fields.Float(string="Total PO", compute="_auto_compute_po_amount", store=True, readonly=True)
    rr_amount = fields.Float(string="RR Amount", store=True, readonly=True)
    paid_amount = fields.Float(string="Amount Paid", compute="_auto_compute_paid_amount", store=True)
    payable_amount = fields.Float(string="To be Paid", compute="_auto_compute_payable_amount", store=True, readonly=False)
    net_amount = fields.Float(string="Net", compute="_auto_compute_net_amount", store=True)
    payment_term = fields.Selection([
        ('full','Full'),
        ('partial','Partial')
    ], default="full", string="Terms")
    terms = fields.Many2one('account.payment.term')
    terms_by_text = fields.Char(string="Terms", default='0/0')
    payment_percentage = fields.Char(string="Payment Percentage", readonly=True)
    balance = fields.Float(string="Balance", compute="_auto_compute_balance", store=True)
    payment_ids = fields.One2many('request.view.payments', 'rfp_line_id')
    isCustomPay = fields.Boolean(string="Custom Payment", default=False)
    isAdvancePay = fields.Boolean(string="Advance Payment", default=False)
    no_received_item = fields.Boolean(store=True, default=False)
    payment_exceeds_received = fields.Boolean(store=True, default=False)
    journal_items = fields.One2many('payment.journal.items', 'rfp_line_id', string='Journal Items')

    # @api.onchange('purchase_order_ids') ========================================>>
    def _onchange_purchase_order_auto_fill_journals(self):
        for rec in self:
            if rec.purchase_order_ids:
                # Collect product account entries
                product_account_entries = []
                # Validate and gather product accounts
                account_exist = []

                order_lines = rec.purchase_order_ids.order_line
                for line in order_lines:
                    # Find the expense account for the product
                    account_name = line.product_id.credit_gl_description or line.product_id.property_account_expense_id.name
                    debit_account = self.env['account.account'].search([('name', '=', account_name)], limit=1)

                    # Ensure product has expense account
                    if debit_account or line.product_id.property_account_expense_id:
                        if debit_account.id not in account_exist: # Aggregate amounts by account
                            account_exist.append(debit_account.id)
                            product_account_entries.append({
                                'debit_account_id': debit_account.id,
                                'product_price': line.price_unit * line.product_qty
                            })
                        else:
                            for entry in product_account_entries:
                                if entry['debit_account_id'] == debit_account.id:
                                    entry['product_price'] += line.price_unit * line.product_qty
                                    break
                    else:
                        raise UserError(_("Please define an expense account for the product: %s" % line.product_id.name))
                    
                default_accounts_reg_payment = self.env['payment.default.accounts'].search([
                    ('payment_type', '=', 'po_entry_rfp')
                ], limit=1)
                debit_accounts = default_accounts_reg_payment.debit_account_ids
                credit_accounts = default_accounts_reg_payment.credit_account_ids

                # Clear existing journal items
                rec.journal_items = [(5, 0, 0)]

                # Collect all journal item commands
                journal_items = []

                # Input Journal Items - Product accounts (Debit)
                for account in product_account_entries: # Add product account entries to journal items
                    journal_items.append((0, 0, {
                        'rfp_line_id': rec.id,
                        'account_id': account['debit_account_id'],
                        'debit_account': account['product_price'],
                        'credit_account': 0.0,
                    }))

                # Input Journal Items (Debit)
                for debit in debit_accounts:
                    debit_amount = rec.vat_amount if debit.name == 'Input VAT' else rec.amount_total
                    journal_items.append((0, 0, {
                        'rfp_line_id': rec.id,
                        'account_id': debit.id,
                        'debit_account': debit_amount,
                        'credit_account': 0.0
                    }))
                
                # Input Journal Items (Credit)
                for credit in credit_accounts:
                    credit_amount = rec.withholding_tax if credit.name == 'Withholding Taxes - Expanded' else rec.balance
                    journal_items.append((0, 0, {
                        'rfp_line_id': rec.id,
                        'account_id': credit.id,
                        'debit_account': 0.0,
                        'credit_account': credit_amount
                    }))

                # Assign all journal items at once
                rec.journal_items = journal_items
    
    @api.onchange('purchase_order_ids')
    def _automate_warning_advance_payment_no_received(self):
        for rec in self:
            if rec.purchase_order_ids:
                if not rec.rr_amount or rec.rr_amount == 0.0:
                    rec.no_received_item = True
                else:
                    rec.no_received_item = False
    
    @api.onchange('payable_amount')
    def _automate_warning_advance_payment_exceeds_amount(self):
        for rec in self:
            # Round to 2 decimal places
            payable_amount = round(rec.payable_amount, 2)
            rr_amount = round(rec.rr_amount, 2)

            if rr_amount or rr_amount != 0.0:
                if payable_amount > rr_amount:
                    rec.payment_exceeds_received = True
                else:
                    rec.payment_exceeds_received = False

    @api.onchange('purchase_order_ids')
    def _validate_vendor_po_and_rfp(self):
        for rec in self:
            if rec.request_payment_id and rec.purchase_order_ids:
                po_vendor = rec.request_payment_id.to_field
                rfp_vendor = rec.purchase_order_ids.partner_id

                if po_vendor != rfp_vendor:
                    raise ValidationError(_("Vendor in Request for Payment must match Vendor in Purchase Order."))

    @api.constrains('payable_amount')
    def _check_payable_amount(self):
        for rec in self:
            # Round to 2 decimal places
            payable_amount = round(rec.payable_amount, 2)
            balance = round(rec.balance, 2)

            if payable_amount <= 0:
                raise ValidationError(_("Payable amount must be greater than zero."))
            if payable_amount > balance:
                raise ValidationError(_("Payable amount cannot exceed the balance."))
    
    @api.constrains('purchase_order_ids')
    def restrict_vendor_in_rfp(self):
        for rec in self:
            if rec.request_payment_id and rec.purchase_order_ids:
                po_vendor = rec.request_payment_id.to_field
                rfp_vendor = rec.purchase_order_ids.partner_id

                if po_vendor != rfp_vendor:
                    raise ValidationError(_("Vendor in Request for Payment must match Vendor in Purchase Order."))
            
    @api.onchange('request_payment_id')
    def _onchange_vendors_default_atc_code_tax(self):
        for rec in self:
            vendor_tax = rec.request_payment_id.to_field.tax_type
            vendor_atc_code = rec.request_payment_id.to_field.atc_code
            if vendor_tax:
                rec.tax_type = vendor_tax
            if vendor_atc_code:
                rec.atc_code = vendor_atc_code

    @api.depends('purchase_order_ids','rr_amount','atc_code')
    def _onchange_purchase_order_tax(self):
        for rec in self:
            # Compute tax
            if rec.atc_code and (rec.rr_amount or rec.po_amount):
                rec.withholding_tax = (rec.rr_amount or rec.po_amount) * (rec.rate / 100)
            else:
                rec.withholding_tax = False
    
    @api.depends('purchase_order_ids')
    def _auto_compute_po_amount(self):
        for rec in self:
            # Auto-fill PO details on PO number
            for order in self.purchase_order_ids:
                if order.amount_total:
                    rec.po_amount = order.amount_total
                    rec.rr_amount = order.received_amount
                    rec.terms = order.terms
                else:
                    rec.po_amount = False
                    rec.rr_amount = False
                    rec.terms = False
    
    @api.depends('purchase_order_ids')
    def _auto_fill_payments(self):
        if self.purchase_order_ids:
            # check if there are other payments existed
            search_payments = self.env['request.view.payments'].search([
                ('purchase_order_ids','=', self.purchase_order_ids.id), 
                ('rfp_line_id.state','=', 'done')
            ])
            # self.payment_ids = {}
    
    @api.depends('amount_total','withholding_tax','atc_code')
    def _auto_compute_net_amount(self):
        for rec in self:
            if rec.amount_total and rec.withholding_tax and rec.atc_code:
                rec.net_amount = rec.amount_total - rec.withholding_tax
            else:
                rec.net_amount = rec.amount_total
    
    @api.depends('rr_amount', 'terms')
    def _auto_compute_paid_amount(self):
        for rec in self:
            total_paid = 0
            
            # check if there are other payments existed
            check_payments = self.env['request.view.payments'].search([
                ('purchase_order_ids','=', rec.purchase_order_ids.id),
                ('rfp_line_id.state','=','done')
            ])
            for paid in check_payments:
                total_paid += paid.payable_amount
            rec.paid_amount = total_paid
    
    @api.depends('rr_amount', 'terms')
    def _auto_compute_payable_amount(self):
        if self.rr_amount != 0.0:
            # check if there are other payments existed
            check_payments = self.env['request.view.payments'].search([
                ('purchase_order_ids','=', self.purchase_order_ids.id),
                ('rfp_line_id.state','=','done')
            ])

            vendor_bill = self.env['account.move'].search([
                ('ref','=', self.purchase_order_ids.name),
                ('move_type', '=', 'in_invoice')
            ])

            # Find corresponding account payment
            account_payment = self.env['account.payment'].search(['|',
                ('move_id', '=', vendor_bill.id),
                ('memo', '=', str(self.purchase_order_ids.name))
            ])

            print(vendor_bill.ref, account_payment.memo, account_payment.amount, '=============>>')

            # Payment terms info
            payment_duration = self.terms.payment_duration
            percentage = self.terms.line_ids
            
            if check_payments: # No w/tax
                total_payments = len(check_payments)
                if len(percentage) >= total_payments: # More payments than terms
                    balanceChecker = 0
                    transactionBalance = self.rr_amount + self.withholding_tax

                    for check in check_payments: # Loop through existing payments
                        balanceChecker += check.payable_amount

                    # Check if balance matches the available payments
                    if transactionBalance == balanceChecker:
                        raise ValidationError("All scheduled payments have already been completed.")
                    
                    if not self.isCustomPay:
                        percentage_id = percentage[total_payments]
                        percentage_value = percentage_id.value_amount

                        self._fill_payable_amount( # Assign values
                            total_payments + 1, 
                            percentage_value,
                            payment_duration
                        )
                else:
                    raise ValidationError("All scheduled payments have already been completed.")

            elif not check_payments: # No payments | Add w/tax amount
                total_payments = 1
                percentage_id = percentage[0]
                percentage_value = percentage_id.value_amount
                
                if not self.isCustomPay:
                    self._fill_payable_amount( # Assign values
                        total_payments, 
                        percentage_value,
                        payment_duration
                    )
    
    def _fill_payable_amount(self, total_payments, percentage_value, payment_duration):
        getBalance = self.rr_amount + self.withholding_tax
        self.payable_amount = getBalance * (percentage_value / 100)
        self.terms_by_text = f'{total_payments}/{payment_duration}'
        self.payment_percentage = f'{total_payments}/{payment_duration} - {percentage_value}%'
    
    @api.depends('purchase_order_ids')
    def _auto_compute_balance(self):
        if self.purchase_order_ids:
            total_paid = 0
            search_payments = self.env['request.view.payments'].search(
                [('purchase_order_ids','=', self.purchase_order_ids.id)],
                order='id desc'
            )
            if search_payments:
                for payment in search_payments:
                    total_paid += payment.payable_amount
                self.balance = search_payments[-1].balance - total_paid
            else:
                untaxed_amount = self.rr_amount or self.po_amount
                wtax = self.withholding_tax
                self.balance = untaxed_amount + wtax
    
    def view_payment(self):
        # check if there are other payments existed
        check_payments = self.search([
            ('purchase_order_ids','=', self.purchase_order_ids.id),
            ('rfp_line_id.state','!=','draft')
        ])

        if not check_payments:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Error"),
                    'type': 'danger',
                    'message': _("Some records could not be approved due to pending payments."),
                    'sticky': False,
                }
            }

        return {
            'type': 'ir.actions.act_window',
            'name': 'List of Payments',
            'res_model': 'request.view.payments',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_rfp_line_id': self.id},
            'domain': []
        }