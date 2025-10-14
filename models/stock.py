from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
import base64 
from dateutil.relativedelta import relativedelta
from collections import defaultdict
import logging
from ast import literal_eval 
from odoo.tools.float_utils import float_compare
from odoo.tools import float_round

_logger = logging.getLogger(__name__)

class StockPickingInherit(models.Model):
    _inherit = 'stock.picking'
    _description = 'ML Stock Picking'
    
    product_id_vismin = fields.Many2one('product.product')
    address = fields.Text('Address')
    invoice_number = fields.Char('Invoice Number')
    po_rr = fields.Boolean('IS PO?', default="True" )
    branch = fields.Many2one('res.company.branches')
    zone = fields.Selection([
        ('luzon', 'LUZON'),
        ('ncr', 'NCR'),
        ('visayas', 'VISAYAS'),
        ('mindanao', 'MINDANAO')
    ], string="Zone", related="branch.zone", store=True)
    partner_id = fields.Many2one(
        'res.partner', 'Supplier',
        check_company=True, index='btree_not_null')
    def _default_received_by(self):
        """ Set default user to the first available user in 'RFP Manager Inventory' group """
        rfp_group = self.env.ref('ml_development.group_rfp_manager_inventory')
        user = self.env['res.users'].search([('groups_id', 'in', rfp_group.id)], limit=1)
        return user.id if user else False
    partner_id = fields.Many2one(
        'res.partner', 'Contact',
        check_company=True, index='btree_not_null')
    received_by = fields.Many2one('res.users', string='Received By', default=lambda self: self.env.user,  help="Received By: Custodian/Division/Branch in Charge")
    attachment = fields.Many2many(
        'ir.attachment', 'stock_picking_attachment_rel', 'picking_id', 'attachment_id', string="Attachments"
    )
    total_amount = fields.Float('Total Amount')
    remarks = fields.Text('Remarks')
    isZone = fields.Char('USER ZONE')
    valuation_move_ids = fields.One2many(
        'account.move', 'picking_id', string="Valuation Moves"
    )
    operation = fields.Selection([
        ('receiving', 'Receiving'),
        ('internal', 'Internal Transfer'),
        ('issuance', 'Issuance'),
    
    ], string="Operation", store=True)
    received_amount = fields.Float(string="Receiived Amount",store=True) 
    move_type = fields.Selection([
        ('direct', 'Partial'),
        ('one', 'All at once'),
    ], string='Delivery Method', default='direct', required=False)

    company_id = fields.Many2one(
        'res.company', string='Company', 
        readonly=True, store=True, index=True)

    company_id_report = fields.Many2one(
        'res.company', string='Company', 
        store=True, index=True)

    # Set default picking type id
    def _default_picking_type_id(self):
        picking_type_code = self.env.context.get('restricted_picking_type_code')
        if self.zone:
            if picking_type_code:
                picking_types = self.env['stock.picking.type'].search([
                    ('code', '=', picking_type_code),
                    ('company_id', '=', self.env.company.id),
                ])
                return picking_types[:1].id
    picking_type_code_value = fields.Char(
        string="Picking Type Code", compute='_compute_picking_type_code', store=True
    )

    @api.depends('picking_type_id')
    def _compute_picking_type_code(self):
        for rec in self:
            rec.picking_type_code_value = rec.picking_type_id.code or ''

    # picking_type_id_dup = fields.Many2one( 'stock.picking.type', 'Operation Type12345', required=True, index=True, )
    picking_type_id_duplicate = fields.Many2one( 'stock.picking.type', 'Operation Type', index=True, )
    picking_type_id_duplicate_related = fields.Many2one( 'stock.picking.type', 'Operation Type',  index=True, related="picking_type_id_duplicate" )
    picking_type_id_vismin = fields.Many2one('stock.picking.type', 'Operation Type', index=True)
    picking_type_id_internal = fields.Many2one(
        'stock.picking.type', 'Operation Type',
         index=True,
        default=_default_picking_type_id)
    location_dest_id = fields.Many2one('stock.location', string='Warehouse',domain="[('company_id', '=', company_id), ('usage', '=', 'internal')]" ,  invisible="[(('operation_type', '=', 'incoming'))]", required=True)

    source_location = fields.Many2one('stock.location', string='Source Location',domain="[('company_id', '=', company_id), ('usage', '=', 'internal')]",  invisible="[(('operation_type', '=', 'incoming'))]")
    destination_location = fields.Many2one('stock.location', string='Destination Location',domain="[('company_id', '=', company_id), ('usage', '=', 'internal')]" ,  invisible="[(('operation_type', '=', 'incoming'))]")
    
    state = fields.Selection(selection_add=[
        ('submitted_to_manager', 'Submitted To Manager'),
        ('partially_received', 'Partially Received')
    ])

# ####################################################################### Conversion Rate ##############################################################################
#     exchange_rate = fields.Float(string='USD Exchange Rate', default=58.0)
    
#     conversion_rate = fields.Float(string="Conversion Rate (PHP per USD)")

#     @api.onchange('conversion_rate', 'currency_id')
#     def _onchange_conversion_rate(self):
#         if self.conversion_rate and self.move_ids_without_package:

#             for move in self.move_ids_without_package:
#                 if move.product_id.product_tmpl_id.purchase_price:
#                     # Multiply USD cost by conversion rate
#                     move.unit_cost = move.product_id.product_tmpl_id.purchase_price / self.conversion_rate 
#                     move.currency_id = self.currency_id.id

#     currency_id = fields.Many2one('res.currency', 'Currency', default=lambda self: self.env.company.currency_id.id)
#     currency = fields.Many2one('res.currency', 'Currency', default=lambda self: self.env.company.currency_id.id)
#     isUSD = fields.Boolean(string="isUSD")
#     total_amount_converted = fields.Float(string='Total Amount USD (Converted)')
#     has_returned = fields.Boolean(string="Has returned items")

#     @api.onchange('currency_id', 'total_amount', 'exchange_rate')
#     def _onchange_currency(self):
#         """Convert total_amount if currency selected is USD."""

#         if self.currency_id.name == 'USD':
#              self.isUSD = True
           
#         else:
     
#             self.isUSD = False
# ############################################################################################################################################################

###
####################################################################### Conversion Rate ##############################################################################
    exchange_rate = fields.Float(string='USD Exchange Rate', default=58.0)
    conversion_rate = fields.Float(string="Conversion Rate (PHP per USD)", default=58.0)

    currency_id = fields.Many2one(
        'res.currency',
        'Currency',
        default=lambda self: self.env.company.currency_id.id
    )
    currency = fields.Many2one(
        'res.currency',
        'Currency',
        default=lambda self: self.env.company.currency_id.id
    )

    isUSD = fields.Boolean(string="isUSD")
    isPHP = fields.Boolean(string="isPHP")

    total_amount_converted = fields.Float(string='Total Amount USD (Converted)')
    has_returned = fields.Boolean(string="Has returned items")

    @api.onchange('currency_id', 'total_amount', 'conversion_rate')
    def _onchange_currency_or_rate(self):
        """Update currency flags, propagate currency to moves, recalc unit costs, and set default tax."""
        for picking in self:
            rate = picking.conversion_rate or 0.0
            # 1. Set currency flags
            picking.isUSD = picking.currency_id.name == 'USD'
            picking.isPHP = picking.currency_id.name == 'PHP'

            for move in picking.move_ids_without_package:
                # 2. Propagate currency to move lines
                move.currency_id = picking.currency_id

                # 3. Recalculate unit costs if conversion rate exists
                if rate:
                    if move.isPHP:
                        move.unit_cost_converted = move.unit_cost / rate if move.unit_cost else 0.0
                    elif move.isUSD:
                        move.unit_cost = move.unit_cost_converted * rate if move.unit_cost_converted else 0.0



