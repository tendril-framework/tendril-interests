

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


class InterestBase(object):
    _model = InterestModel
    _roles = ['Owner', 'Member']
    _role_delegations = {'Owner': ['Member']}
    _child_types = {'interest': None}

    def __init__(self, name):
        self._name = name

    @property
    def name(self):
        return self._name

    @property
    def type_name(self):
        return self._model._type_name

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
        return self._roles

    def assign_role(self, user, role, reference=None):
        assign_role(self.id, user, role, reference=reference)

    def remove_role(self, user, role, reference=None):
        remove_role(self.id, user, role, reference=reference)

    def get_user_roles(self, user):
        return get_user_roles(self.id, user)

    def _get_effective_roles(self, role):
        return [role] + self._role_delegations.get(role, [])

    def get_user_effective_roles(self, user):
        rv = []
        for role in self.get_user_roles(user):
            rv.extend(self._get_effective_roles(role))
        return rv

    def get_role_users(self, role):
        if role not in self._roles:
            raise ValueError(f"{role} is not a recognized role for "
                             f"{self.__class__.__name__}")
        return get_role_users(self.id, role)

    def _get_accepted_roles(self, role):
        rv = [role]
        for k, v in self._role_delegations.items():
            if role in v:
                rv.append(k)
        return rv

    def get_role_accepted_users(self, role):
        if role not in self._roles:
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
        if isinstance(parent, self.__class__):
            parent.clear_children_cache()
            parent = parent.id
        return set_parent(self.name, parent)

    @cached_property
    def all_children(self):
        return get_children(self.name, self.type_name)

    def clear_children_cache(self):
        if 'all_children' in self.__dict__:
            del self.all_children

    def children(self, child_type):
        child_class = self._child_types.get(child_type)
        if not child_class:
            return [x for x in self.all_children if x.type == child_type]
        else:
            return [child_class(x.name) for x in self.all_children if x.type == child_type]

    def _commit_to_db(self):
        upsert_interest(self.name, self.info, type=self.type_name)

    def commit(self):
        self._commit_to_db()
        return self


def init():
    register_interest_role('Owner', "Owner of an Interest")
    register_interest_role('Member', "Member of an Interest")


init()
