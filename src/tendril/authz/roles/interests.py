

from functools import cached_property


class InterestRoleSpec(object):
    prefix = 'interest'
    roles = ['Owner', 'Member']
    role_delegations = {'Owner': ['Member']}
    inherits_from_parent = True

    @cached_property
    def scopes(self):
        return {
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