############################################################################################################################################################



    def _check_company(self):
        # Allow cross-company for stock.picking
        if self.env.context.get('allow_cross_company'):
            return
        return super()._check_company()


    def default_get(self, fields):
        res = super(StockPickingInherit, self).default_get(fields)
           
        user = self.env.user  # Current logged-in user
        group_luzon = self.env.ref('ml_development.group_lncr_mods')
        group_vismin = self.env.ref('ml_development.group_vismin_mods')

        self.company_id =  self.env.company.id
        # self.company_id =  False
        # self.picking_type_id =  False
        # self.remarks = self.picking_type_code

        if self.picking_type_code == 'incoming':
            self.operation = 'receiving'

            if group_luzon in user.groups_id:
                self.isZone = 'lncr'
                picking_type = self.env['stock.picking.type'].search([
                    ('company_id', '=', self.company_id.id),
                    ('code', '=', 'incoming'), 
                    ('warehouse_id.lncr', '=', self.isZone == 'lncr'),
                    # ('warehouse_id.vismin', '=', record.zone in ['visayas', 'mindanao'])
                ], limit=1)
                self.picking_type_id = picking_type.id

            elif  group_vismin in user.groups_id:
                self.operation = 'receiving'
                self.isZone = 'vismin'

                picking_type = self.env['stock.picking.type'].search([
                        ('company_id', '=', self.company_id.id),
                        ('code', '=', 'incoming'), 
                        ('warehouse_id.vismin', '=', self.isZone == 'vismin'),
                        # ('warehouse_id.vismin', '=', record.zone in ['visayas', 'mindanao'])
                    ], limit=1)
                self.picking_type_id = picking_type.id

            else:
                self.isZone = 'all'
                picking_type = self.env['stock.picking.type'].search([
                        ('company_id', '=', self.company_id.id),
                        ('code', '=', 'incoming'), 
                        # ('warehouse_id.lncr', '=', self.isZone == 'lncr'),
                        # ('warehouse_id.vismin', '=', record.zone in ['visayas', 'mindanao'])
                    ], limit=1)
                self.picking_type_id = picking_type.id

        elif  self.picking_type_code == 'internal':
            if group_luzon in user.groups_id:
                self.isZone = 'lncr'
                picking_type = self.env['stock.picking.type'].search([
                    ('company_id', '=', self.company_id.id),
                    ('code', '=', 'internal'), 
                    ('warehouse_id.lncr', '=', self.isZone == 'lncr'),
                    # ('warehouse_id.vismin', '=', record.zone in ['visayas', 'mindanao'])
                ], limit=1)

            elif  group_vismin in user.groups_id:
                self.isZone = 'vismin'
                picking_type = self.env['stock.picking.type'].search([
                        ('company_id', '=', self.company_id.id),
                        ('code', '=', 'internal'), 
                        ('warehouse_id.vismin', '=', self.isZone == 'vismin'),
                        # ('warehouse_id.vismin', '=', record.zone in ['visayas', 'mindanao'])
                    ], limit=1)
                self.picking_type_id = picking_type.id

            else:
                self.isZone = 'all'
                picking_type = self.env['stock.picking.type'].search([
                        ('company_id', '=', self.company_id.id),
                        ('code', '=', 'internal'), 
                        # ('warehouse_id.vismin', '=', self.isZone == 'vismin'),
                        # ('warehouse_id.vismin', '=', record.zone in ['visayas', 'mindanao'])
                    ], limit=1)
                self.picking_type_id = picking_type.id
            self.operation = 'internal'

        else:
            self.operation = 'issuance'

            if group_luzon in user.groups_id:
                self.isZone = 'lncr'
                picking_type = self.env['stock.picking.type'].search([
                    ('company_id', '=', self.company_id.id),
                    ('code', '=', 'outgoing'), 
                    ('warehouse_id.lncr', '=', self.isZone == 'lncr'),
                    # ('warehouse_id.vismin', '=', record.zone in ['visayas', 'mindanao'])
                ], limit=1)

            elif  group_vismin in user.groups_id:
                self.isZone = 'vismin'
                picking_type = self.env['stock.picking.type'].search([
                        ('company_id', '=', self.company_id.id),
                        ('code', '=', 'outgoing'), 
                        ('warehouse_id.vismin', '=', self.isZone == 'vismin'),
                        # ('warehouse_id.vismin', '=', record.zone in ['visayas', 'mindanao'])
                    ], limit=1)
                self.picking_type_id = picking_type.id

            else:
                self.isZone = 'all'
                picking_type = self.env['stock.picking.type'].search([
                        ('company_id', '=', self.company_id.id),
                        ('code', '=', 'outgoing'), 
                        # ('warehouse_id.vismin', '=', self.isZone == 'vismin'),
                        # ('warehouse_id.vismin', '=', record.zone in ['visayas', 'mindanao'])
                    ], limit=1)
                self.picking_type_id = picking_type.id

    #     if group_vismin in user.groups_id:
    #         print("VISMIN")
    #         self.isZone = 'vismin'

    #         picking_type = self.env['stock.picking.type'].search([
    #                     ('company_id', '=', self.company_id.id),
    #                     ('code', '=', 'incoming'), 
    #                     ('warehouse_id.vismin', '=', self.isZone == 'vismin'),
    #                     # ('warehouse_id.vismin', '=', record.zone in ['visayas', 'mindanao'])
    #                 ], limit=1)
                    
    #         _logger.info(f'HELLO VISMIN SIYA: {self.picking_type_id.name}')
    #         self.picking_type_id_vismin = picking_type.id if picking_type else False


    #         # values['isZone'] = 'vismin'
    #     elif group_luzon in user.groups_id:
    #         # values['isZone'] = 'lncr'
    #         print("LNCR") 
    #         self.isZone = 'lncr'
            
    #         picking_type = self.env['stock.picking.type'].search([
    #                     ('company_id', '=', self.company_id.id),
    #                     ('code', '=', 'incoming'), 
    #                     ('warehouse_id.lncr', '=', self.isZone == 'lncr'),
    #                     # ('warehouse_id.vismin', '=', record.zone in ['visayas', 'mindanao'])
    #                 ], limit=1)
                    
    #         _logger.info(f'HELLO LNCR SIYA: {self.picking_type_id.name}')
    #         self.picking_type_id = picking_type.id if picking_type else False
    #     else:
    #         # values['isZone'] = 'all'
    #         print("ALLL")
    #         self.isZone = 'all'

    #         # Check if the picking type is opened from the menu

    #     if self.env.context.get('default_picking_type_id'):
    #         picking_type = self.env['stock.picking.type'].browse(self.env.context['default_picking_type_id'])
    #         _logger.info(f'Picking type: {picking_type.name}')
    #         _logger.info(f'Picking type: {picking_type.name}')
    #         _logger.info(f'Picking type: {picking_type.name}')
    #         _logger.info(f'Picking type: {picking_type.name}')
    #         _logger.info(f'Picking code: {picking_type.code}')

    #         if picking_type.code == 'incoming':
    #             self.update({'operation' : 'receiving'})

    #             # update the picking type id field named picking_type_id_internal to auto select the picking type operation that is incoming 
    #             _logger.info(f'Picking Type ID na Auto field dapat uy', picking_type.name)
    #             _logger.info(f'Picking Type ID na Auto field dapat uy', picking_type.name)
    #             _logger.info(f'Picking Type ID na Auto field dapat uy', picking_type.name)
    #         elif picking_type.code == 'internal':
    #             self.update({'operation' : 'internal'})
    #             # update the picking type id field named picking_type_id_internal to auto select the picking type operation that is internal 

    #             _logger.info(f'Picking Type ID na Auto field dapat uy', picking_type.name)
    #             _logger.info(f'Picking Type ID na Auto field dapat uy', picking_type.name)
    #             _logger.info(f'Picking Type ID na Auto field dapat uy', picking_type.name)
    #         else: 
    #             self.update({'operation' : 'issuance'})
    #             # update the picking type id field named picking_type_id_internal to auto select the picking type operation that is outgoing 
    #         self.write({'picking_type_id': picking_type.id})
    #         self.write({'picking_type_id_internal': picking_type.id})
    #     else:
    #         _logger.info(f'No stock picking type detected')
        return res

    @api.onchange('isZone')
    def _onchange_isZone(self):
        """Dynamically update the domain for branch selection based on isZone value."""
        if self.isZone:
            if self.isZone == 'lncr':
                return {'domain': {'branch': [('zone', 'in', ['luzon', 'ncr'])]}}
            elif self.isZone == 'vismin':
                return {'domain': {'branch': [('zone', 'in', ['visayas', 'mindanao'])]}}
        else:
            return {'domain': {'branch': []}}  # No filter if isZone is empty

    @api.onchange('remarks')
    def check_address(self):
        print(self.partner_id.street,  "Partner ID STREET")
        
    def action_confirm(self):
        res = super(StockPickingInherit, self).action_confirm()
        self.filtered(lambda p: p.state == 'assigned').write({'state': 'partially_received'})
        return res

    def _fix_attachment_ownership(self):
        for record in self:
            record.attachment.write({'res_model': record._name, 'res_id': record.id})
        return self

    def action_assign(self):
        res = super(StockPickingInherit, self).action_assign()
        for picking in self:
            if picking.state == 'assigned' and any(move.state != 'done' for move in picking.move_ids_without_package):
                picking.state = 'partially_received'  #  Keep as "Partially Received" instead of "Ready"
                print("nangyayare action_assign")
        return res

    # @api.model
    # def default_get(self, fields_list):
    #     defaults = super(StockPickingInherit, self).default_get(fields_list)
    #     # Get the Incoming picking type for the logged-in user's company
    #     picking_type = self.env['stock.picking.type'].search([
    #         ('code', '=', 'incoming'),
    #         ('company_id', '=', self.env.company.id)
    #     ], limit=1)

    #     if picking_type:
    #         defaults['picking_type_id'] = picking_type.id
    #         defaults['state'] = 'assigned'

        user = self.env.user  # Current logged-in user
        group_luzon = self.env.ref('ml_development.group_lncr_mods')
        group_vismin = self.env.ref('ml_development.group_vismin_mods')


        if group_vismin in user.groups_id:
            print("VISMIN")
            self.isZone = 'vismin'
            # values['isZone'] = 'vismin'
        elif group_luzon in user.groups_id:
            # values['isZone'] = 'lncr'
            print("LNCR") 
            self.isZone = 'lncr'
        else:
            # values['isZone'] = 'all'
            print("ALLL")
            self.isZone = 'all'

        def get_operation_type(self):
            for picking in self:
                operation_type = picking.picking_type_id.name
                picking_type_code = picking.picking_type_id.code
                print(f"Picking ID: {picking.id}, Operation Type: {operation_type}, Code: {picking_type_code}")

                raise ValidationError(operation_type)
            # You can add additional logic here based on the operation type

        return defaults

    @api.onchange('company_id')
    def _change_picking_type(self):
        if self.company_id:
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'incoming'),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
            self.picking_type_id = picking_type

            
    # def _filter_picking_type(self):
    #     """ Filters picking_type_id based on warehouse_id and isZone field """
    #     if self.company_id:
    #         domain = [('warehouse_id.company_id', '=', self.company_id.id)]

    #         # Check the value of isZone and apply corresponding filter
    #         if self.isZone == 'lncr':  
    #             domain.append(('warehouse_id.lncr', '=', True))
    #         elif self.isZone == 'vismin':
    #             domain.append(('warehouse_id.vismin', '=', True))

    #         return {'domain': {'picking_type_id': domain}}
    @api.onchange('move_ids_without_package')
    def _onchange_move_ids_without_package(self):
        """ Auto-update unit_cost and check for duplicates in UI. """
        total_amount = 0.0
        seen_products = set()

        for move in self.move_ids_without_package:
            if not move.product_id:
                continue
            if move.product_id.id in seen_products:
                raise UserError(_(
                    f"Duplicate item detected: '{move.product_id.display_name}' is already listed."
                ))
            seen_products.add(move.product_id.id)

            # move.unit_cost = move.product_id.product_tmpl_id.standard_price or 0.0

                # Validation: prevent over-adding items if linked to PO

        if self.origin:
            purchase_order = self.env['purchase.order'].search([('name', '=', self.origin)], limit=1)
            if purchase_order:
                po_line_count = len(purchase_order.order_line)
                picking_line_count = len(self.move_ids_without_package)

                _logger.info(f'PO Line Count: {po_line_count}')
                _logger.info(f'Picking Line Count: {picking_line_count}')

                if picking_line_count > po_line_count:
                    raise UserError(_(
                        f"You cannot add more than {po_line_count} items from the original Purchase Order '{purchase_order.name}'."
                    ))


        # if not self.origin:
        #     self.total_amount = total_amount



            # if self.origin:
            #     # Search in purchase order where name is == origin, limit=1
            #     purchase_order = self.env['purchase.order'].search([('name', '=', self.origin)], limit=1)

            #     _logger.info(f"PRICE UNIT  {purchase_order.order_line.filtered(lambda l: l.product_id == move.product_id).price_unit}")
            #     unit_cost = purchase_order.order_line.filtered(lambda l: l.product_id == move.product_id).price_unit
            #     move.unit_cost = unit_cost 
            # else:
            #     # Use the standard price from the product template
            #     unit_cost = move.product_id.product_tmpl_id.standard_price

            # # Calculate the quantity
            # quantity = move.quantity if move.quantity else move.product_uom_qty
            
            # # Calculate the untaxed amount
            # untaxed_amount = quantity * unit_cost
            # move.untaxed_amount = untaxed_amount
            # # Determine the tax and taxed amount
            # if self.partner_id.tax_type == 'vatable':
            #     move.tax_id = 'vat_12'
            #     move.taxed_amount = untaxed_amount * 0.12
            # else:
            #     move.tax_id = 'vat_0'
            #     move.taxed_amount = 0.0

            # # Calculate the total amount
            # move.total_amount = untaxed_amount + move.taxed_amount
            # total_amount += move.total_amount

        # Update the total amount on the stock picking model
        # self.total_amount = total_amount

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """ Prevent adding new stock moves if the stock.picking form has an origin """
        if self.picking_id and self.picking_id.origin:
            raise UserError(_(
                "You cannot add new product lines because this Receiving Receipt Form was generated from a Purchase Order."
            ))

    @api.onchange('partner_id')
    def _onchange_vender(self):
        """ Autofill the address from the vendor configuration """
        if self.partner_id:
            address_parts = filter(None, [self.partner_id.street, self.partner_id.street2, self.partner_id.city])
            address = " ".join(address_parts)
            self.update({ 'address' : address })

    @api.onchange('picking_type_id_duplicate')  
    def _onchange_picking_type_id_duplicate(self):
        for record in self:
            if record.picking_type_id_duplicate:
                record.location_dest_id = record.picking_type_id_duplicate.default_location_dest_id.id
            else:
                record.location_dest_id = False  # Clear field if no picking type selected
                
   
    # Modified validate button for 
    def button_validate(self):
        """
        - Auto-fill received_qty with remaining quantity if empty
        - Update quantity and prevent over-receiving
        - Mark done only when fully received
        - Update On-Hand Quantity
        - Support partial receiving
        """
        if self.picking_type_id.code == 'incoming':

            with self.env.cr.savepoint():
                self = self.with_context(allow_cross_company=True)

            if not self.move_ids_without_package:
                raise UserError("Cannot proceed: No products found in the incoming item list.")

            self.write({'state': 'partially_received'})

            user = self.env.user
            current_user = user.name
            is_zone = 'lncr' if self.env.ref('ml_development.group_lncr_mods') in user.groups_id else 'vismin'
            purchase_order = self.env['purchase.order'].search([('name', '=', self.origin)], limit=1)

            total_received_amount = 0.0
            total_ordered_amount = 0.0
            all_fully_received = True

            has_valid_received = False

            if any(
                move.product_uom_qty == 0 and move.unit_cost == 0
                for move in self.move_ids_without_package
                if move.state not in ['done', 'cancel']
            ):
                raise ValidationError("There is at least one line item with zero ordered quantity, and unit cost. Please enter valid values.")
            
            for move in self.move_ids_without_package:
                if move.state in ['done', 'cancel']:
                    continue

                move.prev_qty = move.received_qty

                if move.quantity == move.product_uom_qty:
                    move.quantity = 0.0

                remaining_qty = move.product_uom_qty - move.quantity

                if move.tax_id == 'vat_12':
                    base_amount = float_round(move.unit_cost * 1.12, precision_digits=2) 
                    taxed_amount = base_amount * move.product_uom_qty
    
                    price_total = float_round(taxed_amount, precision_digits=2)
                    
                    total_untaxed_amount = float_round(move.unit_cost * move.product_uom_qty, precision_digits=2)
                    total = price_total
                    _logger.info(f"Total: {total:.2f}")
                    move.total_amount_report  = total
                    


                elif move.tax_id == 'vat_0':
                    total_untaxed_amount = float_round(move.unit_cost * move.product_uom_qty, precision_digits=2)
                    total = total_untaxed_amount
                    move.total_amount_report  = total
                    
                    
                # amount_report = total

                # Raise error if received_qty exceeds remaining_qty
                if move.received_qty > remaining_qty:
                    self.write({'state': 'draft'})
                    raise UserError(
                        f"Over-receiving not allowed. '{move.product_id.display_name}' exceeds the remaining quantity of {int(remaining_qty)}."
                    )
                if move.received_qty == 0.0:
                    continue  # Skip if received_qty is zero

                has_valid_received = True

                move.quantity += move.received_qty

                # Update zone on move lines
                move.move_line_ids.write({'zone': is_zone})

                # Update stock.quant
                quant = self.env['stock.quant'].search([
                    ('product_id', '=', move.product_id.id),
                    ('location_id', '=', move.location_dest_id.id),
                ], limit=1)
                if quant:
                    quant.quantity += move.received_qty
                else:
                    self.env['stock.quant'].create({
                        'product_id': move.product_id.id,
                        'location_id': move.location_dest_id.id,
                        'quantity': move.received_qty,
                    })

                # Update remaining quantity in move lines
                for ml in move.move_line_ids:
                    new_remaining = (ml.quantity - ml.qty_done) - move.received_qty
                    if new_remaining > 0:
                        ml.remaining_quantity = new_remaining
               
                self.message_post(
                    body=(
                        f"<p style='color: green;'><strong>Received the item:</strong> {move.product_id.display_name}</p>"
                        f"<p><strong>Received by:</strong> {current_user}</p>"
                        f"<p><strong>Date:</strong> {datetime.now().strftime('%m/%d/%Y')}</p>"
                        f"<p><strong>Received Quantity:</strong> {int(move.received_qty)}</p>"
                        f"<p><strong>Remaining to be Received:</strong> {int(remaining_qty - move.received_qty)}</p>"
                        f"{f'<p><strong>Remarks:</strong> {self.remarks}</p>' if self.remarks else ''}"),
                    message_type='comment',
                    subtype_xmlid='mail.mt_log',
                    body_is_html=True
                )

                # tax_multiplier = 1.12 if move.picking_id.partner_id.tax_type == 'vatable' else 1.0
                # move.total_amount = move.quantity * move.unit_cost * tax_multiplier

                # total_ordered_amount += move.unit_cost * move.product_uom_qty * tax_multiplier
                # total_received_amount += move.unit_cost * move.quantity * tax_multiplier

                if move.quantity >= move.product_uom_qty:
                    move.state = 'done'
                    move.received_qty = move.product_uom_qty

                    self.env['res.approvers'].search([
                        ('stock_picking_id', '=', self.id)
                    ]).unlink()
                else:
                    move.received_qty = max(0, move.product_uom_qty - move.quantity)
                    all_fully_received = False
                    if purchase_order:
                        purchase_order.remarks = "Partially Received"
                    if self.state == 'assigned':
                        self.state = 'partially_received'
                        self.write({'state': 'partially_received'})

            if not has_valid_received:
                raise UserError("All received quantities are zero. Please enter at least one valid received quantity to proceed.")

            if purchase_order:
                purchase_order.received_amount = total_received_amount

            if all_fully_received and self.partner_id.email:
                move_details = ""
                for move in self.move_ids_without_package:
                    tax_multiplier = 0.12 if move.tax_id == 'vat_12' else 1.0
                    total_amount = move.quantity * move.unit_cost * tax_multiplier
                    move_details += f"""
                        <tr>
                            <td>{move.product_id.display_name}</td>
                            <td>{int(move.product_uom_qty)}</td>
                            <td>{int(move.quantity)}</td>
                            <td>{int(move.unit_cost):,.2f}</td>
                        </tr>
                    """

                email_body = f"""
                    <p>Hello {self.partner_id.name},</p>
                    <p>The order <strong>{self.name}</strong> has been fully received.</p>
                  
                    <p>Thank you!</p>
                """
                self.action_generate_pdf_and_post_message_done()

                attachment = self.env['ir.attachment'].search([
                    ('res_model', '=', 'stock.picking'),
                    ('res_id', '=', self.id),
                    ('name', 'ilike', f'Receiving_Receipt_{self.name}.pdf'),
                ], order='create_date desc', limit=1)

                mail_values = {
                    'subject': f"Receiving Receipt - {self.name}",
                    'body_html': email_body,
                    'email_to': self.partner_id.email,
                    'email_from': self.env.user.email or 'noreply@mlhuillier.com',
                    'attachment_ids': [(4, attachment.id)] if attachment else []
                }
                self.env['mail.mail'].create(mail_values).send()
            else:
                self.write({'state': 'partially_received'})

                # move_details = ""
                # for move in self.move_ids_without_package:
                #     tax_multiplier = 0.12 if move.tax_id == 'vat_12' else 1.0
                #     total_amount = move.quantity * move.unit_cost * tax_multiplier
                    # move_details += f"""
                    #     <tr>
                    #         <td>{move.product_id.display_name}</td>
                    #         <td>{int(move.product_uom_qty)}</td>
                    #         <td>{int(move.quantity)}</td>
                    #         <td>₱{total_amount:,.2f}</td>
                    #     </tr>
                    # """

            
            #  Loop through each move and compare quantity vs ordered qty
            all_lines_fully_received = True 
         
            for move in self.move_ids_without_package:

                _logger.info("=== START MOVE DEBUG 1 ===")
                """Compute total tax, untaxed, and total amount for the entire picking."""
                received_total = 0.0
                expected_total = 0.0
                _logger.info("=== START MOVE DEBUG 2 ===")

                _logger.info(f"Product: {move.product_id.name}")
                _logger.info(f"Quantity Received: {move.quantity}")
                _logger.info(f"Unit Cost (VAT-exclusive): {move.unit_cost}")
                _logger.info(f"Ordered Quantity: {move.product_uom_qty}")
                _logger.info(f"Tax ID: {move.tax_id}")

                # base_amount = float_round(move.unit_cost * move.quantity, precision_digits=2)
                if move.tax_id == 'vat_12':
                    # raise UserError("VAT 12",base_amount)
                    _logger.info("Applied VAT: 12%")
                    
                    # base_amount = float_round(move.unit_cost * move.quantity, precision_digits=2)

                    base_amount = float_round(move.unit_cost * 1.12, precision_digits=2) 
                    
                    _logger.info(f"Base Amount: {base_amount:.2f}")

                    taxed_amount = base_amount * move.quantity
                    _logger.info(f"Tax Amount Total: {taxed_amount:.2f}")

                    price_total = float_round(taxed_amount, precision_digits=2)

                    total_untaxed_amount = float_round(move.unit_cost * move.quantity, precision_digits=2)
                    _logger.info(f"Untaxed Total: {total_untaxed_amount:.2f}")

                    total = price_total
                    _logger.info(f"Total: {total:.2f}")

                    move.untaxed_amount = total_untaxed_amount
                    move.taxed_amount  = total - total_untaxed_amount
                    move.prev_amount_report = total - total_untaxed_amount
                    move.total_amount = total
                    
                elif move.tax_id == 'vat_0':
                    # raise UserError("VAT 0 ",base_amount)
                    base_amount = float_round(move.unit_cost * move.quantity, precision_digits=2)
                    # tax_amount = 0.0
                    # total = base_amount

                    _logger.info("VAT 0% or Exempt")
                    _logger.info(f"Base Amount: {base_amount:.2f}")

                    price_total = float_round(move.unit_cost * move.quantity, precision_digits=2)
                    total_untaxed_amount = float_round(move.unit_cost * move.quantity, precision_digits=2)

                    move.untaxed_amount = 0.00
                    move.total_amount = price_total
                

                if float_compare(move.quantity, move.product_uom_qty, precision_rounding=move.product_uom.rounding) != 0:
                    all_lines_fully_received = False
                    # break

                # if move.state in ['done', 'cancel']:
                #     continue

            # Calculate the total amount 
            # Calculate the received amount 
            # self.total_amount += move.total_amount Sum 
            self.state = 'done' if all_lines_fully_received else 'partially_received'

            self.received_amount += move.total_amount
            self.action_generate_pdf_and_post_message()
            # self.inventory_receiving_accounting()
            self.inventory_receiving_accounting()
            # self.inventory_valuation()
            # if self.origin:
            #     self.action_create_vendor_bill_and_payment()
            # ← Make sure this method is defined

            for move in self.move_ids_without_package:
                # Reset prev_qty if fully received
                if move.quantity >= move.product_uom_qty:
                    move.prev_qty = 0.0

                move.received_qty = 0.0

            # Updated received amount 
            self.received_amount = sum(self.move_ids_without_package.mapped('total_amount'))

            # If linked to a Purchase Order, also update its received_amount
            if self.origin:
                po = self.env['purchase.order'].search([('name', '=', self.origin)], limit=1)
                if po:
                    po.received_amount = self.received_amount

            
            
            self.write({'remarks': False})


        elif self.picking_type_id.code == 'outgoing':

            for move in self.move_ids_without_package:
                if move.quantity <= 0:
                    raise UserError(f"{move.product_id.display_name}: Please enter quantity to deliver.")

                # Set qty_done for all move lines
                for move_line in move.move_line_ids:
                    move_line.qty_done = move.quantity
                    move_line.write({'state': 'done'})

                # Adjust the StockQuant manually
                quant = self.env['stock.quant'].search([
                    ('product_id', '=', move.product_id.id),
                    ('location_id', '=', self.location_id.id),
                    ('company_id', '=', self.company_id.id),
                # ], limit=1)
                ], limit=1)


                if quant:
                    _logger.info(f"[{self.name}] Found quant for {move.product_id.display_name}: "
                                f"Quantity={quant.quantity}, Reserved={quant.reserved_quantity}")

                    new_reserved_qty = max(quant.reserved_quantity - move.quantity, 0)
                    new_actual_qty = max(quant.quantity - move.quantity, 0)
                    new_available_qty = max(new_actual_qty - new_reserved_qty, 0)

                    # quant.sudo().write({
                    #     'reserved_quantity': new_reserved_qty,
                    #     'quantity': new_actual_qty,
                    #     'available_quantity': new_available_qty,
                    # })

                    _logger.info(f"[{self.name}] Updated Quant for {move.product_id.display_name}: "
                                f"Quantity={new_actual_qty}, Reserved={new_reserved_qty}, Available={new_available_qty}")
                else:
                    raise UserError(f"No available stock for {move.product_id.display_name} in location {self.location_id.display_name}.")

            # Mark the delivery as done
            self.write({'state': 'done'})

            # Generate journal entry for the outgoing transaction
       

            # self._action_done()  # standard outgoing delivery validation
            # self.action_confirm()
            # self.action_assign()
            # self.button_validate()


            # self.inventory_valuation()
            # self.inventory_receiving_accounting()

    #         elif self.picking_type_id.code == 'internal':  

                            
    #             approver_model = self.env['res.approvers']

    #             if not self.move_ids_without_package:
    #                 raise UserError("No items to transfer.")

    #             if not self.source_location:
    #                 raise UserError("Please select Source Location for Item")

    #             if not self.destination_location:
    #                 raise UserError("Please select Destination Location for Item")

    #             if self.source_location.id == self.destination_location.id:
    #                 raise UserError(_("Source and Destination locations cannot be the same."))

    #             StockQuant = self.env['stock.quant']
    #             for move in self.move_ids_without_package:
                    
    #                 move.prev_qty = move.received_qty
    #                 product = move.product_id

    #                 # Check stock
    #                 available_qty = StockQuant._get_available_quantity(product, self.source_location)
    #                 if available_qty <= 0:
    #                     raise UserError(_("Product '%s' has no stock in source location '%s'.") %
    #                                     (product.display_name, self.source_location.display_name))
    #                 if available_qty < move.quantity:
    #                     raise UserError(_("Not enough '%s' in source location '%s'. Available: %.2f, Required: %.2f") %
    #                                     (product.display_name, self.source_location.display_name,
    #                                     available_qty, move.quantity))

    #                 total_qty_done = 0.0
    #                 for line in move.move_line_ids:
    #                     if line.qty_done <= 0:
    #                         line.qty_done = move.product_uom_qty

    #                     StockQuant._update_available_quantity(
    #                         product, self.source_location, -line.qty_done, lot_id=line.lot_id
    #                     )
    #                     StockQuant._update_available_quantity(
    #                         product, self.destination_location, line.qty_done, lot_id=line.lot_id
    #                     )
    #                     total_qty_done += line.qty_done

    #                 # Set move details BEFORE marking as done
    #                 move.quantity = total_qty_done
    #                 move.location_id = self.source_location.id
    #                 move.location_dest_id = self.destination_location.id
    #                 move.state = 'done'

    #             if any(move.quantity < move.product_uom_qty for move in self.move_ids_without_package):
    #                 self.write({'state': 'partially_received'})
    #             # Set picking fields BEFORE marking as done
    #             self.location_id = self.source_location.id
    #             self.location_dest_id = self.destination_location.id
    #             self.state = 'done'

    #             # Delete approvers
    #             approvers_to_delete = approver_model.search([('name', '=', self.name)], limit=1)
    #             if approvers_to_delete:
    #                 approvers_to_delete.unlink()


    # Creating Journal Entries for the Inventory Valuation
    def inventory_valuation(self):
        for picking in self:
            valuation_moves = []
            for move in picking.move_ids_without_package:
                valuation_amount = move.unit_cost * move.prev_qty
                
                journal_entry = self.env['account.move'].create({
                    'journal_id': self.env['account.journal'].search([
                        ('type', '=', 'general'),
                        ('name', '=', 'Inventory Valuation')
                    ], limit=1).id,
                    'date': fields.Date.today(),
                    'ref': f"Stock Valuation - {picking.name}",
                    'picking_id': picking.id,
                    'line_ids': [
                        (0, 0, {
                            'account_id': move.product_id.categ_id.property_stock_valuation_account_id.id,
                            'debit': valuation_amount,
                            'credit': 0,
                            'name': move.product_id.name,
                        }),
                        (0, 0, {
                            'account_id': move.product_id.categ_id.property_stock_account_output_categ_id.id,
                            'debit': 0,
                            'credit': valuation_amount,
                            'name': move.product_id.name,
                        }),
                    ]
                })

                valuation_moves.append(journal_entry.id)

                # Create Stock Valuation Layer
                self.env['stock.valuation.layer'].create({
                    'product_id': move.product_id.id,
                    'value': valuation_amount,
                    'unit_cost': move.unit_cost,
                    'quantity': move.prev_qty,
                    'description': f'Stock Valuation for - {move.product_id.name}',
                    'stock_move_id': move.id,
                    'company_id': self.env.company.id,
                    'account_move_id': journal_entry.id
                })

                # journal_entry.action_post()

            # Link all valuation moves to picking
            picking.write({'valuation_move_ids': [(6, 0, valuation_moves)]})
        # return res

    # Creating Journal Entries for the Expense Account Recording
    def inventory_expense_recording(self):
        for picking in self:
            valuation_moves = []
            for move in picking.move_ids_without_package:
                valuation_amount = move.product_id.standard_price * move.quantity
                move.picking_id.received_amount = valuation_amount
                # Create the journal entry for valuation 
                journal_entry = self.env['account.move'].create({
                    # 'journal_id': self.env['account.journal'].search([('type', '=', 'general')], limit=1).id,
                    'journal_id': self.env['account.journal'].search([('type', '=', 'general'),('name', '=', 'Inventory Valuation')], limit=1).id,
                    'date': fields.Date.today(),
                    'ref': f"Stock Valuation - {picking.name}",
                    'picking_id': picking.id,  # LINK SA STOCK PICKING
                    'line_ids': [
                        (0, 0, {
                            'account_id': move.product_id.categ_id.property_stock_valuation_account_id.id,
                            'debit': valuation_amount,
                            'credit': 0,
                            'name': move.product_id.name,
                        }),
                        (0, 0, {
                            'account_id': move.product_id.categ_id.property_stock_account_output_categ_id.id,
                            'debit': 0,
                            'credit': valuation_amount,
                            'name': move.product_id.name,
                        }),
                    ]
                })
            
            valuation_moves.append(journal_entry.id)
            
            #  Update One2many Field
            picking.write({'valuation_move_ids': [(6, 0, valuation_moves)]})
            for item in valuation_moves:
                print(item, "Mga laman ni valuation")
            journal_entry.action_post()


    # Create journal for returned items 
    def generate_return_journal_entry(self):
        for picking in self:
            _logger.info(f"Processing return for picking: {picking.name}")

            # if picking.picking_type_id.code != 'incoming' or picking.location_dest_id.usage != 'supplier':
            #     _logger.info("Skipping picking because it's not a supplier return.")
            #     continue

            journal = self.env['account.journal'].search([
                ('type', '=', 'general'),
                ('name', '=', 'Supplier Returns')
            ], limit=1)

            if not journal:
                _logger.error("No 'Receiving Operations' journal found.")
                raise UserError("Please set up a 'Receiving Operations' journal.")

            _logger.info(f"Journal found: {journal.name}")

            debit_account = self.env['account.account'].search([
                ('name', '=', 'Accounts Payable')
            ], limit=1)

            credit_account = self.env['account.account'].search([
                ('name', '=', 'Inventory')
            ], limit=1)

            if not debit_account or not credit_account:
                _logger.error("Required accounts not found: Accounts Payable or Inventory.")
                raise UserError("Make sure 'Accounts Payable' and 'Inventory' accounts exist.")

            _logger.info(f"Using Debit Account: {debit_account.name}, Credit Account: {credit_account.name}")

            journal_lines = []
            total_return_amount = 0.0

            for move in picking.move_ids_without_package:
                return_qty = move.prev_qty
                unit_cost = move.unit_cost
                returned_amount = return_qty * unit_cost

                _logger.info(f"Processing move: {move.product_id.display_name} - Qty: {return_qty}, Unit Cost: {unit_cost}")

                if returned_amount <= 0:
                    _logger.warning(f"Skipped zero or negative return amount for: {move.product_id.display_name}")
                    continue

                total_return_amount += returned_amount

                journal_lines += [
                    (0, 0, {
                        'account_id': debit_account.id,
                        'debit': returned_amount,
                        'credit': 0.0,
                        'name': f"Return - {move.product_id.display_name}"
                    }),
                    (0, 0, {
                        'account_id': credit_account.id,
                        'debit': 0.0,
                        'credit': returned_amount,
                        'name': f"Return - {move.product_id.display_name}"
                    }),
                ]

            if journal_lines:
                _logger.info(f"Creating journal entry for total amount: {total_return_amount}")
                journal_entry = self.env['account.move'].create({
                    'journal_id': journal.id,
                    'date': fields.Date.today(),
                    'ref': f"Return for {picking.name}",
                    'line_ids': journal_lines,
                })

                # journal_entry.action_post()  #  Post the entry to generate a proper name/sequence
                _logger.info(f"Journal entry posted: {journal_entry.name}")
                # picking.message_post(body=f"Journal Entry for return posted: {journal_entry.name}")

                # Post message on the source incoming picking
                if picking.origin:
                    source_picking = self.env['stock.picking'].search([('name', '=', picking.origin)], limit=1)
                    if source_picking:
                        source_picking.message_post(
                            body=f"Return processed with Journal Entry: <b>{journal_entry.name}</b><br/>Return Ref: {picking.name}",
                            subtype_xmlid='mail.mt_comment',
                            body_is_html=True
                        )
                        _logger.info(f"Chatter message posted to source picking: {source_picking.name}")
                    else:
                        _logger.warning(f"Source picking not found for origin: {picking.origin}")
                else:
                    _logger.warning("No origin set on return picking.")

                # journal_entry.action_post()
                # _logger.info(f"Journal entry posted: {journal_entry.name}")
                # picking.message_post(body=f"Journal Entry for return posted: <b>{journal_entry.name}</b>")
            else:
                _logger.warning("No journal lines generated; nothing posted.")
        # return res

    def action_create_vendor_bill_and_payment(self):
        for picking in self:
            if picking.picking_type_id.code != 'incoming':
                raise UserError("This action is only allowed for Incoming Shipments.")

            # if not picking.origin:
            #     raise UserError("No source document found (Origin is empty).")

            # Hanapin ang Vendor Bill gamit ang ORIGIN ng PO
            bill = self.env['account.move'].search([
                ('move_type', '=', 'in_invoice'),
                ('ref', '=', picking.origin),
                # ('state', '=', 'posted')
            ], limit=1)

            if not bill:
                raise UserError("No posted Vendor Bill found for %s" % picking.origin)

            if bill.payment_state == 'paid':
                raise UserError("The Vendor Bill for %s is already fully paid." % picking.origin)
            
            if bill:
                    for move in picking.move_ids_without_package:
                        # # Compute per-line amount
                        # if move.tax_id == 'vat_12':
                        #     # then yung taxable ang kunin na 

                        if move.tax_id == 'vat_12':

                            # raise UserError("VAT 12",base_amount)
                            _logger.info("Applied VAT: 12%")
                            
                            # base_amount = float_round(move.unit_cost * move.quantity, precision_digits=2)

                            base_amount = float_round(move.unit_cost * 1.12, precision_digits=2) 
                            
                            _logger.info(f"Base Amount: {base_amount:.2f}")

                            taxed_amount = base_amount * move.prev_qty
                            _logger.info(f"Tax Amount Total: {taxed_amount:.2f}")

                            price_total = float_round(taxed_amount, precision_digits=2)

                            total_untaxed_amount = float_round(move.unit_cost * move.prev_qty, precision_digits=2)
                            _logger.info(f"Untaxed Total: {total_untaxed_amount:.2f}")

                            total = price_total
                            _logger.info(f"Total: {total:.2f}")

                            # move.untaxed_amount = total_untaxed_amount
                            # move.taxed_amount  = total - total_untaxed_amount
                            # move.total_amount = total
                            line_amount = total 
                            
                        elif move.tax_id == 'vat_0':
                            # raise UserError("VAT 0 ",base_amount)
                            base_amount = float_round(move.unit_cost * move.prev_qty, precision_digits=2)
                            # tax_amount = 0.0
                            # total = base_amount

                            _logger.info("VAT 0% or Exempt")
                            _logger.info(f"Base Amount: {base_amount:.2f}")

                            price_total = float_round(move.unit_cost * move.prev_qty, precision_digits=2)
                            total_untaxed_amount = float_round(move.unit_cost * move.prev_qty, precision_digits=2)

                            # move.untaxed_amount = 0.00
                            # move.total_amount = price_total
                            line_amount = price_total

                    if line_amount > 0:
                        payment_register = self.env['account.payment.register'].with_context(
                            active_model='account.move',
                            active_ids=bill.ids,
                        ).create({
                            'payment_date': fields.Date.context_today(self),
                            'journal_id': self.env['account.journal'].search([('type', '=', 'bank')], limit=1).id,
                            'amount': line_amount,
                        })

                        # Create & post the payment
                        payment_register.action_create_payments()
                            # Post a silent chatter message per line
                        picking.with_context(
                            mail_notify_force_send=False,
                            mail_auto_subscribe_no_notify=True
                        ).message_post(
                            body=(
                                f" A <b>Payment</b> of <b>{line_amount:.2f}</b> "
                                f"was registered for the Vendor Bill with PO number <b>{self.origin}</b> "
                                f"for product <b>{move.product_id.name}</b>."
                            ),
                            subtype_xmlid="mail.mt_comment",
                            body_is_html=True,
                        )

                # message post naman here how much is payment registered
                #   picking.with_context(
            #     mail_notify_force_send=False,
            #     mail_auto_subscribe_no_notify=True
            # ).message_post( dapat ganito sir never mag send ng email

            # # Gumawa ng Payment
            # payment = self.env['account.payment'].create({
            #     'partner_id': bill.partner_id.id,
            #     'amount': self.received_amount,
            #     'currency_id': bill.currency_id.id,
            #     'payment_type': 'outbound',
            #     'partner_type': 'supplier',
            #     'journal_id': self.env['account.journal'].search([('type', '=', 'bank')], limit=1).id,
            #     'date': fields.Date.context_today(self),
            # })
            # message post naman here how much is payment registered for whom 

            # Post payment
            # payment.action_post()

            # # Reconcile payment sa payable line ng Bill
            # payable_line = bill.line_ids.filtered(lambda l: l.account_id.internal_type == 'payable')
            # (payment.line_ids + payable_line).reconcile()

            # Mag-log sa chatter ng picking

            # Check if 
            

        return True

    # def action_assign(self):
    #     """ Check availability of picking moves.
    #     This has the effect of changing the state and reserve quants on available moves, and may
    #     also impact the state of the picking as it is computed based on move's states.
    #     @return: True
    #     """
    #     self.mapped('package_level_ids').filtered(lambda pl: pl.state == 'draft' and not pl.move_ids)._generate_moves()

    #     # Include 'waiting' state, not just 'draft'
    #     self.filtered(lambda picking: picking.state in ('draft', 'waiting')).action_confirm()

    #     moves = self.move_ids.filtered(lambda move: move.state not in ('draft', 'cancel', 'done')).sorted(
    #         key=lambda move: (-int(move.priority), not bool(move.date_deadline), move.date_deadline, move.date, move.id)
    #     )  

    #     if moves: 
    #         print("HELLO FROM ACTION ASSIGN MAY MOVESS")

    #     if not moves:
    #         raise UserError(('Nothing to check the availability for.'))

    #     moves._action_assign()
    #     return True
    
       
    # def inventory_receiving_accounting(self):
    #     _logger.info(' START: INVENTORY RECEIVING ACCOUNTING PROCESS ')
    #     for picking in self:
    #         _logger.info(f' Processing Picking: {picking.name} | Company Report: {picking.company_id_report.name} (ID: {picking.company_id_report.id})')

    #         for move in picking.move_ids_without_package:
    #             _logger.info(f' Processing Move ID: {move.id} | Product: {move.product_id.display_name} | Prev Qty: {move.prev_qty}')

    #             received_amount = move.product_id.product_tmpl_id.purchase_price * move.prev_qty
    #             _logger.info(f' Computed Received Amount: {received_amount}')

    #             # Extract GL descriptions from the product
    #             credit_gl_description = move.product_id.credit_gl_description
    #             debit_gl_description = move.product_id.debit_gl_description
    #             _logger.info(f' Debit GL Desc: {debit_gl_description} | Credit GL Desc: {credit_gl_description}')

    #             # Search for account IDs in the account.account model
    #             debit_account = self.env['account.account'].search(
    #                 [
    #                     ('name', '=', debit_gl_description),
    #                     ('company_ids', 'in', [self.company_id_report.id])
    #                 ],
    #                 limit=1
    #             )

    #             credit_account = self.env['account.account'].search(
    #                 [
    #                     ('name', '=', 'Accounts Payable'),
    #                     ('company_ids', 'in', [self.company_id_report.id])
    #                 ],
    #                 limit=1
    #             )
    #             if debit_account:
    #                 company_list = [f"{c.id} - {c.name}" for c in debit_account.company_ids]
    #                 _logger.info(
    #                     f' Debit Account Found: {debit_account.name} '
    #                     f'(ID: {debit_account.id}) | Companies: {company_list}'
    #                 )
    #             else:
    #                 _logger.warning(f' Debit Account NOT FOUND for description: {debit_gl_description}')

    #             if credit_account:
    #                 company_list = [f"{c.id} - {c.name}" for c in credit_account.company_ids]
    #                 _logger.info(
    #                     f'Credit Account Found: {credit_account.name} '
    #                     f'(ID: {credit_account.id}) | Companies: {company_list}'
    #                 )
    #             else:
    #                 _logger.warning(' Credit Account NOT FOUND for Accounts Payable')
                                    
    #             if not debit_account:
    #                 _logger.warning(f' Debit Account NOT FOUND for description: {debit_gl_description}')
    #             if not credit_account:
    #                 _logger.warning(f' Credit Account NOT FOUND for Accounts Payable')

    #             debit_account_id = debit_account.id if debit_account else False
    #             credit_account_id = credit_account.id if credit_account else False

    #             _logger.info(f' Debit Account: {debit_account.name if debit_account else "N/A"} (ID: {debit_account_id})')
    #             _logger.info(f' Credit Account: {credit_account.name if credit_account else "N/A"} (ID: {credit_account_id})')
                
    #             self.env.cr.execute("""
    #                 INSERT INTO account_move (
    #                     create_date, write_date, create_uid, write_uid,
    #                     journal_id, date, ref, picking_id, currency_id,
    #                     company_id, move_type, state, auto_post, amount_total_signed
    #                 )
    #                 VALUES (NOW(), NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    #                 RETURNING id
    #             """, (
    #                 self.env.uid,  # create_uid
    #                 self.env.uid,  # write_uid
    #                 self.env['account.journal'].search([
    #                     ('type', '=', 'general'),
    #                     ('name', '=', 'Receiving Operations'),
    #                     ('company_id', '=', self.company_id_report.id),
    #                 ], limit=1).id,  # journal_id
    #                 fields.Date.today(),  # date
    #                 f"Receiving - {picking.name}",  # ref
    #                 picking.id,  # picking_id
    #                 picking.company_id.currency_id.id,  # currency_id
    #                 picking.company_id_report.id,  # company_id
    #                 'entry',   # move_type
    #                 'draft',   # state
    #                 'no',      # auto_post
    #                 received_amount,  # amount_total_signed
    #             ))


    #             journal_entry_id = self.env.cr.fetchone()[0]
    #             debit_val = float(received_amount) if received_amount else 0.0
    #             credit_val = float(received_amount) if received_amount else 0.0

    #             _logger.info(f" Debit Value: {debit_val} | Credit Value: {credit_val}")

    #             if not debit_account_id or not credit_account_id:
    #                 _logger.error(" Missing Debit or Credit Account. Skipping Journal Entry.")
    #                 continue  # skip this move para hindi mag-insert ng mali

              
    #             # Debit Line
    #             self.env.cr.execute("""
    #                 INSERT INTO account_move_line (
    #                     create_date, write_date, create_uid, write_uid,
    #                     move_id, name, account_id, debit, credit,
    #                     balance, amount_currency, currency_id, company_id, display_type
    #                 )
    #                 VALUES (NOW(), NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    #             """, (
    #                 self.env.uid,  
    #                 self.env.uid,  
    #                 journal_entry_id,  
    #                 "Inventory Debit",  
    #                 debit_account_id,   
    #                 debit_val,          # debit
    #                 0.0,                # credit
    #                 debit_val,          # balance (debit - credit)
    #                 debit_val,          # amount_currency
    #                 picking.company_id.currency_id.id,  
    #                 picking.company_id.id,              
    #                 'product',          
    #             ))

    #             _logger.info("✅ Debit line created for Move %s with amount %s", journal_entry_id, debit_val)


    #             # Credit Line

    #             self.env.cr.execute("""
    #                 INSERT INTO account_move_line (
    #                     create_date, write_date, create_uid, write_uid,
    #                     move_id, name, account_id, debit, credit,
    #                     balance, amount_currency, currency_id, company_id, display_type
    #                 )
    #                 VALUES (NOW(), NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    #             """, (
    #                 self.env.uid,  
    #                 self.env.uid,  
    #                 journal_entry_id,  
    #                 "Expense Credit",  
    #                 credit_account_id, 
    #                 0.0,               # debit
    #                 credit_val,        # credit
    #                 -credit_val,       # balance (0 - credit)
    #                 -credit_val,       # amount_currency (same as balance)
    #                 picking.company_id.currency_id.id,  
    #                 picking.company_id.id,              
    #                 'product',         
    #             ))

    #             _logger.info(" Credit line created for Move %s with amount %s", journal_entry_id, credit_val)

    #             # STEP 4: Refresh move
    #             self.env.cr.commit()
    #             _logger.info(f" Journal Entry Created with ID: {journal_entry_id}")

    #             # Check kung may laman sa DB
    #             self.env.cr.execute("SELECT id, name, state FROM account_move WHERE id = %s", (journal_entry_id,))
    #             created_move = self.env.cr.fetchone()
    #             _logger.info(f" Created Journal Entry: {created_move}")

    
    # def inventory_receiving_accounting(self):

    #     _logger.info('START: INVENTORY RECEIVING ACCOUNTING PROCESS')
    #     for picking in self:
    #         _logger.info(f'Processing Picking: {picking.name} | Company Report: {picking.company_id_report.name} (ID: {picking.company_id_report.id})')

    #         for move in picking.move_ids_without_package:
    #             _logger.info(f'Processing Move ID: {move.id} | Product: {move.product_id.display_name} | Prev Qty: {move.prev_qty}')

    #             # Calculate received amount
    #             received_amount = move.product_id.product_tmpl_id.purchase_price * move.prev_qty
    #             _logger.info(f'Computed Received Amount: {received_amount}')

    #             # Extract GL descriptions
    #             credit_gl_description = move.product_id.credit_gl_description
    #             debit_gl_description = move.product_id.debit_gl_description
    #             _logger.info(f'Debit GL Desc: {debit_gl_description} | Credit GL Desc: {credit_gl_description}')

    #             # Search for account IDs
    #             debit_account = self.env['account.account'].search(
    #                 [('name', '=', debit_gl_description), ('company_ids', 'in', [self.company_id_report.id])],
    #                 limit=1
    #             )
    #             credit_account = self.env['account.account'].search(
    #                 [('name', '=', 'Accounts Payable'), ('company_ids', 'in', [self.company_id_report.id])],
    #                 limit=1
    #             )

    #             # Validate accounts
    #             if not debit_account:
    #                 _logger.error(f'Debit Account NOT FOUND for description: {debit_gl_description}')
    #                 continue
    #             if not credit_account:
    #                 _logger.error(f'Credit Account NOT FOUND for Accounts Payable')
    #                 continue

    #             debit_account_id = debit_account.id
    #             credit_account_id = credit_account.id
    #             _logger.info(f'Debit Account: {debit_account.name} (ID: {debit_account_id})')
    #             _logger.info(f'Credit Account: {credit_account.name} (ID: {credit_account_id})')

    #             # Search for journal
    #             journal = self.env['account.journal'].search([
    #                 ('type', '=', 'general'),
    #                 ('name', '=', 'Receiving Operations'),
    #                 ('company_id', '=', self.company_id_report.id),
    #             ], limit=1)

    #             if not journal:
    #                 _logger.error(f'Journal "Receiving Operations" NOT FOUND for company {self.company_id_report.id}')
    #                 continue

    #             # Validate required fields
    #             if not all([picking.company_id.currency_id.id, picking.company_id_report.id, received_amount is not None]):
    #                 _logger.error(f'Missing required fields: currency_id={picking.company_id.currency_id.id}, company_id={picking.company_id_report.id}, received_amount={received_amount}')
    #                 continue

    #             # Create account_move using SQL
    #             self.env.cr.execute("""
    #                 INSERT INTO account_move (
    #                     create_date, write_date, create_uid, write_uid,
    #                     journal_id, date, ref, picking_id, currency_id,
    #                     company_id, move_type, state, auto_post, amount_total_signed
    #                 )
    #                 VALUES (NOW(), NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    #                 RETURNING id
    #             """, (
    #                 self.env.uid,  # create_uid
    #                 self.env.uid,  # write_uid
    #                 journal.id,  # journal_id
    #                 fields.Date.today(),  # date
    #                 f"Receiving - {picking.name}",  # ref
    #                 picking.id,  # picking_id
    #                 picking.company_id.currency_id.id,  # currency_id
    #                 picking.company_id_report.id,  # company_id
    #                 'entry',  # move_type
    #                 'draft',  # state
    #                 'no',  # auto_post
    #                 received_amount,  # amount_total_signed
    #             ))

    #             journal_entry_id = self.env.cr.fetchone()[0]
    #             _logger.info(f'Journal Entry Created with ID: {journal_entry_id}')

    #             debit_val = float(received_amount) if received_amount else 0.0
    #             credit_val = float(received_amount) if received_amount else 0.0

    #             if debit_val == 0.0 or credit_val == 0.0:
    #                 _logger.error(f'Invalid amount (zero) for Journal Entry {journal_entry_id}. Skipping.')
    #                 continue

    #             # Create account_move_line using ORM
    #             self.env['account.move.line'].create([
    #                 {
    #                     'move_id': journal_entry_id,
    #                     'name': f"Inventory Debit - {move.product_id.display_name}",
    #                     'account_id': debit_account_id,
    #                     'debit': debit_val,
    #                     'credit': 0.0,
    #                     'balance': debit_val,
    #                     'amount_currency': debit_val,
    #                     'currency_id': picking.company_id.currency_id.id,
    #                     'company_id': picking.company_id.id,
    #                     'display_type': 'product',
    #                 },
    #                 {
    #                     'move_id': journal_entry_id,
    #                     'name': f"Expense Credit - {move.product_id.display_name}",
    #                     'account_id': credit_account_id,
    #                     'debit': 0.0,
    #                     'credit': credit_val,
    #                     'balance': -credit_val,
    #                     'amount_currency': -credit_val,
    #                     'currency_id': picking.company_id.currency_id.id,
    #                     'company_id': picking.company_id.id,
    #                     'display_type': 'product',
    #                 }
    #             ])
    #             _logger.info(f" Debit and Credit lines created for Move {journal_entry_id} with amount {debit_val}")

    #             # Commit the transaction
    #             self.env.cr.commit()
    #             _logger.info(f"Journal Entry {journal_entry_id} fully processed")

    #             # Verify the created move
    #             self.env.cr.execute("SELECT id, name, state FROM account_move WHERE id = %s", (journal_entry_id,))
    #             created_move = self.env.cr.fetchone()
    #             _logger.info(f"Created Journal Entry: {created_move}")



    def inventory_receiving_accounting(self):

        _logger.info('START: INVENTORY RECEIVING ACCOUNTING PROCESS')
        for picking in self:
            _logger.info(f'Processing Picking: {picking.name} | Company Report: {picking.company_id_report.name} (ID: {picking.company_id_report.id})')

            for move in picking.move_ids_without_package:
                _logger.info(f'Processing Move ID: {move.id} | Product: {move.product_id.display_name} | Prev Qty: {move.prev_qty}')

                # Calculate received amount
                received_amount = move.unit_cost * move.prev_qty
                _logger.info(f'Computed Received Amount: {received_amount}')

                # Extract GL descriptions
                credit_gl_description = move.product_id.credit_gl_description
                debit_gl_description = move.product_id.debit_gl_description
                _logger.info(f'Debit GL Desc: {debit_gl_description} | Credit GL Desc: {credit_gl_description}')

                # Search for account IDs
                debit_account = self.env['account.account'].search(
                    [('name', '=', debit_gl_description), ('company_ids', 'in', [self.company_id_report.id])],
                    limit=1
                )
                credit_account = self.env['account.account'].search(
                    [('name', '=', 'Accounts Payable'), ('company_ids', 'in', [self.company_id_report.id])],
                    limit=1
                )
                # Validate accounts
                if not debit_account:
                    _logger.error(f'Debit Account NOT FOUND for description: {debit_gl_description}')
                    continue
                if not credit_account:
                    _logger.error(f'Credit Account NOT FOUND for Accounts Payable')
                    continue

                debit_account_id = debit_account.id
                credit_account_id = credit_account.id
                _logger.info(f'Debit Account: {debit_account.name} (ID: {debit_account_id})')
                _logger.info(f'Credit Account: {credit_account.name} (ID: {credit_account_id})')


                # Search for journal
                journal = self.env['account.journal'].search([
                    ('type', '=', 'general'),
                    ('name', '=', 'Receiving Operations'),
                    ('company_id', '=', self.company_id_report.id),
                ], limit=1)

                if not journal:
                    _logger.error(f'Journal "Receiving Operations" NOT FOUND for company {self.company_id_report.id}')
                    continue

                # Validate required fields
                if not all([picking.company_id.currency_id.id, picking.company_id_report.id, received_amount is not None]):
                    _logger.error(f'Missing required fields: currency_id={picking.company_id.currency_id.id}, company_id={picking.company_id_report.id}, received_amount={received_amount}')
                    continue

                # Create account_move using SQL
                self.env.cr.execute("""
                    INSERT INTO account_move (
                        create_date, write_date, create_uid, write_uid,
                        journal_id, date, ref, picking_id, currency_id,
                        company_id, move_type, state, auto_post, amount_total_signed
                    )
                    VALUES (NOW(), NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    self.env.uid,  # create_uid
                    self.env.uid,  # write_uid
                    journal.id,  # journal_id
                    fields.Date.today(),  # date
                    f"Receiving - {picking.name}",  # ref
                    picking.id,  # picking_id
                    picking.company_id.currency_id.id,  # currency_id
                    picking.company_id_report.id,  # company_id
                    'entry',  # move_type
                    'draft',  # state
                    'no',  # auto_post
                    received_amount,  # amount_total_signed
                ))

                journal_entry_id = self.env.cr.fetchone()[0]
                _logger.info(f'Journal Entry Created with ID: {journal_entry_id}')

                debit_val = float(received_amount) if received_amount else 0.0
                credit_val = float(received_amount) if received_amount else 0.0

                if debit_val == 0.0 or credit_val == 0.0:
                    _logger.error(f'Invalid amount (zero) for Journal Entry {journal_entry_id}. Skipping.')
                    continue

                AccountMoveLine = self.env['account.move.line']
                lines = [
                    {
                        'move_id': journal_entry_id,
                        'name': f"Inventory Debit - {move.product_id.display_name}",
                        'account_id': debit_account_id,
                        'debit': debit_val,
                        'credit': 0.0,
                        'balance': debit_val,
                        'amount_currency': debit_val,
                        'currency_id': picking.company_id.currency_id.id,
                        'company_id': picking.company_id_report.id,
                        'display_type': 'product',
                    },
                    {
                        'move_id': journal_entry_id,
                        'name': f"Expense Credit - {move.product_id.display_name}",
                        'account_id': credit_account_id,
                        'debit': 0.0,
                        'credit': credit_val,
                        'balance': -credit_val,
                        'amount_currency': -credit_val,
                        'currency_id': picking.company_id.currency_id.id,
                        'company_id': picking.company_id_report.id,
                        'display_type': 'product',
                    }
                ]
                AccountMoveLine.create(lines)
                # Commit the transaction
                self.env.cr.commit()
                _logger.info(f"Journal Entry {journal_entry_id} fully processed")

                # Verify the created move
                self.env.cr.execute("SELECT id, name, state FROM account_move WHERE id = %s", (journal_entry_id,))
                created_move = self.env.cr.fetchone()
                _logger.info(f"Created Journal Entry: {created_move}")




    def _log_entry_success(self, picking, move, account_move, amount):
        _logger.info(
            " Journal Entry Created: %s | Picking: %s | Product: %s | Amount: %s",
            account_move.id,
            picking.name,
            move.product_id.display_name,
            amount
        )

    def _log_entry_success(self, picking, move, account_move, amount):
        _logger.info(
            " Journal Entry Created: %s | Picking: %s | Product: %s | Amount: %s",
            account_move.id,
            picking.name,
            move.product_id.display_name,
            amount
        )

    def action_create_entry(self):
        """ Check availability of picking moves.
        This has the effect of changing the state and reserve quants on available moves, and may
        also impact the state of the picking as it is computed based on move's states.
        @return: True
        """
        self.mapped('package_level_ids').filtered(lambda pl: pl.state == 'draft' and not pl.move_ids)._generate_moves()

        # Include 'waiting' state, not just 'draft'
        self.filtered(lambda picking: picking.state in ('draft', 'waiting')).action_confirm()

        moves = self.move_ids.filtered(lambda move: move.state not in ('draft', 'cancel', 'done')).sorted(
            key=lambda move: (-int(move.priority), not bool(move.date_deadline), move.date_deadline, move.date, move.id)
        )  

        if moves: 
            print("HELLO FROM ACTION ASSIGN MAY MOVESS")

        # if not moves:
        #     raise UserError(('Nothing to check the availability for.'))

        moves._action_assign()
        return True

    def action_generate_pdf_and_post_message(self):
            # Get the report action
            report_action = self.env.ref('ml_development.report_receiving_receipt_custom_temp')
            if not report_action:
                raise ValueError("Report action not found")
            # Generate the PDF
            pdf_content = self.env['ir.actions.report']._render_qweb_pdf(report_action.id, self.id)[0]

            # Create attachment
            attachment = self.env['ir.attachment'].create({
                'name': 'Receiving_Receipt_%s.pdf' % self.name,
                'type': 'binary',
                'datas': base64.b64encode(pdf_content),
                'res_model': 'stock.picking',
                'res_id': self.id,
                'mimetype': 'application/pdf'
            })

            # Post message
            # Get current date and time
            # current_time = datetime.now().strftime('%B %d, %Y %I:%M %p')
            # Post message


            self.with_context(
                mail_notify_force_send=False,
                mail_auto_subscribe_no_notify=True
                ).message_post(
                    body="Attached Files.",
                    message_type="comment",
                    subtype_xmlid="mail.mt_log",
                    attachment_ids=[attachment.id]
                )

            return True
    
    def action_generate_pdf_and_post_message_done(self):
        # Get the report action
        report_action = self.env.ref('ml_development.report_receiving_receipt_custom')
        if not report_action:
            raise ValueError("Report action not found")

        # Generate the PDF
        pdf_content = self.env['ir.actions.report']._render_qweb_pdf(report_action.id, self.id)[0]

        # Create attachment only
        self.env['ir.attachment'].create({
            'name': 'Receiving_Receipt_%s.pdf' % self.name,
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'res_model': 'stock.picking',
            'res_id': self.id,
            'mimetype': 'application/pdf'
        })
        # No message_post call here
        return True

    @api.model
    def create(self, vals):
        picking = super(StockPickingInherit, self).create(vals)


        picking_type_id = vals.get('picking_type_id')
        if picking_type_id:
            picking_type = self.env['stock.picking.type'].browse(picking_type_id)
            if picking_type.code == 'incoming':
                move_vals_list = vals.get('move_ids_without_package', [])

                for command in move_vals_list:
                    if isinstance(command, (list, tuple)) and command[0] == 0:
                        move_vals = command[2]
                        product_qty = move_vals.get('product_uom_qty', 0.0)
                        unit_cost = move_vals.get('unit_cost', 0.0)

                        if product_qty == 0 or unit_cost == 0:
                            raise UserError("You cannot create a Receiving with an item that has zero quantity or unit cost.")

             # Get current user and groups
        # # Example: tanggalin yung warehouse prefix 'LN/'
        # if picking.name and picking.name.startswith("LN/"):
        #     picking.name = picking.name.replace("LN/", "", 1)

        # # Example: custom prefix depende sa group
        # user = self.env.user
        # group_vismin = self.env.ref('ml_development.group_vismin_mods')
        # group_luzon = self.env.ref('ml_development.group_lncr_mods')

        # if group_vismin in user.groups_id:
        #     picking.name = "VM" + picking.name
        # elif group_luzon in user.groups_id:
        #     picking.name = "LN" + picking.name

        # isZone = vals.get('isZone')
        # if isZone in vals:
        #     getZone = self.isZone
        #     # Determine if it's from LNCR or VISMIN
        #     if getZone in ['lncr']: # LNCR
        #         # Modify the sequence name before creation
        #         # vals['name'] = 'LN/' + self.env['ir.sequence'].next_by_code('purchase.order') or 'LN/' 
        #         raise UserError("LNCR")
        #     elif getZone in ['vismin']: # VISMIN
        #         # Modify the sequence name before creation
        #         # vals['name'] = 'VM/' + self.env['ir.sequence'].next_by_code('purchase.order') or 'VM/' 
        #         raise UserError("VISMIN")

        # else:
        #     raise UserError("Wala isZONE")
        # self.write({'state': 'assigned'})

        # Jo
        # if picking.origin and picking.picking_type_id.code == 'incoming':
            
        #     purchase_order = self.env['purchase.order'].search([('name', '=', picking.origin)], limit=1)
        #     if purchase_order:
        #         picking.write({'state': 'assigned'})  
        #         picking.message_post(
        #             body="Items are ready to be received.",
        #             subtype_xmlid='mail.mt_note'
        #         )

        # Create rec
        # if picking.picking_type_id.code == 'incoming':
        #     _logger.info(f'HELLO INCOMING SIYA:') # logger here
        #     create_approval = self.env['res.approvers'].create({
        #         'name': picking.name,
        #         'stock_picking_id' : picking.id,
        #         'submitted_to': 'custodian', 
        #         'module' : 'rr',
        #         'branch': self.branch.id,
        #         'remarks': self.remarks,
        #         'total_amount': self.total_amount,
        #         'zone' : picking.zone,
        #         'isZone' : picking.isZone
        #     }) 

        # elif picking.picking_type_id.code == 'internal':
        #     # .create() entry to the approval module
        #     # Ensure wala pa don sa res.approvers na ka name
        #     create_approval = self.env['res.approvers'].create({
        #         'name': picking.name,
        #         'internal_transfer_id' : picking.id,
        #         'state': 'submitted_to_manager', 
        #         'submitted_to': 'manager', 
        #         'branch': self.branch.id,
        #         'remarks': self.remarks,
        #         'total_amount': self.total_amount,
        #         'module' : 'it',
        #         'zone' : picking.zone,
        #         'isZone' : picking.isZone
        #     }) 
        # else:
        #     _logger.info(f'WALA YATA KASI PICKING TYPE ID:')
        return picking

    @api.model
    def write(self, vals):
        #  Your custom condition to raise error
        if 'picking_type_id' in vals and any(picking.state in ('done', 'cancel') for picking in self):
            vals.pop('picking_type_id')  # Just remove it from being written

        #  Your custom logic (copy from the original or customize)
        if vals.get('partner_id'):
            for picking in self:
                if picking.location_id.usage == 'supplier' or picking.location_dest_id.usage == 'customer':
                    if picking.partner_id:
                        picking.message_unsubscribe(picking.partner_id.ids)
                    picking.message_subscribe([vals.get('partner_id')])

        if vals.get('picking_type_id'):
            picking_type = self.env['stock.picking.type'].browse(vals.get('picking_type_id'))
            for picking in self:
                if picking.picking_type_id != picking_type:
                    picking.name = picking_type.sequence_id.next_by_id()
                    vals['location_id'] = picking_type.default_location_src_id.id
                    vals['location_dest_id'] = picking_type.default_location_dest_id.id

        res = super().write(vals)

        if vals.get('signature'):
            for picking in self:
                picking._attach_sign()

        after_vals = {}
        if vals.get('location_id'):
            after_vals['location_id'] = vals['location_id']
        if vals.get('location_dest_id'):
            after_vals['location_dest_id'] = vals['location_dest_id']
        if 'partner_id' in vals:
            after_vals['partner_id'] = vals['partner_id']
        if after_vals:
            self.move_ids.filtered(lambda move: not move.scrapped).write(after_vals)

        if vals.get('move_ids') or vals.get('move_ids_without_package'):
            self._autoconfirm_picking()


    def action_cancel(self):
        for rec in self:
            if not rec.remarks:
                raise UserError('Please provide remarks before cancelling receipt form.')
            # Compute totals before sending email
            total_received_qty = sum(rec.move_ids_without_package.mapped('quantity'))
            total_amount = sum(rec.move_ids_without_package.mapped('total_amount'))

            # Build the table for the email body
            table_content = """
                <table border="1" style="border-collapse: collapse; width: 100%;">
                    <thead>
                        <tr style="background-color: #f2f2f2;">
                            <th style="padding: 8px; text-align: left;">Product</th>
                            <th style="padding: 8px; text-align: center;">Received Qty</th>
                            <th style="padding: 8px; text-align: center;">Unit Price</th>
                            <th style="padding: 8px; text-align: center;">Subtotal</th>
                        </tr>
                    </thead>
                    <tbody>
            """
            for move in rec.move_ids_without_package:
                table_content += """
                    <tr>
                        <td style="padding: 8px;">{}</td>
                        <td style="padding: 8px; text-align: center;">{}</td>
                        <td style="padding: 8px; text-align: center;">₱{}</td>
                        <td style="padding: 8px; text-align: center;">₱{}</td>
                    </tr>
                """.format(
                    move.product_id.name,  # Product Name
                    int(move.quantity),  # Received Qty
                    "{:,.2f}".format(move.price_unit),  # Unit Price
                    "{:,.2f}".format(move.total_amount)  # Subtotal
                )

            # Close the table
            table_content += """
                    </tbody>
                </table>
            """
            # Send only ONE email instead of per move
            if rec.partner_id.email:
                mail_values = {
                    'subject': "The Receiving Receipt has been cancelled - {}".format(rec.name),
                    'body_html': """
                        <p>Hello {}</p>
                        <p>The receipt <strong>{}</strong> has been cancelled.</p>
                        <p><strong>Received Quantity:</strong> {}</p>
                        <p><strong>Total Amount:</strong> ₱{}</p>
                        <p>Below are the cancelled items:</p>
                        {}
                        <p>Regards,</p>
                    """.format(
                        rec.partner_id.name, 
                        rec.name,
                        int(total_received_qty),  
                        "{:,.2f}".format(total_amount),  # Proper currency formatting
                        table_content  # Insert the table here
                    ),
                    'email_to': rec.partner_id.email,
                    'email_from': self.env.user.email or 'ronaldboholst@mlhuillier.com',
                }
                mail = self.env['mail.mail'].create(mail_values)
                mail.send()

            # 🔹 **Prevent deletion of received items**
            # for move in rec.move_ids_without_package:
            #     if move.state == 'done':  # Only update completed stock moves
            #         move.write({'state': 'cancel'})  # Mark as cancelled but do NOT delete stock

            # Cancel the receipt document but keep the received stock
            # super().action_cancel()
            
        self.write({'state': 'cancel'})  # Mark as cancelled but do NOT delete stock
        return True
    
    
class ReportReceivingReceipt(models.AbstractModel):
    _name = 'report.ml_development.custom_report_receiving_receipt'
    _description = 'Custom Receiving Receipt Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['stock.picking'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'stock.picking',
            'docs': docs,  # This provides the 'doc' variable to your QWeb template
        }

class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    lncr = fields.Boolean(string="LNCR")
    vismin = fields.Boolean(string="VisMin")

class StockPickingLineInherit(models.Model):
    _inherit = 'stock.move'
    _description = 'ML Stock Move'

    unit = fields.Integer('Units')
    description = fields.Char('Description')

    unit_price = fields.Float(string="Unit Price")
    unit_cost = fields.Float(string="Unit Cost") 
    has_origin = fields.Boolean(string="Has Origin", default=False)


    ########################################################################################## conversion
    unit_cost_converted = fields.Float(string="Unit Cost (USD)")
    isUSD = fields.Boolean(related='picking_id.isUSD', store=True)
    isPHP = fields.Boolean(related='picking_id.isPHP', store=True)
    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        related="picking_id.currency_id",
        store=True,
        readonly=False,
    )

    @api.onchange('product_id')
    def _onchange_product_id_set_defaults(self):
        """Set initial costs from product purchase_price if empty."""
        for move in self:
            if not move.unit_cost and not move.unit_cost_converted and move.product_id:
                purchase_price = move.product_id.purchase_price or 0.0
                move.unit_cost_converted = purchase_price / (move.picking_id.conversion_rate)
                move.unit_cost = purchase_price



    @api.onchange('unit_cost', 'unit_cost_converted', 'picking_id.conversion_rate', 'isUSD', 'isPHP')
    def _onchange_costs_bi_directional(self):
        for move in self:
            rate = move.picking_id.conversion_rate or 0.0
            if not rate:
                continue

            # If USD is editable
            if move.isUSD:
                if move.unit_cost_converted:
                    move.unit_cost = move.unit_cost_converted * rate
                else:
                    move.unit_cost = 0.0

            # If PHP is editable
            elif move.isPHP:
                if move.unit_cost:
                    move.unit_cost_converted = move.unit_cost / rate
                else:
                    move.unit_cost_converted = 0.0



    ##########################################################################################




    amount = fields.Float(string="Amount", compute="_compute_amount", store=True)
    total_amount = fields.Float(string="Total Amount",  store=True)
    
    received_qty = fields.Integer('To be Received', default = 0)

    show_received_qty = fields.Boolean(compute="_compute_show_received_qty", store=False)
    accumulated_qty = fields.Float(string="Accumulated Received Quantity", default=0.0)
    prev_qty = fields.Integer("Prev QTY")
    total_amount_report = fields.Float(string="Total Amount",  store=True)
    prev_amount_report = fields.Float(string="Previous Amount",  store=True)

    product_id_vismin = fields.Many2one('product.product')
    untaxed_amount = fields.Float(string='Untaxed Amount', default=0.0, digits=(6, 2))
    taxed_amount = fields.Float(string='Tax Amount', default=0.0, digits=(6, 2))
    tax_id = fields.Selection([
        ('vat_12', '12%'),
        ('vat_0', '0%'), 
    ], string='Tax Rate')
    tax_id_related = fields.Selection([
        ('vat_12', '12%'),
        ('vat_0', '0%')
    ], string='Tax Rate', related="tax_id")
    product_uom_qty = fields.Float(
    'Demand',
    digits=(16, 0),  # Removes decimal places
    default=0,
    required=True,
    help="This is the quantity of product that is planned to be moved."
         "Lowering this quantity does not generate a backorder."
         "Changing this quantity on assigned moves affects "
         "the product reservation, and should be done with care."
    )

    quantity = fields.Float(
        'Quantity',
        compute='_compute_quantity',
        digits=(16, 0),  # Removes decimal places
        inverse='_set_quantity',
        store=True,
        default=1,
    )   

    is_Zone = fields.Selection(
        [('lncr', 'LNCR'), ('vismin', 'VISMIN')],
        string="Zone",
        store=True,
        # default=_default_zone  #  Call function for dynamic default
    )


    def _check_company(self):
        if self.env.context.get('allow_cross_company', False):
            return  # Bypass company validation
        return super()._check_company()
    

    
    # @api.depends('picking_id.picking_type_id.code')
    # def _compute_show_received_qty(self):
    #     for record in self:
    #         record.show_received_qty = record.picking_id.picking_type_id.code == 'incoming'
    # quantity = fields.Float(string="Quantity", default=0.00, readonly=True)


    # @api.onchange('product_id')
    # def _onchange_product_qty(self):
    #     if self.product_id:
    #         unit_cost = self.product_id.product_tmpl_id.standard_price
    #         self.unit_cost =  unit_cost
    #     # if self.picking_id and self.picking_id.origin:
    #     #     raise UserError(_(
    #     #         "Quantity cannot be changed because this Receiving Receipt Form was generated from a Purchase Order. "
    #     #         "Create a non-PO Receiving Receipt Form instead."
    #     #     ))
    #     _logger.info(f'Onchange Unit Cost')

    @api.onchange('product_uom_qty', 'product_id','unit_cost','tax_id')
    def _onchange_compute_unit_price(self):
        for line in self:
            if line.product_id:
                qty = line.product_uom_qty
                unit_cost = line.unit_cost or 0.0

                _logger.info("Product: %s", line.product_id.name)
                _logger.info("Qty: %s | Unit Cost: %s | Tax: %s", qty, unit_cost, line.tax_id)

                if line.tax_id == 'vat_12':
                    tax_per_unit = float_round(unit_cost * 1.12, precision_digits=2)
                    price_total = float_round(tax_per_unit * qty, precision_digits=2)

                    _logger.info("VAT12: tax/unit=%.2f | total=%.2f", tax_per_unit, price_total)

                    line.update({
                        'total_amount': price_total,
                    })

                elif line.tax_id == 'vat_0':
                    price_total = float_round(unit_cost * qty, precision_digits=2)

                    _logger.info("VAT0: total=%.2f", price_total)

                    line.update({
                        'total_amount': price_total,
                    })


    @api.model
    def create(self, vals):
        """Prevent adding new items to a PO-based receipt; ensure quantity = 0 if from PO."""
        if 'purchase_line_id' in vals:
            vals['quantity'] = 0.00  # Default quantity for PO-based stock moves

        picking_id = vals.get('picking_id')
        if picking_id:
            picking = self.env['stock.picking'].browse(picking_id)
            
            # Check if it's a PO-based receipt
            if picking.exists() and picking.origin and picking.picking_type_id.code == 'incoming':
                if picking.state not in ['draft', 'assigned']:
                    raise UserError(
                        "You cannot add new line items to this Receiving Receipt because it is no longer in draft or assigned state."
                    )
        

        # if picking.state not in ['draft', 'assigned']:
        #     raise UserError("You cannot add new lines unless the status is 'Draft' or 'Assigned'.")
            
        return super(StockPickingLineInherit, self).create(vals)

    @api.model
    def write(self, vals):
        """ Ensure new stock moves have quantity = 0.00 when created from a PO. """
        if 'purchase_line_id' in vals:  # Means it was generated from a PO
            vals['quantity'] = 0.00  # Set the value of the field quantity to zero
        

        
        picking_id = vals.get('picking_id')
        if picking_id:
            picking = self.env['stock.picking'].browse(picking_id)
            if picking.origin:
                raise UserError("You cannot add new products to a Receiving Receipt that originates from a Purchase Order.")
        

            
        return super(StockPickingLineInherit, self).write(vals)
    
    def unlink(self):
        if self.env.context.get('force_unlink'):  #  Allow forced deletion inside button_confirm()
            return super(StockPickingLineInherit, self).unlink()

        # # Restrict manual deletion for non-draft/assigned pickings
        # for move in self:
        #     if move.picking_id.state in ['partially_received']:
        #         raise UserError("You cannot delete lines unless the status is 'Draft' or 'Assigned'.")
        
        # # Restrict manual deletion for non-draft/assigned pickings
        # for move in self:
        #     if move.picking_id.origin:
        #         if move.picking_id.state in ['assigned','partially_received','done']:
        #             raise UserError("You cannot delete lines if Receiving Receipt is from a Purchase Order.")
        
        # If  item were to be deleted please add it on the logs, what item is deleted
        return super(StockPickingLineInherit, self).unlink()
    
    @api.constrains('received_qty')
    def _check_received_qty(self):
        """ Ensure received_qty is valid. """
        for move in self:
            if move.received_qty < 0:
                raise ValidationError("Received quantity cannot be negative.")
            if move.received_qty > move.product_uom_qty:
                raise ValidationError("Received quantity cannot exceed ordered quantity.")
            # remaining_qty = move.product_uom_qty - move.quantity
            # if move.received_qty > remaining_qty:
            #     raise ValidationError("Received quantity cannot exceed remaining quantity.")

    # @api.depends('purchase_line_id.price_unit', 'product_id.standard_price')
    # def _compute_unit_cost(self):
    #     """ Compute unit cost from Purchase Order or standard price. """
    #     for move in self:
    #         move.unit_cost = move.purchase_line_id.price_unit if move.purchase_line_id else move.product_id.purchase_price

    @api.depends('unit_cost', 'product_uom_qty', 'quantity')
    def _compute_amount(self):
        """ Compute line amount based on quantity and unit cost. """
        for move in self:
            quantity = move.quantity if move.quantity else move.product_uom_qty
            move.amount = quantity * move.unit_cost

    # @api.depends('tax_amount', 'quantity', 'untaxed_amount')
    # def _compute_total_amount(self):
    #     """ Compute total amount as Unit Cost * Quantity """
    #     for move in self:

    #         if move.picking_id.partner_id.tax_type == 'vatable':
    #             move.total_amount = move.taxed_amount * move.quantity 
    #         else:
    #             move.total_amount = move.untaxed_amount * move.quantity 

  
    state = fields.Selection([
        ('draft', 'Received but not completed'),
        ('waiting', 'Waiting Another Move'),
        ('confirmed', 'Partial Delivery'),
        ('partially_available', 'Partially Available'),
        ('assigned', 'Available'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')], string='Status',
        copy=False, default='draft', index=True, readonly=True,
        help="* New: The stock move is created but not confirmed.\n"
             "* Waiting Another Move: A linked stock move should be done before this one.\n"
             "* Waiting Availability: The stock move is confirmed but the product can't be reserved.\n"
             "* Available: The product of the stock move is reserved.\n"
             "* Done: The product has been transferred and the transfer has been confirmed.")

    
    # @api.onchange('product_id', 'product_id_vismin'  )
    # def stock_move_change(self):
    #     _logger.info(f'HELLO HELLO HELLO HELLO PRODUCT ID CHANGE: {self.picking_id.name} ')

    #     if self.picking_id.isZone == 'lncr':
    #         _logger.info(f'LNCR TONG STOCK PICKING: ')
    #         self.product_id_vismin.optional = True
    #     elif self.picking_id.isZone == 'vismin':
    #         _logger.info(f'VISMIN TONG STOCK PICKING: ')
    #         self.product_id = self.product_id_vismin.id
    #         self.product_id_vismin.optional = False
    #     else:
    #         _logger.info(f'Wala yatang isZOne: ')


    @api.model
    def default_get(self, fields_list):
        defaults = super(StockPickingLineInherit, self).default_get(fields_list)

        picking_id = self.env.context.get('default_picking_id')
        if picking_id:
            picking = self.env['stock.picking'].browse(picking_id)
            if picking.exists() and picking.partner_id.tax_type == 'vatable':
                # 🔹 Set defaults if partner is vatable
                if 'total_amount' in fields_list:
                    defaults['total_amount'] = 0.0  # Example default value
                if 'tax_id' in fields_list:
                    # Assume vat_12 is a selection field
                    defaults['tax_id'] = 'vat_12'

        return defaults
 
class StockMoveLineInherit(models.Model):
    _inherit = 'stock.move.line'           
    _name = 'stock.move.line'              
    _inherit = ['stock.move.line', 'mail.thread', 'mail.activity.mixin']

    quantity = fields.Float(
        'Received Quantity',
        digits=(16, 0),
        copy=False,
        store=True,
        compute='_compute_quantity',
        readonly=False,
        tracking=True,
    )


    signed_qty = fields.Float(
        string="Quantity",
        digits=(16, 0),
        compute='_compute_signed_qty',
        store=False,   # dynamic
        readonly=True,
        tracking=True,
    )

    total_signed_qty = fields.Float(
        string="Total Signed Quantity",
        compute='_compute_total_signed_qty',
        store=False,
        readonly=True,
    )

    @api.depends('qty_done', 'reference')
    def _compute_signed_qty(self):
        for line in self:
            qty = line.qty_done if line.qty_done else line.quantity
            if line.reference and 'ML/OUT/' in line.reference.upper():
                qty = -qty
            line.signed_qty = qty

    def _compute_total_signed_qty(self):
        """Compute the total of signed_qty for the current recordset"""
        total = sum(line.signed_qty for line in self)
        for line in self:
            line.total_signed_qty = total




    remaining_quantity = fields.Float(
        'Remaining Quantity',
        digits=(16, 0),
        copy=False,
        store=True,
        compute='_compute_quantity',
        readonly=False
    )
    isZone = fields.Char('USER ZONE') # default get para sa laman ni isZone 
    zone = fields.Selection(
        [('lncr', 'LNCR'), ('vismin', 'VISMIN')],
        string="Zone",
        store=True,
        # default=_default_zone  #  Call function for dynamic default
    )
    tax_id = fields.Selection([
        ('vat_12', '12%'),
        ('vat_0', '0%')
    ], string='Tax Rate', default='vat_12')

    def _default_zone(self):
        user = self.env.user
        group_luzon = self.env.ref('ml_development.group_lncr_mods')
        
        return 'lncr' if group_luzon in user.groups_id else 'vismin'  
    
    @api.model
    def action_move_history(self):
        # Get the current user's zone (LNCR / VISMIN)
        print("Hello  action na backend")
        user = self.env.user
        group_luzon = self.env.ref('ml_development.group_lncr_mods')
        group_vismin = self.env.ref('ml_development.group_vismin_mods')

        is_zone = 'lncr' if group_luzon in user.groups_id else 'vismin'

        #  Modify the domain dynamically
        action = self.env.ref("ml_development.action_move_history").sudo().read()[0]
        action['domain'] = [('zone', '=', is_zone)]  #  Filter by user's zone

        return action
    
    @api.depends('product_id', 'product_uom_qty', 'tax_id')
    def _compute_amounts(self):
        for line in self:
            line.unit_cost = line.product_id.product_tmpl_id.standard_price if line.product_id else 0.0
            line.untaxed_amount = line.unit_cost * line.product_uom_qty

            if line.tax_id == 'vat_12':
                line.taxed_amount = line.untaxed_amount * 0.12
            else:
                line.taxed_amount = 0.0

            line.total_amount = line.untaxed_amount + line.taxed_amount

class MLProductTemplateInherit(models.Model):
    _inherit = 'product.template'
    _description = 'ML Product Template'

    name = fields.Char(string="Product Name", copy=True, index=True, tracking=True, required=True)
    trade_name = fields.Char('Trade Name')
    trade_name_supplier = fields.Many2one('res.partner', 'Trade Name')
    item_code = fields.Char('Item Code', required="True")
    default_code = fields.Char(string="Reference", related='item_code', readonly=True)
    expense_account_code = fields.Char('Expense Account Code')
    expense_account_entry = fields.Many2one('account.account')
    item_description = fields.Text('Item Description')  
    vat_type = fields.Char('VAT Type')
    selling_price = fields.Float(string="Selling Price")
    purchase_price = fields.Float(string="Purchase price")
    standard_price = fields.Float(
        "Cost", company_dependent=True,
        digits='Product Price', groups="base.group_user",
        help="""Value of the lot (automatically computed in AVCO).
        Used to value the product when the purchase cost is not known (e.g. inventory adjustment).
        Used to compute margins on sale orders.""",
        related="purchase_price"
    )
    initial_quantity = fields.Float('Initial Quantity', default=0.0)
    list_price = fields.Float(
        "Sales Price", company_dependent=True,
        digits='Sales Price', groups="base.group_user",
        # help="""Value of the lot (automatically computed in AVCO).
        # Used to value the product when the purchase cost is not known (e.g. inventory adjustment).
        # Used to compute margins on sale orders.""",
        related="purchase_price"
    )
    nbr_moves_in = fields.Float(
        string="Total Incoming Quantity",
        compute="_compute_nbr_moves",
        store=False  # Computed dynamically
    )
    nbr_moves_out = fields.Float(
        string="Total Outgoing Quantity",
        compute="_compute_nbr_moves",
        store=False
    )
    suggested_item_type = fields.Selection([
        ('acu_cctv_alarm_system', 'ACU/ CCTV & Alarm System'),
        ('forms', 'Forms'),
        ('marketing_materials', 'Marketing Materials / Promotional Items'),
        ('appraisal_tools_supplies', 'Appraisal Tools and Supplies'),
        ('cleaning_supplies', 'Cleaning Supplies'),
        ('showroom_display_materials', 'Showroom Display Materials'),
        ('office_equipment', 'Office Equipment'),
        ('stationeries_office_supplies', 'Stationeries and Office Supplies'),
        ('signage_components', 'Signage and Components'),
        ('miscellaneous_supplies', 'Miscellaneous Supplies'),
        ('mobile_van_branch', 'Mobile/Van/KiO/Sk Type Branch'),
        ('repairs_maintenance', 'Repairs and Maintenance'),
        ('computers_laptops_peripherals', 'Computers/Laptops & Peripherals'),
        ('furnitures_fixtures', 'Furniture & Fixtures'),
        ('delivery_freight_charges', 'Delivery and Freight Charges'),
        ('uniform', 'Uniform'),
        ('showroom_display_materials_supplies', 'Showroom Display Materials & Supplies'),
        ('general_services', 'General Services'),
        ('general_services', 'General Services'),
        ('it_assets', 'IT Assets'),
        ('furnitures_fixtures','Furnitures & Fixtures'),
        ('mobile_van_type_branch','Mobile/Van Type Branch'),
        ], string="Suggested Item Type")
    
    debit_gl_code = fields.Char('Debit [GL Code]')
    debit_gl_description = fields.Char('Debit [GL Description]')
    credit_gl_code = fields.Char('Credit [GL Code]')
    credit_gl_description = fields.Char('Credit [GL Description]')
    initial_quantity = fields.Float('Initial Quantity', default=0.0)
    location_name = fields.Selection([ 
        ('ln_ml_stock', 'LN MF/Stock'),
        ('vm_ml_stock', 'VM MF/Stock'),
        ], string="Location Name")
    is_Zone = fields.Selection(
        [('lncr', 'LNCR'), ('vismin', 'VISMIN')],
        string="Zone",
        store=True,
        compute="_default_zone" #  Call function for dynamic default
    )
   
    @api.depends('location_name')
    def _default_zone(self):
        if self.location_name:
            if self.location_name == 'ln_ml_stock':
                self.is_Zone = 'lncr'
            else:
                self.is_Zone = 'vismin'

    # def _get_domain_locations(self):
    #     Location = self.env['stock.location']
    #     Warehouse = self.env['stock.warehouse']

    #     def _search_ids(model, values):
    #         ids = set()
    #         domains = []
    #         for item in values:
    #             if isinstance(item, int):
    #                 ids.add(item)
    #             else:
    #                 domains.append([(self.env[model]._rec_name, 'ilike', item)])
    #         if domains:
    #             ids |= set(self.env[model].search(expression.OR(domains)).ids)
    #         return ids

    #     location = self.env.context.get('location')
    #     if location and not isinstance(location, list):
    #         location = [location]
    #     warehouse = self.env.context.get('warehouse_id')
    #     if warehouse and not isinstance(warehouse, list):
    #         warehouse = [warehouse]

    #     # **Filter warehouse locations to only get 'internal' locations**
    #     location_ids = set()

    #     if warehouse:
    #         w_ids = set(Warehouse.browse(_search_ids('stock.warehouse', warehouse)).mapped('view_location_id').ids)
    #         if location:
    #             l_ids = _search_ids('stock.location', location)
    #             parents = Location.browse(w_ids).mapped("parent_path")
    #             location_ids = {
    #                 loc.id
    #                 for loc in Location.browse(l_ids)
    #                 if any(loc.parent_path.startswith(parent) for parent in parents)
    #             }
    #         else:
    #             location_ids = w_ids
    #     else:
    #         if location:
    #             location_ids = _search_ids('stock.location', location)
    #         else:
    #             location_ids = set(Warehouse.search(
    #                 [('company_id', 'in', self.env.companies.ids)]
    #             ).mapped('view_location_id').ids)

    #     # **FILTER ONLY INTERNAL LOCATIONS**
    #     internal_locations = Location.search([('id', 'in', list(location_ids)), ('usage', '=', 'internal')]).ids

    #     # Get the warehouse zone ('lncr' or 'vismin') based on the isZone value
    #     is_zone = self.isZone

    #     print(is_zone, "Current iSZONE")

    #     if is_zone == 'lncr':
    #         print("naka lncr naman")
    #         warehouses = Warehouse.search([('lncr', '=', True)])  # Find all warehouses with 'lncr' checked
    #     elif is_zone == 'vismin':
    #         print("naka vismin naman")
    #         warehouses = Warehouse.search([('vismin', '=', True)])  # Find all warehouses with 'vismin' checked
    #     else:
    #         warehouses = Warehouse  # If no zone is specified, consider all warehouses
    #         print("DI ISZONE")

    #     # Get the locations corresponding to these warehouses
    #     relevant_locations = set(warehouses.mapped('view_location_id.id'))
        
    #     # **Return locations that belong to these warehouses and are of 'internal' type**
    #     filtered_locations = Location.search([
    #         ('id', 'in', list(internal_locations)),
    #         ('warehouse_id', 'in', relevant_locations)  # Ensure only the locations in the selected warehouses are counted
    #     ])

    #     return self._get_domain_locations_new(filtered_locations.ids)


    # For creating the records of products
    @api.model
    def create(self, vals):
        template = super(MLProductTemplateInherit, self).create(vals)
        _logger.info(f"Product Creation is happening: ")
        initial_qty = vals.get('initial_quantity', 0.0)
        product = template.product_variant_id
        standard_price = vals.get('standard_price', 0.0)  # Default to 0.0 if not set

        # Skip the item if the product name exista already
        # Pass the item if not then proceed adding the item 

        # Vendor location (source)
        vendor_location = self.env.ref('stock.stock_location_suppliers', raise_if_not_found=False)
        if not vendor_location:
            raise UserError("Vendor Location (stock.stock_location_suppliers) not found!")

        # Destination: Either LN or VM stock
        location_lncr = self.env['stock.location'].search([('complete_name', '=', 'LN MF/Stock')], limit=1)
        location_vismin = self.env['stock.location'].search([('complete_name', '=', 'VM MF/Stock')], limit=1)

        # Location name from import
        location_name = vals.get('location_name')
        _logger.info(f"Location Name: {location_name}")
        location = False


        if location_name == 'ln_ml_stock':
            location = location_lncr
            _logger.info(f"Location to be used is LN MF/Stock: ")
        elif location_name == 'vm_ml_stock':
            location = location_vismin
            _logger.info(f"Location to be used is LN VM MF/Stock: ")

        if location:
            _logger.info(f"Location to be used: {location.complete_name}")

        if product and initial_qty > 0:
            # Check if the initial quantity will result in a negative on-hand quantity
            quant = self.env['stock.quant'].search([
                ('product_id', '=', product.id),
                ('location_id', '=', location.id),
            ], limit=1)

            if quant and quant.quantity + initial_qty < 0:
                raise UserError(f"Cannot create stock move for {product.name}. The resulting on-hand quantity would be negative.")

            _logger.info(f"[INIT STOCK] Creating Stock Move + Move Line for: {product.name} Qty: {initial_qty} to {location.complete_name}")
            move = self.env['stock.move'].create({
                'name': f'Initial Import - {product.name}',
                'product_id': product.id,
                'product_uom_qty': initial_qty,
                'product_uom': product.uom_id.id,
                'location_id': vendor_location.id,
                'location_dest_id': location.id,
                'state': 'draft',
            })
            move._action_confirm()
            move_line = self.env['stock.move.line'].create({
                'move_id': move.id,
                'product_id': product.id,
                'product_uom_id': product.uom_id.id,
                'quantity': initial_qty,
                'location_id': vendor_location.id,
                'location_dest_id': location.id,
                'state': 'done'
            })

            move._action_done()

            # Update or create stock quant
            if quant:
                quant.quantity += initial_qty
                quant.inventory_quantity += initial_qty
                # quant.unit_cost = standard_price
                # quant.inventory_value = quant.quantity * standard_price
            else:
                self.env['stock.quant'].create({
                    'product_id': product.id,
                    'location_id': location.id,
                    'quantity': initial_qty,
                    'inventory_quantity': initial_qty,
                })
            _logger.info(f"[SUCCESS] Stock Move, Move Line, and Quant created for {product.name}, Qty: {initial_qty}, Location: {location.complete_name}, Unit Cost: {standard_price}")
            move_line.update({'state': 'done'})

            unit_cost = template.purchase_price or product.standard_price or 0.0
            total_value = unit_cost * initial_qty

            # Create an Inventory Valuation Journal Entry here
            valuation_amount = unit_cost * initial_qty
            valuation_moves = []

            journal_entry = self.env['account.move'].create({
                'journal_id': self.env['account.journal'].search([('type', '=', 'general'), ('name', '=', 'Inventory Valuation')], limit=1).id,
                'date': fields.Date.today(),
                'ref': f"Stock Valuation - {template.name}",
                'line_ids': [
                    (0, 0, {
                        'account_id': template.categ_id.property_stock_valuation_account_id.id,
                        'debit': valuation_amount,
                        'credit': 0,
                        'name': template.name,
                    }),
                    (0, 0, {
                        'account_id': template.categ_id.property_stock_account_output_categ_id.id,
                        'debit': 0,
                        'credit': valuation_amount,
                        'name': template.name,
                    }),
                ]
            })

            journal_entry.action_post()
            valuation_moves.append(journal_entry.id)

            for item in valuation_moves:
                _logger.info(f"[SUCCESS] Mga laman ni Valuation {item}")

            self.env['stock.valuation.layer'].create({
                'product_id': product.id,
                'value': total_value,
                'unit_cost': unit_cost,
                'quantity': initial_qty,
                'description': f'Initial Import - {product.name}',
                'stock_move_id': move.id,
                'company_id': self.env.company.id,
            })
            _logger.info(f"[VALUATION] Created for {product.name}: Qty={initial_qty}, Unit Cost={unit_cost}, Total Value={total_value}")

        return template


    # For updating Record of products
    @api.model
    def write(self, vals):
        res = super(MLProductTemplateInherit, self).write(vals)

        for template in self:
            _logger.info(f"Product Update (write) is happening for: {template.name}")

            initial_qty = vals.get('initial_quantity', 0.0)
            product = template.product_variant_id
            standard_price = vals.get('standard_price', 0.0) or template.standard_price

            # Vendor location (source)
            vendor_location = self.env.ref('stock.stock_location_suppliers', raise_if_not_found=False)
            if not vendor_location:
                raise UserError("Vendor Location (stock.stock_location_suppliers) not found!")

            # Destination: Either LN or VM stock
            location_lncr = self.env['stock.location'].search([('complete_name', '=', 'LN MF/Stock')], limit=1)
            location_vismin = self.env['stock.location'].search([('complete_name', '=', 'VM MF/Stock')], limit=1)

            # Location name from vals
            location_name = vals.get('location_name')
            _logger.info(f"Location Name: {location_name}")
            location = False

            if location_name == 'ln_ml_stock':
                location = location_lncr
                _logger.info("Location to be used is LN MF/Stock")
            elif location_name == 'vm_ml_stock':
                location = location_vismin
                _logger.info("Location to be used is VM MF/Stock")

            if location:
                _logger.info(f"Location to be used: {location.complete_name}")

            if product and initial_qty > 0 and location:
                # Check for existing quant
                quant = self.env['stock.quant'].search([
                    ('product_id', '=', product.id),
                    ('location_id', '=', location.id),
                ], limit=1)

                if quant and quant.quantity + initial_qty < 0:
                    raise UserError(
                        f"Cannot create stock move for {product.name}. "
                        f"The resulting on-hand quantity would be negative."
                    )

                _logger.info(f"[INIT STOCK][WRITE] Creating Stock Move for: {product.name}, Qty: {initial_qty} to {location.complete_name}")

                move = self.env['stock.move'].create({
                    'name': f'Update Import - {product.name}',
                    'product_id': product.id,
                    'product_uom_qty': initial_qty,
                    'product_uom': product.uom_id.id,
                    'location_id': vendor_location.id,
                    'location_dest_id': location.id,
                    'state': 'draft',
                })
                move._action_confirm()

                move_line = self.env['stock.move.line'].create({
                    'move_id': move.id,
                    'product_id': product.id,
                    'product_uom_id': product.uom_id.id,
                    'quantity': initial_qty,
                    'location_id': vendor_location.id,
                    'location_dest_id': location.id,
                    'state': 'done'
                })

                move._action_done()

                # Update or create stock quant
                if quant:
                    quant.quantity += initial_qty
                    quant.inventory_quantity += initial_qty
                    # quant.unit_cost = standard_price
                    # quant.inventory_value = quant.quantity * standard_price
                else:
                    self.env['stock.quant'].create({
                        'product_id': product.id,
                        'location_id': location.id,
                        'quantity': initial_qty,
                        'inventory_quantity': initial_qty,
                    })
                _logger.info(f"[SUCCESS][WRITE] Stock Move, Move Line, and Quant updated for {product.name}, Qty: {initial_qty}, Location: {location.complete_name}, Unit Cost: {standard_price}")
                move_line.update({'state': 'done'})

                unit_cost = template.purchase_price or product.standard_price or 0.0
                total_value = unit_cost * initial_qty

                # Inventory Valuation Journal Entry
                valuation_amount = unit_cost * initial_qty
                valuation_moves = []

                # journal_entry = self.env['account.move'].create({
                #     'journal_id': self.env['account.journal'].search(
                #         [('type', '=', 'general'), ('name', '=', 'Inventory Valuation')], limit=1
                #     ).id,
                #     'date': fields.Date.today(),
                #     'ref': f"Stock Valuation (Update) - {template.name}",
                #     'line_ids': [
                #         (0, 0, {
                #             'account_id': template.categ_id.property_stock_valuation_account_id.id,
                #             'debit': valuation_amount,
                #             'credit': 0,
                #             'name': template.name,
                #         }),
                #         (0, 0, {
                #             'account_id': template.categ_id.property_stock_account_output_categ_id.id,
                #             'debit': 0,
                #             'credit': valuation_amount,
                #             'name': template.name,
                #         }),
                #     ]
                # })

                # journal_entry.action_post()
                # valuation_moves.append(journal_entry.id)

                # for item in valuation_moves:
                #     _logger.info(f"[SUCCESS][WRITE] Mga laman ni Valuation {item}")

                # self.env['stock.valuation.layer'].create({
                #     'product_id': product.id,
                #     'value': total_value,
                #     'unit_cost': unit_cost,
                #     'quantity': initial_qty,
                #     'description': f'Update Import - {product.name}',
                #     'stock_move_id': move.id,
                #     'company_id': self.env.company.id,
                # })
                # _logger.info(f"[VALUATION][WRITE] Created for {product.name}: Qty={initial_qty}, Unit Cost={unit_cost}, Total Value={total_value}")

        return res
    # @api.constrains('name','default_code', 'item_code','item_description', 'purchase_price', 'debit_gl_code' )
    # def required_product_fields(self):
    #     if not self.default_code:
    #         raise UserError(f"Default Code is required!")
    #     if not self.item_code:
    #         raise UserError(f"Item Code is required!")






    # def _compute_nbr_moves(self):
    #     one_year_ago = fields.Datetime.now() - relativedelta(years=1)

    #     user = self.env.user  # Current logged-in user
    #     group_luzon = self.env.ref('ml_development.group_lncr_mods')
    #     group_vismin = self.env.ref('ml_development.group_vismin_mods')

    #     # Determine user's warehouse zone filter
    #     if group_vismin in user.groups_id:
    #         _logger.info(f"[VISMIN USER DETECTED, FILTERING FOR VISMIN WAREHOUSE ")
    #         is_zone = 'vismin'
    #     elif group_luzon in user.groups_id:
    #         print("LNCR User Detected - Filtering LNCR Warehouses")
    #         _logger.info(f"LNCR User Detected - Filtering LNCR Warehouses")
    #         is_zone = 'lncr'
    #     else:
    #         print("Admin User - No Filtering Applied (Shows All Warehouses)")
    #         is_zone = 'all'  # Admin sees all moves
    #         _logger.info(f"LNCR User Detected - Filtering LNCR Warehouses")

    #     # Get warehouse locations based on zone
    #     if is_zone == 'lncr':
    #         warehouse_ids = self.env['stock.warehouse'].search([('lncr', '=', True)]).mapped('lot_stock_id.id')
    #         _logger.info(f"WAREHOUSE ID IS LNCR")
    #     elif is_zone == 'vismin':
    #         warehouse_ids = self.env['stock.warehouse'].search([('vismin', '=', True)]).mapped('lot_stock_id.id')
    #         _logger.info(f"WAREHOUSE ID IS VISMIN")
    #     else:
    #         warehouse_ids = self.env['stock.warehouse'].search([]).mapped('lot_stock_id.id')  # Admin sees all
    #         _logger.info(f"WAREHOUSE ID IS ALL")

    #     print(f"Filtered Warehouse IDs: {warehouse_ids}")

    #     # Fetch all stock.move.line records related to this product template
    #     move_lines = self.env['stock.move.line'].search([
    #         ('product_id.product_tmpl_id', 'in', self.ids),
    #         ('state', 'in', ['confirmed', 'done']),
    #         ('location_dest_id', 'in', warehouse_ids),  # Inbound moves
    #     ])

    #     move_lines_out = self.env['stock.move.line'].search([
    #         ('product_id.product_tmpl_id', 'in', self.ids),
    #         ('state', 'in', ['confirmed', 'done']),
    #         ('location_id', 'in', warehouse_ids),  # Outbound moves
    #     ])

    #     # Initialize dictionary to store computed values
    #     res = defaultdict(lambda: {'moves_in': 0.0, 'moves_out': 0.0})

    #     # Retrieve warehouse zones
    #     warehouses_lncr = self.env['stock.warehouse'].search([('lncr', '=', True)])
    #     warehouses_vismin = self.env['stock.warehouse'].search([('vismin', '=', True)])

    #     # Process incoming stock moves
    #     _logger.info(f"SELF IDS: {self.ids} ALL MOVES IN: {warehouse_ids}")
    #     if move_lines:
    #         _logger.info(f"From receiving")
    #         for move_line in move_lines:

    #             product_tmpl_id = move_line.product_id.product_tmpl_id.id
    #             qty = move_line.quantity  

    #             if move_line.location_dest_id.usage == 'internal':
    #                 _logger.info(f"Internal ang operations")
    #                 if is_zone == 'lncr' and move_line.location_dest_id.warehouse_id in warehouses_lncr:
                    
    #                     res[product_tmpl_id]['moves_in'] += qty
    #                     _logger.info(f"MOVES IN: Qty: {qty} LNCR MOVES IN: {res[product_tmpl_id]['moves_in']}")
    #                 elif is_zone == 'vismin' and move_line.location_dest_id.warehouse_id in warehouses_vismin:
    #                     _logger.info(f"MOVES IN: Qty: {qty} VISMIN MOVES IN: {res[product_tmpl_id]['moves_in']}")
    #                     res[product_tmpl_id]['moves_in'] += qty
    #                 elif is_zone == 'all':  # Admin: No filtering
    #                     res[product_tmpl_id]['moves_in'] += qty
    #                     _logger.info(f"ALL: {qty} ALL MOVES IN: {res[product_tmpl_id]['moves_in']}")
    #             else:
    #                 _logger.info(f"NOT Internal ang operations")

    #     else:
    #         _logger.info("No incoming move lines found — Using initial quantities (first-time setup products)")

    #         # Create a dictionary to hold warehouse location IDs per zone
    #         zone_locations = {
    #             'lncr': [],
    #             'vismin': [],
    #             'all': []
    #         }

    #         # Populate based on warehouse zone
    #         if is_zone == 'lncr':
    #             zone_locations['lncr'] = [w.lot_stock_id.id for w in warehouses_lncr]
    #         elif is_zone == 'vismin':
    #             zone_locations['vismin'] = [w.lot_stock_id.id for w in warehouses_vismin]
    #         elif is_zone == 'all':
    #             all_warehouses = self.env['stock.warehouse'].search([])
    #             zone_locations['all'] = [w.lot_stock_id.id for w in all_warehouses]

    #         # Optional: log for verification
    #         _logger.info(f"ZONE LOCATIONS: {zone_locations}")


    #         for product in self:
    #             # Assuming you have a field named `initial_quantity` or similar on product.template
    #             qty = product.initial_quantity or 0.0
            
    #             warehouse_location_ids = zone_locations.get(is_zone, [])

    #             _logger.info(
    #             f"IS ZONE: {is_zone} | Qty: {qty} | Moves In: {res[product.id]['moves_in']} | warehouses_vismin: {[w.name for w in warehouses_vismin]} |  SELF IDS : {[self.ids]} | warehouse_location_ids :  {[warehouse_location_ids]} "
    #             )

    #                # Search for inbound move lines based on collected warehouse location_ids
    #             move_lines_in = self.env['stock.move.line'].search([
    #                 ('product_id', 'in', self.ids),   
    #                 ('state', 'in', ['confirmed', 'done']),
    #                 ('location_dest_id', 'in', warehouse_location_ids),
    #             ])

    #             # Search for outbound move lines
    #             move_lines_out = self.env['stock.move.line'].search([
    #                 ('product_id', 'in', self.ids),  
    #                 # ('state', 'in', ['confirmed', 'done']),
    #                 # ('location_id', 'in', warehouse_location_ids),
    #             ])
    #                  # Count quantities
    #             total_in = sum(move_line.quantity for move_line in move_lines_in)
    #             total_out = sum(move_line.quantity for move_line in move_lines_out)

    #             # Count quantities
    #             if move_lines_in :

    #                 total_in = sum(move_line.quantity for move_line in move_lines_in)

    #                 _logger.info(f"TOTAL IN: {total_in} ")
    #             else:
    #                 _logger.info( "Wala TOTAL IN")

    #             if move_lines_out :
    #                 total_out = sum(move_line.quantity for move_line in move_lines_out)
    #                 _logger.info(f"TOTAL IN: {total_out} ")
    #             else:
    #                 _logger.info( "Wala TOTAL OUT")
           

    #             product_tmpl_id = product.id  
    #             _logger.info(
    #                 f"PRODUCT: {product.name} | IS ZONE: {is_zone} | LOCATIONS USED: {warehouse_location_ids} | "
    #                 f"Initial Qty: {qty} | Moves IN: {total_in} | Moves OUT: {total_out}"
    #             )

    #             res[product_tmpl_id]['moves_in'] += qty
    #             res[product_tmpl_id]['moves_out'] += total_out 
    #             # Can you like append on something here the list of ids of location_ids of the companies that were checked here and its warehouses, 


    #             # if is_zone == 'lncr' and product.warehouse_id in warehouses_lncr:
    #             #     res[product.id]['moves_in'] += qty
    #             #     _logger.info(f"[LNCR - INITIAL] Product {product.name}: Qty: {qty}")
    #             # elif is_zone == 'vismin' and product.warehouse_id in warehouses_vismin:
    #             #     res[product.id]['moves_in'] += qty
    #             #     _logger.info(f"[VISMIN - INITIAL] Product {product.name}: Qty: {qty}")
    #             # elif is_zone == 'all':
    #             #     res[product.id]['moves_in'] += qty
    #             #     _logger.info(f"[ALL ZONES - INITIAL] Product {product.name}: Qty: {qty}")

    #     # Process outgoing stock moves
    #     for move_line in move_lines_out:
    #         product_tmpl_id = move_line.product_id.product_tmpl_id.id
    #         qty = move_line.quantity  

    #         if move_line.location_dest_id.usage == 'customer':
    #             if is_zone == 'lncr' and move_line.location_id.warehouse_id in warehouses_lncr:
    #                 res[product_tmpl_id]['moves_out'] += qty
    #             elif is_zone == 'vismin' and move_line.location_id.warehouse_id in warehouses_vismin:
    #                 res[product_tmpl_id]['moves_out'] += qty
    #             elif is_zone == 'all':  # Admin: No filtering
    #                 res[product_tmpl_id]['moves_out'] += qty

    #     # Assign computed values to each product template
    #     for template in self:
    #         template.nbr_moves_in = res[template.id]['moves_in']
    #         template.nbr_moves_out = res[template.id]['moves_out']

    #         print(f"Product {template.id} - Moves In: {template.nbr_moves_in}, Moves Out: {template.nbr_moves_out}")

    # def action_view_stock_move_lines(self):
    #     self.ensure_one()
    #     # Get the current user
    #     user = self.env.user
    #     group_luzon = self.env.ref('ml_development.group_lncr_mods')
    #     group_vismin = self.env.ref('ml_development.group_vismin_mods')

    #     # Determine the user's zone (LNCR / VISMIN) or None if admin
    #     if group_luzon in user.groups_id:
    #         is_zone = 'lncr'
    #     elif group_vismin in user.groups_id:
    #         is_zone = 'vismin'
    #     else:
    #         is_zone = None  # Admin case, no filtering

    #     # Define the domain filter
    #     domain = [('product_id.product_tmpl_id', '=', self.id)]
    #     if is_zone:
    #         domain.append(('zone', '=', is_zone))  # Filter by zone if applicable

    #     # Get the stock move line action
    #     action = self.env["ir.actions.actions"]._for_xml_id("stock.stock_move_line_action")
    #     action['domain'] = domain

    #     return action

    
    # @api.depends('stock_quant_ids')
    # def _compute_qty_available(self):
    #     """ Custom qty_available = On Hand - Outgoing Moves """
    #     for product in self:
    #         internal_locations = self.env['stock.location'].search([('usage', '=', 'internal')])

    #         # Get actual quantity on hand
    #         quants = self.env['stock.quant'].search([
    #             ('product_id', '=', product.id),
    #             ('location_id', 'in', internal_locations.ids)
    #         ])
    #         on_hand_qty = sum(quants.mapped('quantity'))

    #         # Get outgoing moves (not done yet)
    #         outgoing_moves = self.env['stock.move.line'].search([
    #             ('product_id', '=', product.id),
    #             ('location_id', 'in', internal_locations.ids),
    #             ('state', 'not in', ['done', 'cancel'])
    #         ])
    #         reserved_qty = sum(
    #             move.qty_done if move.qty_done > 0 else move.product_uom_qty
    #             for move in outgoing_moves
    #         )

    #         # Final available quantity
    #         product.qty_available = on_hand_qty - reserved_qty

    #         _logger.info(
    #             f"[{product.display_name}] On Hand: {on_hand_qty}, "
    #             f"Outgoing Reserved: {reserved_qty}, "
    #             f"Computed Available: {product.qty_available}"
    #         )
  
    @api.depends('product_variant_ids')
    def _compute_nbr_moves(self):
        user = self.env.user
        group_luzon = self.env.ref('ml_development.group_lncr_mods')
        group_vismin = self.env.ref('ml_development.group_vismin_mods')

        # Determine zone of user
        if group_vismin in user.groups_id:
            is_zone = 'vismin'
        elif group_luzon in user.groups_id:
            is_zone = 'lncr'
        else:
            is_zone = 'all'  # Admin

        # Warehouse filters
        if is_zone == 'lncr':
            warehouse_ids = self.env['stock.warehouse'].search([('lncr', '=', True)])
        elif is_zone == 'vismin':
            warehouse_ids = self.env['stock.warehouse'].search([('vismin', '=', True)])
        else:
            warehouse_ids = self.env['stock.warehouse'].search([])

        # Get internal stock locations (lot_stock_id)
        internal_location_ids = warehouse_ids.mapped('lot_stock_id.id')

        # Initialize result dict
        res = defaultdict(lambda: {'moves_in': 0.0, 'moves_out': 0.0})

        for template in self:
            variant_ids = template.product_variant_ids.ids

            # Stock moves IN
            move_lines_in = self.env['stock.move.line'].search([
                ('product_id', 'in', variant_ids),
                ('state', 'in', ['done', 'confirmed']),
                ('location_dest_id', 'in', internal_location_ids),
                ('location_dest_id.usage', '=', 'internal'),
            ])
            total_in = sum(move_line.quantity for move_line in move_lines_in)

            # Stock moves OUT (to customer or supplier)
            move_lines_out = self.env['stock.move.line'].search([
                ('product_id', 'in', variant_ids),
                ('state', 'in', ['done', 'confirmed']),
                ('location_id', 'in', internal_location_ids),
                '|',
                ('location_dest_id.usage', '=', 'customer'),
                ('location_dest_id.usage', '=', 'supplier'),
            ])
            total_out = sum(move_line.quantity for move_line in move_lines_out)

            res[template.id]['moves_in'] = total_in
            res[template.id]['moves_out'] = total_out

            # --- Update stock.quant per product variant individually ---
            for product in template.product_variant_ids:
                product_in = sum(move_lines_in.filtered(lambda m: m.product_id == product).mapped('quantity'))
                product_out = sum(move_lines_out.filtered(lambda m: m.product_id == product).mapped('quantity'))
                final_qty = product_in - product_out

                quant = self.env['stock.quant'].search([
                    ('product_id', '=', product.id),
                    ('location_id', 'in', internal_location_ids)
                ], limit=1)

                if quant:
                    quant.quantity = final_qty
                    _logger.info(f"Updated stock.quant → Product: {product.display_name}, Qty: {final_qty}")
                else:
                    self.env['stock.quant'].create({
                        'product_id': product.id,
                        'location_id': internal_location_ids[0] if internal_location_ids else False,
                        'quantity': final_qty,
                    })
                    _logger.info(f"Created stock.quant → Product: {product.display_name}, Qty: {final_qty}")

            _logger.info(f"[{template.name}] Zone: {is_zone} → Moves In Qty: {total_in}, Moves Out Qty: {total_out}")

        # Set fields for reporting
        for template in self:
            template.nbr_moves_in = res[template.id]['moves_in']
            template.nbr_moves_out = res[template.id]['moves_out']


