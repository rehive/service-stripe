from enumfields.enums import Enum


class SessionMode(Enum):
	SETUP = 'setup'
	PAYMENT = 'payment'


class PaymentStatus(Enum):
    PROCESSING = 'processing'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
