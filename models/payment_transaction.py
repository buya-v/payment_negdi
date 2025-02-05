from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Add the fields to the payment.transaction model
class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    negdi_tranid = fields.Char(string='Negdi Transaction ID')
    negdi_checkid = fields.Char(string='Negdi Check ID')