class StockLocationInherit(models.Model):
    _inherit = 'stock.location'

    # Replace the customer Location with Branch Location
    usage = fields.Selection([
        ('supplier', 'Vendor Location'),
        ('view', 'View'),
        ('internal', 'Internal Location'),
        ('customer', 'Branch Location'),
        ('inventory', 'Inventory Loss'),
        ('production', 'Production'),
        ('transit', 'Transit Location')], string='Location Type',
        default='internal', index=True, required=True,
        help="* Vendor Location: Virtual location representing the source location for products coming from your vendors"
             "\n* View: Virtual location used to create a hierarchical structures for your warehouse, aggregating its child locations ; can't directly contain products"
             "\n* Internal Location: Physical locations inside your own warehouses,"
             "\n* Branch Location: Virtual location representing the destination location for products sent to your branch"
             "\n* Inventory Loss: Virtual location serving as counterpart for inventory operations used to correct stock levels (Physical inventories)"
             "\n* Production: Virtual counterpart location for production operations: this location consumes the components and produces finished products"
             "\n* Transit Location: Counterpart location that should be used in inter-company or inter-warehouses operations")
    
    lncr = fields.Boolean(string="LNCR")
    vismin = fields.Boolean(string="VisMin")

class ProductProductInherit(models.Model):
    _inherit = "product.product"

    default_code = fields.Char(
        related='product_tmpl_id.default_code',
        readonly=False
    )

