from odoo import _,api, models, fields 
from odoo.exceptions import ValidationError,UserError
from odoo.tools import float_round
import logging

_logger = logging.getLogger(__name__)

class PurchaseOrderLineInherit(models.Model):
    _inherit = 'purchase.order.line'

    unit = fields.Integer('Units')
    order_id = fields.Many2one('purchase.order', string='Order Reference')
    rfq_id = fields.Many2one('ml.request.quotation', string='Order Reference', index=True, ondelete='cascade')
    supplier_id = fields.Many2one('res.partner', string='Supplier', store=True)
    amount = fields.Float(string='Amount', default=0.0, digits=(6, 2))
    product_qty = fields.Integer(string='Quantity', digits='Product Unit of Measure', required=True,
        compute='_compute_product_qty', store=True, readonly=False)
    item_code = fields.Char('Item Code')
    untaxed_amount = fields.Float(string='Untaxed Amount', default=0.0, digits=(6, 2))
    taxed_amount = fields.Float(string='Taxed Amount', default=0.0, digits=(6, 2))
    tax_duplicate = fields.Many2one('account.tax', string="Tax")
    product_tmpl_id = fields.Many2one('product.template', readonly=False)
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        domain=[('purchase_ok', '=', True)],
        required=True,
        ondelete='restrict',
        store=True,
        compute="_auto_fill_product_id",
        readonly=False
    )
    taxes_id = fields.Many2many('account.tax', string='Taxes', compute='_compute_taxes_id',
        store=True, help="Taxes that apply on the purchase order line.",
        domain="[('type_tax_use', '=', 'purchase'), ('active', '=', True)]", readonly=False)
    
    @api.depends('product_qty', 'price_unit', 'taxes_id')
    def _compute_amount(self):
        for line in self:
            currency = line.order_id.currency_id
            sub_total = line.price_unit * line.product_qty

            if line.tax_duplicate:
                tax = line.tax_duplicate
                tax_amount = (tax.amount / 100.0) + 1

            tax_per_unit = float_round(line.price_unit * tax_amount, precision_digits=2)
            total_tax = tax_per_unit * line.product_qty

            # Round result
            price_total = float_round(total_tax, precision_digits=2)
            line.update({
                'price_subtotal': sub_total,  # optional if you want to ignore base subtotal
                'price_total': price_total,
            })
    
    @api.constrains('price_unit')
    def _check_product_price(self):
        for line in self:
            if line.price_unit <= 0:
                raise ValidationError(_("Price cannot be negative or zero!"))

    @api.depends('product_tmpl_id')
    def _auto_fill_product_id(self):
        for line in self:
            if line.product_tmpl_id:
                # Get first variant only (typical)
                variant = line.product_tmpl_id.product_variant_id  # get the main variant
                line.product_id = variant.id if variant else False

    @api.onchange('product_qty', 'product_id', 'name', 'product_uom', 'price_unit')
    def _onchange_compute_unit_price(self):
        for line in self:
            # Only set price_unit ONCE if walang laman
            if not line.price_unit and line.product_id:
                line.price_unit = line.product_tmpl_id.standard_price

            # Recalculate amount
            if line.product_qty > 0 and line.price_unit:
                line.amount = line.product_qty * line.price_unit
            elif line.product_qty == 0:
                line.product_qty = line._origin.product_qty
                line.amount = line._origin.amount

            # Auto-fill item code
            if line.product_id.item_code:
                line.item_code = line.product_id.item_code
            
            # Assign taxes based on customer tax type
            partner = self.order_id.partner_id
            
            if partner.tax_type == 'vatable':
                tax = self.env['account.tax'].search([('name', '=', '12%'), ('active', '=', True)], limit=1)
            elif partner.tax_type == 'zero':
                tax = self.env['account.tax'].search([('name', '=', '0% ZR')], limit=1)
            else:
                tax = self.env['account.tax'].search([('name', '=', '0% EXEMPT')], limit=1)

            if tax:
                self.tax_duplicate = tax.id
    
    @api.depends('tax_duplicate')
    def _compute_taxes_id(self):
        for line in self:
            if line.tax_duplicate:
                line.taxes_id = [(6, 0, [line.tax_duplicate.id])]
            else:
                line.taxes_id = [(5, 0, 0)]