from odoo import api, models, fields, _
from odoo.exceptions import ValidationError,UserError
from datetime import datetime, timedelta
from markupsafe import Markup  # Import Markup for safe HTML formatting
import logging
from odoo.modules.module import get_module_resource
import base64
import uuid
from odoo.tools import config
from urllib.parse import urlencode
import secrets

_logger = logging.getLogger(__name__)

class Issuance(models.Model):
    _name = 'issuance.form'
    _description = 'Issuance Form'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Reference", required=True, copy=False, readonly=True, default='New')
    company_id = fields.Many2one('res.company', string='Corporation', default=lambda self: self.env['res.company']._company_default_get('account.invoice'))
    company_id_related = fields.Many2one('res.company', string='Corporation', related="company_id")
    company_id_report = fields.Many2one('res.company', string='Corporation')
    location_id = fields.Many2one('stock.location', string='Warehouse', domain="[('usage', '=', 'internal')]", required=True)
    location_id_related = fields.Many2one('stock.location', string='Warehouse', domain="[('usage', '=', 'internal')]", required=True, related="location_id")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('received', 'Received'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')
    ], string='Status', readonly=True, index=True, copy=False, default='draft', tracking=True)
    online_request_number = fields.Char('Online Request Number', tracking=True)
    branch = fields.Many2one('ml.branches')
    assigned_to = fields.Many2one('res.company.branches', string="Assigned To", create="False")
    assigned_to_vismin = fields.Many2one('res.company.branches', string="Assigned To", create="False")
    assigned_to_all = fields.Many2one('res.company.branches', string="Assigned To", create="False")
    assigned_to_selected = fields.Many2one('res.company.branches', string="Assigned To", create="False")
    prepared_by = fields.Many2one('res.users', default=lambda self: self.env.user)
    released_by = fields.Many2one('res.users', string="Released By", tracking=True)
    received_by = fields.Many2one('res.users', string="Received By", tracking=True)
    issuance_line_ids = fields.One2many('issuance.form.line', 'issuance_id', string='Issuance Lines')
    email_sent = fields.Boolean(string='Email Sent')
    allocation_table = fields.One2many('allocation.table.line', 'allocation_id', string='Allocation Table')
    zone = fields.Selection([
        ('luzon', 'LUZON'),
        ('ncr', 'NCR'),
        ('visayas', 'VISAYAS'),
        ('mindanao', 'MINDANAO')
    ], string="Zone", related="assigned_to.zone", store=True)
    zone_vismin = fields.Selection([
        ('luzon', 'LUZON'),
        ('ncr', 'NCR'),
        ('visayas', 'VISAYAS'),
        ('mindanao', 'MINDANAO')
    ], string="Zone", related="assigned_to_vismin.zone", store=True)
    zone_all = fields.Selection([
        ('luzon', 'LUZON'),
        ('ncr', 'NCR'),
        ('visayas', 'VISAYAS'),
        ('mindanao', 'MINDANAO')
    ], string="Zone", related="assigned_to_all.zone", store=True)
    region = fields.Char(string="Region", related="assigned_to.region")
    region_vismin = fields.Char(string="Region", related="assigned_to_vismin.region")
    region_all = fields.Char(string="Region", related="assigned_to_all.region")
    
    date_issued = fields.Date(
        string="Date Issued",
        default=fields.Date.context_today
    )


    isZone = fields.Char('USER ZONE')
    zone_filter = fields.Char(store=False)
    remarks = fields.Text(string='Remarks', tracking=True)
    token = fields.Char(store=True)
    link = fields.Char(store=True)
    confirmation_token = fields.Char("Confirmation Token")
    token_expiry = fields.Datetime("Token Expiry")
    am_email = fields.Many2one('res.partner', 'AM Email')
    rm_email = fields.Many2one('res.partner', "RM Email")

    ###################################### Added by jo start =========

    def _validate_stock_availability(self, product_id, requested_qty, location_id, uom_id):
        """Validate if requested quantity is available considering pending issuances."""
        StockQuant = self.env['stock.quant']
        IssuanceLine = self.env['issuance.form.line']

        # Get available quantity from stock.quant
        quant = StockQuant.search([
            ('product_id', '=', product_id.id),
            ('location_id', '=', location_id.id),
            ('quantity', '>', 0)
        ], limit=1)

        if not quant:
            raise UserError(f"No stock available for product {product_id.display_name} in location {location_id.name}.")

        available_qty = quant.available_quantity
        _logger.info(f"Available quantity for {product_id.display_name} in {location_id.name}: {available_qty}")

        # Sum reserved quantities from other pending issuances
        pending_lines = IssuanceLine.search([
            ('product_id', '=', product_id.id),
            ('location_id', '=', location_id.id),
            # ('issuance_id.state', 'in', ['sent', 'received', 'draft']),
            ('issuance_id.state', '=', 'sent'),
            ('issuance_id', '!=', self.id)  # Exclude current issuance
        ])
        reserved_qty = sum(line.product_uom_qty for line in pending_lines)
        _logger.info(f"Reserved quantity for {product_id.display_name} from pending issuances: {reserved_qty}")

        # Convert requested quantity to product's UoM if needed
        product_uom = product_id.uom_id
        if uom_id != product_uom:
            requested_qty = self.env['uom.uom']._compute_quantity(requested_qty, uom_id, product_uom)

        qty = quant.quantity # On Hand
        # Check if requested quantity exceeds available stock
        if requested_qty > (qty - reserved_qty):
            raise UserError(
                f"Insufficient stock for {product_id.display_name}. "
                f"Requested: {requested_qty}, Available: {available_qty}, Reserved: {reserved_qty}"
            )

    @api.constrains('issuance_line_ids')
    def _check_stock_availability(self):
        """Constraint to validate stock availability when issuance lines are created/updated."""
        for issuance in self:
            for line in issuance.issuance_line_ids:
                if line.product_uom_qty <= 0:
                    raise UserError(f"Product '{line.product_id.display_name}' cannot have zero or negative quantity.")
                self._validate_stock_availability(
                    line.product_id,
                    line.product_uom_qty,
                    line.location_id,
                    line.product_uom
                )

    @api.onchange('issuance_line_ids')
    def _onchange_issuance_line_ids(self):
        """Warn about stock availability and check duplicate products when modifying issuance lines."""
        #  Stock availability check
        seen_products = set()
        for line in self.issuance_line_ids:
            if line.product_id and line.product_uom_qty > 0:
                try:
                    self._validate_stock_availability(
                        line.product_id,
                        line.product_uom_qty,
                        line.location_id,
                        line.product_uom
                    )
                except UserError as e:
                    return {
                        'warning': {
                            'title': 'Stock Warning',
                            'message': str(e)
                        }
                    }
            # added for duplicate items
            if not line.product_id:
                continue
            if line.product_id.id in seen_products:
                raise UserError((
                    f"Duplicate item detected: '{line.product_id.display_name}' is already listed."
                ))
            seen_products.add(line.product_id.id)

    ###################################### Added by jo end ========

    # @api.onchange("assigned_to")
    # def _onchange_assigned_to(self):
    #     if self.assigned_to:
    #         self.company_id = self.assigned_to.company_id
            
    #         self.location_id = self.assigned_to.location_dest_id.location_id.id
    #         self.region = self.assigned_to.region
    #         self.region_vismin = self.assigned_to.region

    #         self.zone = self.assigned_to.zone

    def generate_confirmation_token(self):
        self.confirmation_token = str(uuid.uuid4())
        self.token_expiry = datetime.now() + timedelta(days=1)  # 1 day expiry
        self.env.cr.commit()  # ensure it's saved before sending email


    # When Selecting Branch upon issuance of LNCR ISSUANCE MANAGER
    @api.onchange('assigned_to')
    def _onchange_assigned_to(self):
        if not self.assigned_to:
            return

        branch_name = self.assigned_to.branch_name.strip().upper()
        company = self.company_id or self.env.company

        _logger.info(f"Assigned to branch: {branch_name} | Company: {company.name}")

        StockLocation = self.env['stock.location']

        # Filter by company name directly using a join on company_id.name
        existing_location = StockLocation.search([
            ('usage', '=', 'internal'),
            # ('company_id.name', '=', 'MICHEL J. LHUILLIER FINANCIAL SERVICES (PAWNSHOPS) INC,'),
            ('company_id', '=', self.company_id.id),
            ('lncr', '=', True)
        ], limit=1)

        if existing_location:
            self.location_id = existing_location
            _logger.info(f"Found existing location: {branch_name} | Usage: {existing_location.usage}")
            _logger.info(f"Assigned existing customer location_id: {self.location_id}")
       
        parent_location = StockLocation.search([
            ('usage', '=', 'internal'),
            ('location_id', '=', False),  # top-level
            ('company_id', '=', company.id)
        ], limit=1)

        _logger.info(f"No existing location found. Creating new for: {branch_name}")

        new_location = StockLocation.search([
            ('name', '=', branch_name),
            ('company_id', '=', company.id)
        ], limit=1)

        if new_location:
            self.assigned_to.write({
                'location_dest_id': new_location.id
            })
        else:
            new_location = StockLocation.create({
                'name': branch_name,
                'usage': 'customer',  # branch/outside locations
                'location_id': parent_location.id if parent_location else False,
                'company_id': company.id,
                'lncr': True
            })
            self.assigned_to.write({
                'location_dest_id': new_location.id
            })
        _logger.info(f"Created and assigned new location: {new_location.name} (ID: {new_location.id})")
        _logger.info("Finished onchange for assigned_to.")
        self.update({  'assigned_to_selected' : self.assigned_to.id, 
                       'company_id_report': self.assigned_to.company_id.id
        })

    # When Selecting Branch upon issuance of VISMIN ISSUANCE MANAGER

    @api.onchange("assigned_to_vismin")
    def _onchange_assigned_to_vismin(self):
        if not self.assigned_to_vismin:
            return
        branch_name = self.assigned_to_vismin.branch_name.strip().upper()
        company = self.company_id or self.env.company
        StockLocation = self.env['stock.location']

        _logger.info(f"[VISMIN] Assigned to: {branch_name} | Company: {company.name}")

        existing_location = StockLocation.search([
            ('usage', '=', 'internal'),
            # ('company_id.name', '=', 'MICHEL J. LHUILLIER FINANCIAL SERVICES (PAWNSHOPS) INC,'),
            ('company_id', '=', self.company_id.id),
            ('vismin', '=', True)
        ], limit=1)

        if existing_location:
            self.location_id = existing_location
            _logger.info(f"[VISMIN] Existing customer location found: {existing_location.name}")
        
            parent_location = StockLocation.search([
                ('usage', '=', 'internal'),
                ('company_id', '=', self.company_id.id),
                ('vismin', '=', True)
                # ('location_id', '=', False)
            ], limit=1)

            _logger.info(f"[VISMIN] No existing location. Creating new for: {branch_name}")

            new_location = StockLocation.search([
                ('name', '=', branch_name),
                ('company_id', '=', company.id)
            ], limit=1)

            if new_location:
                self.assigned_to_vismin.write({
                    'location_dest_id': new_location.id
                })
            else:
                new_location = StockLocation.create({
                    'name': branch_name,
                    'usage': 'customer',  # branch/outside locations
                    'location_id': parent_location.id if parent_location else False,
                    'company_id': company.id,
                    'vismin': True
                })
                self.assigned_to_vismin.write({
                    'location_dest_id': new_location.id, 
                   
                })
            # self.location_id = new_location.location_id.id
            _logger.info(f"[VISMIN] Created and assigned new location: {new_location.name} (ID: {new_location.id})")

            self.update({'assigned_to_selected': self.assigned_to_vismin.id, 'company_id_report': self.assigned_to_vismin.company_id.id})

    
    @api.onchange("assigned_to_all")
    def _onchange_assigned_to_all(self):
        if not self.assigned_to_all:
            return
        company = self.company_id or self.env.company
        # vismin_onhand = fields.Float("VISMIN On Hand", compute="_compute_lncr_vismin_onhand", store=False)
        StockLocation = self.env['stock.location']
        Branch = self.env['res.company.branches']

        # 1. Search for stock.location with name same as assigned_to.name
        location = StockLocation.search([('name', '=', self.assigned_to_all.branch_name)], limit=1)

        if location:
            # 2. Check if type is customer
            if location.usage == 'customer':
                self.location_id = location.location_id.id
                print(self.location_id.name, "EXISTING LOCATION ID Name")

                # self.location_id = new_location.location_id.id
                # self.location_dest_id = location.id
        else:
            # 3. Find Parent Location named "Stock"
            print("WALA PA")
        
            domain = [
                ('name', '=', 'Stock'),
                ('usage', '=', 'internal'),
                ('company_id', '=', self.assigned_to_all.company_id.id)
            ]
            
            if self.assigned_to_all.zone in ['luzon', 'ncr']:
                domain.append(('lncr', '=', True))
            else:
                domain.append(('vismin', '=', True))

            parent_location = StockLocation.search(domain, limit=1)


            new_location = StockLocation.search([
                ('name', '=', self.assigned_to_all.branch_name),
                ('company_id', '=', company.id)
            ], limit=1)

            if new_location:
                    self.assigned_to_all.write({
                        'location_dest_id': new_location.id,
                        
                    })
            else:
                new_location = StockLocation.create({
                    'name':self.assigned_to_all.branch_name,
                    'usage': 'customer',  # branch/outside locations
                    'location_id': parent_location.id if parent_location else False,
                    'company_id': company.id,
                    'lncr': True
                })

            self.assigned_to_all.write({
                'location_dest_id': new_location.id, 
            })
        
        self.write({
            'company_id_report': self.assigned_to_all.company_id.id 
        })
        

    def create_delivery_operation(self):
        print("a")

    @api.model
    def default_get(self, fields_list):
        defaults = super(Issuance, self).default_get(fields_list)
        # Get the Incoming picking type for the logged-in user's company

        user = self.env.user  # Current logged-in user
        group_luzon = self.env.ref('ml_development.group_lncr_mods')
        group_vismin = self.env.ref('ml_development.group_vismin_mods')

        if group_vismin in user.groups_id:
            self.isZone = 'vismin'
            defaults['isZone'] = 'vismin'

        elif group_luzon in user.groups_id:
            self.isZone = 'lncr'
            defaults['isZone'] = 'lncr'

        else:
            self.isZone = 'all'
            defaults['isZone'] = 'all'
        return defaults

    def button_draft(self):
        print ("Cancelled")
    
    def print_sticker(self):
        print ("Sticker")
    
    def get_confirmation_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        self.generate_confirmation_token()
        confirmation_url = f"{base_url}/issuance/confirm?token={self.confirmation_token}"
        return confirmation_url


    def action_open_send_email_wizard(self):
        """Open email pop-up window and create/send issuance email with PDF attachment"""
        template = self.env.ref("ml_development.email_template_issuance", raise_if_not_found=False)
        if not template:
            raise UserError("Email template not found!")

        StockPicking = self.env["stock.picking"]
        Report = self.env["ir.actions.report"]
        Attachment = self.env["ir.attachment"]

        for issuance in self:
            _logger.info("[EMAIL DEBUG] Processing issuance %s", issuance.name)

            # ───────────── Generate Issuance PDF ─────────────
            pdf_content, _ = Report._render_qweb_pdf("ml_development.report_issuance_document", [issuance.id])
            pdf_base64 = base64.b64encode(pdf_content)

            attachment_name = f"Issuance_{issuance.name}.pdf"
            attachment = Attachment.search([
                ("res_model", "=", "issuance.form"),
                ("res_id", "=", issuance.id),
                ("name", "=", attachment_name)
            ], limit=1)

            if not attachment:
                attachment = Attachment.create({
                    "name": attachment_name,
                    "type": "binary",
                    "datas": pdf_base64,
                    "res_model": "issuance.form",
                    "res_id": issuance.id,
                    "mimetype": "application/pdf",
                })
                _logger.info("[EMAIL DEBUG] Created new attachment: %s", attachment_name)
            else:
                _logger.info("[EMAIL DEBUG] Found existing attachment: %s", attachment_name)

            # ───────────── Validate Issuance Lines ─────────────
            if not issuance.issuance_line_ids:
                raise UserError("Cannot approve issuance without items.")

            for line in issuance.issuance_line_ids:
                if line.product_uom_qty <= 0:
                    raise UserError(
                        f"Product '{line.product_id.display_name}' cannot have zero or negative quantity."
                    )

            # ───────────── Check for Existing Stock Picking ─────────────
            existing_picking = StockPicking.search([
                ("origin", "=", issuance.name),
                ("state", "not in", ["done", "cancel"])
            ], limit=1)

            if existing_picking:
                _logger.info("[EMAIL DEBUG] Found existing picking for issuance %s", issuance.name)

            # ───────────── Collect Recipients (using branch.managers.email) ─────────────
            branch_record = issuance.assigned_to or issuance.assigned_to_vismin or issuance.assigned_to_all
            email_list = []

            if branch_record and branch_record.branch_manager_id and branch_record.branch_manager_id.email:
                manager = branch_record.branch_manager_id
                email_list.append(manager.email)
                _logger.info(
                    "[EMAIL DEBUG] Using branch manager %s (Email=%s) for branch %s",
                    manager.complete_name, manager.email, branch_record.branch_name
                )
            else:
                _logger.warning(
                    "[EMAIL DEBUG] No valid email found for branch manager in branch: %s",
                    branch_record.branch_name if branch_record else "N/A"
                )

            if not email_list:
                raise UserError("No branch manager email found. Please configure an email for this branch manager.")

            # ───────────── Send Email ─────────────
            template.write({
                "email_to": ",".join(email_list),     # ⬅️ use raw email addresses
                "attachment_ids": [(6, 0, [attachment.id])],
            })
            template.send_mail(issuance.id, force_send=True)
            _logger.info("[EMAIL DEBUG] Email sent using template %s to emails: %s", template.id, email_list)

            # Reset template attachments
            template.attachment_ids = [(5, 0, 0)]

            # ───────────── Update State ─────────────
            issuance.ensure_one()
            issuance.mark_as_sent()
            if issuance.state != "sent":
                issuance.state = "sent"

            # ───────────── Post Chatter Message ─────────────
            _logger.info("[EMAIL DEBUG] Final email list: %s", ", ".join(email_list))

            message_body = "<br/>".join([
                f"<p><strong>Email sent to:</strong> {', '.join(email_list)}</p>",
                f"<strong>Remarks:</strong> {issuance.remarks or 'No remarks provided.'}",
                f"<strong>Submitted By:</strong> {issuance.prepared_by.name}"
            ])
            issuance.message_post(
                body=message_body,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                body_is_html=True,
            )
            issuance.remarks = False



    # def action_open_send_email_wizard(self):
    #     """Open email pop-up window and create a delivery order if not exists"""
    #     template_id = self.env.ref('ml_development.email_template_issuance')
        
    #     if not template_id.id:
    #         raise UserError("Email template not found!")

    #     StockPicking = self.env['stock.picking']
    #     Report = self.env['ir.actions.report']
    #     Attachment = self.env['ir.attachment']

    #     for issuance in self:
    #         #  Generate the Issuance PDF Report
    #         report = Report._render_qweb_pdf('ml_development.report_issuance_document', [issuance.id])
    #         pdf_content, content_type = report
    #         pdf_base64 = base64.b64encode(pdf_content)

    #         #  Create Attachment
    #         attachment_name = f"Issuance_{issuance.name}.pdf"
    #         existing_attachment = Attachment.search([
    #             ('res_model', '=', 'issuance.form'),
    #             ('res_id', '=', issuance.id),
    #             ('name', '=', attachment_name)
    #         ], limit=1)

    #         if existing_attachment:
    #             attachment = existing_attachment
    #         else:
    #             attachment = Attachment.create({
    #                 'name': attachment_name,
    #                 'type': 'binary',
    #                 'datas': pdf_base64,
    #                 'res_model': 'issuance.form',
    #                 'res_id': issuance.id,
    #                 'mimetype': 'application/pdf',
    #             })
    #         if not issuance.issuance_line_ids:
    #             raise UserError("Cannot approve issuance without items.")

    #         for line in issuance.issuance_line_ids:
    #             if line.product_uom_qty <= 0:
    #                 raise UserError(f"Product '{line.product_id.display_name}' cannot have zero or negative quantity.")

    #         #  Check if a Stock Picking already exists for this Issuance
    #         existing_picking = StockPicking.search([
    #             ('origin', '=', issuance.name),  # Same Issuance Form
    #             ('state', 'not in', ['done', 'cancel'])  # Ignore Done or Canceled pickings
    #         ], limit=1)

    #         if existing_picking:
    #             picking = existing_picking  # Reuse existing picking
    #         else:
    #             partner_ids = []

    #             if self.assigned_to:
    #                 if self.assigned_to.partner_id:
    #                     partner_ids.append(self.assigned_to.partner_id.id)
    #                 if self.assigned_to.am_email:
    #                     partner_ids.append(self.assigned_to.am_email.id)
    #                 if self.assigned_to.rm_email:
    #                     partner_ids.append(self.assigned_to.rm_email.id)

    #             elif self.assigned_to_vismin:
    #                 if self.assigned_to_vismin.partner_id:
    #                     partner_ids.append(self.assigned_to_vismin.partner_id.id)
    #                 if self.assigned_to_vismin.am_email:
    #                     partner_ids.append(self.assigned_to_vismin.am_email.id)
    #                 if self.assigned_to_vismin.rm_email:
    #                     partner_ids.append(self.assigned_to_vismin.rm_email.id)

    #             elif self.assigned_to_all:
    #                 if self.assigned_to_all.partner_id:
    #                     partner_ids.append(self.assigned_to_all.partner_id.id)
    #                 if self.assigned_to_all.am_email:
    #                     partner_ids.append(self.assigned_to_all.am_email.id)
    #                 if self.assigned_to_all.rm_email:
    #                     partner_ids.append(self.assigned_to_all.rm_email.id)

    #             # If no valid recipients found, raise error
    #             if not partner_ids:
    #                 raise UserError("No email recipients found. Please set at least one: Partner, AM, or RM email.")
                
    #             # Auto send email without pop-up 
    #             # Modified by: Sansan
    #             template_id.partner_to = ','.join(str(pid) for pid in partner_ids)
    #             template_id.attachment_ids = [(6, 0, [attachment.id])]
    #             template_id.send_mail(self.id, force_send=True)

    #             # Clear all attachments from the template after sending to avoid reuse
    #             template_id.attachment_ids = [(5, 0, 0)]
                
    #             self.ensure_one()
    #             self.mark_as_sent()

    #             if self.state == 'sent':
    #                 return  # Already sent
    #             else:
    #                 self.state = 'sent'

    #             # Find email recipients to contacts
    #             partner_ids = list(map(int, template_id.partner_to.split(',')))
    #             email_recipients = self.env['res.partner'].browse(partner_ids)
    #             email_list = ', '.join(email_recipients.mapped('email') or ['N/A'])

    #             # Post the message
    #             message_body = "<br/>".join([
    #                 f"<p><strong>Email sent to:</strong> {email_list}</p>",
    #                 f"<strong>Remarks:</strong> {self.remarks or 'No remarks provided.'}",
    #                 f"<strong>Submitted By:</strong> {self.prepared_by.name}"
    #             ])
    #             # Post the message as HTML
    #             self.message_post(
    #                 body=message_body,
    #                 message_type='comment',
    #                 subtype_xmlid='mail.mt_comment',
    #                 body_is_html=True
    #             )
    #             self.remarks = False  # Clear remarks after sending

    def mark_as_sent(self):
        """Mark Issuance as Sent and Post Chatter Message"""
        for issuance in self:
            # Determine assigned user and zone
            assigned = None
            zone = ''
            if issuance.assigned_to:
                assigned = issuance.assigned_to
                zone = 'lncr'
            elif issuance.assigned_to_vismin:
                assigned = issuance.assigned_to_vismin
                zone = 'vismin'
            elif issuance.assigned_to_all:
                assigned = issuance.assigned_to_all
                zone = 'vismin'
            else:
                raise UserError("No branch assignment set.")

            # Get branch location
            branch_location = self.env['stock.location'].sudo().search([
                ('name', '=', assigned.branch_name),
                ('usage', '=', 'customer')
            ], limit=1)

            if not branch_location:
                raise UserError(f"Branch location '{assigned.branch_name}' not found!")

            # Get picking type
            picking_type = self.env['stock.picking.type'].sudo().search([
                ('code', '=', 'outgoing'),
                ('warehouse_id.company_id', '=', self.company_id.id)
            ], limit=1)

            if not picking_type:
                raise UserError("No Delivery Operation Type found for Branch Issuance.")

            # Create Stock Picking
            picking = self.env['stock.picking'].sudo().create({
                'partner_id': assigned.partner_id.id,
                'picking_type_id': picking_type.id,
                'location_id': issuance.issuance_line_ids[0].location_id.id,
                'location_dest_id': issuance.issuance_line_ids[0].location_dest_id.id,
                'origin': issuance.name,
                'isZone': zone,
                'move_ids_without_package': [(0, 0, {
                    'name': line.product_id.display_name,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.product_uom_qty,
                    'quantity': line.product_uom_qty,
                    'received_qty': line.product_uom_qty,
                    'product_uom': line.product_uom.id,
                    'location_id': line.location_id.id,
                    'location_dest_id': line.location_dest_id.id,
                    # 'company_id': self.company_id.id,
                }) for line in issuance.issuance_line_ids],
            })

            # Build item details
            # items_details = "<ul>"
            # for line in issuance.issuance_line_ids:
            #     items_details += f"<li>{line.product_id.name}: {int(line.product_uom_qty)} {line.product_uom.name}</li>"
            # items_details += "</ul>"

            # # Post to chatter
            # message = f"""
            #     <p><strong>Email Sent Successfully</strong></p>
            #     <p><strong>Recipient:</strong> {assigned.name} ({assigned.email})</p>
            #     <p><strong>Issued Items:</strong></p>
            #     {items_details}
            # """
            # issuance.message_post(body=message, subtype_xmlid="mail.mt_comment", body_is_html=True)

    def action_cancel_issuance(self):
        """Cancel Issuance and its related Delivery Order"""
        for issuance in self:
            if issuance.state == 'cancel':
                raise UserError("This issuance is already canceled.")
            issuance.state = 'cancel'
            related_picking = self.env['stock.picking'].search([
                ('origin', '=', issuance.name),
                ('state', 'not in', ['done', 'cancel'])  # Ignore already done/canceled ones
            ])
            # for picking in related_picking:
            #     picking.action_cancel()  
            issuance.message_post(
                body="<b>Issuance has been canceled.</b>",
                subtype_xmlid="mail.mt_comment",
                body_is_html=True
            )

    # @api.model_create_multi
    # def create(self, vals_list):
    #     for vals in vals_list:
    #         if vals.get('name', 'New') == 'New':  # Ensure only 'New' gets a sequence
    #             sequence = self.env['ir.sequence'].search([('code', '=', 'issuance.form')], limit=1)
    #             if sequence:
    #                 next_number = sequence.next_by_id()
    #             else:
    #                 next_number = "New"
    #             vals['name'] = next_number
    #     return super(Issuance, self).create(vals_list)


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':  # Only assign if name is "New"
                location_id = vals.get('location_id')
                if not location_id:
                    raise ValidationError("Cannot create issuance without a warehouse (location_id).")
                
                location = self.env['stock.location'].browse(location_id)
                if location.lncr:
                    sequence_code = 'issuance.form.ln.reset'  # LN/ISS00001
                elif location.vismin:
                    sequence_code = 'issuance.form.vm.reset'  # VM/ISS00001
                else:
                    raise ValidationError(
                        f"Warehouse '{location.name}' is not configured for LNCR or VISMIN. "
                        "Please select a valid warehouse."
                    )
                
                next_number = self.env['ir.sequence'].next_by_code(sequence_code)
                if not next_number:
                    raise ValidationError(f"No sequence found for code '{sequence_code}'.")
                vals['name'] = next_number
        return super(Issuance, self).create(vals_list)















    # def button_approve(self):
    #     StockPicking = self.env['stock.picking']
    #     StockQuant = self.env['stock.quant']
    #     StockMoveLine = self.env['stock.move.line']

    #     for issuance in self:
    #         _logger.info(f"[{issuance.name}] Approving issuance...")

    #         # Search for related picking
    #         picking = StockPicking.sudo().search([
    #             ('origin', '=', issuance.name),
    #         ], limit=1)

    #         if not picking:
    #             raise UserError(f"No Stock Picking found for {issuance.name}")

    #         total_issuance_qty = sum(line.product_uom_qty for line in issuance.issuance_line_ids)
    #         total_picking_demand = sum(move.product_uom_qty for move in picking.move_ids_without_package)

    #         if picking.state not in ['done', 'cancel']:
    #             picking.action_confirm()
    #             picking.action_assign()

    #             for move in picking.move_ids_without_package:
    #                 for line in move.move_line_ids:
    #                     line.qty_done = line.quantity  # or line.qty_done = line.product_uom_qty
    #             # picking.button_validate()

    #         # Chatter message
    #         if total_issuance_qty == total_picking_demand:
    #             issuance.write({'state': 'done'})
    #             issuance.message_post(
    #                 body=f"""
    #                     <b>Issuance Approved</b><br/>
    #                     All requested items have been issued.<br/>
    #                     <b>Total Items:</b> {total_issuance_qty}
    #                 """,
    #                 message_type="comment",
    #                 subtype_xmlid='mail.mt_comment',
    #                 body_is_html=True
    #             )
    #         else:
    #             issuance.message_post(
    #                 body=f"""
    #                     <b>Partial Issuance</b><br/>
    #                     <b>Requested:</b> {total_issuance_qty} | <b>Available:</b> {total_picking_demand}
    #                 """,
    #                 message_type="comment",
    #                 subtype_xmlid='mail.mt_comment',
    #                 body_is_html=True
    #             )

    #         # Adjust stock quants
    #         for line in issuance.issuance_line_ids:
    #             quant = StockQuant.search([
    #                 ('product_id', '=', line.product_id.id),
    #                 # ('location_id', '=', line.location_id.id)
    #             ], limit=1)

    #             if quant:
    #                 _logger.info(f"[{issuance.name}] Found quant for {line.product_id.display_name}: Quantity={quant.quantity}, Reserved={quant.reserved_quantity}")

    #                 # Update reserved and available
    #                 new_reserved_qty = max(quant.reserved_quantity - line.product_uom_qty, 0)
    #                 new_actual_qty = max(quant.quantity - line.product_uom_qty, 0)
    #                 new_available_qty = max(new_actual_qty - new_reserved_qty, 0)

    #                 quant.sudo().write({
    #                     'reserved_quantity': new_reserved_qty,
    #                     'quantity': new_actual_qty,
    #                     'available_quantity': new_available_qty
    #                 })

    #                 _logger.info(f"[{issuance.name}] Updated Quant for {line.product_id.display_name}: Quantity={new_actual_qty}, Reserved={new_reserved_qty}, Available={new_available_qty}")

    #             # Update move line state
    #             move_lines = StockMoveLine.search([
    #                 ('move_id', 'in', picking.move_ids_without_package.ids),
    #                 ('product_id', '=', line.product_id.id)
    #             ])
    #             for move_line in move_lines:
    #                 move_line.write({'state': 'done'})
    #                 _logger.info(f"[{issuance.name}] Move line {move_line.id} for {move_line.product_id.display_name} marked as DONE.")

    #     return True



    def button_approve(self):
        """Approve issuance and update stock, with validation for stock availability."""
        StockPicking = self.env['stock.picking']
        StockQuant = self.env['stock.quant']
        StockMoveLine = self.env['stock.move.line']

        for issuance in self:
            _logger.info(f"[{issuance.name}] Approving issuance...")

            # Validate stock availability for all lines
            for line in issuance.issuance_line_ids:
                self._validate_stock_availability(
                    line.product_id,
                    line.product_uom_qty,
                    line.location_id,
                    line.product_uom
                )

            # Search for related picking
            picking = StockPicking.sudo().search([
                ('origin', '=', issuance.name),
            ], limit=1)  

            if not picking:
                raise UserError(f"No Stock Picking found for {issuance.name}")

            total_issuance_qty = sum(line.product_uom_qty for line in issuance.issuance_line_ids)
            total_picking_demand = sum(move.product_uom_qty for move in picking.move_ids_without_package)

            if picking.state not in ['done', 'cancel']:
                picking.action_confirm()
                picking.action_assign()

                for move in picking.move_ids_without_package:
                    for line in move.move_line_ids:
                        line.qty_done = line.quantity
                picking.button_validate()

            # Chatter message
            if total_issuance_qty == total_picking_demand:
                issuance.write({'state': 'done'})
                issuance.message_post(
                    body=f"""
                        Issuance Approved
                        All requested items have been issued.
                        Total Items: {int(total_issuance_qty)}
                    """,
                    message_type="comment",
                    subtype_xmlid='mail.mt_comment',
                    body_is_html=True
                )
            else:
                issuance.message_post(
                    body=f"""
                        <b>Partial Issuance</b><br/>
                        <b>Requested:</b> {total_issuance_qty} | <b>Available:</b> {total_picking_demand}
                    """,
                    message_type="comment",
                    subtype_xmlid='mail.mt_comment',
                    body_is_html=True
                )

            # Adjust stock quants
            for line in issuance.issuance_line_ids:
                quant = StockQuant.search([
                    ('product_id', '=', line.product_id.id),
                    ('location_id', '=', line.location_id.id)
                ], limit=1)

                if quant:
                    _logger.info(f"[{issuance.name}] Found quant for {line.product_id.display_name}: Quantity={quant.quantity}, Reserved={quant.reserved_quantity}")

                    # Convert quantity to product's UoM if needed
                    requested_qty = line.product_uom_qty
                    if line.product_uom != line.product_id.uom_id:
                        requested_qty = self.env['uom.uom']._compute_quantity(
                            requested_qty, line.product_uom, line.product_id.uom_id
                        )

                    new_reserved_qty = max(quant.reserved_quantity - requested_qty, 0)
                    new_actual_qty = max(quant.quantity - requested_qty, 0)
                    new_available_qty = max(new_actual_qty - new_reserved_qty, 0)

                    quant.sudo().write({
                        'reserved_quantity': new_reserved_qty,
                        'quantity': new_actual_qty,
                        'available_quantity': new_available_qty
                    })

                    _logger.info(f"[{issuance.name}] Updated Quant for {line.product_id.display_name}: Quantity={new_actual_qty}, Reserved={new_reserved_qty}, Available={new_available_qty}")

                # Update move line state
                move_lines = StockMoveLine.search([
                    ('move_id', 'in', picking.move_ids_without_package.ids),
                    ('product_id', '=', line.product_id.id)
                ])
                for move_line in move_lines:
                    move_line.write({'state': 'done'})
                    _logger.info(f"[{issuance.name}] Move line {move_line.id} for {move_line.product_id.display_name} marked as DONE.")

        return True


