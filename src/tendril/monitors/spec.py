

import json
from collections.abc import Mapping, Iterable
from decimal import Decimal

from enum import IntEnum
from typing import Any
from typing import Type
from typing import List
from typing import Callable
from typing import NamedTuple
from typing import Optional
from typing import Union

from tendril.utils.types.unitbase import NumericalUnitBase
from tendril.utils.types.unitbase import UnitBase
unit_serializer = lambda x: str(x.value)


def ensure_str(value):
    if isinstance(value, bytes):
        return value.decode()
    return value


_bool_values = {
    'true': True,
    'yes': True,
    'false': False,
    'no': False
}


def bool_parser(value):
    value = ensure_str(value)
    if isinstance(value, str):
        value = value.lower()
        return _bool_values[value]
    return bool(value)


class DecimalEncoder(json.JSONEncoder):
    # See https://stackoverflow.com/a/60243503/1934174
    def encode(self, obj):
        if isinstance(obj, Mapping):
            return '{' + ', '.join(f'{self.encode(k)}: {self.encode(v)}' for (k, v) in obj.items()) + '}'
        if isinstance(obj, Iterable) and (not isinstance(obj, str)):
            return '[' + ', '.join(map(self.encode, obj)) + ']'
        if isinstance(obj, NumericalUnitBase):
            obj = obj.value
        if isinstance(obj, Decimal):
            return f'{obj:f}'  # using normalize() gets rid of trailing 0s, using ':f' prevents scientific notation
        return super().encode(obj)


class MonitorExportLevel(IntEnum):
    STUB = 1
    NORMAL = 2
    FULL = 3
    NEVER = 4


class MonitorPublishFrequency(IntEnum):
    NEVER = 1
    PERIODIC = 2                       # Not actually implemented
    ALWAYS = 3

    ONCHANGE = 4
    ONCHANGE_OR_PERIODIC = 5           # Not actually implemented
    ONCHANGE_THESHOLD = 6              # Not actually implemented
    ONCHANGE_THESHOLD_OR_PERIODIC = 7  # Not actually implemented


class MonitorSpec(NamedTuple):
    path: str
    multiple_container: Optional[Type] = None
    expire: Optional[int] = None
    default: Optional[Any] = None

    preprocessor: Optional[Union[List[Callable[[Any], Any]], Callable[[Any], Any]]] = None
    serializer: Optional[Callable[[Any], str]] = None
    deserializer: Optional[Callable[[str], Any]] = None

    export_name: Optional[str] = None
    export_level: Optional[MonitorExportLevel] = MonitorExportLevel.NEVER
    export_processor: Optional[Callable[[Any], Any]] = None

    publish_frequency: Optional[MonitorPublishFrequency] = MonitorPublishFrequency.ONCHANGE
    publish_period: Optional[int] = 1800
    publish_measurement: Optional[Union[str, Callable[str, str]]] = lambda x: x

    @property
    def keep_hot(self):
        if self.export_level < MonitorExportLevel.NEVER:
            return True
        if self.publish_frequency > MonitorPublishFrequency.ALWAYS:
            return True
        return False

    def publish_name(self):
        return self.export_name or self.path

    def get_serializer(self):
        if self.serializer:
            return self.serializer
        if not self.deserializer:
            return json.dumps
        if issubclass(self.deserializer, Decimal):
            return str
        if issubclass(self.deserializer, UnitBase):
            return unit_serializer
        return json.dumps

    def get_deserializer(self):
        if not self.deserializer:
            return json.loads
        if self.deserializer == bool:
            return bool_parser
        return self.deserializer
