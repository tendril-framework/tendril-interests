

from enum import IntEnum
from typing import Any
from typing import Type
from typing import List
from typing import Callable
from typing import NamedTuple
from typing import Optional
from typing import Union


class MonitorExportLevel(IntEnum):
    STUB = 1
    NORMAL = 2
    FULL = 3
    NEVER = 4


class MonitorSpec(NamedTuple):
    path: str
    export_name: Optional[str] = None
    export_level: Optional[MonitorExportLevel] = MonitorExportLevel.NEVER
    export_processor: Optional[Callable[[Any], Any]] = None
    parser: Optional[Type] = None
    preprocessor: Optional[Union[List[Callable[[Any], Any]], Callable[[Any], Any]]] = None
    serializer: Optional[Callable[[Any], str]] = None
    deserializer: Optional[Callable[[str], Any]] = None
    multiple_container: Optional[Type] = None
    expire: Optional[int] = None
    default: Optional[Any] = None

    @property
    def keep_hot(self):
        if self.export_level < MonitorExportLevel.NEVER:
            return True

    def publish_name(self):
        return self.export_name or self.path
