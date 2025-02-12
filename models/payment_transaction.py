from odoo import api, fields, models, _
import logging
_logger = logging.getLogger(__name__)

class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    negdi_transaction_ref = fields.Char(string='NEGDi Transaction Reference')

    def _get_specific_processing_values(self, processing_values):
        """ Hook for sub-modules to implement.
        """
        if self.provider_code != 'negdi':
            return super()._get_specific_processing_values(processing_values)

        processing_values['negdi_transaction_ref'] = self.negdi_transaction_ref
        return processing_values

    def _send_payment_request(self):
        """ Override of payment to send the payment request to the provider.
        """
        res = super()._send_payment_request()
        if self.provider_code != 'negdi':
            return res

        # Simulate a successful payment and store a dummy transaction reference
        self.negdi_transaction_ref = 'NEGDI-DEMO-' + self.reference
        self._set_pending() # Set pending if you want to simulate an intermediate step.

        return res

    def _process_s2s_digital_payment(self, processing_values):
        """ Override of payment to process a s2s digital payment.
        """
        res = super()._process_s2s_digital_payment(processing_values)
        if self.provider_code != 'negdi':
            return res

        # Mark the transaction as done (successful)
        self._set_done()

        return res

    @api.model
    def _get_available_providers(self, company=None, mode=None, currency_id=None, invoice=None):
        """ Hook for sub-modules to implement. """
        providers = super()._get_available_providers(company=company, mode=mode, currency_id=currency_id, invoice=invoice)
        if not company:
            company = self.env.company
        return providers