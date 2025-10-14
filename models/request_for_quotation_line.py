from odoo import api, Command, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class MLRequestQuotationLine(models.Model):
    _name = 'ml.request.quotation.line'
    _inherit = 'analytic.mixin'
    _description = 'Request for Quotation Line'

    order_id = fields.Many2one('ml.request.quotation', string='Order Reference', ondelete='cascade')
    related_vendor = fields.Many2many('res.partner', string="Suppliers", store=True)
    product_id = fields.Many2one('product.product', string='Product', domain=[('purchase_ok', '=', True)], 
        change_default=True, index='btree_not_null', readonly=False, compute='_compute_related_product', store=True)
    product_tmpl_id = fields.Many2one('product.template', string='Product', readonly=False)
    product_uom = fields.Many2one('uom.uom', string='Unit of Measure', domain="[('category_id', '=', product_uom_category_id)]")
    product_uom_category_id = fields.Many2one(related='product_id.uom_id.category_id')
    name = fields.Text(string='Description', required=True, store=True, readonly=False, compute='_compute_name_and_product_price')
    product_qty = fields.Integer(string='Quantity', required=True, store=True, readonly=False, default="1")
    company_id = fields.Many2one('res.company', related='order_id.company_id', string='Company', store=True, readonly=True)
    state = fields.Selection(related='order_id.state', store=True)
    partner_id = fields.Many2one('res.partner', string='Supplier', store=True, readonly=False)
    currency_id = fields.Many2one(related='order_id.currency_id', store=True, string='Currency', readonly=True)
    date_planned = fields.Datetime(
        string='Expected Arrival', index=True, copy=False, store=True, readonly=False,
        help="Delivery date promised by vendor. This date is used to determine expected arrival of products.")
    selection = fields.Selection(selection=[], string="Selection")
    price_unit = fields.Float(
        string='Unit Price', digits='Product Price',
        compute="_compute_name_and_product_price", store=True, readonly=False)
    price_unit_duplicate = fields.Float(string='Unit Price', digits='Product Price', default=0.0, related='price_unit')
    amount = fields.Float(string='Amount', default=0.0, digits=(6, 2))
    display_type = fields.Selection([
        ('line_section', "Section"),
        ('line_note', "Note")], default=False, help="Technical field for UX purpose.")
    product_packaging_id = fields.Many2one('product.packaging', string='Packaging', domain="[('purchase', '=', True), ('product_id', '=', product_id)]", check_company=True, store=True, readonly=False)

    @api.depends('product_tmpl_id')
    def _compute_related_product(self):
        for record in self:
            if record.product_tmpl_id:
                products = self.env['product.product'].search([
                    ('product_tmpl_id', '=', record.product_tmpl_id.id),
                    ('purchase_ok', '=', True),
                ])
                if len(products) == 1:
                    record.product_id = products.id or record.product_tmpl_id.product_variant_id
                else:
                    record.product_id = False
    
    @api.onchange('order_id', 'partner_id')
    def _validate_vendor_ids(self):
        for rec in self:
            if rec.order_id.vendor_ids:
                vendors = rec.order_id.vendor_ids.ids
                rec.related_vendor = [(6, 0, vendors)]
                
                # Check partner_id value
                if rec.partner_id:
                    if rec.partner_id.id not in vendors:
                        raise UserError(_("The partner {} is not in the list of approved vendors.").format(rec.partner_id.name or ''))

    @api.onchange('price_unit')
    def _onchange_price_unit_amount(self):
        for record in self:
            get_vendors_product = self.env['product.supplierinfo'].search([
                ('product_id','=',record.product_tmpl_id.id),
                ('partner_id','in',record.order_id.vendor_ids.ids)
            ], limit=1)

            product_price = record.product_tmpl_id.purchase_price or record.price_unit
            record.price_unit = product_price or get_vendors_product.price
            record.amount = (record.price_unit or get_vendors_product.price) * record.product_qty

    @api.depends('product_tmpl_id')
    def _compute_name_and_product_price(self):
        """Compute the name field based on the selected product."""
        for record in self:
            product_name = _("{} {}").format(record.product_tmpl_id.default_code or '', record.product_tmpl_id.name or '')
            record.name = product_name if record.product_tmpl_id else ''
            product_price = record.product_tmpl_id.purchase_price or record.price_unit

            get_vendors_product = self.env['product.supplierinfo'].search([
                ('product_id','=',record.product_tmpl_id.id),
                ('partner_id','in',record.order_id.vendor_ids.ids)
            ], limit=1)

            # Add default value from vendor pricelist
            record.price_unit = product_price or get_vendors_product.price
            record.amount = (record.price_unit or get_vendors_product.price) * record.product_qty
            record.product_uom = record.product_tmpl_id.uom_id