# -*- coding: utf-8 -*-
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.payment_negdi import const, utils

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('negdi', "NEGDI")], ondelete={'negdi': 'set default'})
    negdi_api_url = fields.Char(
        string="NEGDI API URL", default=const.DEFAULT_API_URL,
        required_if_provider='negdi')
    negdi_terminal_id = fields.Char(string="NEGDI Terminal ID", required_if_provider='negdi')
    negdi_username = fields.Char(
        string="NEGDI Username", required_if_provider='negdi', groups='base.group_system')
    negdi_password = fields.Char(
        string="NEGDI Password", required_if_provider='negdi', groups='base.group_system')
    negdi_public_key = fields.Text(
        string="NEGDI Public Key", default=const.DEFAULT_PUBLIC_KEY,
        required_if_provider='negdi', groups='base.group_system',
        help="Verifies that each gateway response really comes from NEGDI (merchant "
             "spec, section 12). Replace it only with a key NEGDI itself gives you.")
    negdi_insecure_url = fields.Boolean(compute='_compute_negdi_insecure_url')
    negdi_allow_void = fields.Boolean(
        string="NEGDI allows reversal", readonly=True,
        help="Set by Test connection from what NEGDI reports for the enabled order types. "
             "Refunds are offered only when every one of them allows reversal.")

    @api.depends('negdi_api_url')
    def _compute_negdi_insecure_url(self):
        for provider in self:
            provider.negdi_insecure_url = bool(
                provider.negdi_api_url and not provider.negdi_api_url.startswith('https://'))

    @api.depends('code', 'negdi_allow_void')
    def _compute_feature_support_fields(self):
        super()._compute_feature_support_fields()
        # ec1099 reverses a whole payment, and only on the day it was made. A
        # terminal NEGDI set up without reversal refuses it, so offering the
        # button would only promise a refund that fails.
        for provider in self.filtered(lambda p: p.code == 'negdi'):
            provider.support_refund = 'full_only' if provider.negdi_allow_void else 'none'

    def _get_supported_currencies(self):
        supported = super()._get_supported_currencies()
        if self.code == 'negdi':
            supported = supported.filtered(lambda c: c.name in const.SUPPORTED_CURRENCIES)
        return supported

    def _get_default_payment_method_codes(self):
        default = super()._get_default_payment_method_codes()
        if self.code != 'negdi':
            return default
        return const.DEFAULT_PAYMENT_METHOD_CODES

    def _negdi_credentials(self):
        self.ensure_one()
        provider = self.sudo()
        return {
            'terminalid': provider.negdi_terminal_id,
            'username': provider.negdi_username,
            'password': provider.negdi_password,
        }

    def _negdi_request(self, endpoint, payload):
        """POST to a NEGDI endpoint and return the VERIFIED ``order`` object.

        The payload can carry the merchant password, so it is never logged.

        :raise ValidationError: gateway unreachable, not a NEGDI response, or a
            signature that does not verify against NEGDI's public key.
        """
        self.ensure_one()
        url = (self.negdi_api_url or const.DEFAULT_API_URL).rstrip('/') + endpoint
        try:
            response = requests.post(url, json=payload, timeout=30)
        except requests.exceptions.RequestException as exc:
            _logger.warning("NEGDI %s unreachable: %s", endpoint, exc)
            raise ValidationError("NEGDI: " + _("Could not reach the payment gateway.")) from exc
        try:
            verified, order, _parsed = utils.verify_response(
                response.text, self.sudo().negdi_public_key or const.DEFAULT_PUBLIC_KEY)
        except ValueError as exc:
            _logger.warning("NEGDI %s: HTTP %s with a non-JSON body", endpoint, response.status_code)
            raise ValidationError(
                "NEGDI: " + _("The payment gateway sent an unreadable response.")) from exc
        if not verified:
            _logger.error("NEGDI %s: response signature did NOT verify (status=%s)",
                          endpoint, order.get('status'))
            raise ValidationError("NEGDI: " + _(
                "The gateway's response could not be verified with NEGDI's public key, "
                "so it was ignored."))
        _logger.info("NEGDI %s -> status=%s tranid=%s", endpoint, order.get('status'), order.get('tranid'))
        return order

    def action_negdi_test_connection(self):
        """Prove credentials, reachability and signature checking -- without money.

        Uses INQUIRY ORDER TYPE (ec1096), which only reads the terminal's setup.
        """
        self.ensure_one()
        order = self._negdi_request(const.ENDPOINT_ORDER_TYPES, self._negdi_credentials())
        if order.get('status') not in const.STATUS_DONE:
            raise UserError("NEGDI: " + _(
                "The gateway refused these credentials: %s",
                order.get('detail') or order.get('errors') or order.get('status')))
        types = order.get('ordertypes') or []
        if isinstance(types, dict):
            types = [types]
        enabled = {t.get('ordertype') for t in types}
        self.negdi_allow_void = bool(types) and all(str(t.get('allowvoid')).lower() == 'true' for t in types)
        no_reversal = _(' (no reversal)')
        listed = ', '.join('%s%s' % (t.get('ordertype'), '' if str(t.get('allowvoid')).lower() == 'true' else no_reversal)
                           for t in types) or _("none")
        missing = sorted(set(const.ORDER_TYPE_BY_PAYMENT_METHOD.values()) - enabled)
        message = _("Connected, and the response signature verified. Order types enabled: %s.", listed)
        if missing:
            message += ' ' + _("Not enabled on this terminal: %s.", ', '.join(missing))
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': "NEGDI", 'message': message,
                       'type': 'warning' if missing else 'success', 'sticky': bool(missing)},
        }
