"""MpesaClient: A unified client for M-PESA services."""

from mpesakit.auth import TokenManager
from mpesakit.http_client import MpesaHttpClient
from mpesakit.services import (
    B2BService,
    B2CService,
    BalanceService,
    BillService,
    C2BService,
    DynamicQRCodeService,
    StkPushService,
    RatibaService,
    ReversalService,
    TaxService,
    TransactionService,
)


class MpesaClient:
    """Unified client for all M-PESA services."""

    def __init__(
        self, consumer_key: str, consumer_secret: str, environment: str = "sandbox",use_session: bool = False
    ) -> None:
        """Initialize the MpesaClient with all service facades."""
        self.http_client = MpesaHttpClient(env=environment,use_session=use_session)
        self.token_manager = TokenManager(
            http_client=self.http_client,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
        )

        # express => M-PESA STK Push
        self.express = StkPushService(
            http_client=self.http_client, token_manager=self.token_manager
        )
        self.stk_push = self.express.push  # Alias for convenience
        self.stk_query = self.express.query  # Alias for convenience

        # b2c => M-PESA Business to Customer services
        self.b2c = B2CService(
            http_client=self.http_client, token_manager=self.token_manager
        )

        # b2b => M-PESA Business to Business services
        self.b2b = B2BService(
            http_client=self.http_client, token_manager=self.token_manager
        )

        # transaction => M-PESA Transaction status services
        self.transactions = TransactionService(
            http_client=self.http_client, token_manager=self.token_manager
        )

        # tax => M-PESA Tax services
        self.tax = TaxService(
            http_client=self.http_client, token_manager=self.token_manager
        )

        # balance => M-PESA Account balance services
        self.balance = BalanceService(
            http_client=self.http_client, token_manager=self.token_manager
        )

        # reversal => M-PESA Transaction reversal services
        self.reversal = ReversalService(
            http_client=self.http_client, token_manager=self.token_manager
        )

        # bill => M-PESA Bill services
        self.bill = BillService(
            http_client=self.http_client, token_manager=self.token_manager
        )

        # dynamic_qr => M-PESA Dynamic QR services
        self.dynamic_qr = DynamicQRCodeService(
            http_client=self.http_client, token_manager=self.token_manager
        )

        # c2b => M-PESA Customer to Business services
        self.c2b = C2BService(
            http_client=self.http_client, token_manager=self.token_manager
        )

        # ratiba => M-PESA Ratiba services
        self.ratiba = RatibaService(
            http_client=self.http_client, token_manager=self.token_manager
        )

    def process_callback(self, payload: dict):
        """Unified callback router.
        Detects the payload type dynamically and passes it to the correct model parser.
        """
        if not isinstance(payload, dict):
            raise ValueError("Payload must be a dictionary")

        # 1. STK Push Callback ("Body" -> "stkCallback")
        if "Body" in payload and "stkCallback" in payload["Body"]:
            return self.process_stk_callback(payload)

        # 2. Ratiba Standing Orders ("ResponseHeader" & "ResponseBody")
        if "ResponseHeader" in payload and "ResponseBody" in payload:
            return self.process_ratiba_service_callback(payload)

        # 3. Dynamic QR Response
        if "QRCode" in payload:
            return self.process_dynamic_qr_code_callback(payload)

        # 4. Bill Manager Notification
        if "accountReference" in payload and "shortCode" in payload:
            return self.process_bill_manager_callback(payload)

        # 5. B2B Express Checkout
        if "requestId" in payload and "conversationID" in payload:
            return self.process_b2b_callback(payload)

        # 6. STK Query Response
        if "CheckoutRequestID" in payload and "MerchantRequestID" in payload and "Body" not in payload:
            return self.process_stk_query_callback(payload)

        # 7. Asynchronous Results (B2C, Account Balance, Reversal, Transaction Status, Tax)
        if "Result" in payload:
            result_data = payload.get("Result", {})
            desc = result_data.get("ResultDesc", "").lower()

            # Account Balance Timeout specifically
            if "timed out" in desc and result_data.get("ResultCode") == 2001:
                return self.process_account_balance_timeout(payload)

            params = result_data.get("ResultParameters", {})

            if isinstance(params, dict) and "ResultParameter" in params:
                # Account Balance check
                items = params.get("ResultParameter", [])
                if any(i.get("Key") == "AccountBalance" for i in items):
                    return self.process_account_balance_callback(payload)
                # Tax Remittance check
                if any(i.get("Key") == "TransactionReceipt" for i in items) and not any(i.get("Key") == "B2CRecipientPhoneNumber" for i in items):
                    return self.process_tax_remittance_callback(payload)

            if isinstance(params, list):
                # B2C check
                if any(i.get("Key") == "B2CRecipientPhoneNumber" for i in params):
                    return self.process_b2c_callback(payload)
                # Transaction status check
                if any(i.get("Key") == "TransactionStatus" for i in params):
                    return self.process_transcations_callback(payload)

            # Reversal default fallback or custom parameter structures
            return self.process_reversal_callback(payload)

        raise ValueError("Unsupported or unknown M-PESA callback format structure.")

    def process_stk_callback(self, payload):
        from mpesakit.mpesa_express.schemas import (
            StkPushSimulateCallback
        )
        return StkPushSimulateCallback.model_validate(payload)

    def process_stk_query_callback(self, payload):
        from mpesakit.mpesa_express.schemas import (
            StkPushQueryResponse
        )
        return StkPushQueryResponse.model_validate(payload)

    def process_account_balance_callback(self, payload):
        from mpesakit.account_balance.schemas import (
            AccountBalanceResultCallback
        )
        return AccountBalanceResultCallback.model_validate(payload)

    def process_account_balance_timeout(self, payload):
        from mpesakit.account_balance.schemas import (
            AccountBalanceTimeoutCallback
        )
        return AccountBalanceTimeoutCallback.model_validate(payload)

    def process_b2c_callback(self, payload):
        from mpesakit.b2c.schemas import (
            B2CResultCallback
        )
        return B2CResultCallback.model_validate(payload)

    def process_b2b_callback(self, payload):
        from mpesakit.b2b_express_checkout.schemas import (
            B2BExpressCheckoutCallback
        )
        return B2BExpressCheckoutCallback.model_validate(payload)

    def process_transcations_callback(self, payload):
        from mpesakit.transaction_status.schemas import (
            TransactionStatusResultCallback
        )
        return TransactionStatusResultCallback.model_validate(payload)

    def process_bill_manager_callback(self, payload):
        from mpesakit.bill_manager.schemas import (
            BillManagerPaymentNotificationRequest
        )
        return BillManagerPaymentNotificationRequest.model_validate(payload)


    def process_tax_remittance_callback(self, payload):
        from mpesakit.tax_remittance.schemas import (
            TaxRemittanceResultCallback
        )
        return TaxRemittanceResultCallback.model_validate(payload)

    def process_dynamic_qr_code_callback(self, payload):
        from mpesakit.dynamic_qr_code.schemas import (
             DynamicQRGenerateResponse
        )
        return  DynamicQRGenerateResponse.model_validate(payload)

    def process_ratiba_service_callback(self, payload):
        from mpesakit.mpesa_ratiba.schemas import (
             StandingOrderCallback
        )
        return  StandingOrderCallback.model_validate(payload)

    def process_reversal_callback(self, payload):
        from mpesakit.reversal.schemas import (
            ReversalResultCallback
        )
        return ReversalResultCallback.model_validate(payload)


