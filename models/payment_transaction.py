from odoo import models, fields, api
import requests
import json

class PaymentTransactionNegdi(models.Model):
    _inherit = 'payment.transaction'

    negdi_checkid = fields.Char(string='Negdi Check ID')

    def _get_negdi_payment_status(self):
        credentials = self.provider_id._get_negdi_credentials()
        url = f"{credentials['api_url']}/api/pay/ec1000"
        headers = {'Content-Type': 'application/json'}
        data = {
            "tranid": self.acquirer_reference,
            "checkid": self.negdi_checkid,
        }
        response = requests.post(url, headers=headers, data=json.dumps(data))
        if response.status_code == 200:
            response_data = response.json().get("order", {})
            status = response_data.get("status")
            if status == "approved":
                self._set_done()
            elif status == "cancelled":
                self._set_canceled()
            else:
                self._set_error("Negdi: Payment failed")

    def _set_pending(self):
        super()._set_pending()
        self._get_negdi_payment_status()
