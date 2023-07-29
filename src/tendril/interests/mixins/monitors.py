

import json
import re
from fnmatch import fnmatch
from pprint import pprint
from typing import List
from typing import Any
from typing import Dict
from typing import Optional
from tendril.monitors.spec import MonitorSpec
from tendril.monitors.spec import MonitorExportLevel
from tendril.caching import transit
from tendril.utils.pydantic import TendrilTBaseModel

from .base import InterestMixinBase


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

    # def monitors_print(self):
    #     pprint(self.monitors)
    #     for spec in self.monitors_spec:
    #         try:
    #             print(spec.publish_name(), spec.hot_cache_key(self.id), self.monitors[spec.publish_name()])
    #         except KeyError:
    #             # print(f"err {spec.publish_name()}")
    #             pass
    def _monitor_get_cache_loc(self, spec):
        return {
            'namespace': f'im:{self.id}',
            'key': spec.publish_name()
        }

    def monitor_report(self, monitor, value):
        spec = self.monitor_get_spec(monitor)
        if not spec:
            return
        if spec.keep_hot:
            # Publish to cache
            kwargs = self._monitor_get_cache_loc(spec)
            kwargs.update({
                'ttl': spec.expire,
                'ser': spec.serializer or json.dumps
            })
            transit.write(value, **kwargs)
            # self.monitors[monitor] = value

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
            if monitor_spec.parser:
                value = monitor_spec.parser(value)
        return value

    def _monitor_process_discriminated_value(self, monitor_spec, values):
        if isinstance(values, dict):
            for discriminator, discriminated_value in values.items():
                value = self._monitor_process_value(monitor_spec, discriminated_value)
                name = monitor_spec.publish_name().replace('*', discriminator)
                self.monitor_report(name, value)

    def monitors_report(self, report):
        for monitor_spec in self.monitors_spec:
            value = self._monitor_extract_from_report(monitor_spec.path, report)
            if value is None:
                continue
            if monitor_spec.multiple_container and isinstance(value, monitor_spec.multiple_container):
                self._monitor_process_discriminated_value(monitor_spec, value)
            else:
                value = self._monitor_process_value(monitor_spec, value)
                self.monitor_report(monitor_spec.publish_name(), value)

    def _monitor_get_value(self, spec):
        kwargs = self._monitor_get_cache_loc(spec)
        kwargs.update({
            'deser': spec.deserializer or json.loads
        })
        value = transit.read(**kwargs)
        if spec.default is not None and not value:
            value = spec.default
        print(f"GET {spec.publish_name()} {value}")
        return value

    def _monitors_at_export_level(self, export_level):
        return [x for x in self.monitors_spec if x.export_level <= export_level]

    def export(self, session=None, auth_user=None, **kwargs):
        rv = {}
        if hasattr(super(), 'export'):
            rv.update(super().export(session=session, auth_user=auth_user, **kwargs))
        export_level = MonitorExportLevel.NORMAL
        monitors = self._monitors_at_export_level(export_level)
        if not monitors:
            return rv
        monitor_values = {}
        for monitor_spec in self._monitors_at_export_level(export_level):
            value = self._monitor_get_value(monitor_spec)
            if value is None:
                continue
            if monitor_spec.export_processor:
                value = monitor_spec.export_processor(value)
            monitor_values[monitor_spec.publish_name()] = value
        rv['monitors'] = monitor_values
        return rv
