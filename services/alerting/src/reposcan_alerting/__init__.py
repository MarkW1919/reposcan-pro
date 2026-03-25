"""RepoScan Pro alerting service primitives."""

from .delivery import (
    AlertDeliveryService,
    AlertDeliveryTransport,
    MemoryAlertDeliveryTransport,
    PermanentAlertDeliveryError,
    RetryableAlertDeliveryError,
    WebhookAlertDeliveryTransport,
    create_alert_delivery_service_from_deployment,
)
from .service import AlertingService, normalize_plate_text

__all__ = [
    "AlertDeliveryService",
    "AlertDeliveryTransport",
    "AlertingService",
    "MemoryAlertDeliveryTransport",
    "PermanentAlertDeliveryError",
    "RetryableAlertDeliveryError",
    "WebhookAlertDeliveryTransport",
    "create_alert_delivery_service_from_deployment",
    "normalize_plate_text",
]
