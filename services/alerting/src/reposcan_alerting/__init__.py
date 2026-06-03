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
from .geo import entries_within_zone, haversine_feet
from .service import AlertingService, normalize_plate_text

__all__ = [
    "AlertDeliveryService",
    "AlertDeliveryTransport",
    "AlertingService",
    "entries_within_zone",
    "haversine_feet",
    "MemoryAlertDeliveryTransport",
    "PermanentAlertDeliveryError",
    "RetryableAlertDeliveryError",
    "WebhookAlertDeliveryTransport",
    "create_alert_delivery_service_from_deployment",
    "normalize_plate_text",
]
