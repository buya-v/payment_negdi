# -*- coding: utf-8 -*-
import base64
import json
from unittest.mock import patch

import requests

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

    def _paid_tx(self):
        """A transaction the gateway has confirmed as paid, ready to reverse."""
        tx = self._tx(provider_reference='555', negdi_checkid='chk1')
        with patch(_POST, return_value=_Resp(self._approved())):
            tx._negdi_sync_status()
        return tx

    def test_a_reversed_order_is_cancelled_not_filed_as_an_unknown_status(self):
        """'Reversed' entered NEGDI's status table on 2024.08.21, eight days after
        the v1.8 spec this module was written from. Until v1.13 revealed it, a
        legitimately reversed payment was filed as "Unknown payment status"."""
        tx = self._tx(provider_reference='555', negdi_checkid='chk1')
        preparing = signed({'tranid': 555, 'status': 'Preparing'})
        with patch(_POST, return_value=_Resp(preparing)):
            tx._negdi_sync_status()
        self.assertEqual(tx.state, 'pending')

        reversed_ = signed({'tranid': 555, 'status': 'Reversed'})
        with patch(_POST, return_value=_Resp(reversed_)):
            tx._negdi_sync_status()
        self.assertEqual(tx.state, 'cancel')
        self.assertNotIn('Unknown', tx.state_message or '')

    def test_reversed_is_accepted_as_proof_that_a_reversal_landed(self):
        """The most likely positive answer to "did it happen?" is this status.
        Not recognising it defeated the whole reconciliation."""
        tx = self._paid_tx()
        declined = signed({'tranid': 555, 'status': 'Declined', 'detail': 'gateway hiccup'})
        reversed_ = signed({'tranid': 555, 'status': 'Reversed', 'amount': 10000,
                            'currency': 'MNT', 'ordernum': 'NEGDI-T1'})
        with patch(_POST, side_effect=[_Resp(declined), _Resp(reversed_)]):
            refund_tx = tx._send_refund_request()
        self.assertEqual(refund_tx.state, 'done')

    def test_a_failed_reversal_that_actually_landed_is_recorded_as_done(self):
        """A failed RESPONSE is not a failed OPERATION.

        Seen for real on 2026-09-22 against this gateway: reversal requested,
        error returned, money reached the payer anyway. Believing the error is
        what pays a customer twice -- the operator is told to send it by hand
        on money that already went back.
        """
        tx = self._paid_tx()
        declined = signed({'tranid': 555, 'status': 'Declined', 'detail': 'not same day'})
        reversed_ = signed({'tranid': 555, 'status': 'Cancelled', 'amount': 10000,
                            'currency': 'MNT', 'ordernum': 'NEGDI-T1'})
        with patch(_POST, side_effect=[_Resp(declined), _Resp(reversed_)]):
            refund_tx = tx._send_refund_request()
        self.assertEqual(refund_tx.state, 'done',
                         'ec1098 says the money is gone, so nothing is owed')

    def test_a_reversal_refused_too_late_falls_through_to_the_refund_rail(self):
        """ec1099 is same-day; ec1095 is not. A refusal is a reason to change
        rail, not a reason to send someone to a bank."""
        tx = self._paid_tx()
        declined = signed({'tranid': 555, 'status': 'Declined', 'detail': 'not same day'})
        refunded = signed({'tranid': 777, 'status': 'Approved', 'approvalCode': 'REJR7P'})
        with patch(_POST, side_effect=[_Resp(declined),            # ec1099 refuses
                                       _Resp(self._approved()),    # ec1098: money still there
                                       _Resp(refunded)]) as post:  # ec1095 succeeds
            refund_tx = tx._send_refund_request()
        self.assertEqual(refund_tx.state, 'done')
        self.assertEqual(refund_tx.provider_reference, '777',
                         'the refund is its own transaction with its own tranid')
        self.assertTrue(post.call_args_list[2].args[0].endswith('/api/pay/ec1095'))

    def test_a_human_is_involved_only_when_both_rails_refuse(self):
        tx = self._paid_tx()
        declined = signed({'tranid': 555, 'status': 'Declined', 'detail': 'not same day'})
        refused = signed({'tranid': 555, 'status': 'Declined', 'reason': 'RestrictionViolated'})
        with patch(_POST, side_effect=[_Resp(declined), _Resp(self._approved()), _Resp(refused)]), \
                self.assertRaises(UserError) as caught:
            tx._send_refund_request()
        message = str(caught.exception)
        self.assertIn('bank transfer', message)
        self.assertIn('RestrictionViolated', message,
                      "the refund's own reason must reach the operator, not just the reversal's")

    def test_a_lost_refund_response_never_becomes_a_manual_payout(self):
        """ec1095 makes its own transaction, so a lost response leaves nothing
        to inquire against. Telling the operator to pay would risk paying twice."""
        tx = self._paid_tx()
        declined = signed({'tranid': 555, 'status': 'Declined', 'detail': 'not same day'})
        with patch(_POST, side_effect=[_Resp(declined), _Resp(self._approved()),
                                       requests.exceptions.ConnectionError('down')]), \
                self.assertRaises(UserError) as caught:
            tx._send_refund_request()
        message = str(caught.exception)
        self.assertIn('Do NOT refund by hand yet', message)
        self.assertNotIn('bank transfer', message)

    def test_an_inconclusive_inquiry_is_never_read_as_success(self):
        """'Declined' from ec1098 means the INQUIRY went wrong, not that the
        order was reversed. An earlier version read anything that was not money
        as "it landed", which would report nothing owed and leave the customer
        permanently out of pocket -- the mirror image of the double refund."""
        tx = self._paid_tx()
        declined = signed({'tranid': 555, 'status': 'Declined', 'detail': 'not same day'})
        with patch(_POST, side_effect=[_Resp(declined), _Resp(declined)]), \
                self.assertRaises(UserError) as caught:
            tx._send_refund_request()
        self.assertIn('Do NOT refund by hand yet', str(caught.exception))

    def test_when_the_inquiry_also_fails_the_operator_is_told_not_to_pay_yet(self):
        """Unknown is not the same as no. Paying out on an unknown is the
        double refund this whole path exists to prevent."""
        tx = self._paid_tx()
        declined = signed({'tranid': 555, 'status': 'Declined', 'detail': 'not same day'})
        with patch(_POST, side_effect=[_Resp(declined), _Resp('not json at all')]), \
                self.assertRaises(UserError) as caught:
            tx._send_refund_request()
        message = str(caught.exception)
        self.assertIn('Do NOT refund by hand yet', message)
        self.assertNotIn('genuinely did not happen', message)

    def test_an_unreachable_gateway_is_also_reconciled_not_assumed_failed(self):
        """The riskiest case: we never saw an answer, so the request may well
        have executed. It must not be treated as a plain failure."""
        tx = self._paid_tx()
        reversed_ = signed({'tranid': 555, 'status': 'Cancelled', 'amount': 10000,
                            'currency': 'MNT', 'ordernum': 'NEGDI-T1'})
        with patch(_POST, side_effect=[requests.exceptions.ConnectionError('down'),
                                       _Resp(reversed_)]):
            refund_tx = tx._send_refund_request()
        self.assertEqual(refund_tx.state, 'done')

    def test_refunds_are_offered_whatever_allowvoid_says(self):
        """allowvoid does NOT gate refunds, and gating on it was a real defect.

        On 2026-09-22 a 1000 MNT payment was reversed successfully while ec1096
        reported allowvoid=false for both order types on that merchant. While
        this was gated, Odoo offered no refund at all on a terminal where
        refunds work, and the operator's only recourse was a manual bank
        transfer for money the gateway would have returned.
        """
        for reported in (False, True):
            self.provider.negdi_allow_void = reported
            self.provider.invalidate_recordset(['support_refund'])
            self.assertEqual(self.provider.support_refund, 'partial',
                             'refunds must be offered when allowvoid reports %r' % reported)

    def test_partial_refunds_are_offered(self):
        """ec1095 accepts an amount at or below the original (v1.13 §7)."""
        self.provider.invalidate_recordset(['support_refund'])
        self.assertEqual(self.provider.support_refund, 'partial')

    def test_a_partial_refund_never_touches_the_reversal_rail(self):
        """The money-losing mistake this guards against.

        ec1099 reverses the WHOLE order; v1.13 grants "equal to or less than"
        to ec1095 and withholds it here. Sending a part-amount to ec1099 would
        hand the customer everything back and leave us short the difference,
        with the gateway reporting success either way.
        """
        tx = self._paid_tx()
        refunded = signed({'tranid': 777, 'status': 'Approved', 'approvalCode': 'REJR7P'})
        with patch(_POST, side_effect=[_Resp(refunded)]) as post:
            refund_tx = tx._send_refund_request(amount_to_refund=2500.0)
        self.assertEqual(refund_tx.state, 'done')
        self.assertEqual(len(post.call_args_list), 1,
                         'exactly one call: no reversal was attempted')
        self.assertTrue(post.call_args.args[0].endswith('/api/pay/ec1095'))
        self.assertEqual(post.call_args.kwargs['json']['amount'], 2500.0,
                         'the part amount, not the whole order')

    def test_a_full_refund_still_tries_the_free_rail_first(self):
        tx = self._paid_tx()
        reversed_ok = signed({'tranid': 555, 'status': 'Approved'})
        with patch(_POST, side_effect=[_Resp(reversed_ok)]) as post:
            tx._send_refund_request(amount_to_refund=10000.0)
        self.assertTrue(post.call_args.args[0].endswith('/api/pay/ec1099'))

    def test_test_connection_still_records_what_negdi_reported(self):
        """The flag stays visible as a diagnostic; it just decides nothing."""
        mixed = signed({'status': 'Approved', 'ordertypes': [
            {'ordertype': '3dsOrder', 'title': '3DS Sale Order Type', 'allowvoid': False},
            {'ordertype': 'QPAY', 'title': 'QPay Order Type', 'allowvoid': True}]})
        with patch(_POST, return_value=_Resp(mixed)):
            result = self.provider.action_negdi_test_connection()
        self.assertFalse(self.provider.negdi_allow_void)
        self.assertIn('3dsOrder (reports allowvoid=false)', result['params']['message'])
        # ...and the refund capability is unaffected by that report.
        self.provider.invalidate_recordset(['support_refund'])
        self.assertEqual(self.provider.support_refund, 'partial')

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
