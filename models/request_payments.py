from shutil import move
from xml.parsers.expat import model
from odoo import api, models, fields, _
from odoo.exceptions import ValidationError, UserError
from num2words import num2words
from odoo.tools import float_round
import logging

_logger = logging.getLogger(__name__)

class RequestPayment(models.Model):
    _name = 'request.payments'
    _rec_name = "name"
    _description = "RFP"
    _inherit = ['portal.mixin', 'product.catalog.mixin', 'mail.thread', 'mail.activity.mixin']

    # Purchase Order Form Custom Fields
    name = fields.Char('Ref Number', copy=False, default='New')
    to_field = fields.Many2one('res.partner', 'To vendor', tracking=True)
    bank_id = fields.Many2one('res.partner.bank', string="Bank")
    acc_number = fields.Char(string="Account Number")
    from_field = fields.Many2one('res.company.branches', 'From branch', tracking=True)
    date_requested = fields.Date('Date Requested')
    date_needed = fields.Date('Date Needed')                                                                                                                                                                                                                                                                                                                                                                                                                                   
    purpose = fields.Text(string='Purpose', tracking=True)
    remarks = fields.Text(string='Remarks', tracking=True)
    attachment =  fields.Many2many(
        'ir.attachment',  # Odoo's built-in attachment model
        'request_payments_attachment_rel',  # Link table name
        'request_payment_id',  # Column for your model
        'attachment_id', # Column for ir.attachment
        string="Attachments", 
        tracking=True
    )
    payee = fields.Char(string='Payee', tracking=True)
    select_zones = fields.Selection([
        ('lncr','LNCR'),
        ('vismin','VisMin'),
    ], string="Zones", tracking=True)

    zone = fields.Selection([
        ('luzon', 'LUZON'),
        ('ncr', 'NCR'),
        ('visayas', 'VISAYAS'),
        ('mindanao', 'MINDANAO')
    ], string="Zone" ,related="from_field.zone")
    amount_string = fields.Char(tracking=True)
    amount = fields.Float(tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('manager', 'Submitted to Manager'),
        ('vpo', 'Submitted to VPO'),
        ('iad', 'Submitted to IAD'),
        ('pres', 'Submitted to President'),
        ('finance', 'Submitted to Finance'),
        ('done', 'Approve Payment'),
        ('cancel', 'Cancelled'),
        ('change', 'Request for Change'),
    ], string='Status', readonly=True, copy=False, default='draft', tracking=True)
    po_number = fields.Many2one('purchase.order')
    company = fields.Many2one(
        'res.company', 
        string='Company',
        required=True, 
        default=lambda self: self.env.company
    )
    total_amount = fields.Float(string='Total Amount', compute="_auto_compute_total", store=True, readonly=False)
    request_payments_ids = fields.One2many('request.payments.line','request_payment_id')
    number_to_words = fields.Char(string="Number to Words", compute="_number_to_words")
    prepared_by = fields.Char('Prepared By')
    noted_by = fields.Char('Noted By')
    approved_by = fields.Char('Approved By')
    chairman_of_the_board = fields.Char('Chairman of the Board')
    president_ceo = fields.Char('President/CEO')
    source_document = fields.Many2one('purchase.order')
    currency_id = fields.Many2one(
        'res.currency', 'Currency', 
        required=True, default=lambda self: self.env.company.currency_id.id
    )
    isAdmin = fields.Boolean(store=True, default=False)
    
    @api.model
    def default_get(self, fields):
        # Call the super to get the default values dict
        res = super().default_get(fields)

        # Validate current user what zone he/she belongs
        user = self.env.user  # Current logged-in user
        group_luzon = self.env.ref('ml_development.group_lncr_mods')
        group_vismin = self.env.ref('ml_development.group_vismin_mods')

        if group_vismin in user.groups_id:
            res['select_zones'] = 'vismin'
        elif group_luzon in user.groups_id:
            res['select_zones'] = 'lncr'
        else:
            res['isAdmin'] = True  # If user is not in any zone, set isAdmin to True

        return res
    
    def _fix_attachment_ownership(self):
        for record in self:
            record.attachment.write({'res_model': record._name, 'res_id': record.id})
        return self

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('payments.form') or 'New'
        return super().create(vals_list)._fix_attachment_ownership()

    @api.onchange('to_field')
    def _onchange_vendors_default_payee(self):
        for rec in self:
            if rec.to_field:
                rec.payee = rec.to_field.name

                if not rec.select_zones: # Set zone if user is no region
                    rec.select_zones = rec.to_field.x_studio_zone

    @api.depends('request_payments_ids')
    def _auto_compute_total(self):
        for rec in self:
            rec.total_amount = sum(rec.request_payments_ids.mapped('payable_amount'))
    
    @api.depends('total_amount')
    def _number_to_words(self):
        currency = self.currency_id
        try:
            camelCase = num2words(float(self.total_amount), lang='en', to='currency', currency=currency.name)
            self.number_to_words = camelCase.title().replace("-", " ") or " "
        except NotImplementedError:
            # fallback: spell the number and manually add currency
            camelCase = num2words(float(self.total_amount), lang='en', to='cardinal')
            self.number_to_words = f"{camelCase.title().replace("-", " ")} {currency.name or currency.symbol}" or " "

    # Approved by RFP Manager
    def action_submitted_to_manager(self):
        if not self.to_field:
            raise UserError("Please ensure that a vendor is selected before proceeding.")

        self.state = 'manager'

        # Check if PO number is already exist in approvals
        checkApprovals = self.env['res.approvers'].search([('payment_request_id','=', self.id)], limit=1)
        if not checkApprovals:
            # Create data to approvals module
            self.env['res.approvers'].create({
                'payment_request_id': self.id,
                'zone': self.zone,
                'isZone': self.select_zones,
                'name': self.name,
                'module': 'rfp',
                'branch': self.from_field.id,
                'remarks': self.remarks,
                'total_amount': self.total_amount,
                'submitted_to': 'manager'
            })
        else: 
            # Update data to approvals module
            checkApprovals.update({
                'submitted_to': 'manager'
            })


    # Approved by Manager
    def action_submit_to_vpo(self):
        self.state = 'vpo'

        # Check if PO number is already exist in approvals
        checkApprovals = self.env['res.approvers'].search([('payment_request_id','=', self.id)], limit=1)
        if not checkApprovals:
            # Create data to approvals module
            self.env['res.approvers'].create({
                'payment_request_id': self.id,
                'zone': self.zone,
                'isZone': self.select_zones,
                'name': self.name,
                'module': 'rfp',
                'branch': self.from_field.id,
                'remarks': self.remarks,
                'total_amount': self.total_amount,
                'submitted_to': 'vpo'
            })
        else: 
            # Update data to approvals module
            checkApprovals.update({
                'submitted_to': 'vpo'
            })

    # Create Vendor Bill from Purchase Order
    def _create_vendor_bill(self):
        for rec in self:
            # Prepare bill lines from purchase order lines
            for rp in rec.request_payments_ids:
                # Collect invoice lines from purchase order
                invoice_lines = []

                # Get purchase order lines
                order_lines = rp.purchase_order_ids.order_line

                for line in order_lines:
                    tax_ids = line.taxes_id.ids

                    # 👉 Add Withholding Tax if Tax Type and ATC Code is set
                    if rp.tax_type == "vatable" and rp.atc_code:
                        tax_ids.append(rp.atc_code.id)

                    invoice_lines.append((0, 0, {
                        'product_id': line.product_id.id,
                        'name': line.name,
                        'quantity': line.product_qty,
                        'price_unit': line.price_unit,
                        'price_subtotal':  line.price_total,
                        'tax_ids': [(6, 0, tax_ids)],
                    }))

                # Create the vendor bill
                bill = self.env['account.move'].create({
                    'move_type': 'in_invoice',  # Vendor Bill
                    'partner_id': line.partner_id.id,
                    'invoice_date': fields.Date.context_today(self),
                    'invoice_line_ids': invoice_lines,
                    'purchase_id': line.id,
                    'ref': rec.name,
                })

                if bill: # Confirm Vendor Bill (Status: Posted)
                    bill.action_post()

    def action_submit_to_iad(self):
        for rec in self:
            # Update RFP Status to IAD
            rec.state = 'iad'

    def action_submit_to_pres(self):
        for rec in self:
            # Update RFP Status to President
            rec.state = 'pres'
        
        # Check if PO number is already exist in approvals
        checkApprovals = self.env['res.approvers'].search([('payment_request_id','=', self.id)], limit=1)
        if not checkApprovals:
            # Create data to approvals module
            self.env['res.approvers'].create({
                'payment_request_id': self.id,
                'zone': self.zone,
                'isZone': self.select_zones,
                'name': self.name,
                'module': 'rfp',
                'branch': self.from_field.id,
                'remarks': self.remarks,
                'total_amount': self.total_amount,
                'submitted_to': 'pres_cfo'
            })
        else: 
            # Update data to approvals module
            checkApprovals.update({
                'submitted_to': 'pres_cfo'
            })

    # Approved by IAD
    def action_submit_to_finance(self):
        for rec in self:
            # Run vendor bill creation
            # rec._create_vendor_bill()

            # Update RFP Status to Finance
            rec.state = 'finance'

    def _register_payment_for_vendor_bill(self, vendor_bill, amount):
        # Create payment register
        payment_register = self.env['account.payment.register'].with_context(
            active_model='account.move',
            active_ids=vendor_bill.ids,
        ).create({
            'payment_date': fields.Date.context_today(self),
            'journal_id': self.env['account.journal'].search([
                ('type', '=', 'cash'),
                ('code','=','CSH1')
            ], limit=1).id,
            'amount': float_round(amount, precision_digits=2),
        })

        # Create & post the payment
        payment_register.action_create_payments()

    # Approved by Finance
    def action_approve(self):
        for rec in self:
            payment = self.env['request.view.payments']
            
            for pay in self.request_payments_ids:
                vendor_bill = rec.env['account.move'].search([
                    ('ref','=', pay.purchase_order_ids.name),
                    ('move_type', '=', 'in_invoice')
                ])
                amount_due = float_round(vendor_bill.amount_residual, precision_digits=2)

                if amount_due <= 0 and vendor_bill.payment_state == 'paid':
                    raise ValidationError(_("No amount due for Vendor Bill: %s" % pay.purchase_order_ids.name))
                
                if not vendor_bill:
                    raise UserError(_("Vendor Bill not found for Purchase Order: %s" % pay.purchase_order_ids.name))
                else:
                    # Find outstanding debit line (refund / debit note)
                    outstanding_debits = self.env['account.move.line'].search([
                        ('partner_id', '=', vendor_bill.partner_id.id),
                        ('account_id.reconcile', '=', True),
                        ('reconciled', '=', False),
                        ('balance', '>', 0),  # positive balance = debit note/refund
                    ], limit=1)

                    # If there are outstanding debits, assign them automatically
                    if outstanding_debits:
                        model = self.env['account.move']
                        print([m for m in dir(model) if 'assign' in m])

                        # Find outstanding debit line (refund / debit note)
                        outstanding_debits = self.env['account.move.line'].search([
                            ('partner_id', '=', vendor_bill.partner_id.id),
                            ('account_id.reconcile', '=', True),
                            ('reconciled', '=', False),
                            ('balance', '>', 0),  # positive balance = debit note/refund
                        ], limit=1)

                        vendor_bill.js_assign_outstanding_line(outstanding_debits.id)

                    # If payment is an advance payment - No received amount
                    if pay.isAdvancePay:
                        # Create payment register
                        self._register_payment_for_vendor_bill(vendor_bill, pay.payable_amount)
                    
                    else: # If payment is not an advance payment - Received amount is available
                        received_amount = float_round(pay.rr_amount, precision_digits=2)

                        if received_amount < pay.payable_amount:
                            new_amount = float_round(pay.payable_amount - received_amount, precision_digits=2)
                            
                            # Create payment register for received amount
                            self._register_payment_for_vendor_bill(vendor_bill, received_amount)
                            # Create payment register for new amount - advance payment
                            self._register_payment_for_vendor_bill(vendor_bill, new_amount)

                        else:
                            # Create payment register for received amount
                            self._register_payment_for_vendor_bill(vendor_bill, received_amount)

                payment.create({
                    'rfp_line_id': pay.id,
                    'purchase_order_ids': pay.purchase_order_ids.id,
                    'name': self.name,
                    'tax_type': pay.tax_type,
                    'po_amount': pay.po_amount,
                    'rr_amount': pay.rr_amount,
                    'paid_amount': pay.paid_amount,
                    'payable_amount': pay.payable_amount,
                    'balance': pay.balance
                })

            # Update RFP Status to Done
            rec.state = 'done'
            # Check if PO number is already exist in approvals
            checkApprovals = self.env['res.approvers'].search([('payment_request_id','=', self.id)], limit=1)
            # Delete data to approvals module
            checkApprovals.unlink()

    def action_reject_payment(self):
        self.state = 'cancel'
        checkApprovals = self.env['res.approvers'].search([('payment_request_id','=', self.id)], limit=1)
            # Delete data to approvals module
        checkApprovals.unlink()
    
    def action_request_change(self):
        if not self.remarks:
            raise UserError(_("Please provide remarks for the change request."))

        # Set state to change and reset remarks
        self.state = 'change'

class JournalItemsAccount(models.TransientModel):
    _name = 'payment.journal.items'
    _description = 'Journal Items Account'

    rfp_line_id = fields.Many2one('request.payments.line', string="RFP Line")
    purchase_order_ids = fields.Many2one('purchase.order', related='rfp_line_id.purchase_order_ids', string="Purchase Order")
    account_id = fields.Many2one('account.account', string='Accounts')
    total_amount = fields.Float(string='Total', digits=(16, 2))
    debit_account = fields.Float(string='Debit', digits=(16, 2))
    credit_account = fields.Float(string='Credit', digits=(16, 2))
                