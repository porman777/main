from odoo import api, models, fields, _
from datetime import datetime
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class Approvers(models.Model):
    _name = 'res.approvers'
    _rec_name = 'name'
    _description = 'Approval Module'

    # Common Fields
    name = fields.Char(string="Reference")
    state = fields.Selection([
        ('submitted_to_manager', 'Submitted to Manager'),
        ('submitted_to_vpo','Submitted to VPO '),
        ('submitted_to_president','Submitted to President'),
        ('submitted_to_stock_custodian','Submitted to Stock Custodian'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('purchase', 'Purchase Order'),
    ], string="Status")
    submitted_to = fields.Selection([
        ('manager', 'MMD Manager'),
        ('vpo','VPO '),
        ('supervisor', 'Supervisor'),
        ('custodian', 'Stock Custodian'),
        ('pres_cfo','President/CFO'),
        ('none','NONE')
    ], string="Submitted to", default='none')
    module = fields.Selection([
        ('rfq', 'Request for Quotation'),
        ('po', 'Purchase Order'),
        ('rfp', 'Request for Payment'),
        ('rr', 'Receiving Receipt'),
        ('it', 'Internal Transfer')
    ], string="Module")
    zone = fields.Selection([
        ('luzon', 'LUZON'),
        ('ncr', 'NCR'),
        ('visayas', 'VISAYAS'),
        ('mindanao', 'MINDANAO')
    ], string="Zone", store=True)
    isZone = fields.Selection([
        ('vismin','VISMIN'),
        ('lncr','LNCR'),
        ('all','All')
    ], default='all')

    # Many2one Fields
    purchase_order_id = fields.Many2one('purchase.order', string="Purchase Order")
    payment_request_id = fields.Many2one('request.payments', string="Request for Payment")
    quotation_request_id = fields.Many2one('ml.request.quotation', string="Request for Quotation")
    stock_picking_id = fields.Many2one('stock.picking', string="Inventory Movement")
    internal_transfer_id = fields.Many2one('stock.picking', string="Internal Transfer")

    branch = fields.Many2one('res.company.branches', string="Branch/Head Office")
    remarks = fields.Char('Description')
    total_amount = fields.Float(string="Total Amount")

    def action_view_remarks(self):
        print("Remarks: ", self.remarks)

    # View specific data in RFQ Form
    def view_rfq_form(self):
        return {
            'type': 'ir.actions.act_window',
            'name': f'Request for Quotation - {self.name}',
            'res_model': 'ml.request.quotation',
            'view_mode': 'form',
            'view_id': self.env.ref('ml_development.ml_request_quotation_view_form').id,
            'target': 'new',
            'res_id': self.quotation_request_id.id,
            'context': {}
        }
    
    # More Details
    def view_details_action(self):
        po = self.purchase_order_id
        rr = self.stock_picking_id 
        it = self.internal_transfer_id 
        rfp = self.payment_request_id

        module_value = False
        dict_items = []
        context = {}
        
        if po: # Store data from Purchase Order
            module_value = 'po'
            for items in po.order_line:
                dict_items.append({
                    'item_code': items.item_code,
                    'product_id': items.product_tmpl_id.id,
                    'item_description': items.name,
                    'product_qty': items.product_qty,
                    'product_uom': items.product_uom.id,
                    'price_unit': items.price_unit,
                    'taxes_id': items.taxes_id.ids,
                    'amount': items.amount
                })
                
            # Common Fields
            context['default_res_approver_id'] = self.id
            context['default_whatModule'] = module_value
            context['default_name'] = self.name
            context['default_submitted_to'] = self.submitted_to or 'none'
            context['default_company_id'] = po.corporation.id or False
            context['default_branch'] = po.branch.id or False
            context['default_zone'] = po.zone or False
            context['default_isZone'] = po.isZone or False
            context['default_currency_id'] = po.currency_id.id or False

            # PO Fields
            context['default_purchase_order_id'] = po.id
            context['default_terms'] = po.terms.id
            context['default_expected_arrival'] = po.expected_arrival
            context['default_remarks'] = po.remarks
            context['default_description'] = po.description
            context['default_total_amount'] = po.amount_untaxed # Subtotals
            context['default_total_tax'] = po.amount_tax # VAT Value
            context['default_total_total'] = po.amount_total # Total amount

            # One2Many Fields
            context['default_res_approver_items_ids'] = dict_items
        
        elif rr: # Store data from Receiving Receipt Form 
            module_value = 'rr'
            for items in rr.move_ids_without_package:
                dict_items.append({
                    'item_code': items.product_id.item_code,
                    'product_id': items.product_id.id,
                    'product_qty': items.quantity,
                    'product_uom': items.product_uom.id,
                    'price_unit': items.unit_cost,
                })
            
            # Common Fields
            context['default_whatModule'] = module_value
            context['default_name'] = self.name
            context['default_submitted_to'] = self.submitted_to or 'none'
            context['default_company_id'] = rr.company_id.id
            context['default_branch'] = rr.branch.id
            context['default_isZone'] = rr.isZone

            # RR Fields
            context['default_stock_picking_id'] = rr.id

            # One2Many Fields
            context['default_res_approver_items_ids'] = dict_items

        elif it: # Store data from Internal Transfer
            module_value = 'it'
            for items in it.move_ids_without_package:
                dict_items.append({
                    'item_code': items.product_id.item_code,
                    'product_id': items.product_id.id,
                    'product_qty': items.quantity,
                    'product_uom': items.product_uom.id,
                    'price_unit': items.unit_cost,
                })
            
            # Common Fields
            context['default_whatModule'] = module_value
            context['default_name'] = self.name
            context['default_submitted_to'] = self.submitted_to or 'none'
            context['default_company_id'] = it.company_id.id
            context['default_branch'] = it.branch.id
            context['default_isZone'] = it.isZone

            # IT Fields
            context['default_internal_transfer_id'] = it.id
            
            # One2Many Fields
            context['default_res_approver_items_ids'] = dict_items
        elif rfp:  # Store data from Request for Payment
            module_value = 'rfp'
            if not hasattr(rfp, 'request_payments_ids'):
                # safety fallback, avoid crash
                dict_items = []
            else:
                for items in rfp.request_payments_ids.purchase_order_ids.order_line:
                    dict_items.append({
                        'item_code': items.item_code,
                        'product_id': items.product_tmpl_id.id,
                        'product_qty': items.product_qty,
                        'product_uom': items.product_uom.id,
                        'price_unit': items.price_unit,
                        'taxes_id': items.taxes_id.ids,
                        'amount': items.amount
                    })
                # Common Fields
                context['default_res_approver_id'] = self.id
                context['default_whatModule'] = module_value
                context['default_name'] = self.name
                context['default_submitted_to'] = self.submitted_to or 'none'
                context['default_company_id'] = rfp.company.id if rfp else False
                context['default_branch'] = rfp.from_field.id if rfp else False
                context['default_zone'] = rfp.zone  if rfp else False

                context['default_isZone'] = rfp.select_zones if rfp else False
                context['default_currency_id'] = rfp.currency_id.id if rfp else False
                # RFP Fields
                context['default_payment_request_id'] = rfp.id
                context['default_remarks'] = rfp.remarks if rfp else False
                # One2Many Fields
                context['default_res_approver_items_ids'] = dict_items

        return {
            'type': 'ir.actions.act_window',
            'name': f'More Details - {self.name}',
            'res_model': 'res.approvers.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('ml_development.view_my_wizard_approvals_form').id,
            'target': 'new',
            'context': context
        }

    def batch_approve(self):
        for item in self:
            rfq = item.quotation_request_id
            po = item.purchase_order_id
            rr = item.stock_picking_id 
            it = item.internal_transfer_id 

            # Identify what module
            if item.module == 'po' and po: # Purchase Order
                # Approve by user role
                if item.submitted_to == 'manager':
                    if not po.for_ho:
                        po.submitted_to_vpo()
                    else:
                        po.submitted_to_president_cfo()
                elif item.submitted_to == 'supervisor':
                    po.submitted_to_manager_request()
                elif item.submitted_to == 'vpo':
                    po.submitted_to_president_cfo()
                elif item.submitted_to == 'pres_cfo':
                    po.approve()
                else:
                    raise UserError('Purchase Order has already been approved or rejected. Please check the status of the Purchase Order.')
            elif item.module == 'rr' and rr: # Receiving Receipt
                if rr.state == 'assigned':
                    rr.button_validate()
                else:
                    raise UserError('Receiving Receipt has already been partially received. Please complete the approval process in the Receiving Receipt module.')
            elif item.module == 'it' and it: # Internal Transfer
                it.button_validate()
            elif item.module == 'rfq' and rfq: # Request for Quotation
                raise UserError('RFQ is not allowed in batch approval. Please check the module type.')

        # Show success message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Records Successfully Approved!"),
                'type': 'success',
                'message': _("Records for approval are successfully approved!"),
                'sticky': True,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }
            }
        }
    
    def action_approve(self):
        po = self.purchase_order_id
        rr = self.stock_picking_id
        it = self.internal_transfer_id 
        rfp = self.payment_request_id

        # Purchase Order
        if po and self.module == 'po':
            # Approve by user role
            if self.submitted_to == 'manager':
                if not po.for_ho:
                    po.submitted_to_vpo()
                else:
                    po.submitted_to_president_cfo()
            elif self.submitted_to == 'supervisor':
                po.submitted_to_manager_request()
            elif self.submitted_to == 'vpo':
                po.submitted_to_president_cfo()
            elif self.submitted_to == 'pres_cfo':
                po.approve()

        elif rfp and self.module == 'rfp': # Request for Payment
            # Approve by user role
            if self.submitted_to == 'manager':
                rfp.action_submit_to_vpo()
            elif self.submitted_to == 'supervisor':
                rfp.action_submit_to_vpo()
            elif self.submitted_to == 'vpo':
                rfp.action_submit_to_pres()
            elif self.submitted_to == 'pres_cfo':
                rfp.action_approve()

        # Receiving Receipt
        elif rr and self.module == 'rr':
            if rr.state == 'assigned':
                rr.button_validate()
            else:
                raise UserError('Receiving Receipt has already been partially received. Please complete the approval process in the Receiving Receipt module.')

        # Internal Transfer
        elif it and self.module == 'it':
            if it.state == 'assigned':
                it.button_validate()
            else:
                raise UserError('Internal Transfer has already been partially received. Please complete the approval process in the Internal Transfer module.')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Records Successfully Approved!"),
                'type': 'success',
                'message': _("Records for approval are successfully approved!"),
                'sticky': True,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }
            }
        }
    
    def action_reject(self):
        po = self.purchase_order_id
        rr = self.stock_picking_id
        rfp = self.payment_request_id

        # Purchase Order
        if po and self.module == 'po':
            po.rejected()
        
        # Request for Payment
        if rfp and self.module == 'rfp':
            rfp.action_reject_payment()

        # Receiving Receipt 
        if rr and self.module == 'rr':
            rr.unlink()

        # Internal Transfer
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Records Disapproved"),
                'type': 'success',
                'message': _("Records for approval have been disapproved."),
                'sticky': True,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }
            }
        }