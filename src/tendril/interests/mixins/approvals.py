
from abc import ABC
from typing import Type
from typing import List
from collections.abc import Iterator
from itertools import chain

from tendril.utils.pydantic import TendrilTBaseModel
from tendril.common.states import LifecycleStatus
from tendril.authz.roles.interests import require_state
from tendril.authz.roles.interests import require_permission

from tendril.interests.base import InterestModel
from tendril.authz.roles.interests import InterestRoleSpec
from tendril.authz.approvals.interests import InterestApprovalSpec
from tendril.authz.approvals.interests import ApprovalRequirement

from tendril.db.models.interests_approvals import InterestApprovalModel
from tendril.db.controllers.interests import get_interest
from tendril.db.controllers.interests_approvals import register_approval
from tendril.db.controllers.interests_approvals import withdraw_approval

from tendril.utils.db import with_db
from tendril.utils import log
logger = log.get_logger(__name__, log.DEFAULT)


class InterestBaseApprovalTMixin(TendrilTBaseModel):
    approved: bool


class InterestMixinBase(ABC):
    model: Type[InterestModel]
    role_spec: InterestRoleSpec
    model_instance: InterestModel


class InterestApprovalsMixin(InterestMixinBase):
    @property
    def approval_spec(self) -> InterestApprovalSpec:
        return self.model.approval_spec

    @with_db
    def user_mandated_approvals(self, session=None) -> Iterator[ApprovalRequirement]:
        recognized_approvals = self.approval_spec.optional_approvals
        # TODO Get mandated approval types for the interest from the database
        rv = []
        for required_approval in rv:
            yield rv

    @with_db
    def user_enabled_approvals(self, session=None) -> Iterator[ApprovalRequirement]:
        recognized_approvals = self.approval_spec.optional_approvals
        # TODO Get enabled approval types for the interest from the database
        rv = recognized_approvals
        for required_approval in rv:
            yield ApprovalRequirement(required_approval.name, required_approval.role,
                                      0, required_approval.states, required_approval.context_type)

    @with_db
    def _check_needs_approval(self, session=None):
        if len(self.approval_spec.required_approvals):
            return True
        if next(self.user_mandated_approvals(session=session), default=None):
            return True
        return False

    @with_db
    @require_permission('read_approvals', strip_auth=False)
    def approvals_required(self, auth_user=None, session=None) -> Iterator[ApprovalRequirement]:
        return chain(self.approval_spec.required_approvals,
                     self.user_mandated_approvals(session=session))

    @with_db
    @require_permission('read_approvals', strip_auth=False)
    def approvals_enabled(self, auth_user=None, session=None) -> Iterator[ApprovalRequirement]:
        return chain(self.approvals_required(auth_user=auth_user, session=session),
                     self.user_enabled_approvals(session=session))

    @with_db
    def _find_all_approvals(self, session=None) -> List[InterestApprovalModel]:
        pass

    @with_db
    def _check_approval(self, required_approval: ApprovalRequirement, session=None):
        return False

    @with_db
    def _validate_approval(self, approval: InterestApprovalModel, session=None):
        pass

    @with_db
    @require_permission('read_approvals', strip_auth=False)
    def approvals_pending(self, auth_user=None, session=None) -> Iterator[ApprovalRequirement]:
        for required_approval in self.approvals_required(auth_user=auth_user, session=session):
            if not self._check_approval(required_approval, session=session):
                yield required_approval

    @with_db
    @require_permission('read_approvals', strip_auth=False)
    def export(self, session=None, auth_user=None):
        rv = {}
        if next(self.approvals_pending(auth_user=auth_user, session=session), None):
            rv['approved'] = True
        else:
            rv['approved'] = False
        return rv


class ApprovalTypeAmbiguity(Exception):
    pass


class ApprovalTypeUnrecognized(Exception):
    pass


class InterestApprovalsContextMixin(InterestMixinBase):
    approval_types = []

    def _check_if_done(self, candidates):
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) == 0:
            raise ApprovalTypeUnrecognized()
        else:
            raise ApprovalTypeAmbiguity()

    @with_db
    def _get_approval_subject(self, subject, session=None):
        if isinstance(subject, int):
            from tendril.interests import type_codes
            subject = get_interest(id=subject, session=session)
            subject = type_codes[subject.type_name](subject)
        return subject

    @with_db
    def approval_type_discriminator(self, subject, approval_type=None, auth_user=None, session=None):
        if isinstance(approval_type, ApprovalRequirement):
            if approval_type in self.approval_types:
                return approval_type
            return self._check_if_done([])
        if isinstance(approval_type, str):
            for candidate in self.approval_types:
                if candidate.name == approval_type:
                    return candidate
            return self._check_if_done([])

        candidates = self.approval_types

        try:
            return self._check_if_done(candidates)
        except ApprovalTypeAmbiguity:
            pass

        if isinstance(subject, int):
            from tendril.interests import type_codes
            subject = get_interest(id=subject, session=session)
            subject = type_codes[subject.type_name](subject)

        subject_approval_types = list(subject.approvals_enabled(auth_user=auth_user))
        candidates = [x for x in candidates if x in subject_approval_types]

        try:
            return self._check_if_done(candidates)
        except ApprovalTypeAmbiguity:
            pass

        fcandidates = []
        for candidate in candidates:
            candidate: ApprovalRequirement
            if candidate.role in self.get_user_effective_roles(user=auth_user, session=session):
                fcandidates.append(candidate)

        try:
            return self._check_if_done(fcandidates)
        except ApprovalTypeAmbiguity:
            raise

    @with_db
    @require_state(LifecycleStatus.ACTIVE)
    @require_permission('grant_approvals', strip_auth=False)
    def approval_grant(self, subject, approval_type=None, auth_user=None, session=None):
        subject = self._get_approval_subject(subject, session=session)
        approval_type = self.approval_type_discriminator(subject=subject, approval_type=approval_type,
                                                         auth_user=auth_user, session=session)
        return register_approval(approval_type, self.model_instance,
                                 subject.model_instance, user=auth_user, session=session)

    @with_db
    @require_state(LifecycleStatus.ACTIVE)
    @require_permission('grant_approvals', strip_auth=False)
    def approval_withdraw(self, subject, approval_type=None, auth_user=None, session=None):
        subject = self._get_approval_subject(subject, session=session)
        approval_type = self.approval_type_discriminator(subject=subject, approval_type=approval_type,
                                                         auth_user=auth_user, session=session)
        result = withdraw_approval(approval_type, self.model_instance,
                                   subject.model_instance, user=auth_user, session=session)
        return f"Approval/Rejection of type {approval_type.name} withdrawn."

    @with_db
    @require_state(LifecycleStatus.ACTIVE)
    @require_permission('grant_approvals', strip_auth=False)
    def approval_reject(self, subject, approval_type=None, auth_user=None, session=None):
        subject = self._get_approval_subject(subject, session=session)
        approval_type = self.approval_type_discriminator(subject=subject, approval_type=approval_type,
                                                         auth_user=auth_user, session=session)
        return register_approval(approval_type, self.model_instance,
                                 subject.model_instance, user=auth_user, reject=True, session=session)

    @with_db
    def approvals_validate(self, auth_user=None, session=None):
        raise NotImplementedError

    @with_db
    def approvals_prune(self, auth_user=None, session=None):
        raise NotImplementedError
