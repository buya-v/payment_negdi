{
    'name': "Payment Provider: NEGDi Payment Services",
    'version': '1.0',
    'author': 'Buya Volodya', 
    'category': 'Accounting/Payment Providers',
    'sequence': 350,
    'summary': "An NEGDi payment provider in Mongolia.",
    'description': 
    """ 
    NEGDi is a payment processor company having card issuing and acquiring licenses 
    from Bank of Monngolia.
    To use this module, you should contact with NEGDi and need to get credentials.
    - Username
    - Password 
    - Terminal ID

    Contact: hello@negdi.mn

    """,  # Non-empty string to avoid loading the README file.
    'depends': ['payment','website'],
    'data': [
        'data/payment_method_data.xml',
        'data/payment_provider_data.xml',
        # 'views/payment_negdi_templates.xml',
        'views/payment_provider_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'payment_negdi/static/src/js/payment_form.js',
        ],
    },
    'icon': '/payment_negdi/static/description/icon.png',
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'license': 'LGPL-3',
    'price': 49.99,
    'currency': 'USD',
}
