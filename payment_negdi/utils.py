# -*- coding: utf-8 -*-
"""Verification of NEGDI e-commerce gateway responses.

Every NEGDI response is ``{"order": {...}, "ordersign": "<base64>"}``, where
``ordersign`` is an RSA-SHA256 (PKCS#1 v1.5) signature over the ``order`` object
*as NEGDI serialised it*. The merchant spec's reference verifier is PHP: it
json_decodes the response, json_encodes ``order`` again and runs openssl_verify
on those bytes. So the signed bytes are PHP ``json_encode`` output, which differs
from Python's ``json.dumps``: PHP escapes ``/`` as ``\\/`` and every non-ASCII
character as a lowercase ``\\uXXXX``, and uses no whitespace.

We therefore try a small set of candidate serialisations -- the exact bytes of
``order`` as they arrived, PHP's encoding, and the two plain JSON encodings --
and accept the response if ANY of them verifies. That is safe: each attempt is a
full RSA verification against NEGDI's public key, so no candidate can pass
without NEGDI's private key. What is never acceptable is skipping verification
when none passes; an unverified "Approved" is exactly how a forged payment
confirmation would get in.
"""
import base64
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


def _php_str(text):
    out = ['"']
    for ch in text:
        cp = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == '\\':
            out.append('\\\\')
        elif ch == '/':
            out.append('\\/')
        elif ch == '\b':
            out.append('\\b')
        elif ch == '\f':
            out.append('\\f')
        elif ch == '\n':
            out.append('\\n')
        elif ch == '\r':
            out.append('\\r')
        elif ch == '\t':
            out.append('\\t')
        elif cp < 0x20:
            out.append('\\u%04x' % cp)
        elif cp < 0x80:
            out.append(ch)
        elif cp < 0x10000:
            out.append('\\u%04x' % cp)
        else:  # outside the BMP: a UTF-16 surrogate pair, as PHP writes it
            cp -= 0x10000
            out.append('\\u%04x\\u%04x' % (0xD800 + (cp >> 10), 0xDC00 + (cp & 0x3FF)))
    out.append('"')
    return ''.join(out)


def php_json_encode(value, empty_dict='[]'):
    """Serialise ``value`` exactly as PHP's ``json_encode`` does by default.

    ``empty_dict``: PHP turns a decoded empty object into an empty *array* when
    it was decoded as an associative array (``[]``), but keeps ``{}`` otherwise;
    the caller tries both.
    """
    if value is None:
        return 'null'
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float('inf'), float('-inf')):
            raise ValueError('PHP json_encode cannot encode %r' % value)
        text = repr(value)  # shortest round-trip form, as PHP >= 7.1
        if 'e' in text:
            mantissa, exponent = text.split('e')
            if '.' not in mantissa:
                mantissa += '.0'
            sign = '-' if exponent.startswith('-') else '+'
            text = '%se%s%d' % (mantissa, sign, abs(int(exponent)))
        return text
    if isinstance(value, str):
        return _php_str(value)
    if isinstance(value, (list, tuple)):
        return '[' + ','.join(php_json_encode(v, empty_dict) for v in value) + ']'
    if isinstance(value, dict):
        if not value:
            return empty_dict
        return '{' + ','.join(
            _php_str(str(k)) + ':' + php_json_encode(v, empty_dict) for k, v in value.items()
        ) + '}'
    raise TypeError('cannot encode %r' % type(value))


def raw_member(body, key):
    """Return the exact source text of the top-level member ``key`` of JSON ``body``.

    This is the byte-for-byte serialisation the gateway sent, so if NEGDI signed
    what it transmitted it verifies without any re-encoding guesswork.
    """
    decoder = json.JSONDecoder()
    idx, end = 0, len(body)

    def skip(i):
        while i < end and body[i] in ' \t\r\n':
            i += 1
        return i

    idx = skip(idx)
    if idx >= end or body[idx] != '{':
        return None
    idx = skip(idx + 1)
    while idx < end and body[idx] != '}':
        name, idx = decoder.raw_decode(body, idx)
        idx = skip(idx)
        if idx >= end or body[idx] != ':':
            return None
        idx = skip(idx + 1)
        start = idx
        _value, idx = decoder.raw_decode(body, idx)
        if name == key:
            return body[start:idx]
        idx = skip(idx)
        if idx < end and body[idx] == ',':
            idx = skip(idx + 1)
    return None


def signature_candidates(body, order):
    candidates = []
    raw = raw_member(body, 'order')
    if raw:
        candidates.append(raw)
    candidates.append(php_json_encode(order, empty_dict='[]'))
    candidates.append(php_json_encode(order, empty_dict='{}'))
    candidates.append(json.dumps(order, ensure_ascii=False, separators=(',', ':')))
    candidates.append(json.dumps(order, ensure_ascii=True, separators=(',', ':')))
    return list(dict.fromkeys(candidates))  # de-duplicate, keep order


def verify_response(body, public_key_pem):
    """Parse a NEGDI response and verify its ``ordersign``.

    :param str body: the raw response text.
    :param str public_key_pem: NEGDI's RSA public key, PEM.
    :return: ``(verified, order, parsed)`` -- ``order`` is the ``order`` object
             (or ``{}``), ``parsed`` the whole decoded response.
    """
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        return False, {}, parsed
    order, sign = parsed.get('order'), parsed.get('ordersign')
    if not isinstance(order, dict) or not sign:
        return False, order if isinstance(order, dict) else {}, parsed
    try:
        signature = base64.b64decode(sign)
        key = serialization.load_pem_public_key(public_key_pem.strip().encode())
    except (ValueError, TypeError):
        return False, order, parsed
    for candidate in signature_candidates(body, order):
        try:
            key.verify(signature, candidate.encode('utf-8'), padding.PKCS1v15(), hashes.SHA256())
            return True, order, parsed
        except InvalidSignature:
            continue
    return False, order, parsed
