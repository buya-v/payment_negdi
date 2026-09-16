# payment_negdi

A payment provider for [Odoo 18](https://www.odoo.com) that takes Mongolian tugrik
payments through the **NEGDI** e-commerce gateway: bank cards with 3-D Secure, and QPay.

Free and open source under the LGPL-3.

## What you get

- The standard Odoo redirect flow, so it works with eCommerce, invoices and payment
  links without any per-shop code.
- Gateway responses are verified against NEGDI's public key before they are trusted.
- A scheduled job settles payments whose confirmation arrives late or never, so a
  customer who closes the browser mid-payment is not left waiting.
- Refunds are offered only when NEGDI allows the transaction to be reversed.
- Mongolian translation for the messages a customer actually sees.

Card numbers never reach Odoo: the card is authorised on the issuing bank's page.

## Install

The repository root is an addons directory containing one module folder, so it can be
added to Odoo's `addons_path` as it is:

```bash
git clone https://github.com/buya-v/payment_negdi.git
# then add the clone's path to addons_path and install "Payment Provider: NEGDI"
```

Or install it from the Odoo Apps store.

## Configure

You need a merchant account with NEGDI first — they issue the credentials. Contact
them at hello@negdi.mn.

In Odoo, go to **Invoicing → Configuration → Payment Providers → NEGDI** and fill in:

| Field | Where it comes from |
| --- | --- |
| NEGDI Username | NEGDI |
| NEGDI Password | NEGDI |
| NEGDI Terminal ID | NEGDI |
| NEGDI API URL | Already filled in with the gateway address from the merchant spec. Change it only if NEGDI moves you to a different endpoint. |
| NEGDI Public Key | Already filled in from the merchant spec (section 12). It verifies that a response really came from NEGDI. Replace it only with a key NEGDI itself gives you. |

> **Note on transport.** NEGDI's gateway address is plain HTTP, so the request that
> carries your merchant credentials is not encrypted in transit. That is the gateway's
> own setup, not a choice this module makes, and Odoo shows a warning on the provider
> form about it. If NEGDI gives you an HTTPS endpoint, put it in **NEGDI API URL** and
> the warning goes away. Card details are never part of these requests — the card is
> entered on the bank's own 3-D Secure page.

Then press **Test connection**. It asks NEGDI which order types your terminal has
enabled, which proves the credentials, the reachability and the signature checking
without moving any money. It also records whether your terminal allows reversal, which
is what decides if Odoo offers a refund button.

Then set the provider to *Enabled*.

The password and the public key are stored in Odoo as system-group fields and are never
written to the log.

## Tests

```bash
odoo -d <db> -i payment_negdi --test-enable --test-tags /payment_negdi --stop-after-init
```

The tests stub the gateway; they do not call NEGDI.

## Support

Issues and pull requests are welcome at
<https://github.com/buya-v/payment_negdi/issues>.

This module is maintained by ITAUCO. It is not affiliated with, nor endorsed by, NEGDI.
