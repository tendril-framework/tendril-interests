

from typing import List
from functools import cached_property

from tendril.authn.pydantic import UserStubTMixin
from tendril.utils.pydantic import TendrilTBaseModel

from tendril.db.models.interests import InterestModel

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


class InterestBase(object):
    model = InterestModel
    tmodel = InterestBaseTModel

    def __init__(self, name):
        if isinstance(name, InterestModel):
            self._model_instance = name
            self._name = None
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
    def id(self):
        return self._model_instance.id

    @with_db
    def memberships(self, session=None):
        session.add(self._model_instance)
        return self._model_instance.memberships.all()

    @property
    def info(self):
        return self._info()

    @property
    def roles(self):
        return self._model_instance.role_spec.roles

    @property
    def allowed_children(self):
        return self._model_instance.allowed_children

    @with_db
    def assign_role(self, user, role, reference=None, session=None):
        assign_role(self.id, user, role, reference=reference, session=session)

    @with_db
    def remove_role(self, user, role, reference=None, session=None):
        remove_role(self.id, user, role, reference=reference, session=session)

    @with_db
    def get_user_roles(self, user, session=None):
        return get_user_roles(self.id, user, session=session)

    def _get_effective_roles(self, role):
        return [role] + self.model.role_spec.role_delegations.get(role, [])

    @with_db
    def get_user_effective_roles(self, user, session=None):
        rv = []
        for role in self.get_user_roles(user, session=session):
            rv.extend(self._get_effective_roles(role))
        return rv

    @with_db
    def get_role_users(self, role, session=None):
        if role not in self._model_instance.role_spec.roles:
            raise ValueError(f"{role} is not a recognized role for "
                             f"{self.__class__.__name__}")
        return get_role_users(self.id, role, session=session)

    def _get_accepted_roles(self, role):
        rv = [role]
        for k, v in self._model_instance.role_spec.role_delegations.items():
            if role in v:
                rv.append(k)
        return rv

    @with_db
    def get_role_accepted_users(self, role, session=None):
        if role not in self._model_instance.role_spec.roles:
            raise ValueError(f"{role} is not a recognized role for "
                             f"{self.__class__.__name__}")
        users = {}
        for d_role in self._get_accepted_roles(role):
            for user in get_role_users(self.id, d_role, session=session):
                users[user.id] = user
        return users

    @with_db
    def remove_user(self, user, session=None):
        remove_user(self.id, user, session=session)

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
    def export(self, session=None):
        return {
            'name': self.name,
            'type': self.type_name,
            'id': self.id,
            'info': self.info,
        }

    @with_db
    def _commit_to_db(self, session=None):
        self._model_instance = upsert_interest(self.name, self.info, type=self.type_name, session=session)

    def commit(self):
        self._commit_to_db()
        return self


def load(manager):
    manager.register_interest_role(name='Owner', doc="Owner of an Interest")
    manager.register_interest_role(name='Member', doc="Member of an Interest")
    manager.register_interest_type('InterestBase', InterestBase)
