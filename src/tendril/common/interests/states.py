

import enum


class InterestLifecycleStatus(enum.Enum):
    NEW = "NEW"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"
    ARCHIVAL = "ARCHIVAL"
