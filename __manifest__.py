{
    'name': 'NEGDi Payment Provider',
    'version': '1.0',
    'summary': 'NEGDi Payment Gateway Integration with Odoo (Demo)',
    'description': """
        Provides a demo/example payment provider integration with Odoo, refactored for NEGDi.
    """,
    'category': 'Accounting/Payment Providers',
    'author': 'Buyanmunkh Volodya',  # Replace with your name
    'depends': ['payment'],
    'data': [
        'views/payment_provider_views.xml',
        # 'data/payment_provider_data.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'license': 'LGPL-3',  # Or your preferred license
}