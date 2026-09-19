# -*- coding: utf-8 -*-
import base64
import json
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.payment_negdi import utils

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUB = _KEY.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
_POST = 'odoo.addons.payment_negdi.models.payment_provider.requests.post'


def signed(order, key=_KEY, pretty=False):
    """A response body signed the way NEGDI's PHP reference verifier expects."""
    sig = key.sign(utils.php_json_encode(order).encode(), padding.PKCS1v15(), hashes.SHA256())
    body = {'order': order, 'ordersign': base64.b64encode(sig).decode()}
    return json.dumps(body, indent=2 if pretty else None, ensure_ascii=False)


class _Resp:
    def __init__(self, text, status_code=200):
        self.text, self.status_code = text, status_code


@tagged('post_install', '-at_install')
class TestNegdiSignature(TransactionCase):

    def test_php_encoding_escapes_like_php(self):
        self.assertEqual(
            utils.php_json_encode({'url': 'http://x/y', 'd': 'Тест', 'n': 1000, 'a': 1.5}),
            '{"url":"http:\\/\\/x\\/y","d":"\\u0422\\u0435\\u0441\\u0442","n":1000,"a":1.5}')

    def test_verifies_even_when_transmitted_pretty_printed(self):
        order = {'tranid': 1, 'status': 'Approved', 'description': 'Тест / test'}
        ok, got, _parsed = utils.verify_response(signed(order, pretty=True), _PUB)
        self.assertTrue(ok)
        self.assertEqual(got['status'], 'Approved')

    def test_rejects_tampered_amount(self):
        body = json.loads(signed({'tranid': 1, 'status': 'Approved', 'amount': 10000}))
        body['order']['amount'] = 1
        self.assertFalse(utils.verify_response(json.dumps(body), _PUB)[0])

    def test_rejects_other_key(self):
        self.assertFalse(utils.verify_response(signed({'status': 'Approved'}, key=_OTHER_KEY), _PUB)[0])

    def test_rejects_missing_signature(self):
        self.assertFalse(utils.verify_response(json.dumps({'order': {'status': 'Approved'}}), _PUB)[0])

    def test_raw_member_is_byte_exact(self):
        body = '{"order": {"a": 1 , "b":[1,2]}, "ordersign":"x"}'
        self.assertEqual(utils.raw_member(body, 'order'), '{"a": 1 , "b":[1,2]}')

    def test_spec_public_key_loads(self):
        from odoo.addons.payment_negdi import const
        key = serialization.load_pem_public_key(const.DEFAULT_PUBLIC_KEY.encode())
        self.assertEqual(key.key_size, 2048)


