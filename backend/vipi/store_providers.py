"""Official-store verification adapters. No client price or entitlement is trusted."""

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

import httpx

from .delivery import DeliveryError
from .subscriptions import VerifiedPurchase, billing_account_id

APPLE_PRODUCTS = {"vipi.base.annual": "base", "vipi.botmini.annual": "bot_mini"}
GOOGLE_PRODUCTS = {"vipi_base": "base", "vipi_bot_mini": "bot_mini"}


def value(enum):
    return getattr(enum, "value", enum)


def milliseconds(number):
    if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
        raise ValueError("missing_timestamp")
    return datetime.fromtimestamp(number / 1000, UTC)


class AppleProvider:
    def __init__(self, settings, *, environment=None):
        from appstoreserverlibrary.api_client import AsyncAppStoreServerAPIClient
        from appstoreserverlibrary.models.Environment import Environment
        from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier

        self.environment = environment or settings.apple_environment
        environment = Environment(self.environment)
        self.verifier = SignedDataVerifier(
            [Path(p).read_bytes() for p in settings.apple_root_certificate_paths],
            True,
            environment,
            settings.apple_bundle_id,
            settings.apple_app_id,
        )
        self.client = AsyncAppStoreServerAPIClient(
            Path(settings.apple_private_key_path).read_bytes(),
            settings.apple_key_id,
            settings.apple_issuer_id,
            settings.apple_bundle_id,
            environment,
        )
        self.client.http_client.timeout = httpx.Timeout(15)
        self.parallel = asyncio.Semaphore(4)

    async def decode(self, signed):
        async with self.parallel:
            return await asyncio.to_thread(
                self.verifier.verify_and_decode_signed_transaction, signed
            )

    async def notification(self, signed):
        from .store_notifications import fingerprint
        from appstoreserverlibrary.signed_data_verifier import (
            VerificationException,
            VerificationStatus,
        )

        try:
            async with self.parallel:
                event = await asyncio.to_thread(
                    self.verifier.verify_and_decode_notification, signed
                )
            if event.version != "2.0":
                raise ValueError()
            event_id = str(UUID(event.notificationUUID))
            transaction = None
            if event.data and event.data.signedTransactionInfo:
                decoded = await self.decode(event.data.signedTransactionInfo)
                if decoded.productId in APPLE_PRODUCTS:
                    transaction = decoded.originalTransactionId
                    if (
                        not transaction
                        or not transaction.isdecimal()
                        or len(transaction) > 64
                    ):
                        raise ValueError()
            return (
                event_id,
                transaction,
                fingerprint(
                    {
                        "id": event_id,
                        "transaction": transaction,
                        "type": event.rawNotificationType,
                        "subtype": event.rawSubtype,
                        "signed_date": event.signedDate,
                    }
                ),
            )
        except VerificationException as error:
            if error.status == VerificationStatus.INVALID_ENVIRONMENT:
                raise DeliveryError("purchase_environment_mismatch", 400) from None
            if error.status == VerificationStatus.INVALID_APP_IDENTIFIER:
                raise DeliveryError(
                    "notification_app_identifier_mismatch", 400
                ) from None
            if error.status == VerificationStatus.RETRYABLE_VERIFICATION_FAILURE:
                raise DeliveryError(
                    "notification_verification_unavailable", 503
                ) from None
            raise DeliveryError("notification_invalid", 400) from None
        except (ValueError, KeyError, TypeError, AttributeError):
            raise DeliveryError("notification_invalid", 400) from None
        except Exception:
            # Do not echo a signed event or an SDK error containing its payload.
            raise DeliveryError("notification_verification_unavailable", 503) from None

    async def verify(self, credential, user_id, *, initial, account_check=None):
        try:
            if initial:
                supplied = await self.decode(credential)
                await self.check_account(supplied, user_id, account_check)
                original_id = supplied.originalTransactionId
            else:
                original_id = credential
            if not original_id or not original_id.isdecimal() or len(original_id) > 64:
                raise ValueError("invalid_original_transaction")
            # A valid historical JWS is not proof of current entitlement. Always
            # obtain current subscription status, including refunds and renewals.
            status = await self.client.get_all_subscription_statuses(original_id)
            candidates = []
            for group in status.data or []:
                for item in group.lastTransactions or []:
                    if item.originalTransactionId != original_id:
                        continue
                    transaction = await self.decode(item.signedTransactionInfo)
                    await self.check_account(transaction, user_id, account_check)
                    if transaction.originalTransactionId != original_id:
                        raise ValueError("transaction_changed")
                    expiry = milliseconds(transaction.expiresDate)
                    revoked = transaction.revocationDate is not None or value(
                        item.status
                    ) not in (1, 4)
                    if value(item.status) == 4 and item.signedRenewalInfo:
                        async with self.parallel:
                            renewal = await asyncio.to_thread(
                                self.verifier.verify_and_decode_renewal_info,
                                item.signedRenewalInfo,
                            )
                        if renewal.originalTransactionId != original_id:
                            raise ValueError("renewal_changed")
                        expiry = milliseconds(renewal.gracePeriodExpiresDate)
                    trial = (
                        milliseconds(transaction.expiresDate)
                        if value(transaction.offerDiscountType) == "FREE_TRIAL"
                        else None
                    )
                    candidates.append(
                        VerifiedPurchase(
                            "apple",
                            original_id,
                            original_id,
                            APPLE_PRODUCTS[transaction.productId],
                            expiry,
                            revoked,
                            self.environment,
                            trial,
                        )
                    )
            if len(candidates) != 1:
                raise ValueError("subscription_not_found")
            return candidates[0]
        except DeliveryError:
            raise
        except Exception as error:
            from appstoreserverlibrary.signed_data_verifier import (
                VerificationException,
                VerificationStatus,
            )

            if isinstance(error, VerificationException):
                if error.status == VerificationStatus.INVALID_ENVIRONMENT:
                    raise DeliveryError("purchase_environment_mismatch", 400) from None
                if error.status == VerificationStatus.RETRYABLE_VERIFICATION_FAILURE:
                    raise DeliveryError(
                        "purchase_verification_unavailable", 503
                    ) from None
                raise DeliveryError("purchase_invalid", 400) from None
            if isinstance(error, (ValueError, KeyError, TypeError, AttributeError)):
                raise DeliveryError("purchase_invalid", 400) from None
            raise DeliveryError("purchase_verification_unavailable", 503) from None

    async def check_account(self, transaction, user_id, account_check=None):
        identifier = str(UUID(transaction.appAccountToken or ""))
        if (
            transaction.productId not in APPLE_PRODUCTS
            or value(transaction.type) != "Auto-Renewable Subscription"
            or not (
                await account_check("apple", identifier)
                if account_check
                else identifier == user_id
            )
        ):
            raise DeliveryError("purchase_account_mismatch", 409)

    async def acknowledge(self, purchase):
        # StoreKit Transaction.finish happens on the client only after sync.
        return

    async def close(self):
        await self.client.http_client.aclose()


