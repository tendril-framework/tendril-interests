

from functools import cached_property


class InterestRoleSpec(object):
    prefix = 'interest'
    roles = ['Owner', 'Member']
    role_delegations = {'Owner': ['Member']}
    inherits_from_parent = True

    @cached_property
    def scopes(self):
        return {
            f'{self.prefix}:create': f"Create operations on '{self.prefix}' interests",
            f'{self.prefix}:read': f"Read operations on '{self.prefix}' interests",
            f'{self.prefix}:write': f"Write operations on '{self.prefix}' interests",
            f'{self.prefix}:delete': f"Delete operations on '{self.prefix}' interests",
        }

    @cached_property
    def actions(self):
        return {
            'read': ('Member', f'{self.prefix}:read'),
            'edit': ('Owner', f'{self.prefix}:write'),
            'delete': ('Owner', f'{self.prefix}:delete'),
            'create': ('Owner', f'{self.prefix}:create'),

            # create does not actually need a role. The appropriate scope
            # needs to be assigned when the user gets permissions on the parent

            'read_children': ('Member', f'{self.prefix}:read'),
            'read_children:interest': ('Member', f'{self.prefix}:read'),
            'add_child': ('Owner', f'{self.prefix}:write'),
            'add_child:interest': ('Owner', f'{self.prefix}:write'),

            'read_artefacts': ('Member', f'{self.prefix}:read'),
            'add_artefact': ('Owner', f'{self.prefix}:write'),
            'delete_artefact': ('Owner', f'{self.prefix}:delete'),

            'add_member': ('Owner', f'{self.prefix}:write'),
            'add_member:owner': ('Owner', f'{self.prefix}:write'),
        }

    def get_effective_roles(self, role):
        return [role] + self.role_delegations.get(role, [])

    def get_accepted_roles(self, role):
        rv = [role]
        for k, v in self.role_delegations.items():
            if role in v:
                rv.append(k)
        return rv

    def _get_model(self):
        from tendril import interests
        return interests.type_codes[self.prefix].model

    def get_role_scopes(self, role):
        from tendril import interests
        scopes = set([s for (r, s) in self.actions.values()
                      if r in self.get_effective_roles(role)])

        ac = self._get_model().allowed_children
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