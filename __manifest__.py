{
    'name': 'Negdi Payment Provider',
    'version': '1.0',
    'summary': 'Negdi Payment Gateway Integration',
    'description': """
        Provides integration with the Negdi payment gateway.
    """,
    'category': 'Accounting/Payment Providers',
    'author': 'Buyanmunkh Volodya',  # Replace with your name
    'depends': ['payment'],
    'data': [
        'views/payment_provider_views.xml',
        # 'data/payment_provider_data.xml',  # Optional - for default config
    ],
    'installable': True,
    'license': 'LGPL-3',  # Or your preferred license
}