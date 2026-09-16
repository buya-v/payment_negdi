{
    'name': 'Payment Provider: NEGDI',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Payment Providers',
    'sequence': 350,
    'summary': "Mongolian card (3-D Secure) and QPay payments through the NEGDI e-commerce gateway.",
    'description': " ",  # non-empty, so the README is not loaded as the description
    'author': 'ITAUCO',
    'website': 'https://github.com/buya-v/payment_negdi',
    'depends': ['payment'],
    'data': [
        'views/payment_negdi_templates.xml',
        'views/payment_provider_views.xml',
        'data/payment_method_data.xml',
        'data/payment_provider_data.xml',
        'data/ir_cron_data.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'images': ['static/description/banner.png'],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
