from odoo import _,api, models, fields 
from odoo.tools import float_round
from odoo.exceptions import ValidationError,UserError
import logging
    
_logger = logging.getLogger(__name__)

class PurchaseOrderInherit(models.Model):
    _inherit = 'purchase.order'
    _description = 'ML Purchase Order'

    # Purchase Order Form Custom Fields
    deliver_to = fields.Many2one('stock.warehouse', 'Deliver To')
    for_ho = fields.Boolean('Head Office', default=False)
    branch = fields.Many2one('res.company.branches', string="Branch/Head Office")
    zone = fields.Selection([
        ('luzon', 'LUZON'),
        ('ncr', 'NCR'),
        ('visayas', 'VISAYAS'),
        ('mindanao', 'MINDANAO')
    ], string="Zone", related="branch.zone", store=True)
    origin = fields.Many2one('ml.request.quotation', string='Source Document', help="Reference of the document that generated this purchase order request (e.g. a sales order)")
    terms = fields.Many2one('account.payment.term')
    ordered_by = fields.Many2one('res.users', string='Ordered By')
    audited_by = fields.Many2one('res.users', string='Audited By')
    recommending_approval = fields.Many2one('res.users', string='Recommending Approval')
    approved_by_chairman = fields.Many2one('res.users', string='Approved By (Chairman of the Board)')
    approved_by_president = fields.Many2one('res.users', string='Approved By (President)')                                                                                                                                                                                                                                                                                                                                                                                                                 
    amount_total = fields.Float(string="Total Amount", compute="_compute_amount_total", store=True)
    received_amount = fields.Float(string="Received Amount", store=True) 
    company_id = fields.Many2one('res.company', string='Corporation', default=lambda self: self.env.company)
    corporation = fields.Many2one('res.company', string='Corporation', default=lambda self: self.env.company)
    corporation_id = fields.Char('Corp. ID')
    for_change = fields.Char('For Change')
    tin = fields.Char('TIN', store=True, related="corporation.partner_id.vat", readonly=False)
    tin_related = fields.Char('TIN', related="tin")
    partner_ids = fields.One2many('res.partner', 'purchase_order_id', string="Vendors")
    vendor_ids = fields.Many2many(  
        'res.partner',  # Target model
        compute='_show_vendor_as_tags',
        string="Vendor(s)"
    )
    record_count = fields.Integer(string='Record Count')
    trigger_field = fields.Boolean(string="Trigger Field") # Dummy field
    expected_arrival = fields.Date(string="Expected Arrival")
    date_planned = fields.Date(
        string='Expected Arrival', index=True, copy=False, store=True, readonly=False,
        help="Delivery date promised by vendor. This date is used to determine expected arrival of products.")  
    total_qty = fields.Integer(compute="_auto_compute_total_qty")
    total_amount = fields.Integer(compute="_auto_compute_total_qty")
    isZone = fields.Selection([
        ('vismin','VISMIN'),
        ('lncr','LNCR'),
        ('all','All')
    ], default='all')
    picking_type_id = fields.Many2one('stock.picking.type', 'Operation', required=True, domain="[('warehouse_id', '=', False))]",
        help="This will determine operation type of incoming shipment")
    state = fields.Selection(selection_add=[
        ('draft', 'Purchase Order'),
        ('submitted_to_manager', 'Submitted to Manager'),
        ('submitted_to_vpo','Submitted to VPO '),
        ('submitted_to_president','Submitted to President'),
        ('request_for_change', 'Request For Change'),
        ('purchase', 'Approved Order'),
        ('po_sent', 'Submitted to Supplier'),
        ('rejected', 'Disapproved'),
        ('fully_received', 'Fully Received'),
        ('partially_received', 'Partially Received'),
        ('cancel', 'Cancelled'),
        ('to_cancel', 'To Be Cancelled'),
    ], readonly=True, index=True, copy=False, default='draft', tracking=True)
    remarks = fields.Text('Remarks', tracking=True)
    description = fields.Text('Description', tracking=True)
    vatable = fields.Boolean('isVatable')
    amount_untaxed = fields.Monetary(string='Untaxed Amount', store=True, readonly=True, compute='_amount_all')
    amount_tax = fields.Monetary(string='Taxes', store=True, readonly=True, compute='_amount_all')
    amount_total = fields.Monetary(string='Total', store=True, readonly=True, compute='_amount_all')
    isOrigin = fields.Boolean('isOrigin', compute="_auto_check_if_origin_is_set", store=True)
    partner_ref = fields.Char('Vendor Reference', store=True, tracking=True, help="Reference of the vendor for this purchase order")
    isAdmin = fields.Boolean(store=True, default=False)

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
            values['isAdmin'] = True  # If user is not in any zone, set isAdmin to True
        return values

    @api.depends('order_line.product_qty', 'order_line.price_unit', 'order_line.taxes_id')
    def _amount_all(self):
        for order in self:
            amount_untaxed = 0.0
            amount_tax = 0.0
            total = 0.0

            for line in order.order_line:
                sub_total = line.price_unit * line.product_qty
                tax = line.tax_duplicate
                tax_amount = (tax.amount / 100.0) + 1
                tax_per_unit = float_round(line.price_unit * tax_amount, precision_digits=2)
                total_tax = tax_per_unit * line.product_qty
                
                amount_untaxed += float_round(sub_total, precision_digits=2)
                amount_tax += float_round(sub_total * (tax.amount / 100.0), precision_digits=2)
                total += float_round(total_tax, precision_digits=2)

            order.update({
                'amount_untaxed': amount_untaxed,
                'amount_tax': amount_tax,
                'amount_total': total
            })
    
    def _send_email_to(self, user, zone):
        list = []
        # Define user role
        if user == 'purchaser':
            user_ref = self.env.ref('ml_development.group_purchase_purchaser') 
        elif user == 'manager':
            user_ref = self.env.ref('ml_development.group_purchase_mmd_manager') 
        elif user == 'vpo':
            user_ref = self.env.ref('ml_development.group_purchase_vpo')
        elif user == 'supervisor':
            user_ref = self.env.ref('ml_development.group_purchase_mmd_supervisor') 
        elif user == 'president':
            user_ref = self.env.ref('ml_development.group_purchase_president') 
        elif user == 'cfo':
            user_ref = self.env.ref('ml_development.group_purchase_cfo')

        # Browse group_id to get the user value
        user_grp = self.env['res.groups'].browse(user_ref.id)
        
        # Extract users
        for users in user_grp.users:
            # Define zones
            group_luzon = self.env.ref('ml_development.group_lncr_mods')
            group_vismin = self.env.ref('ml_development.group_vismin_mods')
            if zone: # If zone not False
                if zone in ['ncr','luzon'] and group_luzon in users.groups_id:
                    # Store partner ID
                    list.append(users.partner_id.id)
                elif zone in ['visayas','mindanao'] and group_vismin in users.groups_id:
                    # Store partner ID
                    list.append(users.partner_id.id)
            else:
                list.append(users.partner_id.id)
        # Return partner_ids
        return list

    @api.depends('origin')
    def _auto_check_if_origin_is_set(self):
        for rec in self:
            if rec.origin:
                # If origin is set, then set isOrigin to True
                rec.isOrigin = True
            else:
                # If origin is not set, then set isOrigin to False
                rec.isOrigin = False

    @api.depends('order_line')
    def _auto_compute_total_qty(self):
        for rec in self:
            rec.total_qty = sum(rec.order_line.mapped('product_qty'))
    
    @api.depends('order_line')
    def _auto_compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(rec.order_line.mapped('price_unit'))
    
    @api.model
    def _default_picking_type(self):
        return self._get_picking_type(self.env.context.get('corporate') or self.env.company.id)

    @api.depends('partner_ids')
    def _show_vendor_as_tags(self):
        for record in self:
            record.vendor_ids = record.partner_ids                                                                                                                                                                                                                                                                                                                                                                                                                 

    @api.depends('order_line.price_subtotal')
    def _compute_amount_total(self):
        for order in self:
            order.amount_total = sum(line.price_subtotal for line in order.order_line)

    def action_create_custom_bill(self):
        for po in self:
            bill = self.env['account.move'].create({
                'move_type': 'in_invoice',
                'partner_id': po.partner_id.id,
                'invoice_origin': po.name,
                'ref' : po.name,
                'invoice_date': fields.Date.today(),
                'invoice_line_ids': [
                    (0, 0, {
                        'product_id': line.product_id.id,
                        'quantity': line.product_qty,
                        'price_unit': line.price_unit,
                        'account_id': line.product_id.property_account_expense_id.id,
                        'name': line.name,
                        
                        'tax_ids': [(6, 0, line.taxes_id.ids)],
                    }) for line in po.order_line
                ]
            })
            bill.action_post()
    
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

    @api.model
    def create(self, vals):
        # Check if name/sequence and zone have value
        if 'branch' in vals:
            getZone = self.env['res.company.branches'].browse(vals['branch'])
            # Determine if it's from LNCR or VISMIN
            if getZone.zone in ['ncr','luzon']: # LNCR
                # Modify the sequence name before creation
                vals['name'] = self.env['ir.sequence'].next_by_code('purchase.order.lncr') or 'LN/PXXXXX' 
            elif getZone.zone in ['visayas','mindanao']: # VISMIN
                # Modify the sequence name before creation
                vals['name'] = self.env['ir.sequence'].next_by_code('purchase.order.vismin') or 'VM/PXXXXX' 
        
        # Call the super method to retain default behavior
        return super(PurchaseOrderInherit, self).create(vals)

    @api.onchange('company_id','branch_id','zone','deliver_to')
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
                
                # Assign values
                record.deliver_to = warehouse.id if warehouse else False
                record.picking_type_id = picking_type.id if picking_type else False

    def submitted_to_manager(self):
        # Validate Unit price
        if not self.order_line:
            raise UserError(_("The product lines must have at least one order line."))
            
        for lines in self.order_line:
            if lines.price_unit <= 0:
                raise UserError(_("The unit price must be greater than zero."))

        self.update({'state' : 'submitted_to_manager'})
        
        # Retrieve Purchase-related groups for the current user
        purchase_groups = self.env['res.groups'].search([('category_id.name', '=', 'Purchase')])
        user_purchase_groups = self.env.user.groups_id & purchase_groups  # Intersection of user's groups and Purchase groups
        purchase_groups_str = ", ".join(user_purchase_groups.mapped('name'))

        # Create the message body with <br/> for line breaks
        message_body = "<br/>".join([
            "📧 The purchase order has been submitted to the manager.",
            f"Remarks: {self.remarks}" if self.remarks else "No remarks provided.",
            f"Submitted By: {purchase_groups_str}"
        ])

        # Post the message as HTML
        self.message_post(
            body=message_body,
            subject="Purchase Order Update",
            message_type='email',
            subtype_xmlid='mail.mt_comment',
            body_is_html=True,  # Set to True to interpret HTML
            partner_ids=self._send_email_to('manager', False)
        )

        self.update({'remarks' : False})

        # Check if PO number is already exist in approvals
        checkApprovals = self.env['res.approvers'].search([('purchase_order_id','=', self.id)], limit=1)
        if not checkApprovals:
            # Create data to approvals module
            self.env['res.approvers'].create({
                'purchase_order_id': self.id,
                'zone': self.zone,
                'isZone': self.isZone,
                'name': self.name,
                'module': 'po',
                'branch': self.branch.id,
                'remarks': self.description,
                'total_amount': self.amount_total,
                'submitted_to': 'manager'
            })
        else: 
            # Update data to approvals module
            checkApprovals.update({
                'submitted_to': 'manager'
            })

    def submitted_to_manager_request(self):
        self.update({'state' : 'submitted_to_manager', 'for_change' : False})
        
        purchase_groups = self.env['res.groups'].search([('category_id.name', '=', 'Purchase')])
        user_purchase_groups = self.env.user.groups_id & purchase_groups  # Intersection of user's groups and Purchase groups
        purchase_groups_str = ", ".join(user_purchase_groups.mapped('name'))

        message_body = "<br/>".join([
            "📧 The purchase order is submitted to the manager after request for change.",
            f"Remarks: {self.remarks}" if self.remarks else "No remarks provided.",
            f"Submitted By: {purchase_groups_str}"
        ])

        # Post the message as HTML
        self.message_post(
            body=message_body,
            subject="Purchase Order Update",
            message_type='email',
            subtype_xmlid='mail.mt_comment',
            body_is_html=True,  # Set to True to interpret HTML
            partner_ids=self._send_email_to('manager', False)
        )
        self.update({'remarks' : False})

        # Check if PO number is already exist in approvals
        checkApprovals = self.env['res.approvers'].search([('purchase_order_id','=', self.id)], limit=1)
        if not checkApprovals:
            # Create data to approvals module
            self.env['res.approvers'].create({
                'purchase_order_id': self.id,
                'zone': self.zone,
                'isZone': self.isZone,
                'name': self.name,
                'module': 'po',
                'branch': self.branch.id,
                'remarks': self.description,
                'total_amount': self.amount_total,
                'submitted_to': 'manager'
            })
        else: 
            # Update data to approvals module
            checkApprovals.update({
                'zone': self.zone,
                'isZone': self.isZone,
                'name': self.name,
                'module': 'po',
                'branch': self.branch.id,
                'remarks': self.description,
                'total_amount': self.amount_total,
                'submitted_to': 'manager'
            })

    def submitted_to_vpo(self):
        self.update({'state' : 'submitted_to_vpo'})

        # Retrieve Purchase-related groups for the current user
        purchase_groups = self.env['res.groups'].search([('category_id.name', '=', 'Purchase')])
        user_purchase_groups = self.env.user.groups_id & purchase_groups  # Intersection of user's groups and Purchase groups
        purchase_groups_str = ", ".join(user_purchase_groups.mapped('name'))

        message_body = "<br/>".join([
            "The purchase order has been submitted to VPO.",
            f"Remarks: {self.remarks}" if self.remarks else "No remarks provided.",
            f"Submitted By: {purchase_groups_str}"
        ])

       # Post the message as HTML
        self.message_post(
            body=message_body,
            subject="Purchase Order Update",
            message_type='email',
            subtype_xmlid='mail.mt_comment',
            body_is_html=True,  # Set to True to interpret HTML
            partner_ids=self._send_email_to('vpo', self.zone)
        )

        self.update({'remarks' : False})
        # Check if PO number is already exist in approvals
        checkApprovals = self.env['res.approvers'].search([('purchase_order_id','=', self.id)], limit=1)
        print("Submitted to MANAGER", checkApprovals.submitted_to)
        if not checkApprovals:
            # Create data to approvals module
            self.env['res.approvers'].create({
                'purchase_order_id': self.id,
                'zone': self.zone,
                'isZone': self.isZone,
                'name': self.name,
                'branch': self.branch.id,
                'remarks': self.description,
                'total_amount': self.total_amount,
                'module': 'po',
                'submitted_to': 'vpo'
            })
        else: 
            # Update data to approvals module
            checkApprovals.update({
                'submitted_to': 'vpo'
            })
        
        print("Submitted to VPO", checkApprovals.submitted_to)

    def submitted_to_president_cfo(self):
        self.update({'state' : 'submitted_to_president'})
        
        # Retrieve Purchase-related groups for the current user
        purchase_groups = self.env['res.groups'].search([('category_id.name', '=', 'Purchase')])
        user_purchase_groups = self.env.user.groups_id & purchase_groups  # Intersection of user's groups and Purchase groups
        purchase_groups_str = ", ".join(user_purchase_groups.mapped('name'))

        # Post the message
        message_body = "<br/>".join([
            "The purchase order has been submitted to President/CFO.",
            f"Remarks: {self.remarks}" if self.remarks else "No remarks provided.",
            f"Submitted By: {purchase_groups_str}",
        ])

        main_rec = self._send_email_to('president', False)
        cc_email = self._send_email_to('cfo', False)
        # Send email for both President and CFO Role
        self.message_post(
            body=message_body,
            subject="Purchase Order Update",
            message_type='email',
            subtype_xmlid='mail.mt_comment',
            body_is_html=True,  # Set to True to interpret HTML
            partner_ids=main_rec + cc_email
        )

        self.update({'remarks' : False})

        # Check if PO number is already exist in approvals
        checkApprovals = self.env['res.approvers'].search([('purchase_order_id','=', self.id)], limit=1)
        if not checkApprovals:
            # Create data to approvals module
            self.env['res.approvers'].create({
                'purchase_order_id': self.id,
                'zone': self.zone,
                'isZone': self.isZone,
                'name': self.name,
                'branch': self.branch.id,
                'remarks': self.description,
                'total_amount': self.total_amount,
                'module': 'po',
                'submitted_to': 'pres_cfo'
            })
        else: 
            # Update data to approvals module
            checkApprovals.update({
                'submitted_to': 'pres_cfo'
            })

    def set_to_draft(self):
        self.update({'state' : 'draft'})

        purchase_groups = self.env['res.groups'].search([('category_id.name', '=', 'Purchase')])
        user_purchase_groups = self.env.user.groups_id & purchase_groups  # Intersection of user's groups and Purchase groups
        purchase_groups_str = ", ".join(user_purchase_groups.mapped('name'))

        # Post the message
        message_body = "<br/>".join([
            "The purchase order has been set to draft.",
            f"Remarks: {self.remarks}" if self.remarks else "No remarks provided.",
            f"Submitted By: {purchase_groups_str}"
        ])

        # Post the message as HTML
        self.message_post(
            body=message_body,
            subject="Purchase Order Update",
            message_type='email',
            subtype_xmlid='mail.mt_comment',
            body_is_html=True,  # Set to True to interpret HTML
            partner_ids=self._send_email_to('purchaser', self.zone)
        )
        self.update({'remarks' : False})

    def request_for_change(self):
        if self.remarks:
            self.update({'state': 'request_for_change' , 'for_change' : 'state'})
            self.message_post(
                body=f"The purchase order is returned to the MMD Supervisor with a Request for Change. Remarks: {self.remarks}",
                subject="Purchase Order Update",
                message_type='notification'
            )
        else:
            raise UserError("Change Request Error: Please provide remarks before requesting for a change.")
        
        purchase_groups = self.env['res.groups'].search([('category_id.name', '=', 'Purchase')])
        user_purchase_groups = self.env.user.groups_id & purchase_groups  # Intersection of user's groups and Purchase groups
        purchase_groups_str = ", ".join(user_purchase_groups.mapped('name'))
            
        # Post the message
        message_body = "<br/>".join([
            "The purchase order has been submitted for request for change.",
            f"Remarks: {self.remarks}" if self.remarks else "No remarks provided.",
            f"Submitted By: {purchase_groups_str}"
        ])
        # Post the message as HTML
        self.message_post(
            body=message_body,
            subject="Purchase Order Update",
            message_type='email',
            subtype_xmlid='mail.mt_comment',
            body_is_html=True,  # Set to True to interpret HTML
            partner_ids=self._send_email_to('supervisor', self.zone)
        )

        self.update({'remarks' : False})

        # Check if PO number is already exist in approvals
        checkApprovals = self.env['res.approvers'].search([('purchase_order_id','=', self.id)], limit=1)
        if not checkApprovals:
            # Create data to approvals module
            self.env['res.approvers'].create({
                'purchase_order_id': self.id,
                'zone': self.zone,
                'isZone': self.isZone,
                'name': self.name,
                'branch': self.branch.id,
                'remarks': self.description,
                'total_amount': self.total_amount,
                'module': 'po',
                'submitted_to': 'supervisor'
            })
        else: 
            # Update data to approvals module
            checkApprovals.update({
                'submitted_to': 'supervisor'
            })

    def approve(self):
        # Now this button will be based on  if its for head office or for branch and depending on who is the user on this
        # Call the button_confirm method to retain its functionality
        self.update({'state' : 'purchase'})

        purchase_groups = self.env['res.groups'].search([('category_id.name', '=', 'Purchase')])
        user_purchase_groups = self.env.user.groups_id & purchase_groups  # Intersection of user's groups and Purchase groups
        purchase_groups_str = ", ".join(user_purchase_groups.mapped('name'))

        # Post the message
        message_body = "<br/>".join([
            "The purchase order has been approved.",
            f"Remarks: {self.remarks}" if self.remarks else "No remarks provided.",
            f"Submitted By: {purchase_groups_str}"
        ])
        
       # Post the message as HTML
        self.message_post(
            body=message_body,
            subject="Purchase Order Update",
            message_type='email',
            subtype_xmlid='mail.mt_comment',
            body_is_html=True,  # Set to True to interpret HTML
            partner_ids=self._send_email_to('purchaser', self.zone)
        )
        
        self.update({'remarks' : False})
        self.button_confirm()

        # Check if PO number is already exist in approvals
        checkApprovals = self.env['res.approvers'].search([('purchase_order_id','=', self.id)], limit=1)
        # Delete data to approvals module
        checkApprovals.unlink()

    def rejected(self):
        self.update({'state' : 'rejected'})
        # Retrieve Purchase-related groups for the current user
        purchase_groups = self.env['res.groups'].search([('category_id.name', '=', 'Purchase')])
        user_purchase_groups = self.env.user.groups_id & purchase_groups  # Intersection of user's groups and Purchase groups
        purchase_groups_str = ", ".join(user_purchase_groups.mapped('name'))

        # Post the message
        message_body = "<br/>".join([
            "The purchase order has been disapproved.",
            f"Remarks: {self.remarks}" if self.remarks else "No remarks provided.",
            f"Disapproved By: {purchase_groups_str}"
        ])

        # Post the message as HTML
        self.message_post(
            body=message_body,
            subject="Purchase Order Update",
            message_type='email',
            subtype_xmlid='mail.mt_comment',
            body_is_html=True  # Set to True to interpret HTML
        )
        self.update({'remarks' : False})

        # Check if PO number is already exist in approvals
        checkApprovals = self.env['res.approvers'].search([('purchase_order_id','=', self.id)], limit=1)
        # Delete data to approvals module
        checkApprovals.unlink()

    @api.onchange('partner_id')
    def _onchange_vendors_tin(self):
        if self.partner_id:
            if self.partner_id.tax_type == 'vatable':
                self.vatable = True
            else:
                self.vatable = False

    @api.onchange('company_id')
    def _onchange_corporation(self):
        self.branch = False
        if self.company_id:
            branches = self.env['res.company'].search([('id', '=', self.company_id.id)])
            branches_comp = self.env['res.company.branches'].search([('company_id', '=', self.company_id.id)])
            if branches:
                return {'domain': {'branch': [('company_id', '=', self.company_id.id)]}}
    
    @api.onchange('company_id')
    def _onchange_corporation(self):
        self.branch = False
        if self.company_id:
            branches = self.env['res.company'].search([('id', '=', self.company_id.id)])
            branches_comp = self.env['res.company.branches'].search([('company_id', '=', self.company_id.id)])
            if branches:
                # self.update({ 'tin' : branches.vat, 'corporation_id' : self.corporation.id })
                return {'domain': {'branch': [('company_id', '=', self.company_id.id)]}}

    def send_po_by_email(self):
        self.ensure_one()
        ir_model_data = self.env['ir.model.data']
        try:
            template_id = ir_model_data._xmlid_lookup('purchase.email_template_edi_purchase_done')[1]
        except ValueError:
            template_id = False
        try:
            compose_form_id = ir_model_data._xmlid_lookup('mail.email_compose_message_wizard_form')[1]
        except ValueError:
            compose_form_id = False
        ctx = dict(self.env.context or {})
        ctx.update({
            'default_model': 'purchase.order',
            'default_res_ids': self.ids,
            'default_template_id': template_id,
            'default_composition_mode': 'comment',
            'default_email_layout_xmlid': "mail.mail_notification_layout_with_responsible_signature",
            'model_description': _('Purchase Order'),
            'force_email': True,
            'mark_rfq_as_sent': True,
            'tracking_po_id': self.id,  # Pass purchase ID for tracking
        })

        # In the case of a RFQ or a PO, we want the "View..." button in line with the state of the
        # object. Therefore, we pass the model description in the context, in the language in which
        # the template is rendered.
        lang = self.env.context.get('lang')
        if {'default_template_id', 'default_model', 'default_res_id'} <= ctx.keys():
            template = self.env['mail.template'].browse(ctx['default_template_id'])
            if template and template.lang:
                lang = template._render_lang([ctx['default_res_id']])[ctx['default_res_id']]
        self = self.with_context(lang=lang)

        return {
            'name': _('Send PO by Email'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form_id, 'form')],
            'view_id': compose_form_id,
            'target': 'new',
            'context': ctx,
        }
    
    def action_generate_custom_report(self):
        """Generate a custom Purchase Order report."""
        report = self.env.ref('ml_development.report_purchase_order')  # Make sure this ID exists
        if not report:
            raise ValueError("Report action not found. Check your XML definition.")
        return report.report_action(self)
        

    @api.ondelete(at_uninstall=False)
    def _unlink_if_cancelled(self):
        for order in self:
            if order.state not in ['cancel']:
                raise UserError(_('In order to delete a purchase order, you must cancel it first.'))

    def button_cancel(self):
        # check in stock.moves if there is a record in stock.moves that has a po_number 
        purchase_exist = self.env['stock.picking'].search([('origin', '=', self.name)])
        if purchase_exist:
            for item in purchase_exist:
                if item.state == 'confirmed':
                    raise UserError(_('Cannot cancel the purchase order anymore as there are items that are partially delivered. Cancel the receiving form instead.'))
                else:
                    purchase_orders_with_invoices = self.filtered(lambda po: any(i.state not in ('cancel', 'draft') for i in po.invoice_ids))
                    
                    # Cancel the PO 
                    self.write({'state': 'cancel', 'mail_reminder_confirmed': False})
                    # Cancel the receiving receipt form  related to this Purchase Order
                    purchase_exist.write({
                        'state': 'cancel',
                        'remarks': f'The Purchase Order ({self.name}) related to this receiving receipt form is approved to be cancelled by {self.env.user.name}.'
                    })

        # Retrieve Purchase-related groups for the current user
        purchase_groups = self.env['res.groups'].search([('category_id.name', '=', 'Purchase')])
        user_purchase_groups = self.env.user.groups_id & purchase_groups  # Intersection of user's groups and Purchase groups
        purchase_groups_str = ", ".join(user_purchase_groups.mapped('name'))

        # Post the message
        message_body = "<br/>".join([
            "The purchase order has been cancelled.",
            f"Remarks: {self.remarks if self.remarks else ""}",
            f"Submitted By: {purchase_groups_str}"
        ])

        # Post the message as HTML
        self.message_post(
            body=message_body,
            subject="Purchase Order Update",
            message_type='email',
            subtype_xmlid='mail.mt_comment',
            body_is_html=True,  # Set to True to interpret HTML
            partner_ids=self._send_email_to('purchaser', self.zone)
        )
        
    def request_for_cancel(self):
        """Send email and process it immediately in backend."""
        for rec in self:
            if not rec.remarks:
                raise UserError("Please provide remarks before requesting to cancel purchase order.")

            receiver_email = rec.user_id.email  # Change to appropriate recipient
            if not receiver_email:
                raise UserError("The recipient has no email address set.")

            purchase_exists = self.env['stock.picking'].search([('origin', '=', rec.name)])
            # Check if any stock.picking record is in 'partially_delivered' state
            if self.remarks == 'Partially Received':
                raise UserError(_('Cannot cancel the purchase order anymore as there are items that are partially delivered. Cancel the receiving form instead.'))
            if any(pick.state == 'partially_delivered' for pick in purchase_exists):
                raise UserError(_('Cannot cancel the purchase order anymore as there are items that are partially delivered. Cancel the receiving form instead.'))

            # Get email template
            template = self.env.ref('ml_development.email_template_purchase_cancel', raise_if_not_found=False)
            if not template:
                raise UserError("Email template not found! Check XML ID.")
            
            # Send email
            mail_id = template.send_mail(rec.id, force_send=True)

            # Format the message to post in the chatter
            find_user = self.env['res.partner'].browse(self._send_email_to('manager', False))
            chatter_message = f"""
            📧 Email sent to: <strong>{find_user.email}</strong><br/>
            <p>A request to cancel the following Purchase Order has been made:<br/>
            <strong>Reference:</strong> {rec.name}<br/>
            <strong>Vendor:</strong> {rec.partner_id.name}<br/>
            <strong>Remarks: </strong> {rec.remarks}</p>
            """
            # Post the formatted message to the chatter
            rec.message_post(
                body=chatter_message,
                message_type='email',
                subtype_xmlid='mail.mt_comment',
                body_is_html=True,
                partner_ids=self._send_email_to('manager', False)
            )
            rec.update({'state' : 'to_cancel'})
        self.update({'remarks' : False})
        return True

    
    def button_confirm(self):
        """ Override Confirm Button to Auto-Create Receiving Receipt with Zero Initial Quantity """
        res = super(PurchaseOrderInherit, self).button_confirm()

        for order in self:
            # DELETE AUTO-CREATED PICKINGS (If Any)
            auto_pickings = self.env['stock.picking'].search([
                ('origin', '=', order.name),
                ('state', '!=', 'done')
            ])
            if auto_pickings:
                auto_pickings.with_context(force_unlink=True).unlink()
                order.invalidate_cache()  #  Refresh order to avoid stale data

            #  Determine picking type based on zone
            picking_type = None
            isZone_char = ""

            if self.zone in ['luzon', 'ncr']:
                # need to add name here for specific warehouse operation only to allow cross company operation 
                picking_type = self.env['stock.picking.type'].sudo().search([
                    ('code', '=', 'incoming'),
                    ('company_id', '=', order.company_id.id),
                    ('warehouse_id.lncr', '=', True)
                ], limit=1)
                isZone_char = 'lncr'

            elif self.zone in ['visayas', 'mindanao']:
                # need to add name here for specific warehouse operation only to allow cross company operation 
                picking_type = self.env['stock.picking.type'].sudo().search([
                    ('code', '=', 'incoming'),
                    ('company_id', '=', order.company_id.id), 
                    ('warehouse_id.vismin', '=', True)
                ], limit=1)
                isZone_char = 'vismin'

            if not picking_type:
                raise UserError(_("No Incoming Picking Type found."))

            #  Create Stock Picking (Receiving Receipt)
            address_parts = filter(None, [order.partner_id.street, order.partner_id.street2, order.partner_id.city])
            address = " ".join(address_parts)

            if self.partner_id.tax_type == 'vatable':
                # Calculate total_amount with 12% VAT
                total_amount = order.amount_total 
            else:
                # Use the normal total_amount
                total_amount = order.amount_total

            picking = self.env['stock.picking'].sudo().create({
                'partner_id': order.partner_id.id,
                'address': address,
                'picking_type_id': picking_type.id,
                'location_id': picking_type.default_location_src_id.id,
                'location_dest_id': picking_type.default_location_dest_id.id,
                'origin': order.name,
                'company_id': self.company_id.id,
                'company_id_report': self.corporation.id,
                'total_amount': total_amount,
                'branch': order.branch.id,
                'zone': order.zone,
                'received_by': False,
                'isZone': isZone_char,
                'currency_id': order.currency_id.id,
                'state' : 'assigned'
            })
            
            stock_moves = []

            for line in order.order_line:                
                tax_type_xmlid = 'vat_0'
                tax_amount = 0.0

                # Compute unit cost and untaxed base amount
                unit_price = line.price_unit  # or line.product_id.purchase_price if custom
                untaxed_amount = unit_price * line.product_qty

                for tax in line.tax_duplicate:
                    if tax.name == '12%':
                        tax_type_xmlid = 'vat_12'
                        tax_amount = untaxed_amount * 0.12  # compute tax only if 12%
                        break

                total_amount = untaxed_amount + tax_amount

                move = self.env['stock.move'].create({
                    'picking_id': picking.id,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.product_qty,
                    'quantity': 0.00,
                    'product_uom': line.product_uom.id,
                    'location_id': picking_type.default_location_src_id.id,
                    'location_dest_id': picking_type.default_location_dest_id.id,
                    'name': line.name,
                    'unit_cost': unit_price,
                    'total_amount': line.price_total,
                    'taxed_amount': line.price_total - line.amount,
                    'untaxed_amount': line.amount,
                    'company_id': self.company_id.id,
                    'tax_id': tax_type_xmlid,
                    'has_origin': True
                })
                stock_moves.append(move.id)
                
            #  Set Stock Picking to Ready
            picking.action_assign()
            self.env['stock.move'].browse(stock_moves).write({'state': 'assigned'})

            #  Add Log to Chatter
            picking.with_context(
                mail_notify_force_send=False,
                mail_auto_subscribe_no_notify=True
            ).message_post(
                body=(
                    f"<p>The system has created a <strong>Receiving Receipt</strong> for "
                    f"the <strong>Purchase Order: {picking.origin}</strong>.</p>"
                    f"<p><strong>Vendor:</strong> {picking.partner_id.name}</p>"
                    f"<p><strong>Total Amount:</strong> <span style='color: green;'>₱{order.amount_total:,.2f}</span></p>"
                ),
                message_type='comment',
                subtype_xmlid='mail.mt_note',
                body_is_html=True
            )

        return res
            
    @api.onchange('partner_id')
    def onchange_vatable(self):
        if self.partner_id:
            if self.partner_id.tax_type == 'vatable':
                self.vatable = True
            else:
                self.vatable = False
    
    @api.onchange('order_line')
    def _onchange_order_line(self):
        if not self.order_line:
            return

        seen = {}
        duplicates = []

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


    @api.onchange('branch')
    def _onchange_branches(self):
        if self.branch:
            if self.branch.head_office:
                self.for_ho = True
            else:
                self.for_ho = False

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