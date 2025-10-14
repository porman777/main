from odoo import api, models, fields, _
from datetime import datetime
from odoo.exceptions import UserError, ValidationError

class MLAttachments(models.Model):
    _name = 'ml.attachment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'attachment_filename'
    _description = 'ML Attachments'

    attachment_id = fields.Many2one('ml.request.quotation', ondelete="cascade")
    attachment_file = fields.Binary(string='Attachments', help='Attach multiple files to this record', store=True)
    attachment_ids = fields.Many2many(
        'ir.attachment', 
        string="Attachments",
        help="Attach multiple files to this record"
    )
    attachment_filename = fields.Char(string="File Name", store=True)
    partner_id = fields.Many2one('res.partner', string='Supplier', store=True)
    attached_date = fields.Date(string='Date', default=datetime.today())

    def _fix_attachment_ownership(self):
        for record in self:
            record.attachment_ids.write({'res_model': record._name, 'res_id': record.id})
        return self
    
    @api.model
    def create(self, vals):
        return super(MLAttachments, self).create(vals)._fix_attachment_ownership()

    @api.onchange('attachment_id', 'partner_id')
    def _get_vendor_ids(self):
        for rec in self:
            if rec.attachment_id.vendor_ids and rec.partner_id:
                vendors = rec.attachment_id.vendor_ids.ids
                if rec.partner_id.id not in vendors:
                    raise UserError(_("The supplier {} is not in the list of approved vendors.").format(rec.partner_id.name or ''))
                
    @api.onchange('attachment_id')
    def _get_attachment_ids(self):
        for rec in self:
            if rec.attachment_file:
                rec.attachment_filename = self._context.get('filename')
    
class MLDashboard(models.TransientModel):
    _name = 'ml.dashboard'
    _description = 'ML Dashboard'

    total_purchase_orders = fields.Integer(string="Total Purchase Orders", compute="_compute_metrics")
    pending_approvals = fields.Integer(string="Pending Approvals", compute="_compute_metrics")
    total_purchase_amount = fields.Float(string="Total Purchase Amount", compute="_compute_metrics")

    def _compute_metrics(self):
        for record in self:
            record.total_purchase_orders = self.env['purchase.order'].search_count([])
            record.pending_approvals = self.env['purchase.order'].search_count([('state', '=', 'to approve')])
            record.total_purchase_amount = sum(self.env['purchase.order'].search([]).mapped('amount_total'))
  
    # same as above
    @api.model
    def default_get(self, fields):
        rec = self.search([], limit=1)
        return rec.read(fields)[0] if rec else super().default_get(fields)
