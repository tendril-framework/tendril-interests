

import enum


class LifecycleStatus(enum.Enum):
    NEW = "NEW"
    APPROVAL = "APPROVAL"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"
    ARCHIVAL = "ARCHIVAL"
