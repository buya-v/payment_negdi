# -*- coding: utf-8 -*-
import logging
from datetime import timedelta
from urllib.parse import parse_qsl, quote, urljoin, urlsplit

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

from odoo.addons.payment_negdi import const
from odoo.addons.payment_negdi.controllers.main import NegdiController

_logger = logging.getLogger(__name__)

# NEGDI's inquiry `paymentmethod` -> Odoo payment method code.
PAYMENT_METHOD_BY_NEGDI = {'card': 'card', 'qr': 'qpay'}


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    negdi_checkid = fields.Char(string="NEGDI Check ID", readonly=True, copy=False)

    def _negdi_tranid(self):
        ref = self.provider_reference or ''
        return int(ref) if ref.isdigit() else ref

    # --- redirect flow --------------------------------------------------------

    def _get_specific_rendering_values(self, processing_values):
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'negdi':
            return res
        provider = self.provider_id
        # The reference in the PATH: NEGDI appends its own "?tranid=.." to this URL
        # even when it already has a query string (see the controller).
        return_url = urljoin(provider.get_base_url(), '%s/%s' % (
            NegdiController._return_url, quote(self.reference, safe='')))
        payload = dict(
            provider._negdi_credentials(),
            ordertype=const.ORDER_TYPE_BY_PAYMENT_METHOD.get(self.payment_method_code, '3dsOrder'),
            returnurl=return_url,
            amount=round(self.amount, 2),
            currency=self.currency_id.name,
            ordernum=self.reference[:20],
            description=self.reference[:100],
        )
        order = provider._negdi_request(const.ENDPOINT_CREATE_ORDER, payload)
        negdi_url = order.get('negdiurl')
        if not order.get('tranid') or not negdi_url:
            raise ValidationError("NEGDI: " + _(
                "The gateway did not open a payment page: %s",
                order.get('detail') or order.get('errors') or order.get('status')))
        # Stored now. After the redirect, THESE -- not whatever comes back on the
        # return URL -- are what the payment's status is checked against.
        self.provider_reference = str(order['tranid'])
        self.negdi_checkid = order.get('checkid')
        return {'api_url': negdi_url, 'url_params': dict(parse_qsl(urlsplit(negdi_url).query))}

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'negdi' or len(tx) == 1:
            return tx
        base = [('provider_code', '=', 'negdi')]
        reference, tranid = notification_data.get('ref'), notification_data.get('tranid')
        checkid = notification_data.get('checkid')
        tx = self.browse()
        if reference:
            tx = self.search(base + [('reference', '=', reference)], limit=1)
        if not tx and tranid:
            tx = self.search(base + [('provider_reference', '=', str(tranid))], limit=1)
        if not tx and checkid:
            tx = self.search(base + [('negdi_checkid', '=', checkid)], limit=1)
        if not tx:
            raise ValidationError("NEGDI: " + _(
                "No transaction found matching reference %s.", reference or tranid))
        return tx

    def _process_notification_data(self, notification_data):
        super()._process_notification_data(notification_data)
        if self.provider_code != 'negdi':
            return
        returned = notification_data.get('tranid')
        if returned and str(returned) != (self.provider_reference or ''):
            _logger.warning("NEGDI: return for %s carried tranid %s, expected %s; ignored",
                            self.reference, returned, self.provider_reference)
        self._negdi_sync_status()

    def _negdi_sync_status(self):
        """Ask the gateway about THIS transaction's order and apply the answer.

        The only input trusted here is NEGDI's signed answer about the order we
        created ourselves; request parameters never reach this method.
        """
        self.ensure_one()
        if not self.provider_reference or not self.negdi_checkid:
            raise ValidationError("NEGDI: " + _(
                "Transaction %s has no gateway order to check.", self.reference))
        order = self.provider_id._negdi_request(const.ENDPOINT_INQUIRY_ORDER, {
            'tranid': self._negdi_tranid(), 'checkid': self.negdi_checkid,
        })
        problem = self._negdi_mismatch(order)
        if problem:
            _logger.error("NEGDI: %s (transaction %s)", problem, self.reference)
            self._set_error("NEGDI: " + problem)
            return

        method = PAYMENT_METHOD_BY_NEGDI.get((order.get('paymentmethod') or '').lower())
        if method:
            self.payment_method_id = (self.env['payment.method']._get_from_code(method)
                                      or self.payment_method_id)

        status = order.get('status')
        if status in const.STATUS_DONE:
            self._set_done()
        elif status in const.STATUS_HELD:
            # Authorised, not captured. Pending, never done: releasing the
            # purchase here would give away goods for money still on hold.
            _logger.info("NEGDI: %s is authorised but not captured; leaving it pending",
                         self.reference)
            self._set_pending()
        elif status in const.STATUS_PENDING:
            self._set_pending()
        elif status in const.STATUS_CANCEL:
            self._set_canceled("NEGDI: " + _("Payment %s.", status))
        elif status in const.STATUS_ERROR:
            self._set_error("NEGDI: " + _("%(status)s. %(detail)s",
                                         status=status, detail=order.get('detail') or ''))
        else:
            _logger.warning("NEGDI: unknown status %r for %s", status, self.reference)
            self._set_error("NEGDI: " + _("Unknown payment status: %s", status))

    def _negdi_mismatch(self, order):
        """Why this answer must not be applied to this transaction, if at all."""
        if str(order.get('tranid')) != (self.provider_reference or ''):
            return _("the gateway answered about order %(got)s instead of %(want)s",
                     got=order.get('tranid'), want=self.provider_reference)
        # Deliberately STATUS_ABOUT_MONEY, not STATUS_DONE: a hold carries an
        # amount and a currency too, and they must be checked against what we
        # asked for. Narrowing this to STATUS_DONE would stop verifying the
        # amount on exactly the transactions we have not been paid for yet.
        if order.get('status') not in const.STATUS_ABOUT_MONEY:
            return None
        amount, currency, ordernum = order.get('amount'), order.get('currency'), order.get('ordernum')
        if amount is None or not currency:
            return _("an approval arrived without an amount or currency")
        if currency != self.currency_id.name:
            return _("paid in %(got)s, expected %(want)s", got=currency, want=self.currency_id.name)
        if float_compare(float(amount), self.amount, precision_digits=2) != 0:
            return _("paid %(got)s, expected %(want)s", got=amount, want=self.amount)
        if ordernum and ordernum != self.reference[:20]:
            return _("paid for order number %(got)s, expected %(want)s",
                     got=ordernum, want=self.reference[:20])
        return None

    # --- refunds ----------------------------------------------------------------

    def _send_refund_request(self, amount_to_refund=None):
        refund_tx = super()._send_refund_request(amount_to_refund=amount_to_refund)
        if self.provider_code != 'negdi':
            return refund_tx
        creds = self.provider_id._negdi_credentials()
        order = self.provider_id._negdi_request(const.ENDPOINT_CANCEL_ORDER, {
            'tranid': self._negdi_tranid(),
            'username': creds['username'],
            'password': creds['password'],
            'amount': round(self.amount, 2),
        })
        if order.get('status') not in const.STATUS_DONE:
            raise UserError("NEGDI: " + _(
                "The gateway refused the reversal (%(detail)s). NEGDI reverses a payment only "
                "on the day it was made; refund this customer by bank transfer instead and "
                "record it manually.",
                detail=order.get('detail') or order.get('errors') or order.get('status')))
        refund_tx.provider_reference = str(order.get('tranid') or self.provider_reference)
        refund_tx._set_done()
        return refund_tx

    # --- polling ------------------------------------------------------------------

    @api.model
    def _cron_negdi_poll_pending(self):
        """Settle payments whose customer never came back from the gateway.

        The spec has no webhook: without this, a customer who pays and closes
        the tab would be charged and never credited.
        """
        since = fields.Datetime.now() - timedelta(hours=const.POLL_WINDOW_HOURS)
        txs = self.search([
            ('provider_code', '=', 'negdi'), ('operation', '!=', 'refund'),
            ('state', 'in', ('draft', 'pending')),
            ('provider_reference', '!=', False), ('negdi_checkid', '!=', False),
            ('create_date', '>=', since),
        ], limit=200)
        for tx in txs:
            try:
                tx._negdi_sync_status()
                self.env.cr.commit()  # one gateway round-trip per payment; keep each result
            except Exception:
                self.env.cr.rollback()
                _logger.warning("NEGDI: could not check %s; will retry", tx.reference, exc_info=True)
