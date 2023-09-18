

import time
import re
import json
import pytz
from datetime import datetime
from pydantic import Field

from os.path import commonprefix
from fnmatch import fnmatch
from typing import List
from typing import Any
from typing import Optional
from typing import Union

from tendril.caching import transit
from tendril.core.tsdb.query.models import QueryTimeSpanTModel
from tendril.core.tsdb.query.models import TimeSeriesQueryItemTModel
from tendril.core.tsdb.query.planner import TimeSeriesQueryPlanner
from tendril.core.tsdb.constants import TimeSeriesExporter
from tendril.core.mq.aio import with_mq_client
from tendril.core.tsdb.aio import tsdb_execute_query_plan

# TODO Replace with a query planner
from tendril.connectors.influxdb.query.schema import DistinctTagsFluxQueryBuilder
from tendril.connectors.influxdb.aio import influxdb_execute_query

from tendril.monitors.spec import MonitorSpec
from tendril.monitors.spec import MonitorPublishFrequency
from tendril.monitors.spec import DecimalEncoder

from tendril.utils.pydantic import TendrilTBaseModel
from tendril.utils.types.unitbase import UnitBase
from tendril.common.interests.representations import ExportLevel
from tendril.authz.roles.interests import require_permission

from tendril.config import INFLUXDB_MONITORS_BUCKET
from tendril.config import INFLUXDB_MONITORS_TOKEN

from .base import InterestMixinBase
from tendril.utils import log
logger = log.get_logger(__name__)


local_tz = pytz.timezone("Asia/Kolkata")
idx_rex = re.compile(r"^(?P<key>\S+)\[(?P<idx>\d+)\]")


class MonitorQueryItemTModel(TendrilTBaseModel):
    name: str
    exporter: TimeSeriesExporter


class MonitorsQueryTModel(TendrilTBaseModel):
    time_span: QueryTimeSpanTModel = Field(default_factory=QueryTimeSpanTModel)
    monitors: Optional[List[Union[str, MonitorQueryItemTModel]]]


class InterestBaseMonitorsTMixin(TendrilTBaseModel):
    monitors: Optional[Any]


