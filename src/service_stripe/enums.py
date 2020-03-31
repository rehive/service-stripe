from enumfields.enums import Enum


class SubscriptionStatus(Enum):
    PENDING = 'pending'
    FAILED = 'failed'
    ACTIVE = 'active'
    EXPIRED = 'expired'
    CANCELED = 'canceled'
