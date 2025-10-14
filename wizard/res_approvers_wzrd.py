from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_round
import logging

_logger = logging.getLogger(__name__)

class ResApproversWizard(models.TransientModel):
    _name = 'res.approvers.wizard'
    _description = 'Approvals Wizard'

    total_quantity = fields.Float(string="Quantity", store=False)
    total_tax = fields.Monetary(string="VAT", store=False, currency_field='currency_id')
    total_total = fields.Monetary(string="Total", store=False, currency_field='currency_id')
    total_amount = fields.Monetary(string="Subtotal Amount", store=False, currency_field='currency_id')
    taxes_id = fields.Many2many('account.tax', string="Taxes")

    name = fields.Char()
    res_approver_id = fields.Many2one('res.approvers')
    whatModule = fields.Selection([
        ('rfq','Request for Quotation'),
        ('po','Purchase Order'),
        ('rfp', 'Request for Payments'),
        ('rr', 'Receiving'),
        ('it', 'Internal Transfer'),
        ('none','None')
    ], string="Module", required=True, readonly=True, default='none')
    submitted_to = fields.Selection([
        ('manager', 'MMD Manager'),
        ('vpo','VPO '),
        ('supervisor', 'Supervisor'),
        ('custodian', 'Stock Custodian'),
        ('pres_cfo','President/CFO'),
        ('none','NONE')
    ], string="Submitted to", default='none')
    company_id = fields.Many2one('res.company', 'Company', required=True)
    branch = fields.Many2one('res.company.branches')
    zone = fields.Selection([
        ('luzon', 'LUZON'),
        ('ncr', 'NCR'),
        ('visayas', 'VISAYAS'),
        ('mindanao', 'MINDANAO')
    ], string="Zone", related="branch.zone", store=True)
    isZone = fields.Selection([
        ('vismin','VISMIN'),
        ('lncr','LNCR'),
        ('all','All')
    ], default='all')
    currency_id = fields.Many2one('res.currency', 'Currency', required=True, default=lambda self: self.env.company.currency_id.id)

    # RFQ Fields
    quotation_request_id = fields.Many2one('ml.request.quotation', string="Request for Quotation")
    vendor_ids = fields.Many2many(
        'res.partner',  # Target model
        string="Vendor(s)",
        store=True
    )
    date_planned = fields.Date(
        string='RFQ Deadline', index=True, copy=False, store=True, readonly=False,
        help="Delivery date promised by vendor. This date is used to determine expected arrival of products.")

    # PO Fields
    purchase_order_id = fields.Many2one('purchase.order', string="Purchase Order")
    deliver_to = fields.Many2one('stock.warehouse', 'Deliver To')
    terms = fields.Many2one('account.payment.term')
    expected_arrival = fields.Date(string="Expected Arrival")
    remarks = fields.Text('Remarks')
    description = fields.Text('Description')

    # RR Fields
    stock_picking_id = fields.Many2one('stock.picking', string="Inventory Movement")

    # IT Fields
    internal_transfer_id = fields.Many2one('stock.picking', string="Internal Transfer")

    #RFP Fields
    payment_request_id = fields.Many2one('request.payments', string="Request for Payment")
    payment_terms = fields.Many2one('account.payment.term', string="Payment Terms")

    # One2Many fields here
    res_approver_items_ids = fields.One2many('res.approvers.wizard.line.items', 'res_approver_id', string="Line IDS")

    def action_approve(self):
        po = self.purchase_order_id
        rr = self.stock_picking_id
        it = self.internal_transfer_id
        rfp = self.payment_request_id

        if po: # Purchase Order
            # Approve by user role
            if self.submitted_to == 'manager':
                if not po.for_ho:
                    po.update({'remarks': self.remarks})
                    po.submitted_to_vpo()
                else:
                    po.update({'remarks': self.remarks})
                    po.submitted_to_president_cfo()

            elif self.submitted_to == 'supervisor':
                po.update({'remarks': self.remarks})
                po.submitted_to_manager_request()

            elif self.submitted_to == 'vpo':
                po.update({'remarks': self.remarks})
                po.submitted_to_president_cfo()

            elif self.submitted_to == 'pres_cfo':
                po.update({'remarks': self.remarks})
                po.approve()
        elif rfp: # Request for Payment
            # Approve by user role
            if self.submitted_to == 'manager':
                rfp.action_submit_to_vpo()
            elif self.submitted_to == 'supervisor':
                rfp.action_submit_to_vpo()
            elif self.submitted_to == 'vpo':
                rfp.action_submit_to_pres()
            elif self.submitted_to == 'pres_cfo':
                rfp.action_approve()
        elif rr: # Receiving Receipt
            if self.stock_picking_id.state == 'assigned':
                self.stock_picking_id.button_validate()
            else:
                raise UserError('Receiving Receipt has already been partially received. Please complete the approval process in the Receiving Receipt module.')
        elif it: # Internal Transfer
            self.stock_picking_id.button_validate()

        return {'type': 'ir.actions.act_window_close'}

    def action_reject(self):
        # Your logic here
        po = self.purchase_order_id

        if po: # Purchase Order
            po.rejected()

        return {'type': 'ir.actions.act_window_close'}
    
    def action_request_change(self):
        # Your logic here
        po = self.purchase_order_id
        
        if po: # Purchase Order
            po.update({'remarks': self.remarks})
            po.request_for_change()

        return {'type': 'ir.actions.act_window_close'}

