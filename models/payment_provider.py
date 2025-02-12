from odoo import api, fields, models, _

class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('negdi', 'NEGDI (Demo)')],
        ondelete={'negdi': 'set default'}
    )
    # negdi_dummy_field = fields.Char(string='Dummy NEGDI Field', required_if_provider='negdi')

    def _get_default_payment_method_id(self, provider_code=None):
        self.ensure_one()
        if self.code != 'negdi':
            return super()._get_default_payment_method_id(provider_code)
        return self.env.ref('payment.payment_method_manual').id  # Or card, if you prefer

    def _get_supported_currencies(self):
        """ Hook for sub-modules to implement.
        :return: A set of supported currency names.
        :rtype: set
        """
        res = super()._get_supported_currencies()
        return res | {'MNT'} # Adding MNT currency to the base

    def _get_validation_supported_fields(self):
        """ Hook for sub-modules to implement. """
        return super()._get_validation_supported_fields() + [
            'cc_number', 'cc_expiry', 'cc_holder_name', 'cc_cvc'
        ]

    def _get_payment_methods_mapping(self):
        """ Hook for sub-modules to implement. """
        return {
            'card': 'card',
        }

    def _get_compatible_payment_methods(self, invoice=None, currency=None, country=None):
        """ Hook for sub-modules to implement. """
        self.ensure_one()
        payment_methods = super()._get_compatible_payment_methods(invoice=invoice, currency=currency, country=country)
        if self.code != 'negdi':
            return payment_methods

        payment_methods = payment_methods.filtered(lambda pm: pm.code == 'manual')
        return payment_methods