class StockQuantInherit(models.Model):
    _inherit = 'stock.quant'

    isZone = fields.Char('USER ZONE')
    zone = fields.Selection([
        ('lncr', 'LNCR'),
        ('vismin', 'VISMIN'),
    ], string="Zone", store=True)
    
    @api.model
    def default_get(self, fields_list):
        defaults = super(StockQuantInherit, self).default_get(fields_list)
        user = self.env.user  # Current logged-in user
        group_luzon = self.env.ref('ml_development.group_lncr_mods')
        group_vismin = self.env.ref('ml_development.group_vismin_mods')

        if group_vismin in user.groups_id:
            print("VISMIN")
            self.isZone = 'vismin'

            # values['isZone'] = 'vismin'
        elif group_luzon in user.groups_id:
            # values['isZone'] = 'lncr'
            print("LNCR") 
            self.isZone = 'lncr'
            
        else:
            # values['isZone'] = 'all'
            print("ALLL")
            self.isZone = 'all'
        return defaults

    @api.model
    def create(self, vals):
        _logger.info(f"[STOCK.QUANT CREATE] Creating quant with values: {vals}")

        # Optionally, you can add checks or modifications here
        # For example: auto-log if quantity is 0
        if vals.get('quantity', 0) == 0:
            _logger.warning("Creating a stock.quant with zero quantity.")
        return super(StockQuantInherit, self).create(vals)

