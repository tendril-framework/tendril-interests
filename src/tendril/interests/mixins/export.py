

from typing import List
from typing import Optional
from pydantic import Field
from pydantic import create_model
from inflection import camelize

from tendril.utils.pydantic import TendrilTBaseModel
from tendril.common.states import LifecycleStatus
from tendril.common.interests.representations import ExportLevel
from tendril.authz.roles.interests import require_permission

from .base import InterestMixinBase
from tendril.utils.db import with_db
from tendril.utils import log
logger = log.get_logger(__name__, log.DEBUG)


class InterestIdOnlyTModel(TendrilTBaseModel):
    id: int


class InterestBaseStubTModel(InterestIdOnlyTModel):
    type: str
    name: str
    descriptive_name: Optional[str]
    status: LifecycleStatus


class InterestBaseNormalTModel(InterestBaseStubTModel):
    pass


class InterestBaseDetailedTModel(InterestBaseNormalTModel):
    info: Optional[dict]
    roles: Optional[List[str]]
    permissions: Optional[List[str]]


_base_tmodels = {
    ExportLevel.ID_ONLY: ('tmodel_idonly', 'IdOnly'),
    ExportLevel.STUB: ('tmodel_stub', 'Stub'),
    ExportLevel.NORMAL: ('tmodel_normal', 'Normal'),
    ExportLevel.DETAILED: ('tmodel_detailed', 'Detailed')
}


class InterestExportMixin(InterestMixinBase):

    tmodel_idonly = InterestIdOnlyTModel
    tmodel_stub = InterestBaseStubTModel
    tmodel_normal = InterestBaseNormalTModel
    tmodel_detailed = InterestBaseDetailedTModel

    _tmodel_unified = None

    # Fields required for creation. Will also be included in NORMAL export.
    additional_fields = []
    # Fields included in exports only. Will be included in NORMAL export.
    additional_export_fields = []

    additional_tmodel_mixins = {}

    @classmethod
    def _additional_tmodel_mixins(cls):
        try:
            mro = list(cls.__mro__)
        except AttributeError:
            logger.warning(f"There isn't an __mro__ on {cls}. "
                           f"This is probably a classic class. We don't support this.")
            return cls.additional_tmodel_mixins
        rv = {}
        for parent_cls in mro:
            if hasattr(parent_cls, 'additional_tmodel_mixins'):
                for level, tmodels in parent_cls.additional_tmodel_mixins.items():
                    if level in rv.keys():
                        rv[level].extend(tmodels)
                    else:
                        rv[level] = tmodels
        return rv

    @classmethod
    def tmodel_mixins_at_level(cls, target_level):
        rv = []
        for level in ExportLevel:
            if level > target_level:
                return rv
            try:
                rv.extend(cls._additional_tmodel_mixins()[level])
            except KeyError:
                continue

    @classmethod
    def _extract_additional_field_tmodels(cls, export_level):
        rv = {}
        # TODO additional_fields and additional_export_fields should
        #  also be gathered from the class hierarchy
        for field in cls.additional_fields + cls.additional_export_fields:
            if isinstance(field, tuple):
                name, level, ftype, args, kwargs = field
            else:
                name = field
                level = ExportLevel.NORMAL
                ftype = Optional[str]
                args = None
                kwargs = None

            if export_level >= level:
                if args or kwargs:
                    rv[name] = (ftype, Field(*args, **kwargs))
                else:
                    rv[name] = (ftype, ...)
        return rv

    @classmethod
    def tmodel_build(cls, export_level):
        base_tmodel = _base_tmodels[export_level]
        additional_fields = cls._extract_additional_field_tmodels(export_level)
        additional_mixins = cls.tmodel_mixins_at_level(export_level)
        type_name = f'{camelize(cls.model.type_name)}{base_tmodel[1]}TModel'
        logger.debug(f"Building TModel {type_name}")
        return create_model(
            type_name,
            __base__=(getattr(cls, base_tmodel[0]),
                      *additional_mixins),
            **additional_fields
        )

    @classmethod
    def export_tmodel_stub(cls):
        return cls._tmodel_stub

    @classmethod
    def export_tmodel_normal(cls):
        return cls._tmodel_normal

    @classmethod
    def export_tmodel_detailed(cls):
        return cls._tmodel_detailed

    @classmethod
    def export_tmodel_unified(cls):
        return cls._tmodel_unified

    @with_db
    @require_permission(action='read', strip_auth=False, required=False)
    def export(self, session=None, auth_user=None,
               export_level=ExportLevel.NORMAL,
               **kwargs):

        rv = {'id': self.id}
        if export_level >= ExportLevel.STUB:
            rv.update({
                'type': self.type_name,
                'name': self.name,
                'descriptive_name': self.descriptive_name,
                'status': self.status
            })

        if export_level >= ExportLevel.NORMAL:
            for field in self.additional_fields + self.additional_export_fields:
                if isinstance(field, tuple):
                    field = field[0]
                rv[field] = getattr(self, field)

        if export_level >= ExportLevel.DETAILED:
            rv.update({'info': self.info})
            # TODO maybe move this into the base class along with the other auth stuff for
            #  a later AuthMixin
            user_roles = self.get_user_effective_roles(auth_user, session=session)
            rv['roles'] = sorted(user_roles)
            rv['permissions'] = sorted(self.model.role_spec.get_roles_permissions(user_roles))

        if hasattr(super(), 'export'):
            rv.update(super().export(session=session, auth_user=auth_user,
                                     export_level=export_level, **kwargs))

        return rv