class InterestMonitorsMixin(InterestMixinBase):
    monitors_spec : List[MonitorSpec] = []

    @property
    def monitors(self):
        if not hasattr(self, '_monitors'):
            self._monitors = {}
        return self._monitors

    def monitor_get_spec(self, monitor) -> MonitorSpec:
        for spec in self.monitors_spec:
            if fnmatch(monitor, spec.publish_name()):
                return spec

    def _monitor_get_cache_loc(self, spec):
        return {
            'namespace': f'im:{self.id}',
            'key': spec.publish_name()
        }

    def _monitor_get_publish_loc(self, spec, name=None, for_read=False):
        tags = {}
        if not for_read and spec.localization_from_hierarchy:
            if hasattr(self, 'cached_localizers'):
                localizers = {k: v['name'] for k, v in self.cached_localizers().items()}
                tags.update(localizers)
                tags.update(localizers)
        tags[self.type_name] = str(self.name)

        measurement = spec.measurement_name(name)
        if measurement != name:
            parts = name.split('.')
            if measurement in parts:
                parts.remove(measurement)
            for value_key in spec.normalized_structure:
                if value_key in parts:
                    parts.remove(value_key)
            if len(parts) == 1:
                # TODO Multiple discriminators here will break
                tags[spec.multiple_discriminators[0]] = parts[0]
            if len(parts) > 1:
                raise ValueError(f"Don't know how to construct an influxdb "
                                 f"string from parts {parts}")

        return measurement, tags

    @with_mq_client
    async def monitor_publish(self, spec: MonitorSpec, value,
                              name=None, timestamp=None,
                              additional_localizers=None,
                              mq=None):
        if not timestamp:
            timestamp = time.clock_gettime_ns(time.CLOCK_REALTIME)
        elif isinstance(timestamp, datetime):
            # If a timestamp is provided, it should be timezone-aware. If it isn't, we
            # assume it is in UTC.
            if timestamp.tzinfo is None or timestamp.tzinfo.utcoffset(timestamp) is None:
                timestamp = timestamp.replace(tzinfo=pytz.utc)
            # We actually store in local time. This is something that should be corrected.
            # It is as it is now for legacy reasons. Specifically, to be consistent with
            # the naive use of time.clock_gettime_ns above, and all the downstream users of
            # monitor data across instances
            timestamp = timestamp.astimezone(local_tz)
            timestamp = int(timestamp.timestamp() * (10 ** 9))
        elif isinstance(timestamp, int):
            # Something further up the chain probably used time.clock_gettime_ns. This is
            # treated as a ns precision timestamp in localtime.
            pass
        else:
            logger.warn(f"Got timestamp '{timestamp}' of type {type(timestamp)} for monitor "
                        f"'{spec.publish_name()}'. This is likely incorrect.")
        if not name:
            name = spec.publish_name()
        bucket = 'im'

        measurement, tags = self._monitor_get_publish_loc(spec, name)

        if additional_localizers:
            tags.update(additional_localizers)

        # We don't use the usual serializers here. Instead, we rely on the DecimalEncoder
        # This is another significant source of fragility and may need to be improved.
        # value = spec.get_serializer()(value)
        if isinstance(spec.structure, str):
            fields = {spec.structure: value}
        else:
            raise NotImplementedError("We don't currently only support scalar, independent datapoints")

        if spec.flatten_cardinality:
            for key in spec.flatten_cardinality:
                if key in tags.keys():
                    fields[key] = tags.pop(key)

        msg = json.dumps({'measurement': measurement,
                       'tags': tags,
                     'fields': fields,
                  'timestamp': timestamp}, cls=DecimalEncoder)

        key = f'{bucket}.{self.type_name}.{measurement}'
        await mq.publish(key, msg)

    async def monitor_write(self, spec: MonitorSpec, value,
                            name=None, timestamp=None,
                            additional_localizers=None):
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
            await self.monitor_publish(spec, value, name=name, timestamp=timestamp,
                                       additional_localizers=additional_localizers)

    async def monitor_report_async(self, monitor, value, timestamp=None):
        spec = self.monitor_get_spec(monitor)
        if not spec:
            return
        if not timestamp:
            timestamp = time.clock_gettime_ns(time.CLOCK_REALTIME)
        await self.monitor_write(spec, value, name=monitor,
                                 timestamp=timestamp)

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

    def _monitor_get_dynamic_keys(self, spec):
        namespace = f'im:{self.id}'
        cache_keys = transit.find_keys(namespace=namespace, pattern=spec.path)
        keys = []
        prefix = ''
        for cache_key in cache_keys:
            if b'*' in cache_key:
                continue
            key = cache_key.decode().removeprefix(namespace + ':')
            name = spec.path.removeprefix(namespace)
            prefix = commonprefix([key, name])
            key = key.removeprefix(prefix)
            if not key:
                continue
            keys.append(key)
        return prefix, keys

    def _monitor_get_multiple_value(self, spec):
        # namespace = f'im:{self.id}'
        # keys = transit.find_keys(namespace=namespace, pattern=spec.path)
        namespace = f'im:{self.id}'
        values = {}
        prefix, keys = self._monitor_get_dynamic_keys(spec)
        for key in keys:
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

    @require_permission('read', strip_auth=False, required=False,
                        exceptions=[(('export_level', ExportLevel.STUB),)])
    def monitors_export(self, export_level=ExportLevel.EVERYTHING,
                        auth_user=None, session=None):
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
                name = monitor_spec.publish_name(). \
                    replace('*', ''). \
                    replace('..', '.'). \
                    strip('.')
                monitor_values[name] = value
            else:
                value = self._monitor_get_value(monitor_spec)
                if value is None:
                    continue
                value = self._monitor_export_process(value, monitor_spec)
                monitor_values[monitor_spec.publish_name()] = value
        return monitor_values

    def export(self, export_level=ExportLevel.NORMAL,
               session=None, auth_user=None, **kwargs):
        rv = {}
        if hasattr(super(), 'export'):
            rv.update(super().export(export_level=export_level, session=session,
                                     auth_user=auth_user, **kwargs))
        monitors = self.monitors_export(export_level=export_level,
                                        auth_user=auth_user, session=session)
        if monitors:
            rv['monitors'] = monitors
        return rv

    @require_permission('read', strip_auth=False, required=False)
    def monitors_spec_render(self, auth_user=None, session=None):
        specs = [x.render() for x in self.monitors_spec]
        for spec in specs:
            if spec['is_dynamic_container']:
                _, spec['known_keys'] = self._monitor_get_dynamic_keys(
                    self.monitor_get_spec(spec['publish_name'])
                )
        return specs

    def _monitor_get_query(self, name,
                           spec:MonitorSpec,
                           time_span:QueryTimeSpanTModel,
                           exporter: TimeSeriesExporter):
        measurement, tags = self._monitor_get_publish_loc(spec, name, for_read=True)
        fields = [spec.structure]
        query = TimeSeriesQueryItemTModel(
            domain='monitors',
            export_name=name,
            time_span=time_span,
            measurement=measurement,
            tags=tags,
            fields=fields,
            exporter=exporter,
            include_ends=spec.is_continuous,
        )
        return query

    def _monitor_get_dynamic_keys_published(self, name, spec, time_span=None):
        measurement, tags = self._monitor_get_publish_loc(spec, name, for_read=True)
        tags = { k:v for k, v in tags.items() if v != '*' }
        all_fields = spec.normalized_structure
        if len(all_fields) == 1:
            wanted_field = spec.normalized_structure[0]
        else:
            raise NotImplementedError("We only presently support scalar measurements")
        tag_query = DistinctTagsFluxQueryBuilder(
            bucket='monitors',
            measurement=measurement,
            field = wanted_field,
            tag=spec.multiple_discriminators[0],
            filters=tags,
            time_span=time_span,
        )
        return tag_query

    @require_permission('read', strip_auth=False, required=False)
    async def monitors_export_historical(self, query: MonitorsQueryTModel,
                                         auth_user=None, session=None):
        rv = {}
        rv['time_span'] = query.time_span
        exportable = []
        if not query.monitors:
            monitors = [x.publish_name() for x in self.monitors_spec
                        if x.publish_frequency > MonitorPublishFrequency.NEVER]
        else:
            monitors = query.monitors
        for target in monitors:
            if isinstance(target, MonitorQueryItemTModel):
                exporter = target.exporter
                target = target.name
            else:
                exporter = None
            spec = self.monitor_get_spec(target)
            if exporter:
                # TODO Check if it actually allows, clear if not
                pass
            if not exporter:
                exporter = spec.get_preferred_exporter()
            logger.debug(f"{target}, {spec.multiple_container}")
            if spec.multiple_container and '*' in target:
                logger.debug(f"Searching for published keys for {target}")
                published_keys_query = (
                    self._monitor_get_dynamic_keys_published(target, spec, time_span=query.time_span))
                published_keys = await influxdb_execute_query(published_keys_query)
                published_keys = published_keys["data"]
                logger.debug(f"Found {published_keys}")
                if target.endswith('*'):
                    prefix = target[:-1]
                else:
                    raise NotImplementedError("We only support multiple container targets of type '<static>.*' here!")
                for key in published_keys:
                    exportable.append({'name': f"{prefix}{key}",
                                       'spec': spec,
                                       'exporter': exporter})
            else:
                exportable.append({'name': target, 'spec': spec,
                                   'exporter': exporter})

        query_planner = TimeSeriesQueryPlanner()
        for item in exportable:
            query_planner.add_item(self._monitor_get_query(item['name'], item['spec'], query.time_span, item['exporter']))

        data = await tsdb_execute_query_plan(query_planner)
        rv['data'] = data['monitors']
        return rv
