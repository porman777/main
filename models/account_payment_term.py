from odoo import _,api, models, fields 
from odoo.exceptions import ValidationError,UserError
import logging

_logger = logging.getLogger(__name__)

class RequestPaymentLines(models.Model):
    _inherit = 'account.payment.term'
    _description = 'Payments Terms Custom'

    payment_duration = fields.Integer()
    rec_types = fields.Selection([
        ('days','Day/s'),
        ('week','Week/s'),
        ('month','Month/s'),
        ('year','Year/s'),
    ], default='month')