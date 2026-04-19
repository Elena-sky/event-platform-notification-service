class NotificationError(Exception):
    """Base notification error."""


class TemporaryNotificationError(NotificationError):
    """Retry may help."""


class FatalNotificationError(NotificationError):
    """Retry will not help."""