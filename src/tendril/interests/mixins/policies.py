

from .base import InterestMixinBase

from tendril.policies.base import PolicyBase
from tendril import policies

from tendril.authz.roles.interests import require_state
from tendril.authz.roles.interests import require_permission
from tendril.common.states import LifecycleStatus
from tendril.db.controllers.interests_policies import get_policy
from tendril.db.controllers.interests_policies import upsert_policy
from tendril.db.controllers.interests_policies import clear_policy

from tendril.common.interests.exceptions import AuthorizationRequiredError

from tendril.utils.db import with_db
from tendril.utils import log
logger = log.get_logger(__name__)


class InterestPoliciesMixin(InterestMixinBase):
    def policies_assignable(self):
        return policies.assignable_templates(self.type_name)

    def policies_types(self):
        rv = {}
        for x in self.policies_assignable():
            rv[x.name] = x
        return rv

    def policies_spec(self):
        rv = {}
        for x in self.policies_assignable():
            rv[x.name] = x.render_spec()
        return rv

    @with_db
    def policies_current(self, auth_user=None, session=None):
        rv = {}
        for x in self.policies_assignable():
            rv[x.name] = self.policy_get(x.name, auth_user=auth_user, session=session)
        return rv

    def _policy_context_check_inherits(self, context_spec):
        for spec in context_spec:
            if spec['interest_type'] == self.type_name and spec['inherits_from'] == 'ancestors':
                return True
        return False

    @with_db
    @require_permission('read_policies', strip_auth=True, required=False)
    def policy_get(self, name, resolve_ancestors=True, session=None):
        policy = get_policy(policy_type=name, interest=self.id, session=session)
        if policy:
            return policy.policy

        if not resolve_ancestors:
            return None

        try:
            spec: PolicyBase = self.policies_types()[name]
        except KeyError:
            logger.warn(f"Could not find policy type '{name}' for interest type '{self.type_name}'")
            return None

        inherit = self._policy_context_check_inherits(spec.context_spec)

        if not inherit:
            return None

        for ancestor in self.ancestors(session=session):
            try:
                policy = ancestor.policy_get(name, resolve_ancestors=False, session=session)
            except AttributeError:
                continue
            if policy:
                return policy

        return None

    @with_db
    def _policy_check_auth_context(self, spec, context, auth_user, session=None):
        if context.type_name not in spec['interest_type']:
            return False
        if spec['role'] not in context.get_user_effective_roles(auth_user, session=session):
            return False
        logger.info(f"Approving with Context {context}")
        return True

    @with_db
    @require_state(LifecycleStatus.ACTIVE)
    @require_permission('write_policies', strip_auth=False, required=True)
    def policy_set(self, name, policy, auth_user=None, session=None):
        spec: PolicyBase = self.policies_types()[name]

        # TODO This permission check does not actually work as intended. Specifically, we allow
        #   Apex Role delegation to count for the actual role, even when the Apex Role is inherited.
        #   This problem likely also occurs for Approval roles, and this must be fixed.
        #
        #   Possibly, we could allow the required role to be suffixed with a '*', indicating
        #   that inherited roles should not be accepted.

        for ancestor in self.ancestors(session=session):
            accepted = self._policy_check_auth_context(spec.write_requires, ancestor, auth_user, session=session)
            if accepted:
                break
        else:
            raise AuthorizationRequiredError(user_id=auth_user, action=f"policy_set:{name}",
                                             interest_id=self.id, interest_name=self.name)

        if not policy:
            result = clear_policy(policy_type=name, interest=self.id, session=session)
            return result

        result = upsert_policy(policy_type=name, interest=self.id, user=auth_user,
                               policy=spec.schema(**policy).dict(), session=session)
        return result
