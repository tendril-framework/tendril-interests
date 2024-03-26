

class InterestPolicyRolesMixin(object):
    policies_role = None

    @property
    def mixin_scopes(self):
        return {}

    @property
    def mixin_actions(self):
        return {
            'read_policies': (self.base_role, f'{self.prefix}:read'),
            'write_policies': (self.policies_role or self.apex_role, f'{self.prefix}:write')
        }
