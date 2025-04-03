# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Payment Provider: NEGDi',
    'version': '2.0',
    'category': 'Hidden',
    'sequence': 350,
    'summary': "A payment provider for running fake payment flows for negdi purposes.",
    'description': " ",  # Non-empty string to avoid loading the README file.
    'depends': ['payment'],
    'data': [
        'views/payment_negdi_templates.xml',
        'views/payment_provider_views.xml',
        'views/payment_token_views.xml',
        'views/payment_transaction_views.xml',

        'data/payment_method_data.xml',
        'data/payment_provider_data.xml',  # Depends on `payment_method_negdi`.
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'assets': {
        'web.assets_frontend': [
            'payment_negdi/static/src/js/**/*',
        ],
    },
    'license': 'LGPL-3',
}
