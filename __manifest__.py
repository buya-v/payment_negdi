{
    'name': 'NEGDi Payment Provider',
    'version': '1.0',
    'summary': 'NEGDi Payment Gateway Integration with Odoo',
    'description': """
        Provides integration with the NEGDi payment gateway.
    """,
    'category': 'Accounting/Payment Providers',
    'author': 'Buyanmunkh Volodya',
    'depends': ['payment', 'account'],  # Added 'account' dependency
    'data': [
        'security/ir.model.access.csv',
        'views/payment_provider_views.xml',
        'data/payment_provider_data.xml',
        'views/payment_transaction_views.xml',  # Added transaction views
    ],
    'assets': {
        'web.assets_frontend': [
            'payment_negdi/static/src/js/payment_form.js', #Added JS file
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}