@tagged('post_install', '-at_install')
class TestNegdiTransaction(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mnt = cls.env.ref('base.MNT')
        cls.mnt.active = True
        cls.provider = cls.env.ref('payment_negdi.payment_provider_negdi')
        cls.provider.write({
            'state': 'test', 'negdi_terminal_id': 'T1', 'negdi_username': 'u',
            'negdi_password': 'secret', 'negdi_public_key': _PUB,
        })
        cls.card = cls.env.ref('payment.payment_method_card')
        cls.qpay = cls.env.ref('payment_negdi.payment_method_qpay')
        cls.partner = cls.env['res.partner'].create({'name': 'NEGDI Buyer'})

    def _tx(self, reference='NEGDI-T1', method=None, **extra):
        return self.env['payment.transaction'].create(dict({
            'provider_id': self.provider.id,
            'payment_method_id': (method or self.card).id,
            'reference': reference, 'amount': 10000.0, 'currency_id': self.mnt.id,
            'partner_id': self.partner.id, 'operation': 'online_redirect',
        }, **extra))

    def _approved(self, tranid=555, **over):
        return signed(dict({'tranid': tranid, 'ordertype': '3dsOrder', 'paymentmethod': 'Card',
                            'status': 'Approved', 'amount': 10000, 'currency': 'MNT',
                            'ordernum': 'NEGDI-T1'}, **over))

    def test_redirect_creates_order_and_keeps_its_ids(self):
        tx = self._tx()
        body = signed({'tranid': 555, 'checkid': 'chk1', 'status': 'Preparing',
                       'negdiurl': 'https://pay.negdi.mn/p?t=abc&l=mn'})
        with patch(_POST, return_value=_Resp(body)) as post:
            values = tx._get_specific_rendering_values({})
        sent = post.call_args.kwargs['json']
        self.assertEqual(sent['ordertype'], '3dsOrder')
        self.assertEqual(sent['currency'], 'MNT')
        self.assertEqual(sent['ordernum'], 'NEGDI-T1')
        self.assertTrue(sent['returnurl'].endswith('/payment/negdi/return/NEGDI-T1'), sent['returnurl'])
        self.assertEqual((tx.provider_reference, tx.negdi_checkid), ('555', 'chk1'))
        self.assertEqual(values['url_params'], {'t': 'abc', 'l': 'mn'})

    def test_qpay_uses_the_qpay_order_type(self):
        tx = self._tx(method=self.qpay)
        body = signed({'tranid': 7, 'checkid': 'c', 'status': 'Preparing', 'negdiurl': 'https://q/x'})
        with patch(_POST, return_value=_Resp(body)) as post:
            tx._get_specific_rendering_values({})
        self.assertEqual(post.call_args.kwargs['json']['ordertype'], 'QPAY')

    def test_approved_marks_done(self):
        tx = self._tx(provider_reference='555', negdi_checkid='chk1')
        with patch(_POST, return_value=_Resp(self._approved())):
            tx._negdi_sync_status()
        self.assertEqual(tx.state, 'done')

    def test_an_authorised_hold_is_pending_not_done(self):
        """NEGDI supports pre-authorisation holds: money held is not money taken.

        `Authorized` used to sit in STATUS_DONE, so a hold released the purchase
        and granted credits for funds that were never captured.
        """
        tx = self._tx(provider_reference='555', negdi_checkid='chk1')
        body = signed({'tranid': 555, 'checkid': 'chk1', 'status': 'Authorized',
                       'amount': 10000.0, 'currency': 'MNT', 'ordernum': 'NEGDI-T1'})
        with patch(_POST, return_value=_Resp(body)):
            tx._negdi_sync_status()
        self.assertEqual(tx.state, 'pending')

    def test_a_hold_with_the_wrong_amount_is_still_rejected(self):
        """The amount check must not be skipped just because it is only a hold."""
        tx = self._tx(provider_reference='555', negdi_checkid='chk1')
        body = signed({'tranid': 555, 'checkid': 'chk1', 'status': 'Authorized',
                       'amount': 1.0, 'currency': 'MNT', 'ordernum': 'NEGDI-T1'})
        with patch(_POST, return_value=_Resp(body)):
            tx._negdi_sync_status()
        self.assertEqual(tx.state, 'error')

    def test_wrong_amount_is_an_error_not_a_payment(self):
        tx = self._tx(provider_reference='555', negdi_checkid='chk1')
        with patch(_POST, return_value=_Resp(self._approved(amount=1))):
            tx._negdi_sync_status()
        self.assertEqual(tx.state, 'error')

    def test_unverified_approval_is_ignored(self):
        tx = self._tx(provider_reference='555', negdi_checkid='chk1')
        forged = signed({'tranid': 555, 'status': 'Approved', 'amount': 10000,
                         'currency': 'MNT'}, key=_OTHER_KEY)
        with patch(_POST, return_value=_Resp(forged)), self.assertRaises(ValidationError):
            tx._negdi_sync_status()
        self.assertEqual(tx.state, 'draft')

    def test_return_parameters_are_not_trusted(self):
        tx = self._tx(provider_reference='555', negdi_checkid='chk1')
        with patch(_POST, return_value=_Resp(self._approved())) as post:
            self.env['payment.transaction']._handle_notification_data(
                'negdi', {'ref': 'NEGDI-T1', 'tranid': '999', 'checkid': 'forged'})
        asked = post.call_args.kwargs['json']
        self.assertEqual((asked['tranid'], asked['checkid']), (555, 'chk1'))
        self.assertEqual(tx.state, 'done')

    def test_preparing_is_pending_and_expired_is_cancelled(self):
        tx = self._tx(provider_reference='555', negdi_checkid='chk1')
        with patch(_POST, return_value=_Resp(signed({'tranid': 555, 'status': 'Preparing'}))):
            tx._negdi_sync_status()
        self.assertEqual(tx.state, 'pending')
        with patch(_POST, return_value=_Resp(signed({'tranid': 555, 'status': 'Expired'}))):
            tx._negdi_sync_status()
        self.assertEqual(tx.state, 'cancel')

    def test_partially_paid_does_not_release_the_purchase(self):
        tx = self._tx(provider_reference='555', negdi_checkid='chk1')
        with patch(_POST, return_value=_Resp(self._approved(status='Partially paid'))):
            tx._negdi_sync_status()
        self.assertEqual(tx.state, 'pending')

    def test_refused_reversal_explains_the_same_day_rule(self):
        tx = self._tx(provider_reference='555', negdi_checkid='chk1')
        with patch(_POST, return_value=_Resp(self._approved())):
            tx._negdi_sync_status()
        declined = signed({'tranid': 555, 'status': 'Declined', 'detail': 'not same day'})
        with patch(_POST, return_value=_Resp(declined)), self.assertRaises(UserError):
            tx._send_refund_request()

    def test_refunds_are_offered_only_when_negdi_allows_reversal(self):
        self.provider.negdi_allow_void = False
        self.provider.invalidate_recordset(['support_refund'])
        self.assertEqual(self.provider.support_refund, 'none')
        self.provider.negdi_allow_void = True
        self.provider.invalidate_recordset(['support_refund'])
        self.assertEqual(self.provider.support_refund, 'full_only')

    def test_test_connection_records_whether_reversal_is_allowed(self):
        # ASLA's production terminal (2026-09-15) reports allowvoid false for both types.
        mixed = signed({'status': 'Approved', 'ordertypes': [
            {'ordertype': '3dsOrder', 'title': '3DS Sale Order Type', 'allowvoid': False},
            {'ordertype': 'QPAY', 'title': 'QPay Order Type', 'allowvoid': True}]})
        with patch(_POST, return_value=_Resp(mixed)):
            result = self.provider.action_negdi_test_connection()
        self.assertFalse(self.provider.negdi_allow_void)
        self.assertIn('3dsOrder (no reversal)', result['params']['message'])
        both = signed({'status': 'Approved', 'ordertypes': [
            {'ordertype': '3dsOrder', 'allowvoid': True}, {'ordertype': 'QPAY', 'allowvoid': True}]})
        with patch(_POST, return_value=_Resp(both)):
            self.provider.action_negdi_test_connection()
        self.assertTrue(self.provider.negdi_allow_void)
        self.provider.invalidate_recordset(['support_refund'])
        self.assertEqual(self.provider.support_refund, 'full_only')

    def test_the_return_url_carries_no_query_string(self):
        # NEGDI appends "?tranid=..", so a query string of ours would be corrupted.
        tx = self._tx()
        body = signed({'tranid': 555, 'checkid': 'chk1', 'status': 'Preparing',
                       'negdiurl': 'https://pay.example/pay?tranid=555&checkid=chk1'})
        with patch(_POST, return_value=_Resp(body)) as post:
            tx._get_specific_rendering_values({})
        returnurl = post.call_args.kwargs['json']['returnurl']
        self.assertTrue(returnurl.endswith('/payment/negdi/return/NEGDI-T1'), returnurl)
        self.assertNotIn('?', returnurl)

    def test_a_return_with_negdis_appended_query_is_repaired(self):
        from odoo.addons.payment_negdi.controllers.main import NegdiController
        data = NegdiController._negdi_return_data(
            None, {'ref': 'S00061?tranid=1341417231', 'checkid': 'hpbzf4gl5sry'})
        self.assertEqual(data, {'ref': 'S00061', 'tranid': '1341417231', 'checkid': 'hpbzf4gl5sry'})
        self.assertEqual(NegdiController._negdi_return_data('S00062', {'tranid': '7'}),
                         {'ref': 'S00062', 'tranid': '7'})

    def test_a_return_is_found_by_its_checkid(self):
        tx = self._tx(provider_reference='555', negdi_checkid='chk-found')
        found = self.env['payment.transaction']._get_tx_from_notification_data(
            'negdi', {'checkid': 'chk-found'})
        self.assertEqual(found, tx)


@tagged('post_install', '-at_install')
class TestNegdiOrderTypeDiagnostics(TransactionCase):
    """Test connection must report what it does not understand.

    Capture is blocked on one fact: whether this terminal can hold funds. That
    is a property of the order type rather than of the request, so the flag is
    in ec1096's reply under a name NEGDI chose. Dropping unknown attributes
    threw the answer away on every call.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env.ref('payment_negdi.payment_provider_negdi')

    def _describe(self, types):
        return self.provider._negdi_unknown_order_type_attributes(types)

    def test_an_unknown_attribute_is_reported(self):
        text = self._describe([
            {'ordertype': '3dsOrder', 'allowvoid': 'true', 'authkind': 'Preliminary'},
        ])
        self.assertIn('3dsOrder', text)
        self.assertIn('authkind=Preliminary', text)

    def test_attributes_we_already_act_on_are_not_repeated(self):
        """They are already in the first line; repeating them buries the new ones."""
        self.assertEqual(self._describe([{'ordertype': 'QPAY', 'allowvoid': 'true'}]), '')

    def test_every_order_type_is_reported_not_just_the_first(self):
        text = self._describe([
            {'ordertype': '3dsOrder', 'phase': 'Auth'},
            {'ordertype': 'QPAY', 'phase': 'Single'},
        ])
        self.assertIn('3dsOrder: phase=Auth', text)
        self.assertIn('QPAY: phase=Single', text)

    def test_a_malformed_entry_does_not_break_the_button(self):
        """ec1096 has already returned a bare dict instead of a list once. A
        diagnostic that raises is worse than useless: it hides the diagnosis."""
        self.assertEqual(self._describe(['not-a-dict', None]), '')

    def test_nothing_enabled_reports_nothing(self):
        self.assertEqual(self._describe([]), '')
