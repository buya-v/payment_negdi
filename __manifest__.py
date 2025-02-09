{
    'name': 'NEGDi Payment Provider',
    'version': '1.0',
    'summary': 'NEGDi Payment Gateway Integration with Odoo',
    'description': """
        Provides integration with the Negdi payment gateway.
    """,
    'category': 'Accounting/Payment Providers',
    'author': 'Buyanmunkh Volodya',
    'depends': ['payment'],
    'data': [
        'views/payment_provider_views.xml',
        'data/payment_provider_data.xml',  # Optional - for default config
        'security/ir.model.access.csv' # Added security file
    ],
    'installable': True,
    'license': 'LGPL-3',  # Or your preferred license
}