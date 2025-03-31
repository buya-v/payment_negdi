from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging
import datetime
from werkzeug import urls
from . import const
from controllers import NegdiController

_logger = logging.getLogger(__name__)

class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    negdi_tranid = fields.Char(string='NEGDI Transaction ID', help="Transaction ID from NEGDI")
    negdi_checkid = fields.Char(string='NEGDI Check ID', help="Check ID from NEGDI")
    negdi_order_num = fields.Char(string='NEGDI order num', help="NEGDI internal order number")
    negdi_payment_type = fields.Selection(
        selection=[
            ('card', 'Card'),
            ('token', 'Token'),
        ],
        string='Payment Type',
        readonly=True
    )

    def _get_specific_processing_values(self, processing_values):
        """ Hook for sub-modules to implement.
        """
        if self.provider_code != 'negdi':
            return super()._get_specific_processing_values(processing_values)

        processing_values['negdi_tranid'] = self.negdi_tranid
        processing_values['negdi_checkid'] = self.negdi_checkid
        return processing_values

    def _negdi_build_request_data(self, endpoint):
        """Build the base request data for NEGDI API calls.

        :param str endpoint: The API endpoint to call.
        :return: A dictionary with the base request data.
        :rtype: dict
        """
        self.ensure_one()
        provider = self.provider_id
        data = {
            'terminalid': provider.negdi_terminal_id,
            'username': provider.negdi_username,
            'password': provider.negdi_password,
        }
        return data

    def _negdi_create_order(self, order_type):
        """Create an order on NEGDI.  Handles ec1000, ec1001, ec1002.

        :param str order_type: The NEGDI order type ('3dsOrder', 'Non3dsOrder', etc.)
        :return: The NEGDI API response.
        :rtype: dict
        """
        self.ensure_one()
        provider = self.provider_id

        api_url = provider._get_negdi_api_url()  # Get the API URL from the provider
        endpoint = const.API_ENDPOINT_CREATE_ORDER
        data = self._negdi_build_request_data(endpoint)
        data.update({
            'ordertype': order_type,
            'amount': self.amount,
            'currency': self.currency_id.name,
            'returnurl': self.get_base_url() + NegdiController._return_url,  # Update with your actual return URL
            'ordernum': self.reference, # Use the Odoo transaction reference as the NEGDI order number
            'description': f'Odoo Order {self.reference}',
        })

        if endpoint == 'ec1001':  # Add customer info for TOKEN creation
            data.update({
                'customerid': self.partner_id.id or 'guest',  # Use partner ID or 'guest'
                'customername': self.partner_id.name or 'Guest',
            })
        elif endpoint == 'ec1002':
             data.update({
                'customerid': self.partner_id.id or 'guest',  # Use partner ID or 'guest'
                'customername': self.partner_id.name or 'Guest',
            })

        response = provider._negdi_make_request(endpoint, data)
        return response

    def _negdi_process_order(self):
        """Process an existing order (ec1003)."""
        self.ensure_one()
        provider = self.provider_id

        api_url = provider._get_negdi_api_url() #Get the API URL from the provider
        endpoint = const.API_ENDPOINT_PROCESS_ORDER
        data = self._negdi_build_request_data(endpoint)
        data.update({
            'tranid': self.negdi_tranid,
            'checkid': self.negdi_checkid,
            'amount': self.amount,
            'customerid': self.partner_id.id or 'guest'
        })

        response = provider._negdi_make_request(endpoint, data)
        return response

    def _negdi_cancel_order(self):
         """Cancel an order (ec1099)"""
         self.ensure_one()
         provider = self.provider_id

         api_url = provider._get_negdi_api_url() #Get the API URL from the provider
         endpoint = const.API_ENDPOINT_CANCEL_ORDER
         data = self._negdi_build_request_data(endpoint)
         data.update({
            'tranid': self.negdi_tranid,
            'username': provider.negdi_username,
            'password': provider.negdi_password,
            'amount': self.amount
         })
         response = provider._negdi_make_request(endpoint, data)
         return response

    def _negdi_inquiry_order(self):
         """Inquiry an order (ec1098)"""
         self.ensure_one()
         provider = self.provider_id

         api_url = provider._get_negdi_api_url() #Get the API URL from the provider
         endpoint = const.API_ENDPOINT_INQUIRY_ORDER
         data = self._negdi_build_request_data(endpoint)
         data.update({
            'tranid': self.negdi_tranid,
            'checkid': self.negdi_checkid,
         })
         response = provider._negdi_make_request(endpoint, data)
         return response

    def _negdi_cancel_token(self):
         """cancel a token (ec1097)"""
         self.ensure_one()
         provider = self.provider_id

         api_url = provider._get_negdi_api_url() #Get the API URL from the provider
         endpoint = const.API_ENDPOINT_CANCEL_TOKEN
         data = self._negdi_build_request_data(endpoint)
         data.update({
             'customerid': self.partner_id.id or 'guest',
             'tokenid': self.negdi_tranid, #the documentation does not specify any token id so i use the transaction id
         })
         response = provider._negdi_make_request(endpoint, data)
         return response

    def _negdi_inquiry_order_type(self):
         """inquiry order type (ec1096)"""
         self.ensure_one()
         provider = self.provider_id

         api_url = provider._get_negdi_api_url() #Get the API URL from the provider
         endpoint = const.API_ENDPOINT_INQUIRY_ORDER_TYPE
         data = self._negdi_build_request_data(endpoint)
         response = provider._negdi_make_request(endpoint, data)
         return response

    def _send_payment_request(self):
        """Override to initiate the payment with NEGDI."""
        res = super()._send_payment_request()
        if self.provider_code != 'negdi':
            return res

        # Choose the NEGDI endpoint and order type based on your requirements
        #Example create order with ec1000 and 3dsOrder type
        try:
            response = self._negdi_create_order(const.ORDER_TYPE_3DS)

            if response and response.get('order'):
                order = response.get('order')
                if order.get('tranid'):
                    self.negdi_tranid = order.get('tranid')
                    self.negdi_checkid = order.get('checkid')
                    negdi_status = order.get('status')

                    if negdi_status == 'Preparing' and response.get('order').get('negdiurl'):
                        negdi_url = response.get('order').get('negdiurl')
                        return {
                            'type': 'ir.actions.act_url',
                            'url': negdi_url,
                            'target': '_self',
                        }
                    else:
                        _logger.warning(f"NEGDI: Payment not in Preparing state or negdiurl not found. Status: {negdi_status}")
                        self._set_error(_("NEGDI: Payment process error. Please check logs."))

                else:
                     _logger.warning(f"NEGDI: No tranid in response: {response}")
                     self._set_error(_("NEGDI: Payment process error. Please check logs."))

            else:
                 _logger.warning(f"NEGDI: No response from NEGDI API: {response}")
                 self._set_error(_("NEGDI: No response from NEGDI API."))

        except Exception as e:
            _logger.exception("NEGDI: Error creating order: %s", str(e))
            self._set_error(_("NEGDI: Error creating order: %s") % str(e))

        return res

    def _process_s2s_digital_payment(self, processing_values):
        """Override to process the payment with NEGDI."""
        res = super()._process_s2s_digital_payment(processing_values)
        if self.provider_code != 'negdi':
            return res

        try:
            response = self._negdi_process_order()
            if response and response.get('order'):
                order = response.get('order')
                negdi_status = order.get('status')

                if negdi_status in ('Approved', 'Authorized', 'Funded', 'Fully paid'):
                   self._set_done()
                else:
                    _logger.warning(f"NEGDI: Payment failed with status: {negdi_status}")
                    self._set_error(f"NEGDI: Payment failed with status: {negdi_status}")
            else:
                 _logger.warning(f"NEGDI: No response from NEGDI API: {response}")
                 self._set_error(_("NEGDI: No response from NEGDI API."))

        except Exception as e:
            _logger.exception("NEGDI: Error processing order: %s", str(e))
            self._set_error(_("NEGDI: Error processing order: %s") % str(e))

        return res

    def _negdi_make_request(self, endpoint, data=None):
        """ Make a request to the NEGDI API. """
        import requests
        import json

        url = self._get_negdi_api_url() + endpoint  # Use the centralized URL method
        headers = {
            'Content-Type': 'application/json'
        }
        try:
            _logger.info("NEGDI Request URL: %s", url)
            _logger.info("NEGDI Request Data: %s", data)
            response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _logger.exception("NEGDI API Error: %s", str(e))
            raise UserError(_("NEGDI API Error: %s") % str(e))

    @api.model
    def _get_available_providers(self, company=None, mode=None, currency_id=None, invoice=None):
        """ Hook for sub-modules to implement. """
        providers = super()._get_available_providers(company=company, mode=mode, currency_id=currency_id, invoice=invoice)
        if not company:
            company = self.env.company
        return providers