

from functools import cached_property
from .db.model import InterestModel

from .db.controller import get_interest
from .db.controller import register_interest_role
from .db.controller import upsert_interest
from .db.controller import assign_role
from .db.controller import get_role_users
from .db.controller import get_user_roles
from .db.controller import remove_role
from .db.controller import remove_user
from .db.controller import get_children
from .db.controller import set_parent
from .db.controller import get_parent

from tendril.utils import log
logger = log.get_logger(__name__, log.DEFAULT)


class InterestBase(object):
    _model = InterestModel

    def __init__(self, name):
        self._name = name

    @property
    def name(self):
        return self._name

    @property
    def type_name(self):
        return self._model.type_name

    @property
    def ident(self):
        return self.__class__.__name__ + self.name

    def _info(self):
        return {}

    @cached_property
    def id(self):
        return get_interest(self.name, self.type_name).id

    @property
    def memberships(self):
        return get_interest(self.name, self.type_name).memberships

    @property
    def info(self):
        return self._info()

    @property
    def roles(self):
        return self._model.roles

    @property
    def allowed_children(self):
        return self._model.allowed_children

    def assign_role(self, user, role, reference=None):
        assign_role(self.id, user, role, reference=reference)

    def remove_role(self, user, role, reference=None):
        remove_role(self.id, user, role, reference=reference)

    def get_user_roles(self, user):
        return get_user_roles(self.id, user)

    def _get_effective_roles(self, role):
        return [role] + self._model.role_delegations.get(role, [])

    def get_user_effective_roles(self, user):
        rv = []
        for role in self.get_user_roles(user):
            rv.extend(self._get_effective_roles(role))
        return rv

    def get_role_users(self, role):
        if role not in self._model.roles:
            raise ValueError(f"{role} is not a recognized role for "
                             f"{self.__class__.__name__}")
        return get_role_users(self.id, role)

    def _get_accepted_roles(self, role):
        rv = [role]
        for k, v in self._model.role_delegations.items():
            if role in v:
                rv.append(k)
        return rv

    def get_role_accepted_users(self, role):
        if role not in self._model.roles:
            raise ValueError(f"{role} is not a recognized role for "
                             f"{self.__class__.__name__}")
        users = {}
        for d_role in self._get_accepted_roles(role):
            for user in get_role_users(self.id, d_role):
                users[user.id] = user
        return list(users.values())

    def remove_user(self, user):
        remove_user(self.id, user)

    def get_parent(self):
        return get_parent(self.name)

    def set_parent(self, parent):
        if not isinstance(parent, self.__class__):
            parent = get_interest(parent)
        if '*' not in parent.allowed_children and \
                self.type_name not in parent.allowed_children:
            parent.clear_children_cache()
            parent = parent.id
        else:
            raise TypeError(f"Parent to type {parent.type_name} does not "
                            f"accept children of type {self.type_name}")
        return set_parent(self.name, parent)

    @cached_property
    def all_children(self):
        return get_children(self.name, self.type_name)

    def clear_children_cache(self):
        if 'all_children' in self.__dict__:
            del self.all_children

    def children(self, child_type):
        child_class = _child_types.get(child_type)
        if not child_class:
            return [x for x in self.all_children if x.type == child_type]
        else:
            return [child_class(x.name) for x in self.all_children if x.type == child_type]

    def _commit_to_db(self):
        upsert_interest(self.name, self.info, type=self.type_name)

    def commit(self):
        self._commit_to_db()
        return self


_child_types = {}


def register_child_type(name, cls):
    logger.info(f"Registering {cls} to handle Interest type '{name}'")
    _child_types[name] = cls


def init():
    register_interest_role('Owner', "Owner of an Interest")
    register_interest_role('Member', "Member of an Interest")
    register_child_type('interest', None)

init()
