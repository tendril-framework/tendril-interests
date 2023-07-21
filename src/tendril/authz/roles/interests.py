

import enum
from collections.abc import Iterable
from functools import cached_property
from functools import wraps
from tendril.authn.pydantic import UserStubTModel
from tendril.utils.pydantic import TendrilTBaseModel
from tendril.common.states import LifecycleStatus
from tendril.common.interests.exceptions import InterestStateException
from tendril.common.interests.exceptions import AuthorizationRequiredError
from tendril.utils import log
logger = log.get_logger(__name__, log.DEBUG)


class MembershipInfoTModel(TendrilTBaseModel):
    user: UserStubTModel
    delegated: bool
    inherited: bool


def normalize_role_name(role: str):
    return role.lower().replace(" ", '_')


def normalize_type_name(type: str):
    return type.lower().replace(" ", "_")


class InterestRoleSpec(object):
    prefix = 'interest'

    allowed_children = ['interest']
    recognized_artefacts = {}

    roles = ['Owner', 'Member']

    apex_role = 'Owner'
    base_role = 'Member'

    read_role = None
    edit_role = None
    delete_role = None

    authz_read_role = None
    authz_write_role = None
    authz_write_peers = False

    child_read_role = None
    child_add_role = None
    child_delete_role = None

    artefact_read_role = None
    artefact_add_role = None
    artefact_delete_role = None

    child_read_roles = {}
    child_add_roles = {}
    child_delete_roles = {}

    inherits_from_parent = True

    custom_delegations = {}
    additional_roles_required = []
    parent_required = True

    mixin_scopes = {}
    mixin_actions = {}

    @cached_property
    def activation_requirements(self):
        rv = {'roles_required': [self.apex_role] + self.additional_roles_required,
              'parent_required': self.parent_required,
              'allowed_states': [LifecycleStatus.NEW, LifecycleStatus.APPROVAL]}
        return rv

    @cached_property
    def role_delegations(self):
        rv = {self.apex_role: [r for r in self.roles if r != self.apex_role]}
        rv.update(self.custom_delegations)
        for role in self.roles:
            if role in [self.base_role, self.apex_role]:
                continue
            rv.setdefault(role, [])
            rv[role].append(self.base_role)
        return rv

    @staticmethod
    def normalize_role_name(role: str):
        return role.lower().replace(" ", '_')

    @staticmethod
    def normalize_type_name(type: str):
        return type.lower().replace(" ", "_")

    def _standard_scopes(self):
        return {
            f'{self.prefix}:create': f"Create operations on '{self.prefix}' interests",
            f'{self.prefix}:read': f"Read operations on '{self.prefix}' interests",
            f'{self.prefix}:write': f"Write operations on '{self.prefix}' interests",
            f'{self.prefix}:delete': f"Delete operations on '{self.prefix}' interests",
        }

    def _mixin_scopes(self):
        try:
            mro = list(self.__class__.__mro__)
            mro.reverse()
        except AttributeError:
            print(f"There isn't an __mro__ on {self.__class__}. "
                  f"This is probably a classic class. We don't support this.")
            return self.mixin_scopes
        rv = {}
        for cls in mro:
            v = getattr(cls, 'mixin_scopes', {})
            if hasattr(v, '__get__'):
                v = v.__get__(self)
            rv.update(v)
        return rv

    def _custom_scopes(self):
        return {}

    @cached_property
    def scopes(self):
        rv = {}
        rv.update(self._standard_scopes())
        rv.update(self._mixin_scopes())
        rv.update(self._custom_scopes())
        return rv

    def _crud_actions(self):
        rv = {'read': (self.read_role or self.apex_role, f'{self.prefix}:read'),
              'edit': (self.edit_role or self.apex_role, f'{self.prefix}:write'),
              # 'delete': (self.delete_role or self.apex_role, f'{self.prefix}:delete'),
              'delete': (None, f'{self.prefix}:delete'),
              'create': (None, f'{self.prefix}:create')}

        # create does not actually need a role and no role will get checked.
        # The appropriate scope needs to be assigned when the user gets
        # permissions on the parent.

        # delete is suppressed entirely for the moment. We'll only allow detach from
        # parent by way of the parent:write role. We'll deal with actual delete later on.
        return rv

    def _authz_actions(self):
        rv = {'read_members': (self.authz_read_role or self.apex_role,
                               f'{self.prefix}:read'),
              'add_member': (self.authz_write_role or self.apex_role,
                             f'{self.prefix}:write')}
        for role in self.roles:
            nrole = self.normalize_role_name(role)
            rv[f'read_members:{nrole}'] = (self.authz_read_role or self.apex_role, f'{self.prefix}:read')
            if self.authz_write_peers:
                rv[f'add_member:{nrole}'] = (role, f'{self.prefix}:write')
            else:
                rv[f'add_member:{nrole}'] = (self.authz_write_role or self.apex_role, f'{self.prefix}:write')
        return rv

    def _hierarchy_actions(self):
        rv = {'read_children': (self.child_read_role or self.apex_role,
                                f'{self.prefix}:read'),
              'add_child': (self.child_add_role or self.apex_role,
                            f'{self.prefix}:write'),
              'remove_child': (self.child_delete_role or self.apex_role,
                               f'{self.prefix}:write')}

        ac = self.allowed_children
        if '*' in ac:
            from tendril import interests
            ac = interests.type_codes.keys()

        for ctype in ac:
            ctype = self.normalize_type_name(ctype)
            rv[f'read_children:{ctype}'] = (self.child_read_roles.get(ctype, None)
                                            or self.child_read_role
                                            or self.apex_role, f'{self.prefix}:read')
            rv[f'add_child:{ctype}'] = (self.child_add_roles.get(ctype, None)
                                        or self.child_add_role
                                        or self.apex_role, f'{self.prefix}:write')
            rv[f'remove_child:{ctype}'] = (self.child_delete_roles.get(ctype, None)
                                           or self.child_delete_role
                                           or self.apex_role, f'{self.prefix}:write')
        return rv

    def _artefact_actions(self):
        return {
            'read_artefacts': (self.artefact_read_role or self.base_role, f'{self.prefix}:read'),
            'add_artefact': (self.artefact_add_role or self.apex_role, f'{self.prefix}:write'),
            'delete_artefact': (self.artefact_delete_role or self.apex_role, f'{self.prefix}:delete'),
        }

    def _mixin_actions(self):
        try:
            mro = list(self.__class__.__mro__)
            mro.reverse()
        except AttributeError:
            print(f"There isn't an __mro__ on {self.__class__}. "
                  f"This is probably a classic class. We don't support this.")
            return self.mixin_actions
        rv = {}
        for cls in mro:
            v = getattr(cls, 'mixin_actions', {})
            if hasattr(v, '__get__'):
                v = v.__get__(self)
            rv.update(v)
        return rv

    def _custom_actions(self):
        return {}

    @cached_property
    def actions(self):
        rv = {}
        rv.update(self._crud_actions())
        rv.update(self._authz_actions())
        rv.update(self._hierarchy_actions())
        rv.update(self._artefact_actions())
        rv.update(self._mixin_actions())
        rv.update(self._custom_actions())
        return rv

    def get_delegated_roles(self, role):
        return self.role_delegations.get(role, [])

    def get_effective_roles(self, role):
        return [role] + self.get_delegated_roles(role)

    def get_alternate_roles(self, role):
        rv = []
        for k, v in self.role_delegations.items():
            if role in v:
                rv.append(k)
        return rv

    def get_accepted_roles(self, role):
        return [role] + self.get_alternate_roles(role)

    def get_role_scopes(self, role):
        from tendril import interests
        scopes = set([s for (r, s) in self.actions.values()
                      if r in self.get_effective_roles(role)])

        ac = self.allowed_children
        if '*' in ac:
            ac = interests.type_codes.keys()
        for child_type in ac:
            if child_type == self.prefix:
                continue
            if role in self.get_permitted_roles(f'add_child:{child_type}'):
                scopes.add(f'{child_type}:create')
            for r in self.get_effective_roles(role):
                scopes.update(interests.type_codes[child_type].
                              model.role_spec.get_role_scopes(r))
        return scopes

    def get_role_permissions(self, role):
        return set([a for a, (r, s) in self.actions.items() if r == role])

    def get_roles_permissions(self, roles):
        allowed = set()
        for role in roles:
            allowed.update(self.get_role_permissions(role))
        return allowed

    def get_permitted_roles(self, action):
        if action not in self.actions.keys():
            if ':' in action:
               action = action.rsplit(':', 1)[0]
        if action not in self.actions.keys():
            raise ValueError(f"Action {action} does not seem to be "
                             f"recognized by {self.__class__.__name__}")
        return set(self.get_accepted_roles(self.actions[action][0]))

    def check_permitted(self, action, roles):
        permitted = self.get_permitted_roles(action)
        for role in roles:
            if role in permitted:
                return True
        return False


