

class InterestApprovalRolesMixin(object):
    @property
    def mixin_scopes(self):
        return {}

    @property
    def mixin_actions(self):
        return {
            'read_approvals': (self.base_role, f'{self.prefix}:read'),
        }


class InterestApprovalContextRolesMixin(object):
    approval_role = None

    @property
    def mixin_scopes(self):
        return {}

    @property
    def mixin_actions(self):
        return {
            'read_approvals': (self.base_role, f'{self.prefix}:read'),
            'grant_approvals': (self.approval_role or self.apex_role, f'{self.prefix}:write'),
        }
