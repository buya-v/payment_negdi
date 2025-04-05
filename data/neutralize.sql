-- disable negdi payment provider
UPDATE payment_provider
   SET negdi_merchant_identifier = NULL,
       negdi_access_code = NULL,
       negdi_sha_request = NULL,
       negdi_sha_response = NULL;
