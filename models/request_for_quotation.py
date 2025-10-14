# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from collections import defaultdict
from datetime import datetime
from dateutil.relativedelta import relativedelta
from pytz import timezone
import base64

from markupsafe import escape, Markup
from werkzeug.urls import url_encode

from odoo import api, Command, fields, models, _
from odoo.osv import expression
from odoo.tools import format_amount, format_date, formatLang, groupby
from odoo.tools.float_utils import float_is_zero
from odoo.exceptions import UserError, ValidationError
import logging
_logger = logging.getLogger(__name__)

class MLPurchaseOrder(models.Model):
    _name = 'ml.request.quotation'
    _inherit = ['portal.mixin', 'product.catalog.mixin', 'mail.thread', 'mail.activity.mixin']
    _description = 'Request for Quotation (RFQ)'
    
    name = fields.Char('Order Reference', required=True, index='trigram', copy=False, default='New')
    priority = fields.Selection(
        [('0', 'Normal'), ('1', 'Urgent')], 'Priority', default='0', index=True)
    date_order = fields.Datetime('Order Deadline', required=True, index=True, copy=False, default=fields.Datetime.now,
        help="Depicts the date within which the Quotation should be confirmed and converted into a purchase order.")
    date_approve = fields.Date('Confirmation Date', readonly=True, index=True, copy=False)
    date_planned = fields.Date(
        string='RFQ Deadline', required="True", index=True, copy=False, store=True, readonly=False,
        help="Delivery date promised by vendor. This date is used to determine expected arrival of products.")  
    partner_id = fields.Many2one('res.partner', string='Vendor', help="You can find a vendor by its Name, TIN, Email or Internal Reference.")
    currency_id = fields.Many2one('res.currency', 'Currency', required=True, default=lambda self: self.env.company.currency_id.id)
    fiscal_position_id = fields.Many2one('account.fiscal.position', string="Fiscal Position")
    dest_address_id = fields.Many2one('res.partner', check_company=True, string='Dropship Address',
        help="Put an address if you want to deliver directly from the vendor to the customer. "
             "Otherwise, keep empty to deliver to your own company.")
    picking_type_id = fields.Many2one('stock.picking.type', string="Picking Type")
    incoterm_id = fields.Many2one('account.incoterms', 'Incoterm', help="International Commercial Terms are a series of predefined commercial terms used in international transactions.")
    state = fields.Selection([
        ('draft', 'RFQ'),
        ('sent', 'RFQ Sent'),
        ('submitted_to_manager', 'Submitted to MMD Manager'),
        ('purchase', 'Purchase Order'),
    ], string='Status', readonly=True, index=True, copy=False, default='draft', tracking=True)
    order_line = fields.One2many('ml.request.quotation.line', 'order_id', string='Order Lines', copy=True, tracking=True)
    notes = fields.Html('Terms and Conditions')
    deliver_to = fields.Many2one('stock.warehouse', 'Deliver To')
    branch = fields.Many2one('res.company.branches')
    zone = fields.Selection([
        ('luzon', 'LUZON'),
        ('ncr', 'NCR'),
        ('visayas', 'VISAYAS'),
        ('mindanao', 'MINDANAO')
    ], string="Zone", related="branch.zone", store=True)
    terms = fields.Many2one('account.payment.term', required=True)
    tin = fields.Char('TIN', tracking=True)
    company_id = fields.Many2one('res.company', 'Company', required=True, domain="[]", default=lambda self: self.env.company)
    company_id_dupl = fields.Many2one('res.company', 'Company', required=True, domain="[]")
    country_code = fields.Char(related='company_id.account_fiscal_country_id.code', string="Country code")
    currency_rate = fields.Float("Currency Rate", compute='_compute_currency_rate', compute_sudo=True, store=True, readonly=True, help='Ratio between the purchase order currency and the company currency')
    vendor_ids = fields.Many2many(
        'res.partner',  # Target model
        required=True,
        string="Vendor(s)",
        store=True
    )
    attachment_id = fields.One2many('ml.attachment', 'attachment_id', string='Attachments', store=True)
    for_ho = fields.Boolean('For Head Office', default=False)
    isMail_template = fields.Boolean('IsMail Template', default=False)
    isZone = fields.Selection([
        ('vismin','VISMIN'),
        ('lncr','LNCR'),
        ('all','All')
    ], default='all')
    remarks = fields.Text(string="Description", tracking=True)

    @api.model
    def default_get(self, fields):
        values = super().default_get(fields)
        # Validate current user what zone he/she belongs
        user = self.env.user  # Current logged-in user
        group_luzon = self.env.ref('ml_development.group_lncr_mods')
        group_vismin = self.env.ref('ml_development.group_vismin_mods')

        if group_vismin in user.groups_id:
            values['isZone'] = 'vismin'
        elif group_luzon in user.groups_id:
            values['isZone'] = 'lncr'
        else:
            values['isZone'] = 'all'
        return values

    @api.onchange('company_id','branch_id','zone')
    def _onchange_company_id(self):
        for record in self:
            if record.company_id:
                # Find the warehouse assigned to this company
                if self.zone in ['ncr','luzon']:
                    warehouse = self.env['stock.warehouse'].search([
                        ('company_id', '=', record.company_id.id),
                        ('lncr', '=', True)
                    ], limit=1) 
                else:
                    warehouse = self.env['stock.warehouse'].search([
                        ('company_id', '=', record.company_id.id),
                        ('vismin', '=', True) 
                    ], limit=1)

                # Find the internal picking type assigned to this company
                picking_type = self.env['stock.picking.type'].search([
                    ('company_id', '=', record.company_id.id),
                    ('code', '=', 'incoming'),
                    ('warehouse_id', '=', record.deliver_to.id)
                    # Ensure it's an internal transfer type
                ], limit=1)
                
                # record.deliver_to = warehouse.id if warehouse else False
                record.picking_type_id = picking_type.id if picking_type else False

    def _email_notif_to(self, next_user):
        user_cont = []
        
        if next_user == 'purchaser':
            user_notif = self.env.ref('ml_development.group_purchase_purchaser')
        elif next_user == 'manager':
            user_notif = self.env.ref('ml_development.group_purchase_mmd_manager')
        elif next_user == 'vpo':
            user_notif = self.env.ref('ml_development.group_purchase_vpo')
        elif next_user == 'president':
            user_notif = self.env.ref('ml_development.group_purchase_president')
        elif next_user == 'cfo':
            user_notif = self.env.ref('ml_development.group_purchase_cfo')
        
        res_groups = self.env['res.groups'].browse(user_notif.ids)
        for users in res_groups.users:
            user_cont.append(users.partner_id.id)

        return user_cont

    @api.constrains('attachment_id')
    def _check_duplicate_lines_attachment(self):
        for record in self:
            seen_values = set()
            for attach in record.attachment_id:
                if attach.partner_id.id in seen_values:
                    raise ValidationError(_("❌ A supplier {} cannot be added more than once in Attachment Lines! Please remove duplicates.").format(attach.partner_id.name or ""))
                seen_values.add(attach.partner_id.id)
    
    @api.onchange('branch')
    def _onchange_branches(self):
        if self.branch:
            # Auto-fill corporation
            if self.branch:
                self.company_id_dupl = self.branch.company_id.id

            # Auto-fill corporate TIN
            if self.company_id_dupl:
                self.tin = self.company_id_dupl.vat 
            
            # Auto-fill head office field
            if self.branch.head_office == True:
                self.for_ho = True
            else:
                self.for_ho = False

            # Auto-fill deliver to field
            if self.isZone == 'lncr':
                self.deliver_to = self.env['stock.warehouse'].search(
                    [('company_id', '=', self.company_id.id), ('lncr', '=', True), ('vismin', '=', False)],
                    limit=1
                ).id
            elif self.isZone == 'vismin':
                self.deliver_to = self.env['stock.warehouse'].search(
                    [('company_id', '=', self.company_id.id), ('lncr', '=', False), ('vismin', '=', True)],
                    limit=1
                ).id

    def submitted_to_manager(self):
        # Validate product lines
        for order in self.order_line:
            if order.price_unit <= 0:
                raise UserError(_('Unit Price must be greater than zero for all products. Please correct the prices before proceeding.'))

        # Check if no attachments
        if not self.attachment_id:
            raise UserError(_('No attachments found. Please attach the necessary files before proceeding.'))

        # Record the attachments to logs
        for attach in self.attachment_id:
            self.message_post(
                body=(_("This file belongs to vendor {}").format(attach.partner_id.name or '')),
                message_type="email",
                subtype_xmlid="mail.mt_log",
                attachment_ids=attach.attachment_ids.ids  # Add the attachment(s)
            )
        
        # Retrieve Purchase-related groups for the current user
        purchase_groups = self.env['res.groups'].search([('category_id.name', '=', 'Purchase')])
        user_purchase_groups = self.env.user.groups_id & purchase_groups  # Intersection of user's groups and Purchase groups
        purchase_groups_str = ", ".join(user_purchase_groups.mapped('name'))
        
        # Create the message body with <br/> for line breaks
        message_body = "<br/>".join([
            "📧 The request has been submitted to the manager.",
            f"Submitted By: {purchase_groups_str}"
        ])

        # Post the message as HTML
        self.message_post(
            body=message_body,
            subject="Request for Quotation Update",
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            body_is_html=True,  # Set to True to interpret HTML
            partner_ids=self._email_notif_to('manager')
        )
        self.update({'state' : 'submitted_to_manager'})

        # Check if RFQ number is already exist in approvals
        checkApprovals = self.env['res.approvers'].search([('quotation_request_id','=', self.id)], limit=1)
        if not checkApprovals:
            total_amount = 0

            for line in self.order_line:
                line_amount = line.price_unit * line.product_qty if line.product_qty else line.amount
                total_amount += line_amount

            # Create data to approvals module
            self.env['res.approvers'].create({
                'quotation_request_id': self.id,
                'zone': self.zone,
                'isZone': self.isZone,
                'name': self.name,
                'branch': self.branch.id,
                'remarks': self.remarks if self.remarks else 'No remarks provided.',
                'module': 'rfq',
                'submitted_to': 'manager',
                'total_amount': total_amount
            })
    
    def _write_partner_values(self, vals):
        partner_values = {}
        if 'receipt_reminder_email' in vals:
            partner_values['receipt_reminder_email'] = vals.pop('receipt_reminder_email')
        if 'reminder_date_before_receipt' in vals:
            partner_values['reminder_date_before_receipt'] = vals.pop('reminder_date_before_receipt')
        return vals, partner_values
    
    @api.constrains('zone')
    def _validate_user_by_zone(self):
        # Validate current user what zone he/she belongs
        user = self.env.user  # Current logged-in user
        group_luzon = self.env.ref('ml_development.group_lncr_mods') 
        group_vismin = self.env.ref('ml_development.group_vismin_mods') 

        if group_luzon in user.groups_id and self.zone in ['visayas','mindanao']:
            raise ValidationError("You are not allowed to create request under Visayas or Mindanao zone.")
        if group_vismin in user.groups_id and self.zone in ['ncr','luzon']:
            raise ValidationError("You are not allowed to create request under NCR or Luzon zone.")

    def write(self, vals):
        vals, partner_vals = self._write_partner_values(vals)
        res = super().write(vals)
        if partner_vals:
            self.partner_id.sudo().write(partner_vals)  # Because the purchase user doesn't have write on `res.partner`
        return res
    
    @api.model_create_multi
    def create(self, vals_list):
        orders = self.browse()
        partner_vals_list = []

        for vals in vals_list:
            company_id = vals.get('company_id', self.default_get(['company_id']))
            # Ensures default picking type and currency are taken from the right company.
            self_comp = self.with_company(company_id)
            if vals.get('name', 'New') == 'New':
                seq_date = None
                if 'date_order' in vals:
                    seq_date = fields.Datetime.context_timestamp(self, fields.Datetime.to_datetime(vals['date_order']))

                # Set sequence number based by zone
                if vals['isZone'] == 'vismin':
                    code = 'ml.request.quotation.vismin'
                elif vals['isZone'] == 'lncr':
                    code = 'ml.request.quotation.lncr'

                vals['name'] = self_comp.env['ir.sequence'].next_by_code(code or False, sequence_date=seq_date) or 'RFQXXXXX'

            vals, partner_vals = self._write_partner_values(vals)
            partner_vals_list.append(partner_vals)
            orders |= super(MLPurchaseOrder, self_comp).create(vals)
        for order, partner_vals in zip(orders, partner_vals_list):
            if partner_vals:
                order.sudo().write(partner_vals)  # Because the purchase user doesn't have write on `res.partner`
        return orders

    @api.ondelete(at_uninstall=False)
    def _unlink_if_cancelled(self):
        for order in self:
            if not order.state == 'draft':
                raise UserError(_('You can only delete a request for quotation in draft/RFQ state.'))

    # ------------------------------------------------------------
    # ACTIONS
    # ------------------------------------------------------------
    def action_rfq_send(self):
        '''
        This function auto send an email
        '''
        # Check is product lines is empty
        if not self.order_line:
            raise UserError(_('No product lines found. Please add at least one product before proceeding.'))
        
        # Validate product lines
        for line in self.order_line:
            if line.price_unit <= 0:
                raise UserError(_('Unit Price must be greater than zero for all products. Please correct the prices before proceeding.'))

        for vendor in self.vendor_ids:
            # Set vendor_id to partner_id field
            self.partner_id = vendor.id
            
            # Send the email to the vendor
            if self.partner_id:
                self.ensure_one()
                template = self.env.ref('ml_development.email_template_request_for_quotation')
                template.send_mail(self.id, force_send=True)

        # If state is draft, set it to sent
        if self.state == 'draft':
            self.update({'state' : 'sent'})
        
    def button_draft(self):
        self.write({'state': 'draft'})
        return {}

    def button_confirm(self):
        for order in self:
            #Validation: Prevent confirmation if only one or zero line items (by jo)
            if len(order.order_line) == 0:
                raise UserError(_('At least one line item is required before confirming.'))

            product_items = []
            supplier_count = 0
            for ol in order.order_line:
                if not ol.partner_id.id:
                    raise UserError(_('Supplier is a required field. Please select or enter a valid supplier before proceeding.'))
                
                product_items.append({
                    'supplier': ol.partner_id.id,
                    'order_line': {
                        'product_id': ol.product_id.id,
                        'product_tmpl_id': ol.product_tmpl_id.id,
                        'item_code': ol.product_tmpl_id.item_code,
                        'product_uom': ol.product_uom.id,
                        'name': ol.name,
                        'product_qty': ol.product_qty,
                        'price_unit': ol.price_unit,
                        'tax_type': ol.partner_id.tax_type,
                        'amount': ol.amount,
                        'supplier': ol.partner_id.id
                    }
                })

            # Create the record - Group order lines by supplier
            grouped_by_supplier = defaultdict(list)
            for entry in product_items:
                supplier = entry['supplier']
                order_line = entry['order_line']
                grouped_by_supplier[supplier].append(order_line)

            # Iterate over each supplier and create purchase orders
            for supplier_id, order_lines in grouped_by_supplier.items():
                # Prepare the items for the order_line field
                items = []
                for line in order_lines:
                    product_id = line['product_id']
                    product_tmpl_id = line['product_tmpl_id']
                    item_code = line['item_code']
                    product_uom = line['product_uom']
                    name = line['name']
                    product_qty = line['product_qty']
                    price_unit = line['price_unit']
                    tax_type = line['tax_type']
                    amount = line['amount']
                    product_qty = line['product_qty']
                    vendor = line['supplier']

                    # Define tax in creating purchase order
                    if tax_type == 'vatable':
                        tax = self.env['account.tax'].search([('name', '=', '12%'), ('active', '=', True)], limit=1)
                    elif tax_type == 'zero':
                        tax = self.env['account.tax'].search([('name', '=', '0% ZR')], limit=1)
                    else:
                        tax = self.env['account.tax'].search([('name', '=', '0% EXEMPT')], limit=1)

                    items.append((0, 0, {
                        'rfq_id': order.id,
                        'item_code': item_code,
                        'product_uom': product_uom,
                        'partner_id': vendor,
                        'product_id': product_id,
                        'product_tmpl_id': product_tmpl_id,
                        'name': name,
                        'product_qty': product_qty,
                        'price_unit': price_unit,
                        'taxes_id': [(6, 0, [tax.id])] if tax else False,
                        'tax_duplicate': tax.id if tax else False,
                        'amount': amount * product_qty if product_qty else amount,
                    }))
                
                # Count supplier
                supplier_count += 1
                
                # Create the purchase order
                purchase_order = self.env['purchase.order']
                purchase = purchase_order.create({
                    'partner_id': supplier_id,  
                    'corporation': order.company_id_dupl.id,  
                    'branch': order.branch.id,  
                    'picking_type_id': order.deliver_to.in_type_id.id,  
                    'terms': order.terms.id,  
                    'tin' : order.tin,
                    'for_ho' : order.for_ho,
                    'deliver_to': order.deliver_to.id, 
                    'currency_id': order.currency_id.id,
                    'date_planned': False,
                    'date_approve': order.date_approve,
                    'order_line': items,
                    'origin': order.id,
                    'isOrigin': True,  # Indicate that this PO is created from an RFQ
                })

                # Post the message as HTML
                self.message_post(
                    body=_("<p>Purchase order <strong>{}</strong> has been successfully created for <strong>{}</strong> supplier.</p>").format(purchase.name, purchase.partner_id.name),
                    subject=_("Purchase Order Created"),
                    message_type='email',
                    subtype_xmlid='mail.mt_comment',
                    body_is_html=True  # Set to True to interpret HTML
                )

                # Add attachment to purchase order logs
                for attach in order.attachment_id:
                    if purchase.partner_id.id == attach.partner_id.id:
                        # Pass the attachment for specific vendor'
                        purchase.message_post(
                            body=f"This file belongs to vendor {attach.partner_id.name}.",
                            message_type="comment",
                            subtype_xmlid="mail.mt_log",
                            attachment_ids=attach.attachment_ids.ids  # Add the attachment(s) to logs
                        )
                
            order.state = 'purchase'
            order.date_approve = datetime.now()

            # Check if PO number is already exist in approvals
            checkApprovals = self.env['res.approvers'].search([('quotation_request_id','=', self.id)], limit=1)
            # Delete data to approvals module
            checkApprovals.unlink()

            # Show a popup notification
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Purchase Order Created"),
                    'type': 'success',
                    'message': _("Purchase order has been successfully created."),
                    'sticky': False,  # Set to True if you want it to remain until dismissed manually
                    'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                }
            }
            
    def button_cancel(self):
        # Post the message as HTML
        self.message_post(
            body=_("<p>Purchase order <strong>{}</strong> has been successfully cancelled!</p>"),
            subject=_("Purchase Order Created"),
            message_type='comment',
            subtype_xmlid='mail.mt_note',
            body_is_html=True  # Set to True to interpret HTML
        )

        self.write({'state': 'cancel'})

    
    @api.onchange('order_line')
    def _onchange_order_line(self):
        seen = {}
        duplicates = []

        if not self.order_line:
            return

        for line in self.order_line:
            product = line.product_tmpl_id
            if not product:
                continue

            key = product.id
            if key in seen:
                duplicates.append(line)
            else:
                seen[key] = line

        if duplicates:
            for dup_line in duplicates:
                self.order_line -= dup_line  # remove only duplicate line
            raise ValidationError(_("Duplicate product found in order lines. Duplicates have been removed. Please review the order."))
    
    @api.constrains('order_line')
    def _check_duplicate_products(self):
        for order in self:
            seen_products = set()
            for line in order.order_line:
                product = line.product_tmpl_id
                if not product:
                    continue
                if product.id in seen_products:
                    raise ValidationError(_(
                        "Duplicate product '%s' is not allowed in the order. "
                        "Please consolidate quantities or remove duplicate lines."
                    ) % product.display_name)
                seen_products.add(product.id)