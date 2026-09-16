# -*- coding: utf-8 -*-
import logging
from urllib.parse import parse_qsl

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


class NegdiController(http.Controller):
    _return_url = '/payment/negdi/return'

    @http.route([_return_url, _return_url + '/<string:reference>'], type='http', auth='public',
                methods=['GET', 'POST'], csrf=False, save_session=False)
    def negdi_return_from_checkout(self, reference=None, **data):
        """Customer is back from NEGDI's payment page.

        The query parameters only say WHICH transaction to look at; its outcome
        is always fetched from the gateway (ec1098) and signature-checked, so a
        hand-crafted redirect cannot mark anything paid. `save_session=False`
        for the same reason as Mollie: a cross-site POST may arrive without the
        session cookie, and /payment/status recovers the session anyway.
        """
        data = self._negdi_return_data(reference, data)
        _logger.info("NEGDI return: %s", {k: data.get(k) for k in ('ref', 'tranid', 'checkid')})
        try:
            request.env['payment.transaction'].sudo()._handle_notification_data('negdi', data)
        except ValidationError:
            # Leave the transaction as it is: the polling cron will settle it.
            _logger.warning("NEGDI: could not settle return %s now; the cron will retry",
                            data.get('ref') or data.get('tranid'), exc_info=True)
        return request.redirect('/payment/status')

    @staticmethod
    def _negdi_return_data(reference, data):
        """The return parameters, repaired.

        NEGDI appends "?tranid=..&checkid=.." to the return URL as given, even
        when that URL already has a query string: "...?ref=S00061" came back as
        "ref=S00061?tranid=1341417231&checkid=..", the lookup found nothing, and
        the customer waited for the polling cron. The reference now travels in
        the path; an old-style URL still in flight is repaired here.
        """
        data = dict(data)
        if reference:
            data['ref'] = reference
        ref = data.get('ref') or ''
        if '?' in ref:
            ref, _sep, tail = ref.partition('?')
            for key, value in parse_qsl(tail):
                data.setdefault(key, value)
            data['ref'] = ref
        return data

