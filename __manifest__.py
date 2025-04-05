{
    'name': "Payment Provider: NEGDi Payment Services",
    'version': '1.0',
    'author': 'NEGDi Processor', 
    'category': 'Accounting/Payment Providers',
    'sequence': 350,
    'summary': "An NEGDi payment provider in Mongolia.",
    'description': " ",  # Non-empty string to avoid loading the README file.
    'depends': ['payment','website'],
    'data': [
        # 'views/payment_negdi_templates.xml',
        'views/payment_provider_views.xml',

        'data/payment_provider_data.xml',
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
}
