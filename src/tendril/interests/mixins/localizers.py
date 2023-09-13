

from typing import Any
from typing import List
from typing import Dict
from typing import Union
from typing import Optional

from tendril.utils.pydantic import TendrilTBaseModel
from .base import InterestMixinBase
from tendril.utils.db import with_db
from tendril.common.interests.representations import ExportLevel
from tendril.utils import log
logger = log.get_logger(__name__, log.DEFAULT)


# TODO Use the interest stub model here.
#  We've probably already defined it somewhere.
InterestReferenceTModel = Any


class InterestBaseLocalizersTMixin(TendrilTBaseModel):
    localizers: Optional[Dict[str, Union[List[InterestReferenceTModel], InterestReferenceTModel]]]


class InterestLocalizersMixin(InterestMixinBase):
    localizers_spec = {'ancestors': []}

    @with_db
    def localizers(self, export_level=ExportLevel.NORMAL, session=None):
        itypes = self.localizers_spec['ancestors']
        if not itypes:
            return {}
        rv = {}
        for candidate in self.ancestors(session=session):
            if candidate.type_name in itypes:
                if export_level >= ExportLevel.NORMAL:
                    stub = candidate.export(export_level=ExportLevel.STUB)
                else:
                    stub = candidate.export(export_level=ExportLevel.ID_ONLY)
                if (candidate.type_name not in rv.keys() and
                        candidate.type_name != self.type_name):
                    rv[candidate.type_name] = stub
                    continue
                idx = 1
                while f'{candidate.type_name}-{idx}' in rv.keys():
                    idx += 1
                rv[f'{candidate.type_name}-{idx}'] = stub
        return rv

    def cached_localizers(self, session=None):
        if not hasattr(self, '_localizers'):
            self._localizers = self.localizers(session=session)
        return self._localizers

    @with_db
    def compacted_localizers(self, session=None):
        return set([v['id'] for k, v in self.cached_localizers(session=session).items()])

    def export(self, export_level=ExportLevel.NORMAL, session=None, auth_user=None, **kwargs):
        rv = {}
        if hasattr(super(), 'export'):
            rv.update(super().export(export_level=export_level, session=session,
                                     auth_user=auth_user, **kwargs))
        rv['localizers'] = self.localizers(export_level=ExportLevel.ID_ONLY, session=session)
        return rv
