

from pprint import pprint
import time
import re
import json

from os.path import commonprefix
from fnmatch import fnmatch
from typing import List
from typing import Any
from typing import Optional

from tendril.caching import transit
from tendril.utils.pydantic import TendrilTBaseModel
from tendril.core.mq.aio import with_mq_client

from tendril.monitors.spec import MonitorSpec
from tendril.monitors.spec import MonitorPublishFrequency
from tendril.monitors.spec import DecimalEncoder
from tendril.utils.types.unitbase import UnitBase
from tendril.common.interests.representations import ExportLevel

from .base import InterestMixinBase
from tendril.utils import log
logger = log.get_logger(__name__, log.DEFAULT)


idx_rex = re.compile(r"^(?P<key>\S+)\[(?P<idx>\d+)\]")


class InterestBaseMonitorsTMixin(TendrilTBaseModel):
    monitors: Optional[Any]


class InterestMonitorsMixin(InterestMixinBase):
    monitors_spec : List[MonitorSpec] = []

    @property
    def monitors(self):
        if not hasattr(self, '_monitors'):
            self._monitors = {}
        return self._monitors

    def monitor_get_spec(self, monitor):
        for spec in self.monitors_spec:
            if fnmatch(monitor, spec.publish_name()):
                return spec

    def _monitor_get_cache_loc(self, spec):
        return {
            'namespace': f'im:{self.id}',
            'key': spec.publish_name()
        }

    @with_mq_client
    async def monitor_publish(self, spec: MonitorSpec, value,
                              name=None, timestamp=None, mq=None):
        if not timestamp:
            timestamp = time.clock_gettime_ns(time.CLOCK_REALTIME)
        if not name:
            name = spec.publish_name()
        bucket = 'im'

        tags = {}

        if hasattr(self, 'cached_localizers'):
            localizers = {k: v['name'] for k, v in self.cached_localizers().items()}
            tags.update(localizers)
        tags[self.type_name] = str(self.name)

        if isinstance(spec.publish_measurement, str):
            measurement = spec.publish_measurement
        else:
            measurement = spec.publish_measurement(name)
        if measurement != name:
            parts = name.split('.')
            if measurement in parts:
                parts.remove(measurement)
            if len(parts) == 1:
                tags['identifier'] = parts[0]
            if len(parts) > 1:
                raise ValueError("Don't know how to construct an influxdb string")

        # We don't use the usual serializers here. Instead, we rely on the DecimalEncoder
        # This is another significant source of fragility and may need to be improved.
        # value = spec.get_serializer()(value)
        fields = {'value': value}

        msg = json.dumps({'measurement': measurement,
                       'tags': tags,
                     'fields': fields,
                  'timestamp': timestamp}, cls=DecimalEncoder)

        key = f'{bucket}.{self.type_name}.{measurement}'
        await mq.publish(key, msg)

    async def monitor_write(self, spec: MonitorSpec, value,
                            name=None, timestamp=None):
        if spec.keep_hot:
            # Publish to cache
            kwargs = self._monitor_get_cache_loc(spec)
            if name:
                kwargs['key'] = name
            kwargs.update({'ttl': spec.expire, 'ser': spec.get_serializer(), 'get': True})

            # TODO Replace with async when tendril-caching allows it
            old_value = transit.write(value, **kwargs)
            if old_value:
                deser = spec.get_deserializer()
                if isinstance(old_value, bytes):
                    old_value = old_value.decode()
                if deser:
                    old_value = deser(old_value)
        publish = False
        match spec.publish_frequency:
            case MonitorPublishFrequency.ALWAYS:
                publish = True
            case MonitorPublishFrequency.ONCHANGE:
                if old_value != value:
                    publish = True
        if publish:
            await self.monitor_publish(spec, value,
                                       name=name, timestamp=timestamp)


    def monitor_report(self, monitor, value, timestamp=None,
                       background_tasks=None):
        spec = self.monitor_get_spec(monitor)
        if not spec:
            return
        if not background_tasks:
            raise NotImplementedError("Monitors currently need to be updated through "
                                      "apiserver endpoints with background_tasks.")
        if not timestamp:
            timestamp = time.clock_gettime_ns(time.CLOCK_REALTIME)
        background_tasks.add_task(self.monitor_write, spec, value,
                                  name=monitor, timestamp=timestamp)

    def _monitor_extract(self, parts, walker):
        for part in parts:
            match = idx_rex.match(part)
            try:
                if match:
                    walker = walker[match.group('key')]
                    walker = walker[int(match.group('idx'))]
                else:
                    walker = walker[part]
            except KeyError:
                return None
        return walker

    def _monitor_extract_discriminated(self, parts, walker, discriminators):
        rv = {}
        for discriminator in discriminators:
            rv[discriminator] = self._monitor_extract(parts, walker[discriminator])
        return rv

    def _monitor_extract_from_report(self, path, report):
        parts = path.split('.')
        walker = report
        discriminators = None
        for part in parts:
            if discriminators:
                subparts.append(parts)
                continue
            elif part == '*':
                subparts = []
                discriminators = walker.keys()
                continue
            else:
                match = idx_rex.match(part)
                try:
                    if match:
                        walker = walker[match.group('key')]
                        walker = walker[int(match.group('idx'))]
                    else:
                        walker = walker[part]
                except KeyError:
                    return None
        if not discriminators:
            return walker
        else:
            return self._monitor_extract_discriminated(subparts, walker, discriminators)

    def _monitor_process_value(self, monitor_spec, value):
        if value is not None:
            if monitor_spec.preprocessor:
                if isinstance(monitor_spec.preprocessor, list):
                    for preprocessor in monitor_spec.preprocessor:
                        value = preprocessor(value)
                else:
                    value = monitor_spec.preprocessor(value)
            if monitor_spec.deserializer:
                value = monitor_spec.deserializer(value)
        return value

    def _monitor_process_discriminated_value(self, monitor_spec, values,
                                             timestamp=None, background_tasks=None):
        if isinstance(values, dict):
            for discriminator, discriminated_value in values.items():
                value = self._monitor_process_value(monitor_spec, discriminated_value)
                name = monitor_spec.publish_name().replace('*', discriminator)
                self.monitor_report(name, value, timestamp=timestamp,
                                    background_tasks=background_tasks)

    def monitors_report(self, report, timestamp=None, background_tasks=None):
        # pprint(report)
        if not timestamp:
            timestamp = time.clock_gettime_ns(time.CLOCK_REALTIME)
        for monitor_spec in self.monitors_spec:
            value = self._monitor_extract_from_report(monitor_spec.path, report)
            if value is None:
                continue
            if monitor_spec.multiple_container and isinstance(value, monitor_spec.multiple_container):
                self._monitor_process_discriminated_value(monitor_spec, value, timestamp=timestamp,
                                                          background_tasks=background_tasks)
            else:
                value = self._monitor_process_value(monitor_spec, value)
                self.monitor_report(monitor_spec.publish_name(), value,
                                    timestamp=timestamp,
                                    background_tasks=background_tasks)

    def _monitor_get_value(self, spec):
        kwargs = self._monitor_get_cache_loc(spec)
        kwargs.update({
            'deser': spec.get_deserializer()
        })
        value = transit.read(**kwargs)
        if spec.default is not None and not value:
            value = spec.default
        return value

    def _monitor_get_multiple_value(self, spec):
        namespace = f'im:{self.id}'
        keys = transit.find_keys(namespace=namespace, pattern=spec.path)
        values = {}
        for key in keys:
            key = key.decode().removeprefix(namespace + ':')
            name = spec.path.removeprefix(namespace)
            prefix = commonprefix([key, name])
            key = key.removeprefix(prefix)
            if not key:
                continue
            values[key] = transit.read(namespace, prefix + key)
        return values

    def _monitors_at_export_level(self, export_level):
        return [x for x in self.monitors_spec if x.export_level <= export_level]

    def _monitor_export_process(self, value, spec):
        if spec.export_processor:
            value = spec.export_processor(value)
        elif isinstance(value, UnitBase):
            value = str(value)
        return value

    def export(self, export_level=ExportLevel.NORMAL,
               session=None, auth_user=None, **kwargs):
        rv = {}
        if hasattr(super(), 'export'):
            rv.update(super().export(export_level=export_level, session=session,
                                     auth_user=auth_user, **kwargs))
        monitor_values = {}
        for monitor_spec in self._monitors_at_export_level(export_level):
            if monitor_spec.multiple_container:
                value = self._monitor_get_multiple_value(monitor_spec)
                if not value:
                    continue
                if monitor_spec.multiple_container != dict:
                    raise NotImplementedError(f"We only support flat dict type multiple containers. "
                                              f"Got {monitor_spec.multiple_container}")
                for key, val in value.items():
                    value[key] = self._monitor_export_process(value[key], monitor_spec)
                # TODO This will break if the * is elsewhere or if there are multiple
                name = monitor_spec.publish_name().\
                    replace('*', '').\
                    replace('..', '.').\
                    strip('.')
                monitor_values[name] = value
            else:
                value = self._monitor_get_value(monitor_spec)
                if value is None:
                    continue
                value = self._monitor_export_process(value, monitor_spec)
                monitor_values[monitor_spec.publish_name()] = value
        rv['monitors'] = monitor_values
        return rv
