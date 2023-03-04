

from functools import cached_property
from tendril.authn.pydantic import UserStubTModel
from tendril.utils.pydantic import TendrilTBaseModel


class MembershipInfoTModel(TendrilTBaseModel):
    user: UserStubTModel
    delegated: bool
    inherited: bool


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

    child_read_roles = {}
    child_add_roles = {}
    child_delete_roles = {}

    inherits_from_parent = True

    custom_delegations = {}

    @cached_property
    def role_delegations(self):
        rv = {self.apex_role: '*'}
        rv.update(self.custom_delegations)
        for role in self.roles:
            if role == self.base_role:
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

    def _custom_scopes(self):
        return {}

    @cached_property
    def scopes(self):
        rv = {}
        rv.update(self._standard_scopes())
        rv.update(self._custom_scopes())
        return rv

    def _crud_actions(self):
        rv = {'read': (self.read_role or self.apex_role, f'{self.prefix}:read'),
              'edit': (self.edit_role or self.apex_role, f'{self.prefix}:write'),
              'delete': (self.delete_role or self.apex_role, f'{self.prefix}:delete'),
              'create': (self.apex_role, f'{self.prefix}:create')}

        # create does not actually need a role and no role will get checked.
        # The appropriate scope needs to be assigned when the user gets
        # permissions on the parent.
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

        for ctype in self.allowed_children:
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
            'read_artefacts': ('Member', f'{self.prefix}:read'),
            'add_artefact': ('Owner', f'{self.prefix}:write'),
            'delete_artefact': ('Owner', f'{self.prefix}:delete'),
        }

    def _custom_actions(self):
        return {}

    @cached_property
    def actions(self):
        rv = {}
        rv.update(self._crud_actions())
        rv.update(self._authz_actions())
        rv.update(self._hierarchy_actions())
        rv.update(self._artefact_actions())
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
        while action not in self.actions.keys():
            if ':' in action:
                action = action.rsplit(':', 1)[0]
        return set(self.get_accepted_roles(self.actions[action][0]))
