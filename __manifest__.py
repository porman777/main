{
    'name': 'ml_development',
    'version': '1.0',
    'author': 'ODIS',
    'category': 'Uncategorized',
    'summary': 'ODIS – Streamline Inventory, Expenses, Procurement & Financials',
    'license': 'OEEL-1',
    'description': """
        Welcome to ODIS
        Streamline your business with our easy-to-use platform.
        Your system is designed to help manage your business more efficiently.
        From managing Inventory, Expenses, Procurement, to Financial Reporting,
        ODIS simplifies your day-to-day operations and keeps everything in one secure platform.
    """,
    'depends': [
        'base',
        'web',
        'website',
        'web_studio',
        'mail',
        'account',
        'accountant',
        'purchase',
        'stock',
        'sale',
        'board',
        'contacts',
        'hr_expense'
    ],
    'assets': {
        'web.assets_backend': [
            'ml_development/static/src/scss/dashboard.scss',
            'ml_development/static/src/scss/custom_theme.scss',
            'ml_development/static/src/js/auto_check_company.js',
            'ml_development/static/src/css/approval_buttons.css',
        ],
        'web.assets_frontend': [
            'ml_development/static/src/scss/custom_login.scss',
          ],
    },
    'data': [
        # Security
        'security/security_groups.xml',
        'security/security_record_rules.xml',
        'security/ir.model.access.csv',

        # Data 
        'data/issuance_sequence.xml',
        'data/request_payments_seq.xml',
        'data/request_for_quotation_seq.xml',
        'data/report_paperformat.xml',
        'data/cancellation_request.xml',
        'data/purchase_order_seq.xml',

        # Reports 
        'report/purchase_order_request.xml',
        'report/purchase_order_report.xml',
        'report/receiving_report.xml',
        'report/request_for_payment_report.xml',
        'report/issuance_report.xml',
        'report/receiving_report_temp.xml',

        # Templates
        'views/components/confirmation_page.xml',
        'views/template/email/modify_purchase_email_template.xml',
        'views/template/email/mail_request_quotation.xml',
        'views/template/email/issuance_email_request.xml',
        'views/template/email/issuance_email_action.xml',

        # Wizards
        'wizard/res_approvers_wzrd.xml',
        'wizard/remarks_wzrd.xml',

        # Views
        'views/settings.xml',
        'views/request_for_quotation.xml',
        'views/request_for_payment.xml',
        'views/account_account.xml',
        'views/purchase_order.xml',
        'views/issuance_form.xml', 
        'views/res_company.xml',
        'views/product_supplierinfo.xml',   
        'views/ml.xml',
        'views/stock.xml',
        'views/res_partner.xml',
        'views/res_partner_bank.xml',
        'views/hr_expense.xml',
        'views/res_approvers.xml',
        'views/account_payment_term.xml',
    ],
    'installable': True,
    'application': False,
}