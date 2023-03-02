

from typing import List
from typing import Optional
from functools import cached_property

from tendril.authn.pydantic import UserStubTMixin
from tendril.utils.pydantic import TendrilTBaseModel

from tendril.authn.db.controller import get_user_by_id
from tendril.db.models.interests import InterestModel
from tendril.db.models.interests import InterestLifecycleStatus

from tendril.db.controllers.interests import get_interest
from tendril.db.controllers.interests import upsert_interest
from tendril.db.controllers.interests import assign_role
from tendril.db.controllers.interests import get_role_users
from tendril.db.controllers.interests import get_user_roles
from tendril.db.controllers.interests import remove_role
from tendril.db.controllers.interests import remove_user
from tendril.db.controllers.interests import get_children
from tendril.db.controllers.interests import set_parent
from tendril.db.controllers.interests import get_parent

from tendril.utils.db import with_db
from tendril.utils import log
logger = log.get_logger(__name__, log.DEFAULT)


class InterestBaseTModel(TendrilTBaseModel):
    name: str
    type: str
    id: int
    info: dict
    status: InterestLifecycleStatus
    roles: Optional[List[str]]
    permissions: Optional[List[str]]


class InterestBase(object):
    model = InterestModel
    tmodel = InterestBaseTModel

    def __init__(self, name):
        self._name = None
        self._model_instance = None
        self._status: InterestLifecycleStatus = None
        if isinstance(name, InterestModel):
            self._model_instance = name
        else:
            self._name = name
            self._model_instance: InterestModel = self._commit_to_db()

    @property
    def name(self):
        if self._name:
            return self._name
        else:
            return self._model_instance.name

    @property
    def type_name(self):
        return self.model.type_name

    @property
    def ident(self):
        return f"{self.__class__.__name__} {self.name}"

    def _info(self):
        return {}

    @property
    def status(self):
        self._status = self._model_instance.status
        return self._status

    @status.setter
    def status(self, value):
        self._status = value
        self._commit_to_db()

    @property
    def id(self):
        return self._model_instance.id

    @property
    def info(self):
        return self._info()

    @property
    def roles(self):
        return self._model_instance.role_spec.roles

    @property
    def allowed_children(self):
        return self._model_instance.role_spec.allowed_children

    @with_db
    def assign_role(self, role, user, reference=None, session=None):
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
            rv.add(self.model.role_spec.get_effective_roles(role))
        if self.model.role_spec.inherits_from_parent:
            pass
        return rv

    @with_db
    def get_role_users(self, role, session=None):
        if role not in self.model.role_spec.roles:
            raise ValueError(f"{role} is not a recognized role for "
                             f"{self.__class__.__name__}")
        return get_role_users(self.id, role, session=session)

    @with_db
    def get_role_accepted_users(self, role, session=None):
        if role not in self.model.role_spec.roles:
            raise ValueError(f"{role} is not a recognized role for "
                             f"{self.__class__.__name__}")
        users = []
        for d_role in self.model.role_spec.get_accepted_roles(role):
            for user in get_role_users(self.id, d_role, session=session):
                users.append(user)
        return users

    @with_db
    def check_user_access(self, user, action, session=None):
        action_roles = self.model.role_spec.get_permitted_roles(action)
        user_roles = set(self.get_user_effective_roles(user, session=session))
        return any(x in user_roles for x in action_roles)

    @staticmethod
    def _build_ms_info_dict(user, prov):
        from tendril.authn.users import get_user_stub
        infodict = {'user': get_user_stub(user.puid)}
        infodict.update(prov)
        return infodict

    @with_db
    def memberships(self, role=None, session=None,
                    include_effective=True, include_inherited=True):
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
            return rv
        else:
            rv = [self._build_ms_info_dict(x, {'delegated': False, 'inherited': False})
                  for x in self.get_role_users(role, session=session)]
            if include_effective:
                for d_role in self.model.role_spec.get_alternate_roles(role):
                    rv = [self._build_ms_info_dict(x, {'delegated': True, 'inherited': False})
                          for x in self.get_role_users(d_role, session=session)]
            return rv

    @with_db
    def get_parent(self, session=None):
        return get_parent(self.name, session=session)

    @with_db
    def set_parent(self, parent, session=None):
        if not isinstance(parent, self.__class__):
            parent = get_interest(parent, session=session)
        if '*' not in parent.allowed_children and \
                self.type_name not in parent.allowed_children:
            raise TypeError(f"Interest of type {parent.type_name} does not "
                            f"accept children of type {self.type_name}")
        else:
            parent.clear_children_cache()
            parent = parent.id
        return set_parent(self.name, parent, session=session)

    @cached_property
    def all_children(self):
        return get_children(self.id, self.type_name)

    def clear_children_cache(self):
        if 'all_children' in self.__dict__:
            del self.all_children

    def children(self, child_type):
        from tendril import interests
        child_class = getattr(interests, child_type)
        if not child_class:
            return [x for x in self.all_children if x.type == child_type]
        else:
            return [child_class(x.name) for x in self.all_children if x.type == child_type]

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
    def export(self, session=None, user=None,
               include_permissions=False,
               include_roles=False):
        rv = {
            'name': self.name,
            'type': self.type_name,
            'id': self.id,
            'info': self.info,
            'status': self.status,
        }
        if include_roles or include_permissions:
            user_roles = self.get_user_effective_roles(user, session=session)
        if include_roles:
            rv['roles'] = user_roles
        if include_permissions:
            rv['permissions'] = self.model.role_spec.get_roles_permissions(user_roles)
        return rv

    @with_db
    def _commit_to_db(self, session=None):
        kwargs = {'name': self.name,
                  'info': self.info,
                  'status': self._status,
                  'type': self.type_name,
                  'session': session}
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
