# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "Payment Provider: NEGDi Payment Services",
    'version': '1.0',
    'author': 'NEGDi Processor', 
    'category': 'Accounting/Payment Providers',
    'sequence': 350,
    'summary': "An NEGDi payment provider in Mongolia.",
    'description': " ",  # Non-empty string to avoid loading the README file.
    'depends': ['payment'],
    'data': [
        'views/payment_negdi_templates.xml',
        'views/payment_provider_views.xml',

        'data/payment_provider_data.xml',
    ],
    'icon': '/payment_negdi/static/description/icon.png',
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'license': 'LGPL-3',
}
