from odoo import api, models, fields, _
from odoo.exceptions import ValidationError,UserError

class MLVendorPricelist(models.Model):
    _inherit = 'product.supplierinfo'
    _description = 'Supplier Pricelist'

    attachment_ids = fields.Many2many('ir.attachment', string='Attachments', help='Attach multiple files to this record', store=True)