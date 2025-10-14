from odoo import api, models, fields, _
import logging
_logger = logging.getLogger(__name__)

class CompanyInherit(models.Model):
    _inherit = 'res.company'

    # one2many field here for branches 
    branch_ids = fields.One2many('res.company.branches', 'company_id', string="Branches")

    @api.model
    def create(self, vals):
        company = super(CompanyInherit, self).create(vals)
        # Add the following line to avoid user error: Incompatible companies on records.
        company.partner_id.company_id = False # or you can make it = False
        return company

class CompanyBranches(models.Model):
    _name = 'res.company.branches'
    _description = 'Company Branches'
    _rec_name = 'branch_name'

    branch_name = fields.Char(string="Branch Name")
    branch_id = fields.Char(string="Branch ID")
    area = fields.Char(string="Area")
    area_id = fields.Char(string="Area ID")
    region = fields.Char(string="Region")
    region_id = fields.Char(string="Region ID")
    zone = fields.Selection([
        ('luzon', 'LUZON'),
        ('ncr', 'NCR'),
        ('visayas', 'VISAYAS'),
        ('mindanao', 'MINDANAO')
    ], string="Zone")
    zone_id = fields.Char('Zone ID')
    status = fields.Selection([
        ('active', 'ACTIVE'),
        ('inactive', 'INACTIVE')
    ], string="Status")
    company_id = fields.Many2one('res.company', string="Company")
    head_office = fields.Boolean('Head Office')
    tin = fields.Char('TIN')

    location_dest_id = fields.Many2one(
        'stock.location', 
        string='Branch Stock Location', 
        domain="[('usage', '=', 'customer')]"
    )
    branch_email = fields.Char('Branch Email')
    partner_id = fields.Many2one('res.partner', string="Branch Contact")  
    # location_dest_id or something, it will  be a record for the location_dest_id = fields.Many2one('stock.location', string='Branch Location', domain="[('usage', '=', 'customer')]",  required=True) 
    # default get when i def create here dapat ang value ng location_dest_id is search sa location yung may same company, same warehouse na may naka assign bale if the zone is either 'luzon' or 'ncr' then yung location na same sa company niya then    ('usage', '=', 'customer') ang magiging value ng location_dest_id, 
    # branch_contact = fields.Many2one('branch.managers', 'Branch Email')
    am_email = fields.Many2one('res.partner', 'ML AM')
    rm_email = fields.Many2one('res.partner',"ML RM")
    abm_email = fields.Many2one('res.partner',"ML ABM")

    branch_manager_id = fields.Many2one(
        'branch.managers',
        string="Branch Manager",
        help="Branch Manager linked to this branch"
    )


    @api.model
    def create(self, vals):
        # Your logic here
        if self.env.context.get('import_file'):
            _logger.info("[IMPORT][CREATE] Creating Branch: %s",  vals.get('branch_name'))
        else:
            _logger.info("[MANUAL][CREATE] Creating Branch: %s", vals.get('branch_name'))
        return super().create(vals)

    def write(self, vals):
        # Only do the extra lookups/assignments if we're in an import context
        if self.env.context.get('import_file'):
            # Build a copy of `vals` so we can inject partner_id/am_email without recursion
            updated_vals = dict(vals)

            for record in self:
                # ────────────────────────────────────────────────────────────────────────────
                # 1) BRANCH MANAGER → partner_id
                # ────────────────────────────────────────────────────────────────────────────
                updated_branch_name = vals.get('branch_name', record.branch_name)
                if updated_branch_name:
                    _logger.info("[IMPORT][WRITE] Branch Name from Excel: %s", updated_branch_name)

                    manager_match = self.env['branch.managers'].sudo().search([
                        ('branch_name', '=', updated_branch_name)
                    ], limit=1)

                    if manager_match:
                        _logger.info(
                            "[FOUND] Branch Manager: %s (ID: %s)",
                            manager_match.complete_name,
                            manager_match.id
                        )

                        partner_match = self.env['res.partner'].sudo().search([
                            ('name', '=', manager_match.complete_name)
                        ], limit=1)

                        if partner_match:
                            # Only set partner_id if this record doesn’t already have one
                            if not record.partner_id:
                                _logger.info(
                                    "[MATCH] Will assign partner_id = %s (ID: %s) to Branch ID %s",
                                    partner_match.name, partner_match.id, record.id
                                )
                                # Instead of record.partner_id = partner_match.id, update updated_vals:
                                updated_vals['partner_id'] = partner_match.id
                            else:
                                _logger.info(
                                    "[SKIPPED] Branch already has contact: %s (ID: %s)",
                                    record.partner_id.name,
                                    record.partner_id.id
                                )
                        else:
                            _logger.info(
                                "[NOT FOUND] No contact in res.partner for manager: %s",
                                manager_match.complete_name
                            )
                    else:
                        _logger.info(
                            "[NOT FOUND] No Branch Manager for branch: %s",
                            updated_branch_name
                        )

                # ────────────────────────────────────────────────────────────────────────────
                # 2) AREA REGION MANAGER → am_email
                # ────────────────────────────────────────────────────────────────────────────
                updated_region = vals.get('region', record.region)
                if updated_region:
                    _logger.info("[IMPORT][WRITE] Region from Excel: %s", updated_region)

                    area_mgr_match = self.env['area.region.managers'].sudo().search([
                        ('region_name', '=', updated_region)
                    ], limit=1)

                    if area_mgr_match:
                        _logger.info(
                            "[FOUND] Region Manager: %s (Region: %s)",
                            area_mgr_match.complete_name,
                            updated_region
                        )
                        region_partner = self.env['res.partner'].sudo().search([
                            ('name', '=', area_mgr_match.complete_name)
                        ], limit=1)

                        if region_partner:
                            _logger.info(
                                "[MATCH] Will assign am_email = %s (ID: %s) for Region",
                                region_partner.name,
                                region_partner.id
                            )
                            updated_vals['am_email'] = region_partner.id
                        else:
                            _logger.info(
                                "[NOT FOUND] No contact in res.partner for region manager: %s",
                                area_mgr_match.complete_name
                            )
                    else:
                        _logger.info(
                            "[NOT FOUND] No Area Region Manager for region: %s",
                            updated_region
                        )
                else:
                    _logger.info(
                        "[SKIPPED] No region value found in imported file for Branch ID %s",
                        record.id
                    )
                
            # ────────────────────────────────────────────────────────────────────────────
            # 3) ABM MANAGER → abm_email
            # ────────────────────────────────────────────────────────────────────────────

             # ────────────────────────────────────────────────────────────────────────────
                # 3) ABM (ml.abm) → ml_abb
                # ────────────────────────────────────────────────────────────────────────────
                # Gagamitin din natin ang 'branch_name' mula sa Excel para mag-search sa ml.abm.
                if updated_branch_name:
                    _logger.info("[IMPORT][WRITE] ABM Step: Branch Name from Excel: %s", updated_branch_name)

                    # Hanapin sa ml.abm model (field: branch_name)
                    abm_match = self.env['ml.abm'].sudo().search([
                        ('branch_name', '=', updated_branch_name)
                    ], limit=1)

                    if abm_match:
                        _logger.info(
                            "[FOUND] ABM Record: %s (ID: %s)",
                            abm_match.complete_name,
                            abm_match.id
                        )
                        # Gamitin ang abm_match.complete_name para maghanap sa res.partner
                        abm_partner = self.env['res.partner'].sudo().search([
                            ('name', '=', abm_match.complete_name)
                        ], limit=1)

                        if abm_partner:
                            if not record.ml_abb:
                                _logger.info(
                                    "[MATCH] Will assign ml_abb = %s (ID: %s) to Branch ID %s",
                                    abm_partner.name, abm_partner.id, record.id
                                )
                                updated_vals['ml_abb'] = abm_partner.id
                            else:
                                _logger.info(
                                    "[SKIPPED] Branch already has ml_abb: %s (ID: %s)",
                                    record.ml_abb.name,
                                    record.ml_abb.id
                                )
                        else:
                            _logger.info(
                                "[NOT FOUND] No contact in res.partner for ABM name: %s",
                                abm_match.complete_name
                            )
                    else:
                        _logger.info(
                            "[NOT FOUND] No ABM record for branch: %s in ml.abm",
                            updated_branch_name
                        )
            # Call super.write WITHOUT the import_file flag to avoid recursion
            return super(CompanyBranches, self.with_context(import_file=False)).write(updated_vals)

        # If not in import context, do the normal write:
        return super(CompanyBranches, self).write(vals)