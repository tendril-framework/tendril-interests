

import re
from typing import Any
from typing import List
from typing import Union
from typing import Optional
from typing import Literal
from functools import cached_property
from pydantic import Field
from pydantic import create_model

from tendril.utils.pydantic import TendrilTBaseModel

from tendril.authn.db.controller import get_user_by_id
from tendril.db.models.interests import InterestModel

from tendril.common.states import LifecycleStatus
from tendril.common.interests.exceptions import RequiredRoleNotPresent
from tendril.common.interests.exceptions import RequiredParentNotPresent
from tendril.common.interests.exceptions import ActivationNotAllowedFromState
from tendril.common.interests.exceptions import AuthorizationRequiredError
from tendril.common.interests.representations import ExportLevel

from tendril.db.controllers.interests import get_interest
from tendril.db.controllers.interests import upsert_interest
from tendril.db.controllers.interests import assign_role
from tendril.db.controllers.interests import get_role_users
from tendril.db.controllers.interests import get_user_roles
from tendril.db.controllers.interests import remove_role
from tendril.db.controllers.interests import remove_user
from tendril.db.controllers.interests import add_child
from tendril.db.controllers.interests import get_children
from tendril.db.controllers.interests import get_parents

from tendril.authz.roles.interests import require_state
from tendril.authz.roles.interests import require_permission
from tendril.authz.roles.interests import normalize_role_name
from tendril.authz.roles.interests import normalize_type_name

from tendril.utils.db import with_db
from tendril.utils import log
logger = log.get_logger(__name__, log.DEBUG)


class InterestBaseCreateTModel(TendrilTBaseModel):
    name: str = Field(..., max_length=255)
    descriptive_name: Optional[str] = Field(..., max_length=255)
    type: Literal['interest']
    info: dict


class InterestBaseEditTModel(TendrilTBaseModel):
    descriptive_name: Optional[str] = Field(default="", max_length=255)
    info: Optional[dict]


class InterestIdOnlyTModel(TendrilTBaseModel):
    id: int


class InterestBaseStubTModel(InterestIdOnlyTModel):
    type: str
    name: str
    descriptive_name: Optional[str]
    status: LifecycleStatus


class InterestBaseNormalTModel(InterestBaseStubTModel):
    info: Optional[dict]


class InterestBaseDetailedTModel(InterestBaseNormalTModel):
    roles: Optional[List[str]]
    permissions: Optional[List[str]]


def camel_case(s):
    s = re.sub(r"(_|-)+", " ", s).title().replace(" ", "")
    return ''.join([s[0].lower(), s[1:]])


_base_tmodels = {
    ExportLevel.ID_ONLY: ('tmodel_idonly', 'IdOnly'),
    ExportLevel.STUB: ('tmodel_stub', 'Stub'),
    ExportLevel.NORMAL: ('tmodel_normal', 'Normal'),
    ExportLevel.DETAILED: ('tmodel_detailed', 'Detailed')
}