class ResApproversWizardLine(models.TransientModel):
    _name = 'res.approvers.wizard.line.items'
    _description = 'Approvals Wizard Line'

    res_approver_id = fields.Many2one('res.approvers.wizard')
    purchase_order_id = fields.Many2one('purchase.order', string="Ref #")
    request_quotation_id = fields.Many2one('ml.request.quotation', string="Ref #")
    stock_picking_id = fields.Many2one('stock.picking', string="Inventory Movement")

    description = fields.Char()
    item_code = fields.Char()
    product_id = fields.Many2one('product.template', string='Product', domain=[('purchase_ok', '=', True)], change_default=True, index='btree_not_null')
    item_description = fields.Text(string="Product")
    product_uom = fields.Many2one('uom.uom', string='Unit of Measure', domain="[('category_id', '=', product_uom_category_id)]")
    product_uom_category_id = fields.Many2one(related='product_id.uom_id.category_id')
    product_qty = fields.Integer(string='Quantity', required=True, store=True, readonly=False, default="1")
    price_unit = fields.Float(string="Unit Price", store=True)
    amount = fields.Float(string='Amount', default=0.0, digits=(6, 2))
    total_amount = fields.Float(string='Total Amount', default=0.0, digits=(6, 2))
    taxes_id = fields.Many2many('account.tax', store=True, string="Tax")
    tax_duplicate = fields.Many2one('account.tax', string="Tax", compute="_compute_tax_duplicate", store=True)
    taxed_amount = fields.Float(string='Taxed Amount', default=0.0, compute='_compute_taxed_amount', store=True, digits=(6, 2))
    currency_id = fields.Many2one('res.currency', string="Currency", related='res_approver_id.currency_id')

    @api.depends('taxes_id')
    def _compute_tax_duplicate(self):
        for record in self:
            if record.taxes_id:
                # Example logic: set to first tax selected
                record.tax_duplicate = record.taxes_id[0]
            else:
                record.tax_duplicate = False
    
    @api.depends('price_unit', 'product_qty', 'tax_duplicate')
    def _compute_taxed_amount(self):
        for record in self:
            tax_amount = 0.0
            if record.tax_duplicate:
                tax = record.tax_duplicate
                tax_amount = (tax.amount / 100.0)

            tax_per_unit = float_round(record.price_unit * tax_amount, precision_digits=2)
            total_tax = tax_per_unit * record.product_qty
            # Round result
            price_total = float_round(total_tax, precision_digits=2)

            record.update({
                'taxed_amount': price_total,
            })

    @api.depends('product_qty', 'price_unit')
    def _compute_amount(self):
        for record in self:
            if record.tax_duplicate:
                tax = record.tax_duplicate
                tax_amount = (tax.amount / 100.0) + 1

            tax_per_unit = float_round(record.price_unit * tax_amount, precision_digits=2)
            total_tax = tax_per_unit * record.product_qty
            # Round result
            price_total = float_round(total_tax, precision_digits=2)

            record.update({
                'amount': price_total,
            })