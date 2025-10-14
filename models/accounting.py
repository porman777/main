# The model for accounting related transactions
from odoo import api, models, fields
 
class AccountAccountInherit(models.Model):
    _inherit = "account.account"

    account_id = fields.Char(string='Account ID')
    current_account_code = fields.Char(string='Current Account ID')
    fs_account_type= fields.Selection(
        selection=[
            ('balance', 'Balance Sheet'),
            ('asset', 'Asset'),
            ('income_statement', 'Income Statement'),
        ],
        string="FS Account Type"
    )
    normal_balance = fields.Selection(
        selection=[
            ('dr', 'DR'),
            ('cr', 'CR'),
        ],
        string="Normal Balance"
    )
    isdefault = fields.Boolean(string='Is Default')
    account_type = fields.Selection(
        selection=[
            ("asset_receivable", "Receivable"),
            ("asset_cash", "Bank and Cash"),
            ("asset_current", "Current Assets"),
            ("asset_non_current", "Non-current Assets"),
            ("asset_prepayments", "Prepayments"),
            ("asset_fixed", "Fixed Assets"),
            ("liability_payable", "Payable"),
            ("liability_credit_card", "Credit Card"),
            ("liability_current", "Current Liabilities"),
            ("liability_non_current", "Non-current Liabilities"),
            ("equity", "Equity"),
            ("equity_unaffected", "Current Year Earnings"),
            ("income", "Income"),
            ("forex_income", "Forex Income"),
            ("income_other", "Other Income"),
            ("expense", "Expenses"),
            ("expense_ho_expense", "HO Expenses"),
            ("expense_depreciation", "Depreciation"),
            ("expense_direct_cost", "Cost of Revenue"),
            ("off_balance", "Off-Balance Sheet"),
            ("expense_cost_of_sales", "Cost of Sales"),
            ("expense_general_and_administrative_expense", "General and Administrative Expenses"),
            ("income_sales", "Sales"),
            ("income_sales_contra", "Sales (Contra)"),
            ("income_revenue", "Revenue"),
            ("service_revenue", "Service Revenue"),
            ("asset_non_current_assets_contra", "Non-current Assets (Contra)"),
            ("asset_other_non_current_assets", "Other Non-current Assets"),
            ("asset_non_current_liablities", "Non Current Liabilities"),
            ("asset_current_assets", "Current Asset (Contra)"),
            ("ml_asset_current", "Current Asset"),
            ("ml_asset_non_current", "Non Current Asset"),
            ("ml_asset_non_current_contra", "Non Current Asset (Contra)"),
            ("ml_other_non_current_asset", "Other Non Current Asset"),
        ],
        string="Category", tracking=True,
        required=True,
        compute='_compute_account_type', store=True, readonly=False, precompute=True, index=True,
        help="Account Type is used for information purpose, to generate country-specific legal reports, and set the rules to close a fiscal year and generate opening entries."
    )
    # internal_group = fields.Selection(
    #     selection=[
    #         ('equity', 'Equity'),
    #         ('asset', 'Asset'),
    #         ('liability', 'Liability'),
    #         ('income', 'Income'),
    #         ('expense', 'Expense'),
    #         ('off_balance', 'Off Balance'),
    #         ('revenue', 'Revenue'),
    #     ],
    #     string="Internal Group",
    #     compute="_compute_internal_group", store=True, precompute=True,
    # )
    account_subtype =  fields.Char(string='Subtype')
    acc_type = fields.Char(string='Account Type')
    account_category = fields.Char(string='Account Category')
    
    @api.depends('account_type')
    def _compute_include_initial_balance(self):
        for account in self:
            account.include_initial_balance = account.account_type not in ('income', 'income_other', 'expense', 'expense_depreciation', 'expense_direct_cost', 'off_balance',  'revenue')