class InterestBase(object):
    model = InterestModel

    tmodel_create = InterestBaseCreateTModel
    tmodel_edit = InterestBaseEditTModel

    tmodel_idonly = InterestIdOnlyTModel
    tmodel_stub = InterestBaseStubTModel
    tmodel_normal = InterestBaseNormalTModel
    tmodel_detailed = InterestBaseDetailedTModel

    _tmodel_unified = None

    # Fields required for creation. Will also be included in NORMAL export.
    additional_fields = []
    # Fields required for creation one. Will not be included in exports.
    additional_creation_fields = []
    # Fields included in exports only. Will be included in NORMAL export.
    additional_export_fields = []

    additional_activation_checks = []
    additional_tmodel_mixins = {}

    def __init__(self, name, info=None, must_create=False,
                 can_create=True, session=None):
        self._name = None
        self._descriptive_name = None
        self._info = None
        self._model_instance: InterestModel = None
        self._status: LifecycleStatus = None
        if isinstance(name, InterestModel):
            if must_create:
                raise AttributeError("Expected a name, not an object")
            self._model_instance = name
        else:
            self._name = name
            self._info = info or {}
            self._commit_to_db(must_create=must_create,
                               can_create=can_create,
                               session=session)

    @classmethod
    def _additional_tmodel_mixins(cls):
        try:
            mro = list(cls.__class__.__mro__)
        except AttributeError:
            print(f"There isn't an __mro__ on {cls.__class__}. "
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
        type_name = (f'{camel_case(cls.model.type_name)}{base_tmodel[1]}TModel')
        logger.debug(f"Building TModel {type_name}")
        return create_model(
            type_name,
            __base__=(getattr(cls, base_tmodel[0]),
                      *cls.tmodel_mixins_at_level(export_level)),
            **additional_fields
        )

    @classmethod
    def export_tmodel_stub(cls):
        if not hasattr(cls, '_tmodel_stub'):
            cls._tmodel_stub = cls.tmodel_build(ExportLevel.STUB)
        return cls._tmodel_stub

    @classmethod
    def export_tmodel_normal(cls):
        if not hasattr(cls, '_tmodel_normal'):
            cls._tmodel_normal = cls.tmodel_build(ExportLevel.NORMAL)
        return cls._tmodel_normal

    @classmethod
    def export_tmodel_detailed(cls):
        if not hasattr(cls, '_tmodel_detailed'):
            cls._tmodel_detailed = cls.tmodel_build(ExportLevel.DETAILED)
        return cls._tmodel_detailed

    @classmethod
    def export_tmodel_unified(cls):
        if not hasattr(cls, '_tmodel_unified'):
            logger.info(f"Generating Unified Export Type Model for {cls.__name__}")
            cls._tmodel_unified = Union[
                cls.tmodel_build(ExportLevel.ID_ONLY),
                cls.export_tmodel_stub(),
                cls.export_tmodel_normal(),
                cls.export_tmodel_detailed()
            ]
        return cls._tmodel_unified

    @property
    def type_name(self):
        return self.model.type_name

    @property
    def name(self):
        if self._name:
            return self._name
        else:
            return self._model_instance.name

    @property
    def descriptive_name(self):
        if self._descriptive_name:
            return self._descriptive_name
        else:
            return self._model_instance.descriptive_name

    @with_db
    def set_descriptive_name(self, value, session=None):
        self._descriptive_name = value
        self._commit_to_db(session=session)

    @with_db
    @require_permission('edit', strip_auth=False, required=False)
    def edit(self, changes, auth_user=None, session=None):
        for field_name in changes.__fields__:
            value = getattr(changes, field_name)
            if value and hasattr(self.model_instance, field_name):
                setattr(self.model_instance, field_name, value)
        session.add(self.model_instance)

    @property
    def ident(self):
        return f"{self.__class__.__name__} {self.name}"

    @property
    def info(self):
        if self._info is not None:
            return self._info
        else:
            return self._model_instance.info

    @property
    def id(self):
        return self._model_instance.id

    @property
    def status(self):
        self._status = self._model_instance.status
        return self._status

    @status.setter
    def status(self, value):
        self._status = value
        self._commit_to_db()

    @with_db
    def _check_activation_requirements(self, session=None):
        if self.status not in self.model.role_spec.activation_requirements['allowed_states']:
            raise ActivationNotAllowedFromState(self.status, self.id, self.name)
        for role in self.model.role_spec.activation_requirements['roles_required']:
            users = self.get_role_accepted_users(role, session=session)
            if not len(users):
                raise RequiredRoleNotPresent(role, self.id, self.name)
        if self.model.role_spec.activation_requirements['parent_required']:
            if not len(self.parents(limited=False, session=session)):
                raise RequiredParentNotPresent(self.id, self.name)

    @property
    def _additional_activation_checks(self):
        try:
            mro = list(self.__class__.__mro__)
        except AttributeError:
            print(f"There isn't an __mro__ on {self.__class__}. "
                  f"This is probably a classic class. We don't support this.")
            return self.additional_activation_checks
        rv = []
        for cls in mro:
            if hasattr(cls, 'additional_activation_checks'):
                for check_fn in cls.additional_activation_checks:
                    rv.append(check_fn)
        return rv

    @with_db
    @require_permission('edit', strip_auth=False, required=False)
    @require_state([LifecycleStatus.NEW, LifecycleStatus.APPROVAL, LifecycleStatus.ACTIVE])
    def activate(self, background_tasks=None, auth_user=None, session=None):
        # logger.debug(f"Attempting to activate {self.type_name} {self.id}")
        if self.model_instance.status == LifecycleStatus.ACTIVE:
            msg = f"{self.model.type_name} Interest {self.id} {self.name} is already active"
            logger.info(msg)
            return False, msg

        # logger.debug(f"Checking Activation Requirements for {self.type_name} {self.id}")
        self._check_activation_requirements(session=session)

        for check_fn_orig in self._additional_activation_checks:
            # logger.debug(f"Trying Additional Activation Check for {self.type_name} {self.id} : {check_fn_orig}")
            if not callable(check_fn_orig):
                check_fn = getattr(self, check_fn_orig)
            else:
                check_fn = check_fn_orig
            result = check_fn(auth_user=auth_user, session=session)
            if not result:
                msg = f"Additional activation check '{check_fn_orig}' failed. " \
                      f"Will not activate."
                logger.debug(msg)
                return False, msg
            # else:
            #   logger.debug(f"Additional activation check '{check_fn_orig}' passed. Got {result}.")

        logger.debug(f"Passed all activation checks. Activating {self.type_name} {self.id}")
        self._model_instance.status = LifecycleStatus.ACTIVE
        session.add(self._model_instance)
        msg = f"Activated {self.model.type_name} Interest {self.id} {self.name}"
        logger.info(msg)
        return True, msg

    @with_db
    @require_permission('edit', strip_auth=False, required=False)
    @require_state([LifecycleStatus.ACTIVE, LifecycleStatus.APPROVAL])
    def deactivate(self, auth_user=None, session=None):
        self._model_instance.status = LifecycleStatus.NEW
        session.add(self.model_instance)
        msg = f"Deactivated {self.model.type_name} Interest {self.id} {self.name}"
        logger.info(msg)
        return msg

    @property
    def roles(self):
        return self._model_instance.role_spec.roles

    @property
    def allowed_children(self):
        return self._model_instance.role_spec.allowed_children

    @with_db
    @require_state(LifecycleStatus.ACTIVE,
                   exceptions=[(('status', 'NEW'),)])
    @require_permission('add_member', specifier='role', required=False,
                        preprocessor=normalize_role_name, strip_auth=False,
                        exceptions=[(('status', 'NEW'), ('role', 'self.model.role_spec.apex_role'))])
    def assign_role(self, role=None, user=None, reference=None, auth_user=None, session=None):
        if not reference:
            reference = {}
        reference['by'] = auth_user.id if hasattr(auth_user, 'id') else auth_user
        membership = assign_role(self.id, user, role, reference=reference, session=session)
        scopes_assignable = self.model.role_spec.get_role_scopes(role)
        from tendril.authz.connector import add_user_scopes
        user = get_user_by_id(membership.user_id, session=session)
        add_user_scopes(user.puid, scopes_assignable)

    @with_db
    def remove_role(self, user, role, reference=None, session=None):
        # TODO Scopes should be recalculated and pruned here.
        remove_role(self.id, user, role, reference=reference, session=session)

    @with_db
    def remove_user(self, user, session=None):
        remove_user(self.id, user, session=session)

    @with_db
    def get_user_roles(self, user, session=None):
        return get_user_roles(self.id, user, session=session)

    @with_db
    def get_user_effective_roles(self, user, session=None):
        rv = set()
        for role in self.get_user_roles(user, session=session):
            rv.update(self.model.role_spec.get_effective_roles(role))
        if self.model.role_spec.inherits_from_parent:
            recognized_roles = set(self.model.role_spec.roles)
            for parent in self.parents(limited=False, session=session):
                roles = parent.get_user_effective_roles(user, session=session)
                parent_roles = roles.intersection(recognized_roles)
                rv.update(parent_roles)
        return rv

    @with_db
    def get_role_users(self, role, session=None):
        return get_role_users(self.id, role, session=session)

    @with_db
    def get_role_accepted_users(self, role, session=None):
        return self.memberships(role=role, session=session)

    @with_db
    def check_user_access(self, user, action, session=None):
        if hasattr(user, 'id'):
            user_str = user.id
        else:
            user_str = user
        logger.debug(f"Checking permissions to '{action}' on '{self}' for user '{user_str}'")
        action_roles = self.model.role_spec.get_permitted_roles(action)
        user_roles = set(self.get_user_effective_roles(user, session=session))
        return any(x in user_roles for x in action_roles)

    @staticmethod
    def _build_ms_info_dict(user, prov):
        from tendril.authn.users import get_user_stub
        infodict = {'user': get_user_stub(user.puid)}
        infodict.update(prov)
        return infodict

    @staticmethod
    def _merge_membership_dict(master, new, roles):
        for role in new.keys():
            if role not in roles:
                continue
            master.setdefault(role, [])
            existing_users = [x['user']['user_id'] for x in master[role]]
            for m in new[role]:
                if m['user']['user_id'] in existing_users:
                    continue
                m['inherited'] = True
                master[role].append(m)
        return master

    @with_db
    @require_permission('read_members', strip_auth=False, required=False,
                        specifier='role', preprocessor=normalize_role_name)
    def memberships(self, role=None, session=None, auth_user=None,
                    include_effective=True, include_inherited=True):
        # TODO Consider building this once and caching it.
        if not role:
            rv = {}
            session.add(self._model_instance)
            ms = self._model_instance.memberships.all()
            for membership in ms:
                rn = [(membership.role.name, {'delegated': False, 'inherited': False})]
                if include_effective:
                    rn.extend([(x, {'delegated': True, 'inherited': False})
                               for x in self.model.role_spec.get_delegated_roles(rn[0][0])])
                for rname, rprov in rn:
                    rv.setdefault(rname, [])
                    rv[rname].append(
                        self._build_ms_info_dict(membership.user, rprov)
                    )
            if include_inherited and self.model.role_spec.inherits_from_parent:
                for parent in self.parents(limited=False, session=session):
                    try:
                        pm = parent.memberships(role=role, auth_user=auth_user, session=session,
                                                include_effective=include_effective,
                                                include_inherited=include_inherited)
                        self._merge_membership_dict(rv, pm, self.model.role_spec.roles)
                    except AuthorizationRequiredError:
                        pass
            return rv
        else:
            rv = [self._build_ms_info_dict(x, {'delegated': False, 'inherited': False})
                  for x in self.get_role_users(role, session=session)]
            if include_effective:
                for d_role in self.model.role_spec.get_alternate_roles(role):
                    rv = [self._build_ms_info_dict(x, {'delegated': True, 'inherited': False})
                          for x in self.get_role_users(d_role, session=session)]
            if include_inherited and self.model.role_spec.inherits_from_parent:
                for parent in self.parents(limited=False, session=session):
                    existing_users = [x['user']['user_id'] for x in rv]
                    if role in parent.model.role_spec.roles:
                        parent_members = parent.memberships(auth_user=auth_user, role=role, session=session,
                                                            include_effective=include_effective,
                                                            include_inherited=True)
                        for member in parent_members:
                            if member['user']['user_id'] in existing_users:
                                continue
                            member['inherited'] = True
                            rv.append(member)
            return rv

    @staticmethod
    def _repack_interest_list(ilist):
        from tendril.interests import type_codes
        return [type_codes[x.type](x) for x in ilist]

    @with_db
    @require_permission('read', required=False)
    def parents(self, limited=None, session=None):
        return self._repack_interest_list(
            get_parents(self.id, limited=limited, session=session)
        )

    @with_db
    @require_permission('read', strip_auth=False, required=False)
    def ancestors(self, auth_user=None, session=None):
        rv = []
        parents = self.parents(auth_user=auth_user, session=session)
        rv.extend(parents)
        for parent in parents:
            rv.extend(parent.ancestors(auth_user=auth_user, session=session))
        return rv

    @with_db
    @require_permission('read_children', strip_auth=False, required=False,
                        specifier='child_type', preprocessor=normalize_type_name)
    def children(self, child_type=None, limited=None, auth_user=None, session=None):
        return self._repack_interest_list(
            get_children(self.id, self.type_name,
                         child_type=child_type, limited=limited, session=session)
        )

    @staticmethod
    def _get_child_type(cls, child, *a, **k):
        if isinstance(child, int):
            child = get_interest(id=child)
        return child.type_name

    @with_db
    @require_state(LifecycleStatus.ACTIVE)
    @require_permission('add_child', specifier=_get_child_type, preprocessor=normalize_type_name)
    def add_child(self, child, limited=False, session=None):
        return add_child(child, self.id, self.type_name,
                         limited=limited, session=session)

    @with_db
    def add_artefact(self, artefact, session=None):
        self.clear_artefact_cache()

    @with_db
    def remove_artefact(self, artefact, session=None):
        self.clear_artefact_cache()

    @with_db
    def transfer_artefact(self, artefact, interest, session=None):
        self.remove_artefact(artefact, session=session)
        interest.add_artefact(artefact, session=session)

    @cached_property
    def all_artefacts(self):
        pass

    def clear_artefact_cache(self):
        if 'all_artefacts' in self.__dict__:
            del self.all_artefacts

    @with_db
    def artefacts(self, artefact_type, session=None):
        pass

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
            rv.update({'info': self.info})

            for field in self.additional_fields:
                rv[field] = getattr(self, field)

            for field in self.additional_export_fields:
                rv[field] = getattr(self, field)

        if export_level >= ExportLevel.DETAILED:
            user_roles = self.get_user_effective_roles(auth_user, session=session)
            rv['roles'] = sorted(user_roles)
            rv['permissions'] = sorted(self.model.role_spec.get_roles_permissions(user_roles))

        if hasattr(super(), 'export'):
            rv.update(super().export(session=session, auth_user=auth_user,
                                     export_level=export_level, **kwargs))

        return rv

    @property
    def role_spec(self):
        return self.model.role_spec

    @property
    def model_instance(self):
        return self._model_instance

    @with_db
    def _commit_to_db(self, must_create=False, can_create=True, session=None):
        kwargs = {'name': self.name,
                  'info': self.info,
                  'status': self._status,
                  'type': self.type_name,
                  'must_create': must_create,
                  'can_create': can_create,
                  'session': session}
        if self._descriptive_name:
            kwargs['descriptive_name'] = self._descriptive_name
        for field in self.additional_fields:
            kwargs[field] = getattr(self, field)
        if self._model_instance:
            kwargs['id'] = self.id
        self._model_instance = upsert_interest(**kwargs)

    def commit(self):
        self._commit_to_db()
        return self

    def __repr__(self):
        return f"<{self.ident}>"


def load(manager):
    manager.register_interest_role(name='Owner', doc="Owner of an Interest")
    manager.register_interest_role(name='Member', doc="Member of an Interest")
    manager.register_interest_type('InterestBase', InterestBase)