class AccountMove(models.Model):
    _inherit = 'account.move'

    picking_id = fields.Many2one('stock.picking', string="Picking")

class UomCategoryInherit(models.Model):
    _inherit = 'uom.category'

    description = fields.Char('Description')


# Stock Srap Operations
class StockScrapInherit(models.Model):

    _inherit = 'stock.scrap'


    def action_validate(self):



        return super(StockScrapInherit, self).action_create_returns()



# Stock Return 

class StockReturnPicking(models.TransientModel):
    _inherit = 'stock.return.picking'

    return_reason = fields.Text(string="Return Reason")


    # def action_create_returns(self):

    #     self.ensure_one()
    #     picking = self.picking_id
    #     # raise UserError(_("No return picking type defined for this operation type."))
    #     # Use custom picking type (outgoing)
    #     return_type = picking.picking_type_id.return_picking_type_id
    #     if not return_type:
    #         raise UserError(_("No return picking type defined for this operation type."))

    #     # Create the return picking record
    #     new_picking = self.env['stock.picking'].create({
    #         'origin': _('Return of: %s') % picking.name,
    #         'picking_type_id': return_type.id,
    #         'location_id': return_type.default_location_src_id.id,
    #         'location_dest_id': return_type.default_location_dest_id.id,
    #         'partner_id': picking.partner_id.id,
    #     })

    #     # Loop through return lines
    #     for line in self.product_return_moves:
    #         if line.quantity <= 0:
    #             continue
    #         original_move = line.move_id
    #         return_move = original_move.copy({
    #             'product_uom_qty': line.quantity,
    #             'picking_id': new_picking.id,
    #             'state': 'draft',
    #             'location_id': return_type.default_location_src_id.id,
    #             'location_dest_id': return_type.default_location_dest_id.id,
    #         })
    #         # return_move._action_confirm()
    #         # return_move._action_assign()

    #     # Post message to chatter
    #     new_picking.message_post(body=_("Return created from %s") % picking.name)

    #     return {
    #         'type': 'ir.actions.act_window',
    #         'res_model': 'stock.picking',
    #         'view_mode': 'form',
    #         'res_id': new_picking.id,
    #         'target': 'current',
    #     }




