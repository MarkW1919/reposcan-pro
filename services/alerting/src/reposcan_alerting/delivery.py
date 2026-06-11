"""Optional outbound alert delivery transports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol
from urllib import error, request

from reposcan_contracts.alert import AlertRecord
from reposcan_contracts.config.loader import load_deployment_config


class AlertDeliveryTransport(Protocol):
    def send_alert(self, alert: AlertRecord) -> None:
        ...


class RetryableAlertDeliveryError(RuntimeError):
    pass


class PermanentAlertDeliveryError(RuntimeError):
    pass


class MemoryAlertDeliveryTransport:
    def __init__(self) -> None:
        self.sent_alerts: list[AlertRecord] = []

    def send_alert(self, alert: AlertRecord) -> None:
        self.sent_alerts.append(alert)


def _load_error_body(exc: error.HTTPError) -> dict[str, Any]:
    try:
        payload = exc.read().decode("utf-8")
        return json.loads(payload) if payload else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}


class WebhookAlertDeliveryTransport:
    def __init__(
        self,
        *,
        webhook_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.webhook_url = webhook_url
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def send_alert(self, alert: AlertRecord) -> None:
        payload = json.dumps(alert.model_dump(mode="json")).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": alert.alert_id,
            "X-RepoScan-Record-Type": "alert",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        outbound_request = request.Request(
            self.webhook_url,
            data=payload,
            headers=headers,
            method="POST",
        )

        try:
            with request.urlopen(outbound_request, timeout=self.timeout_seconds) as response:
                if response.status >= 400:
                    raise RetryableAlertDeliveryError(f"alert delivery returned HTTP {response.status}")
                return
        except error.HTTPError as exc:
            body = _load_error_body(exc)
            if exc.code == 409 and (
                body.get("idempotent") is True
                or body.get("status") == "already_exists"
                or body.get("status") == "duplicate"
            ):
                return
            if exc.code in (408, 429) or exc.code >= 500:
                raise RetryableAlertDeliveryError(f"alert delivery retryable HTTP {exc.code}") from exc
            raise PermanentAlertDeliveryError(f"alert delivery rejected HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RetryableAlertDeliveryError(f"alert delivery unavailable: {exc.reason}") from exc


class AlertDeliveryService:
    def __init__(self, transport: AlertDeliveryTransport) -> None:
        self.transport = transport

    def deliver(self, alert: AlertRecord) -> None:
        self.transport.send_alert(alert)


def create_alert_delivery_service_from_deployment(
    *,
    deployment_config_path: str | Path = "configs/deployments/local-dev.yaml",
) -> AlertDeliveryService | None:
    deployment = load_deployment_config(deployment_config_path)
    if not deployment.alert_delivery.enabled or not deployment.alert_delivery.webhook_url:
        return None
    return AlertDeliveryService(
        WebhookAlertDeliveryTransport(
            webhook_url=deployment.alert_delivery.webhook_url,
            api_key=deployment.alert_delivery.api_key,
            timeout_seconds=deployment.alert_delivery.timeout_seconds,
        )
    )