def _check_value(value, allowed):
    if isinstance(value, enum.Enum):
        value = value.value
    if value == allowed:
        return True
    return False


def _check_predicate(predicate, self, kwargs):
    # This entire funciton and the reason it exists is likely to
    # cause significant long term headaches. An alternative pathway
    # to manage exceptions is probably needed.
    attr, value = predicate
    if value.startswith('self'):
        parts = value.split('.')
        value = self
        for part in parts[1:]:
            value = getattr(value, part)
    if hasattr(self, attr):
        if _check_value(getattr(self, attr), value):
            return True
    elif attr in kwargs.keys():
        if _check_value(kwargs[attr], value):
            return True


def require_permission(action,
                       specifier=None, preprocessor=lambda x: x,
                       strip_auth=True, required=True,
                       exceptions=[]):
    def decorator(func):
        @wraps(func)
        def permission_check(self, *args, probe_only=False, **kwargs):
            if strip_auth:
                auth_user = kwargs.pop('auth_user', None)
            else:
                auth_user = kwargs.get('auth_user', None)

            in_exception = False
            for exception in exceptions:
                for predicate in exception:
                    if not _check_predicate(predicate, self, kwargs):
                        break
                else:
                    in_exception = True
                    break

            if not in_exception and required and auth_user is None:
                raise AttributeError("auth_user is required to execute "
                                     "this interest instance method")
            if not auth_user:
                if probe_only:
                    return True
                return func(self, *args, **kwargs)
            session = kwargs.get('session', None)
            if specifier:
                s = kwargs.get(specifier, None)
                if callable(s):
                    s = s(self, *args, **kwargs)
                if s:
                    laction = f'{action}:{preprocessor(s)}'
                else:
                    laction = action
            else:
                laction = action
            # logger.debug(f"Checking permissions of {auth_user} for '{laction}' on {self}")
            if in_exception or self.check_user_access(user=auth_user, action=laction, session=session):
                if probe_only:
                    return True
                return func(self, *args, **kwargs)
            else:
                raise AuthorizationRequiredError(auth_user, laction, self.id, self.name)
        return permission_check
    return decorator


def require_state(states, exceptions=[]):
    def decorator(func):
        @wraps(func)
        def state_check(self, *args, **kwargs):
            in_exception = False
            for exception in exceptions:
                for predicate in exception:
                    if not _check_predicate(predicate, self, kwargs):
                        print(predicate)
                        break
                else:
                    in_exception = True
                    break

            # logger.debug(f"Checking state of {self} for '{states}'")
            if not in_exception:
                if isinstance(states, Iterable):
                    if self.status not in states:
                        raise InterestStateException(self.status, states,
                                                     func.__name__, self.id, self.name)
                else:
                    if self.status != states:
                        raise InterestStateException(self.status, states,
                                                     func.__name__, self.id, self.name)
            return func(self, *args, **kwargs)
        return state_check
    return decorator