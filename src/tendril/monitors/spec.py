

import json
from collections.abc import Mapping, Iterable
from numbers import Number
from decimal import Decimal
from datetime import timedelta
from datetime import datetime
from inspect import isclass
from enum import IntEnum
from typing import Any
from typing import Type
from typing import List
from typing import Callable
from typing import NamedTuple
from typing import Optional
from typing import Union

from tendril.core.tsdb.constants import TimeSeriesFundamentalType
from tendril.core.tsdb.constants import TimeSeriesExporter
from tendril.utils.types.unitbase import NumericalUnitBase
from tendril.utils.types.unitbase import UnitBase
from tendril.utils import log

logger = log.get_logger(__name__)
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
        if isinstance(obj, timedelta):
            return obj.total_seconds()
        if isinstance(obj, datetime):
            return obj.timestamp()
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
    expire: Optional[int] = None
    default: Optional[Any] = None

    multiple_container: Optional[Type] = None
    multiple_discriminators: Optional[List[str]] = ['identifier']

    localization_from_hierarchy: Optional[bool] = True
    flatten_cardinality: Optional[tuple] = ()
    structure: Optional[Any] = 'value'
    drill_down: Optional[List] = []

    fundamental_type: Optional[TimeSeriesFundamentalType] = None
    preprocessor: Optional[Union[List[Callable[[Any], Any]], Callable[[Any], Any]]] = None
    serializer: Optional[Callable[[Any], str]] = None
    deserializer: Optional[Callable[[str], Any]] = None
    is_cumulative: Optional[bool] = False
    is_constant: Optional[bool] = False
    is_continuous: Optional[bool] = True
    is_monotonic: Optional[bool] = False

    export_name: Optional[str] = None
    export_level: Optional[MonitorExportLevel] = MonitorExportLevel.NEVER
    export_processor: Optional[Callable[[Any], Any]] = None

    publish_frequency: Optional[MonitorPublishFrequency] = MonitorPublishFrequency.ONCHANGE
    publish_period: Optional[int] = 1800
    publish_measurement: Optional[Union[str, Callable[[str], str]]] = lambda x: x

    @property
    def normalized_structure(self):
        if isinstance(self.structure, str):
            return [self.structure]
        raise NotImplementedError("Non-scalar measurements are not presently supported")

    @property
    def keep_hot(self):
        if self.export_level < MonitorExportLevel.NEVER:
            return True
        if self.publish_frequency > MonitorPublishFrequency.ALWAYS:
            return True
        return False

    def publish_name(self):
        return self.export_name or self.path

    def measurement_name(self, name):
        if isinstance(self.publish_measurement, str):
            return self.publish_measurement
        else:
            return self.publish_measurement(name)

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

    def get_fundamental_type(self):
        if self.fundamental_type:
            return self.fundamental_type
        else:
            if isclass(self.deserializer):
                if issubclass(self.deserializer, bool):
                    return TimeSeriesFundamentalType.BOOLEAN
                elif issubclass(self.deserializer, (Number, NumericalUnitBase)):
                    return TimeSeriesFundamentalType.NUMERIC

    def get_preferred_exporter(self):
        fundamental_type = self.get_fundamental_type()
        if fundamental_type is not TimeSeriesFundamentalType.NUMERIC:
            return TimeSeriesExporter.CHANGES_ONLY
        else:
            if self.is_constant:
                return TimeSeriesExporter.CHANGES_ONLY
            if self.is_monotonic:
                return TimeSeriesExporter.DISCONTINUITIES_ONLY
            if self.is_cumulative:
                return TimeSeriesExporter.WINDOWED_SUMMATION
            if self.is_continuous:
                return TimeSeriesExporter.WINDOWED_MEAN
        raise ValueError(f"No preferred exported found for {self.publish_name()}")

    def render(self):
        # TODO These names may need to use better terminology
        # is_cumulative:
        #   Adding up adjacent data points is usually meaningful.
        #   Downsampling should use sum aggregation instead of mean.
        # is_constant:
        #   Generally (but not always) a constant. It often might not make sense to
        #   plot these unless to provide level markers for associated non-constant monitors.
        #   Downsampling of these should use preferably use CHANGES_ONLY type processors.
        # is_continuous:
        #   Underlying monitor data is usually continuous and interpolation between consecutive
        #   data points is probably meaningful. Instead of interpolation, however, we simply
        #   fill the last known value until a new one turns up. For non-continuous datasets,
        #   such intermediate values will be null.
        # is_monotonic:
        #   Underlying monitor data is fundamentally monotonic. Generally applied to monitors
        #   which are linear with time or whose rate of change is less important than points
        #   at which monotonicity is broken.
        return {
            'publish_name': self.publish_name(),
            'publish_frequency': self.publish_frequency,
            'publish_measurement': self.measurement_name(self.publish_name()),
            'export_level': self.export_level,
            'fundamental_type': self.get_fundamental_type(),
            'is_dynamic_container': self.multiple_container is not None,
            'is_cumulative': self.is_cumulative,
            'is_constant': self.is_constant,
            'is_continuous': self.is_continuous,
            'is_monotonic': self.is_monotonic,
        }
