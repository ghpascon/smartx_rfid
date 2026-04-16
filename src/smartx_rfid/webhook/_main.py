import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime, date
from decimal import Decimal

import httpx


logger = logging.getLogger(__name__)


class WebhookManager:
    def __init__(
        self,
        url: str,
        timeout: float = 5.0,
        max_retries: int = 2,
        max_concurrent_requests: int = 50,
    ):
        self.url = url
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_concurrent_requests = max_concurrent_requests

        self.default_headers = {"Content-Type": "application/json", "User-Agent": "SmartX-Connector/1.0"}
        self._client: Optional[httpx.AsyncClient] = None
        self._client_lock = asyncio.Lock()
        self._request_semaphore = asyncio.Semaphore(max(1, max_concurrent_requests))

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None and not self._client.is_closed:
            return self._client

        async with self._client_lock:
            if self._client is None or self._client.is_closed:
                limits = httpx.Limits(
                    max_connections=max(20, self.max_concurrent_requests),
                    max_keepalive_connections=max(10, self.max_concurrent_requests // 2),
                )
                self._client = httpx.AsyncClient(timeout=self.timeout, limits=limits)

        return self._client

    async def aclose(self) -> None:
        async with self._client_lock:
            if self._client is not None and not self._client.is_closed:
                await self._client.aclose()

    async def __aenter__(self):
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.aclose()

    def _build_headers(self, headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        merged_headers = dict(self.default_headers)
        if headers:
            merged_headers.update(headers)
        return merged_headers

    @staticmethod
    def _should_retry_status_code(status_code: int) -> bool:
        return status_code == 429 or status_code >= 500

    def _make_serializable(self, obj: Any) -> Any:
        """
        Converts objects to JSON-serializable format.

        Handles:
        - datetime/date objects -> ISO format strings
        - Decimal -> float
        - Classes with __dict__ -> dict
        - Sets -> lists
        - Bytes -> string (decoded)
        - Iterables -> lists

        Args:
            obj: Object to convert

        Returns:
            JSON-serializable version of the object
        """
        # Handle None
        if obj is None:
            return None

        # Handle datetime and date
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()

        # Handle Decimal
        if isinstance(obj, Decimal):
            return float(obj)

        # Handle bytes
        if isinstance(obj, bytes):
            try:
                return obj.decode("utf-8")
            except Exception:
                return str(obj)

        # Handle sets
        if isinstance(obj, set):
            return list(obj)

        # Handle dictionaries (recursively)
        if isinstance(obj, dict):
            return {key: self._make_serializable(value) for key, value in obj.items()}

        # Handle lists and tuples (recursively)
        if isinstance(obj, (list, tuple)):
            return [self._make_serializable(item) for item in obj]

        # Handle objects with __dict__ (custom classes)
        if hasattr(obj, "__dict__"):
            return self._make_serializable(obj.__dict__)

        # Handle primitive types (str, int, float, bool)
        if isinstance(obj, (str, int, float, bool)):
            return obj

        # Last resort: convert to string
        return str(obj)

    async def post(
        self,
        payload: Any,
        headers: Optional[Dict[str, str]] = None,
        url: Optional[str] = None,
    ) -> bool:
        """
        Sends a custom JSON payload via POST.

        Args:
            payload: JSON payload to send
            headers: Optional headers for the request
            url: Optional target URL. Uses base URL if not provided.

        Returns:
            bool: True if sent successfully, False otherwise
        """

        target_url = url or self.url
        if not target_url:
            logger.warning("WEBHOOK_URL not configured in settings")
            return False

        serializable_payload = self._make_serializable(payload)
        request_headers = self._build_headers(headers)
        total_attempts = max(1, self.max_retries + 1)
        last_error = "unknown error"

        async with self._request_semaphore:
            for attempt in range(1, total_attempts + 1):
                try:
                    client = await self._get_client()
                    response = await client.post(target_url, json=serializable_payload, headers=request_headers)

                    if response.status_code < 300:
                        logger.info("Webhook sent successfully to %s - Status: %s", target_url, response.status_code)
                        return True

                    response_preview = (response.text or "")[:200]
                    last_error = f"HTTP {response.status_code}: {response_preview}"

                    if self._should_retry_status_code(response.status_code) and attempt < total_attempts:
                        wait_time = 2 ** (attempt - 1)
                        logger.warning(
                            "Webhook returned retryable status %s (attempt %s/%s). Retrying in %ss.",
                            response.status_code,
                            attempt,
                            total_attempts,
                            wait_time,
                        )
                        await asyncio.sleep(wait_time)
                        continue

                    logger.warning("Webhook failed - Status: %s - Response: %s", response.status_code, response_preview)
                    return False

                except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError, httpx.RequestError) as exc:
                    last_error = str(exc)
                    if attempt < total_attempts:
                        wait_time = 2 ** (attempt - 1)
                        logger.warning(
                            "Webhook network error (attempt %s/%s): %s. Retrying in %ss.",
                            attempt,
                            total_attempts,
                            exc,
                            wait_time,
                        )
                        await asyncio.sleep(wait_time)
                        continue

                    logger.error("Webhook failed after %s attempts due to network error: %s", total_attempts, exc)
                    return False

                except Exception as exc:
                    last_error = str(exc)
                    logger.error("Unexpected webhook error (attempt %s/%s): %s", attempt, total_attempts, exc)

                    if attempt < total_attempts:
                        wait_time = 2 ** (attempt - 1)
                        await asyncio.sleep(wait_time)
                        continue

                    break

        logger.error("Webhook failed after %s attempts. Last error: %s", total_attempts, last_error)
        return False

    async def post_event(
        self,
        device: str,
        event_type: str,
        event_data: Any = None,
        headers: Optional[Dict[str, str]] = None,
        url: Optional[str] = None,
    ) -> bool:
        """
        Sends a standardized event payload.

        Args:
            device: Name of the device sending the webhook
            event_type: Type of event being sent
            event_data: Event payload data
            headers: Optional headers for the request
            url: Optional target URL. Uses base URL if not provided.
        """
        payload = {
            "device": device,
            "event_type": event_type,
            "event_data": event_data,
        }
        return await self.post(payload=payload, headers=headers, url=url)
