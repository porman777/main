from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging
from collections import defaultdict

_logger = logging.getLogger(__name__)

class MLInheritPartners(models.Model):
    _inherit = 'res.partner'

    purchase_order_id = fields.Many2one('purchase.order', string='Purchase ID')
    bank = fields.Many2one('res.partner.bank')
    account_number = fields.Char(related='bank.acc_number')
    tin_number = fields.Char(string="TIN")
    tax_type = fields.Selection([
        ('vatable','Vatable'),
        ('exempt','Exempt'),
        ('zero','Zero Rated'),
        ('non_vat','NONVAT')
    ], default="vatable")
    tax_classification = fields.Selection([
        ('vat','Private - Value Added Tax (VAT) 12%'),
        ('pt','Private - Percentage Tax (PT) 12%'),
        ('foreign','Foreign'),
        ('zero','Zero Rated'),
        ('government','Government'),
        ('coop','Coop Exempt'),
        ('non_govt','Non-Government'),
    ], default="vat")
    expense_classification = fields.Selection([
        ('asset','Asset'),
        ('goods','Goods'),
        ('service','Services'),
        ('puchase','Importation - Purchases'),
        ('vat','Importation - VAT'),
        ('import_other','Importation - Other Charges'),
        ('bir','National/Local Govt. - BIR'),
        ('sss','National/Local Govt. - SSS'),
        ('phic','National/Local Govt. - PHIC'),
        ('hdmf','National/Local Govt. - HDMF'),
        ('national_other','National/Local Govt. - Other')
    ], default="asset")
    account_form_goods = fields.Selection([
        ('sales_order','Sales Order'),
        ('del_receipt','Delivery Receipt'),
        ('sales_invoice','Sales Invoice'),
        ('billing','Billing Statement'),
        ('collection','Collection Receipt')
    ], default="sales_order")
    account_form_service = fields.Selection([
        ('sales_invoice','Sales Invoice'),
        ('statement_acc','Statement of Accounts'),
        ('official_receipt','Official Receipt')
    ], default="sales_invoice")
    atc_code = fields.Many2one('account.tax')
    rate = fields.Float(related='atc_code.amount')
    supplier_code = fields.Char()

class AreaRegionManagers(models.Model):
    _name = 'area.region.managers'
    _description = 'Area/Region Manager'

    zone = fields.Selection([
        ('luzon', 'LUZON'),
        ('ncr', 'NCR'),
        ('visayas', 'VISAYAS'),
        ('mindanao', 'MINDANAO')
    ], string="Zone",  store=True)
    region_code = fields.Char('Region Code')
    region_name = fields.Char('Region Name')
    area_name = fields.Char('Area Name')
    resource_id_number =  fields.Char('Resource ID Number')
    last_name =  fields.Char('Last Name')
    first_name =  fields.Char('First Name')
    middle_name = fields.Char('Middle Name')
    suffix = fields.Char('Suffix')
    email = fields.Char('Email Address')
    complete_name = fields.Char('Complete Name')
    contact_number = fields.Char('Contact Number')
    manager_rank = fields.Boolean()
    manager_type = fields.Selection([
        ('area_manager', 'Area Manager'),
        ('region_manager', 'Region Manager'),
    ], string="Zone",  store=True)
    

class BranchManagers(models.Model):
    _name = 'branch.managers'
    _description = 'Branch Manager'
    _rec_name = 'complete_name'

    complete_name = fields.Char('Complete Name')
    phone  = fields.Char('Phone')
    zone = fields.Selection([
        ('luzon', 'LUZON'),
        ('ncr', 'NCR'),
        ('visayas', 'VISAYAS'),
        ('mindanao', 'MINDANAO')
    ], string="Zone",  store=True)
    region_code = fields.Char('Region Code')
    region_name = fields.Char('Region Name')
    resource_id_number =  fields.Char('Resource ID Number')
    last_name =  fields.Char('Last Name')
    first_name =  fields.Char('First Name')
    middle_name = fields.Char('Middle Name')
    suffix = fields.Char('Suffix')
    email = fields.Char('Email Address')
    area_name = fields.Char('Area Name')
    contact_number = fields.Char('Contact Number')
    manager_rank = fields.Boolean()
    manager_type = fields.Selection([
        ('area_manager', 'Area Manager'),
        ('region_manager', 'Region Manager'),
    ], string="Zone",  store=True)
    branch_name = fields.Char('Branch Name')
    old_branch_code = fields.Char('Old Branch Code')
    new_branch_code = fields.Char('New Branch Code')
    manager_type = fields.Selection([
        ('area_manager', 'Area Manager'),
        ('region_manager', 'Region Manager'),
    ], string="Zone",  store=True)


    partner_id = fields.Many2one('res.partner', string="Related Partner")

    @api.model
    def create(self, vals):
        record = super().create(vals)
        # Auto-create partner if not linked
        if vals.get('email') and not record.partner_id:
            partner = self.env['res.partner'].create({
                'name': vals.get('complete_name') or vals.get('first_name') or 'Unnamed',
                'email': vals.get('email'),
                'phone': vals.get('phone'),
            })
            record.partner_id = partner.id
        return record

    def write(self, vals):
        res = super().write(vals)
        for rec in self:
            if rec.partner_id:
                update_vals = {}
                if vals.get('complete_name'):
                    update_vals['name'] = vals['complete_name']
                if vals.get('email'):
                    update_vals['email'] = vals['email']
                if vals.get('phone'):
                    update_vals['phone'] = vals['phone']
                if update_vals:
                    rec.partner_id.write(update_vals)
        return res

class MLABM(models.Model):
    _name = 'ml.abm'
    _description = 'ML ABM List'

    complete_name = fields.Char('Complete Name')
    phone  = fields.Char('Phone')
    zone = fields.Selection([
        ('luzon', 'LUZON'),
        ('ncr', 'NCR'),
        ('visayas', 'VISAYAS'),
        ('mindanao', 'MINDANAO')
    ], string="Zone",  store=True)
    region_code = fields.Char('Region Code')
    region_name = fields.Char('Region Name')
    resource_id_number =  fields.Char('Resource ID Number')
    last_name =  fields.Char('Last Name')
    first_name =  fields.Char('First Name')
    middle_name = fields.Char('Middle Name')
    suffix = fields.Char('Suffix')
    email = fields.Char('Email Address')
    area_name = fields.Char('Area Name')
    contact_number = fields.Char('Contact Number')
    manager_rank = fields.Boolean()
    manager_type = fields.Selection([
        ('area_manager', 'Area Manager'),
        ('region_manager', 'Region Manager'),
    ], string="Zone",  store=True)
    branch_name = fields.Char('Branch Name')
    old_branch_code = fields.Char('Old Branch Code')
    new_branch_code = fields.Char('New Branch Code')