class GoogleProvider:
    def __init__(self, settings, *, transport=None, credentials=None):
        from google.oauth2 import service_account

        self.settings = settings
        self.credentials = (
            credentials
            or service_account.Credentials.from_service_account_file(
                settings.google_service_account_path,
                scopes=["https://www.googleapis.com/auth/androidpublisher"],
            )
        )
        self.http = httpx.AsyncClient(
            timeout=15, follow_redirects=False, transport=transport
        )
        self.auth_lock = asyncio.Lock()
        self.root = (
            "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/"
            + quote(settings.google_package_name, safe="")
        )

    async def headers(self):
        async with self.auth_lock:
            if not self.credentials.valid:
                from google.auth.transport.requests import Request

                request = Request()

                def bounded_request(*args, **kwargs):
                    kwargs["timeout"] = 15
                    return request(*args, **kwargs)

                await asyncio.to_thread(self.credentials.refresh, bounded_request)
            return {"Authorization": "Bearer " + self.credentials.token}

    async def verify(self, credential, user_id, *, initial, account_check=None):
        if not 1 <= len(credential) <= 4096 or any(c.isspace() for c in credential):
            raise DeliveryError("purchase_invalid", 400)
        try:
            response = await self.http.get(
                self.root
                + "/purchases/subscriptionsv2/tokens/"
                + quote(credential, safe=""),
                headers=await self.headers(),
            )
            if response.status_code in (400, 404, 410):
                raise DeliveryError("purchase_invalid", 400)
            if response.status_code != 200:
                raise DeliveryError("purchase_verification_unavailable", 503)
            data = response.json()
            identifier = data.get("externalAccountIdentifiers", {}).get(
                "obfuscatedExternalAccountId"
            )
            if not (
                await account_check("google", identifier)
                if account_check
                else identifier == billing_account_id(user_id)
            ):
                raise DeliveryError("purchase_account_mismatch", 409)
            if "testPurchase" in data and not (
                self.settings.google_allow_test_purchases
                or (
                    self.settings.sandbox_restricted
                    and user_id in self.settings.store_sandbox_user_ids
                )
            ):
                raise DeliveryError("purchase_environment_mismatch", 400)
            items = data.get("lineItems", [])
            if len(items) != 1:
                raise ValueError("unsupported_subscription_items")
            item = items[0]
            product = item["productId"]
            if (
                product not in GOOGLE_PRODUCTS
                or item.get("offerDetails", {}).get("basePlanId") != "annual"
            ):
                raise ValueError("unsupported_product")
            expiry = datetime.fromisoformat(item["expiryTime"].replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                raise ValueError("missing_timezone")
            active_states = {
                "SUBSCRIPTION_STATE_ACTIVE",
                "SUBSCRIPTION_STATE_IN_GRACE_PERIOD",
                "SUBSCRIPTION_STATE_CANCELED",
            }
            linked = data.get("linkedPurchaseToken")
            # offerId describes the offer purchased, not whether trial is still
            # running. Only the provider's current free-trial phase supplies it.
            trial = expiry if "freeTrial" in item.get("offerPhase", {}) else None
            return VerifiedPurchase(
                "google",
                credential,
                hashlib.sha256(credential.encode()).hexdigest(),
                GOOGLE_PRODUCTS[product],
                expiry,
                data.get("subscriptionState") not in active_states,
                "Sandbox" if "testPurchase" in data else "Production",
                trial,
                hashlib.sha256(linked.encode()).hexdigest() if linked else None,
                data.get("acknowledgementState") == "ACKNOWLEDGEMENT_STATE_PENDING",
                product,
            )
        except DeliveryError:
            raise
        except (ValueError, KeyError, TypeError):
            raise DeliveryError("purchase_invalid", 400) from None
        except Exception:
            raise DeliveryError("purchase_verification_unavailable", 503) from None

    async def verify_for_environment(
        self, credential, user_id, environment, *, account_check=None
    ):
        result = await self.verify(
            credential, user_id, initial=False, account_check=account_check
        )
        if result.environment != environment:
            raise DeliveryError("purchase_environment_mismatch", 400)
        return result

    async def acknowledge(self, purchase):
        if not purchase.needs_acknowledgement or purchase.revoked:
            return
        try:
            response = await self.http.post(
                self.root
                + "/purchases/subscriptions/"
                + quote(purchase.store_product, safe="")
                + "/tokens/"
                + quote(purchase.reference, safe="")
                + ":acknowledge",
                headers=await self.headers(),
                json={},
            )
            if response.status_code not in (200, 204):
                raise DeliveryError("purchase_acknowledgement_pending", 503)
        except httpx.HTTPError:
            raise DeliveryError("purchase_acknowledgement_pending", 503) from None

    async def close(self):
        await self.http.aclose()


class AccountScopedAppleProvider:
    """Separate signed-store verifiers; environment is accepted only after verification."""

    def __init__(self, settings):
        self.settings = settings
        self.production = AppleProvider(settings, environment="Production")
        self.sandbox = AppleProvider(settings, environment="Sandbox")

    async def verify(self, credential, user_id, *, initial, account_check=None):
        try:
            return await self.production.verify(
                credential, user_id, initial=initial, account_check=account_check
            )
        except DeliveryError as error:
            if (
                error.code != "purchase_environment_mismatch"
                or user_id not in self.settings.store_sandbox_user_ids
            ):
                raise
        return await self.sandbox.verify(
            credential, user_id, initial=initial, account_check=account_check
        )

    async def verify_for_environment(
        self, credential, user_id, environment, *, account_check=None
    ):
        if environment == "Sandbox":
            if user_id not in self.settings.store_sandbox_user_ids:
                raise DeliveryError("purchase_environment_mismatch", 400)
            return await self.sandbox.verify(
                credential, user_id, initial=False, account_check=account_check
            )
        if environment == "Production":
            return await self.production.verify(
                credential, user_id, initial=False, account_check=account_check
            )
        raise DeliveryError("purchase_environment_mismatch", 400)

    async def notification(self, signed):
        try:
            result = await self.production.notification(signed)
            return (*result, "Production")
        except DeliveryError as error:
            # Sandbox notifications can omit appAppleId; the production SDK
            # checks that field before reporting the environment mismatch.
            # The separate sandbox verifier still validates signature, bundle and environment.
            if error.code not in (
                "purchase_environment_mismatch",
                "notification_app_identifier_mismatch",
            ):
                raise
        result = await self.sandbox.notification(signed)
        return (*result, "Sandbox")

    async def acknowledge(self, purchase):
        return

    async def close(self):
        await self.production.close()
        await self.sandbox.close()


def providers_for(settings):
    providers = {}
    if settings.apple_private_key_path:
        providers["apple"] = (
            AccountScopedAppleProvider(settings)
            if settings.sandbox_restricted
            else AppleProvider(settings)
        )
    if settings.google_service_account_path:
        providers["google"] = GoogleProvider(settings)
    return providers
