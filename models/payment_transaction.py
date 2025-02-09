from odoo import models, fields, api

class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    negdi_tranid = fields.Char(string="NEGDI Transaction ID")
    negdi_checkid = fields.Char(string="NEGDI Check ID")

    def _process_notification_data(self, notification_data):
        super()._process_notification_data(notification_data)
        if self.provider_code != 'negdi':
            return

        self.negdi_tranid = notification_data.get('tranid')
        self.negdi_checkid = notification_data.get('checkid')
        self._set_done()