# Entries for RFP Process


# def create_journal_entry_rfp(self):
#     for rfp in self:
#         amount = rfp.amount_total
#         debit_account = self.env['account.account'].search([('name', '=', 'Accounts Payable')], limit=1)
#         credit_account = self.env['account.account'].search([('name', '=', 'Accrued Expense')], limit=1)

#         journal_entry = self.env['account.move'].create({
#             'journal_id': self.env['account.journal'].search([('type', '=', 'general'), ('name', '=', 'RFP Journal')], limit=1).id,
#             'date': fields.Date.today(),
#             'ref': f"RFP - {rfp.name}",
#             'rfp_id': rfp.id,  # Optional if you want to link it
#             'line_ids': [
#                 (0, 0, {
#                     'account_id': debit_account.id,
#                     'debit': amount,
#                     'credit': 0,
#                     'name': 'RFP Entry',
#                 }),
#                 (0, 0, {
#                     'account_id': credit_account.id,
#                     'debit': 0,
#                     'credit': amount,
#                     'name': 'RFP Entry',
#                 }),
#             ]
#         })
#         rfp.write({'account_move_id': journal_entry.id})
#         journal_entry.action_post()


# def create_journal_entry_payment(self):
#     for payment in self:
#         amount = payment.amount_paid
#         debit_account = self.env['account.account'].search([('name', '=', 'Accounts Payable')], limit=1)
#         credit_account = self.env['account.account'].search([('name', '=', 'Cash/Bank')], limit=1)

#         journal_entry = self.env['account.move'].create({
#             'journal_id': self.env['account.journal'].search([('type', '=', 'bank'), ('name', '=', 'Payment Journal')], limit=1).id,
#             'date': fields.Date.today(),
#             'ref': f"Payment - {payment.name}",
#             'payment_id': payment.id,  # Optional
#             'line_ids': [
#                 (0, 0, {
#                     'account_id': debit_account.id,
#                     'debit': amount,
#                     'credit': 0,
#                     'name': 'Payment Entry',
#                 }),
#                 (0, 0, {
#                     'account_id': credit_account.id,
#                     'debit': 0,
#                     'credit': amount,
#                     'name': 'Payment Entry',
#                 }),
#             ]
#         })
#         payment.write({'account_move_id': journal_entry.id})
#         journal_entry.action_post()

class Company(models.Model):
    _inherit = "res.company"

    @api.model
    def create(self, vals):
        company = super(Company, self).create(vals)
        # Add the following line to avoid user error: Incompatible companies on records.
        company.partner_id.company_id = False
        return company