class IssuanceFormLine(models.Model):
    _name = 'issuance.form.line'
    _description = 'Issuance Form Line'

    issuance_id = fields.Many2one('issuance.form', string='Issuance Reference', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', domain="[('qty_available', '>', 0)]", required=True)
    product_uom_qty = fields.Float('Quantity', digits=(16, 0), store=True, required=True)
    product_uom = fields.Many2one('uom.uom', string='Unit of Measure', required=True)
    location_id = fields.Many2one('stock.location', string='Warehouse', required=True)
    location_id_related = fields.Many2one('stock.location', string='Warehouse', domain="[('usage', '=', 'internal')]", required=True, related="location_id")
    location_dest_id = fields.Many2one('stock.location', string='Branch Location', domain="[('usage', '=', 'customer')]", required=True)
    branch_location = fields.Many2one('res.company.branches')
    partner_ids = fields.Many2many('res.partner', string="Assigned Partners")
    email_to = fields.Char(string="Email To", compute="_compute_email_to", store=False)
    item_code = fields.Char('Item Code')
    item_code_related = fields.Char('Item Code', related="item_code")
    
    @api.depends('partner_ids')
    def _compute_email_to(self):
        for record in self:
            # Collect emails from all partners in partner_ids
            record.email_to = ', '.join(record.partner_ids.mapped('email'))
            
    @api.onchange('issuance_id')
    def onchange_issuance_id(self):
        """ Auto-fill Source (WH/Stock), Destination (Branch Location), and Default Quantity """
        if self.issuance_id:
            # 🔹 Set WH/Stock as the default source location
            
            # if self.issuance_id.assigned_to.zone == "luzon" or "ncr":
            #     print("LN WH")
            #     warehouse_stock_location = self.env['stock.location'].search([
            #     ('usage', '=', 'internal'),
            #     ('complete_name', 'ilike', 'LW WH/Stock')  # Adjust this if necessary
            #     ], limit=1)
            #     if not warehouse_stock_location:
            #         raise ValidationError("No default warehouse location (WH/Stock) found!")
            #     self.location_id = warehouse_stock_location  # 
            # else:
            #     print("VM WH")
            #     warehouse_stock_location = self.env['stock.location'].search([
            #     ('usage', '=', 'internal'),
            #     ('complete_name', 'ilike', 'VM WH/Stock')  # Adjust this if necessary
            #     ], limit=1)
            #     if not warehouse_stock_location:
            #         raise ValidationError("No default warehouse location (WH/Stock) found!")
            #     self.location_id = warehouse_stock_location  # 

            self.location_id = self.issuance_id.location_id.id

            # 🔹 Set the destination location based on assigned branch
            if self.issuance_id.assigned_to:
                branch_location = self.issuance_id.assigned_to.location_dest_id
                if not branch_location:
                    raise ValidationError(
                        f"No stock location is set for the branch {self.issuance_id.assigned_to.branch_name}!"
                    )
                self.location_dest_id = branch_location  
            if self.issuance_id.assigned_to_vismin:
                branch_location = self.issuance_id.assigned_to_vismin.location_dest_id
                if not branch_location:
                    raise ValidationError(
                        f"No stock location is set for the branch {self.issuance_id.assigned_to_vismin.branch_name}!"
                    )
                self.location_dest_id = branch_location  
            if self.issuance_id.assigned_to_all:
                branch_location = self.issuance_id.assigned_to_all.location_dest_id
                if not branch_location:
                    raise ValidationError(
                        f"No stock location is set for the branch {self.issuance_id.assigned_to_all.branch_name}!"
                    )
                self.location_dest_id = branch_location  

    @api.onchange('product_id', 'product_uom_qty')
    def onchange_product_id(self):
        if self.product_id:
            self.update({
                'product_uom': self.product_id.uom_po_id,
                'item_code': self.product_id.item_code
            })

        if self.location_id_related and self.product_id:
            # Disable company isolation temporarily to read from any company
            quants = self.env['stock.quant'].with_company(False).search([
                ('product_id', '=', self.product_id.id),
                # ('location_id', '=', self.location_id_related.id)
            ])
            quant_qty = sum(quants.mapped('quantity'))

            # Optional: Also show incoming/outgoing moves for reference
            incoming_moves = self.env['stock.move'].search([
                ('product_id', '=', self.product_id.id),
                ('location_dest_id', '=', self.location_id_related.id),
                ('state', '=', 'done')
            ])
            outgoing_moves = self.env['stock.move'].search([
                ('product_id', '=', self.product_id.id),
                ('location_id', '=', self.location_id_related.id),
                ('state', '=', 'done')
            ])
            incoming_qty = sum(incoming_moves.mapped('product_uom_qty'))
            outgoing_qty = sum(outgoing_moves.mapped('product_uom_qty'))

            if quant_qty <= 0:
                return {
                    'warning': {
                        'title': "No Stock Available",
                        'message': f"The product '{self.product_id.display_name}' has no on-hand quantity in the selected warehouse.",
                    }
                }

            if self.product_uom_qty > quant_qty:
                raise UserError(
                    f"Cannot issue more than the quantity on hand: {quant_qty:,.0f}")

class AllocationTableLine(models.Model):
    _name = 'allocation.table.line'
    _description = 'Allocation Table Lines'

    allocation_id = fields.Many2one('issuance.form', string='Allocation Id Reference', ondelete='cascade')

class MailComposeMessage(models.TransientModel):
    _inherit = 'mail.compose.message'

    def action_send_mail(self):
        """Override send_mail_action to update state and post in chatter after sending"""
        res = super(MailComposeMessage, self).action_send_mail()

        # Ensure this wizard is related to issuance.form and only one record is passed
        if self.model == 'issuance.form' and self.res_ids:

            # If res_ids is a string, evaluate it to get the actual list
            if isinstance(self.res_ids, str):
                try:
                    # Safely evaluate the string to convert it into a list of integers
                    res_ids = eval(self.res_ids)
                except Exception as e:
                    raise UserError(f"Error parsing res_ids: {e}")
            else:
                res_ids = self.res_ids

            # Ensure res_ids is a list of integers
            if not isinstance(res_ids, list) or not all(isinstance(id, int) for id in res_ids):
                raise UserError("Invalid format for res_ids. It should be a list of integers.")

            # Ensure only one record is selected
            if len(res_ids) > 1:
                raise UserError("Multiple records are not allowed. Please select only one record.")

            # Browse the first and only record
            issuance_records = self.env['issuance.form'].browse(res_ids[0])  # Using the first record only

            if issuance_records:
                #  Update State
                issuance_records.state = 'sent'
                email_display = '' 

                #  Prepare Email Recipients
                if issuance_records.assigned_to:
                    recipient_emails = ', '.join(issuance_records.assigned_to.mapped('branch_email'))
                    email_display = recipient_emails  # fallback to same list

                elif issuance_records.assigned_to_vismin:
                    recipient_emails = ', '.join(filter(lambda e: e, issuance_records.assigned_to_vismin.mapped('branch_email')))

                    emails = [
                        issuance_records.assigned_to_vismin.partner_id.email or '',
                        issuance_records.assigned_to_vismin.am_email.email if issuance_records.assigned_to_vismin.am_email else '',
                        issuance_records.assigned_to_vismin.abm_email.email if issuance_records.assigned_to_vismin.abm_email else '',
                    ]
                    email_display = ', '.join(filter(None, emails))

                elif issuance_records.assigned_to_all:
                    recipient_emails = ', '.join(issuance_records.assigned_to_all.mapped('branch_email'))
                    email_display = recipient_emails  # fallback here too
                #  Prepare Item Details
                item_details = "<br/>".join([
                    f"<b>{line.product_id.name}</b>: {int(line.product_uom_qty)} {line.product_uom.name}"
                    for line in issuance_records.issuance_line_ids
                ])

                #  Post Message to Chatter
                issuance_records.message_post(
                    body=Markup(
                        f"Issuance email sent to: {email_display}<br/><br/>"
                        f"Items Issued: <br/>{item_details}"
                    ),
                    subtype_xmlid='mail.mt_comment',
                    message_type='comment',
                    body_is_html=True
                )

            for issuance in issuance_records:
                   # Fetch the Outgoing Operation Type
                picking_type = self.env['stock.picking.type'].search([
                    ('code', '=', 'outgoing'),
                    ('warehouse_id.company_id', '=', self.env.company.id)
                ], limit=1)

                if not picking_type:
                    raise UserError("No Delivery Operation Type found for Branch Issuance.")

                # Find the correct branch location
                branch_location = None
                if issuance.assigned_to: 
                    branch_location = self.env['stock.location'].search([
                        ('name', '=', issuance.assigned_to.branch_name),
                        ('usage', '=', 'customer')  
                    ], limit=1)
                elif issuance.assigned_to_vismin: 
                    branch_location = self.env['stock.location'].search([
                        ('name', '=', issuance.assigned_to_vismin.branch_name),
                        ('usage', '=', 'customer')  
                    ], limit=1)
                elif issuance.assigned_to_all: 
                    branch_location = self.env['stock.location'].search([
                        ('name', '=', issuance.assigned_to_all.branch_name),
                        ('usage', '=', 'customer')  
                    ], limit=1)

                if not branch_location:
                    raise UserError("Branch Location not found in stock.location!")

                # Create the picking
                picking = self.env['stock.picking'].sudo().create({
                    'partner_id': (
                        issuance.assigned_to.partner_id.id
                        if issuance.assigned_to else
                        issuance.assigned_to_vismin.partner_id.id
                        if issuance.assigned_to_vismin else
                        issuance.assigned_to_all.partner_id.id
                    ),
                    'picking_type_id': picking_type.id,
                    'location_id': issuance.issuance_line_ids[0].location_id.id,
                    'location_dest_id': issuance.issuance_line_ids[0].location_dest_id.id,
                    'origin': issuance.name,
                    'isZone': (
                        'lncr' if issuance.assigned_to else
                        'vismin'
                    ),
                    'move_ids_without_package': [(0, 0, {
                        'name': line.product_id.display_name,
                        'product_id': line.product_id.id,
                        'product_uom_qty': line.product_uom_qty,
                        'quantity': line.product_uom_qty,
                        'received_qty': line.product_uom_qty,
                        'product_uom': line.product_uom.id,
                        'location_id': line.location_id.id,
                        'location_dest_id': line.location_dest_id.id,
                        # 'company_id': line.company_id.id,
                    }) for line in issuance.issuance_line_ids],
                })
        return res

class MailTemplate(models.Model):
    _inherit = 'mail.template'

    def send_mail(self, res_id, force_send=False, raise_exception=False, email_values=None):
        # Call original method
        result = super().send_mail(res_id, force_send=force_send, raise_exception=raise_exception, email_values=email_values)

        # Now add your custom logic
        record = self.env[self.model].browse(res_id)

        # Example: Set a boolean field or trigger an action
        if self.model == 'issuance.form':  # your model
            record.write({'email_sent': True})  # or call record.action_x()

        return result

class MlBranches(models.Model):
    _name = 'ml.branches'

    name = fields.Char('Branch')
    head_office = fields.Boolean('Head Office')