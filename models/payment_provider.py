from odoo import models, fields, api
import requests
import json

class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    provider_code = fields.Char(string='Provider Code', default='negdi', readonly=True)
    negdi_terminal_id = fields.Char(string='Negdi Terminal ID', required_if_provider='negdi', groups='payment.group_payment_acquirer_manager')
    negdi_username = fields.Char(string='Negdi Username', required_if_provider='negdi', groups='payment.group_payment_acquirer_manager')
    negdi_password = fields.Char(string='Negdi Password', required_if_provider='negdi', groups='payment.group_payment_acquirer_manager')
    # ... other Negdi-specific fields

    def _get_supported_currencies(self):
        return ['MNT']  # Negdi supports MNT according to the spec

    def _get_payment_methods(self):
        return ['negdi']

    def _create_payment_transaction(self, data):
        transaction = self.env['payment.transaction'].create(data)
        return transaction

    def _get_negdi_payment_url(self, transaction):
        url = 'http://103.229.177.10:8032/api/pay/ec1000'
        payload = {
            'ordertype': '3dsOrder',  # Or another appropriate order type
            'terminalid': self.negdi_terminal_id,
            'username': self.negdi_username,
            'password': self.negdi_password,
            'returnurl': f'{self.env.cr.dbname}.negdi_payment_controller/payment/negdi/redirect',  # Important! Full URL
            'amount': transaction.amount,
            'currency': transaction.currency_id.name, # MNT
            'ordernum': transaction.reference,  # Or a separate order number
            'description': 'Order Payment', # Example
        }

        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
            negdi_data = response.json()
            transaction.write({'negdi_tranid': negdi_data.get('order', {}).get('tranid'), 'negdi_checkid': negdi_data.get('order', {}).get('checkid')})
            return negdi_data.get('order', {}).get('negdiurl')
        except requests.exceptions.RequestException as e:
            transaction.write({'state': 'error', 'acquirer_reference': str(e)})  # Store error
            return False


    def negdi_payment(self, transaction, **kwargs):
        # After redirect from Negdi, do Inquiry Order to get the final status
        tranid = transaction.negdi_tranid
        checkid = transaction.negdi_checkid
        if not tranid or not checkid:
            transaction.write({'state': 'error', 'acquirer_reference': 'Missing tranid or checkid'})
            return False

        inquiry_url = 'http://103.229.177.10:8032/api/pay/inquiry'  # Replace with the correct Inquiry URL
        inquiry_payload = {
            'terminalid': self.negdi_terminal_id,
            'username': self.negdi_username,
            'password': self.negdi_password,
            'tranid': tranid,
            'checkid': checkid,
        }
        try:
            inquiry_response = requests.post(inquiry_url, json=inquiry_payload)
            inquiry_response.raise_for_status()
            inquiry_data = inquiry_response.json()
            order_status = inquiry_data.get('order', {}).get('status')  # Adjust based on the actual response structure

            if order_status == 'success': # Check the correct success status from negdi documentation
                transaction.write({'state': 'done'})
                return True
            else:
                transaction.write({'state': 'error', 'acquirer_reference': f"Negdi payment failed: {order_status}"})
                return False

        except requests.exceptions.RequestException as e:
            transaction.write({'state': 'error', 'acquirer_reference': str(e)})
            return False
