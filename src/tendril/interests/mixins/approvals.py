
from abc import ABC
from typing import Type
from typing import List
from typing import Dict
from collections.abc import Iterator
from itertools import chain
from functools import cached_property

from tendril.utils.pydantic import TendrilTBaseModel
from tendril.common.states import LifecycleStatus
from tendril.authz.roles.interests import require_state
from tendril.authz.roles.interests import require_permission

from tendril.interests.base import InterestModel
from tendril.authz.roles.interests import InterestRoleSpec
from tendril.authz.approvals.interests import InterestApprovalSpec
from tendril.authz.approvals.interests import ApprovalRequirement
from tendril.common.interests.approvals import ApprovalCollector

from tendril.db.models.interests_approvals import InterestApprovalModel
from tendril.db.controllers.interests import get_interest
from tendril.db.controllers.interests_approvals import get_approval
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
    additional_activation_checks = ['check_activation_approvals']

    @property
    def approval_spec(self) -> InterestApprovalSpec:
        return self.model.approval_spec

    @with_db
    def user_mandated_approvals(self, session=None) -> Iterator[ApprovalRequirement]:
        recognized_approvals = self.approval_spec.optional_approvals
        # TODO Get mandated approval types for the interest from the
        #  database based on parents
        rv = []
        for required_approval in rv:
            yield rv

    @with_db
    def user_enabled_approvals(self, session=None) -> Iterator[ApprovalRequirement]:
        recognized_approvals = self.approval_spec.optional_approvals
        # TODO Get enabled approval types for the interest from the
        #  database based on parents
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
    @require_permission('read_approvals', strip_auth=False, required=False)
    def approvals_required(self, auth_user=None, session=None) -> Iterator[ApprovalRequirement]:
        return chain(self.approval_spec.required_approvals,
                     self.user_mandated_approvals(session=session))

    @with_db
    @require_permission('read_approvals', strip_auth=False)
    def approvals_enabled(self, auth_user=None, session=None) -> Iterator[ApprovalRequirement]:
        return chain(self.approvals_required(auth_user=auth_user, session=session),
                     self.user_enabled_approvals(session=session))

    @with_db
    @require_permission('read_approvals', strip_auth=False, required=False)
    def approvals(self, auth_user=None, session=None):
        if not hasattr(self, '_approvals') or not self._approvals:
            self._approvals = ApprovalCollector()
            self._approvals.add_approvals(get_approval(subject=self, session=session))
            self._approvals.process()
        return self._approvals

    def _clear_approval_cache(self):
        # TODO This does not actually clear the cache on other instances.
        #  Consider use of redis caching or a back channel cache management
        #  messaging system
        self._approvals = None

    @with_db
    def signal_approval_granted(self, approval, session=None):
        # print(f"SIGNAL : APPROVAL_GRANTED : {approval}")
        self._clear_approval_cache()
        if self.status == LifecycleStatus.APPROVAL:
            if self.check_activation_approvals(auth_user=None, session=session):
                self.activate(session=session)

    @with_db
    def signal_approval_withdrawn(self, approval, session=None):
        # print(f"SIGNAL : APPROVAL_WITHDRAWN : {approval}")
        self._clear_approval_cache()
        if self.status == LifecycleStatus.ACTIVE:
            if not self.check_activation_approvals(auth_user=None, session=session):
                self.unapprove(session=session)

    @with_db
    def signal_approval_rejected(self, approval, session=None):
        # print(f"SIGNAL : APPROVAL_REJECTED : {approval}")
        self._clear_approval_cache()

    @with_db
    def _check_approval(self, required_approval: ApprovalRequirement, session=None):
        possible_contexts = []
        if required_approval.context_type == self.model_instance.type_name:
            possible_contexts.append(self.id)
        for ancestor in self.ancestors(session=session):
            if ancestor.model_instance.type_name == required_approval.context_type:
                possible_contexts.append(ancestor.id)

        if len(possible_contexts) == 0:
            return True

        approvals = []
        for context in possible_contexts:
            rejections = self.approvals(session=session).\
                approvals(subject=self.id, context=context,
                          name=required_approval.name, approved=False)
            if len(rejections):
                return False
            approvals += self.approvals(session=session).\
                approvals(subject=self.id, context=context,
                          name=required_approval.name)

        if required_approval.spread == 0:
            return True

        if required_approval.spread < 0:
            raise NotImplementedError

        if len(approvals) >= required_approval.spread:
            return True

        return False

    @with_db
    def _validate_approval(self, approval: InterestApprovalModel, session=None):
        pass

    @with_db
    @require_permission('read_approvals', strip_auth=False, required=False)
    def approvals_pending(self, auth_user=None, session=None) -> Iterator[ApprovalRequirement]:
        for required_approval in self.approvals_required(auth_user=auth_user, session=session):
            if not self._check_approval(required_approval, session=session):
                yield required_approval

    @with_db
    @require_state([LifecycleStatus.ACTIVE, LifecycleStatus.APPROVAL])
    def check_accepts_approval(self, session=None):
        return True

    @with_db
    @require_permission('read_approvals', strip_auth=False, required=False)
    def check_activation_approvals(self, auth_user=None, session=None):
        if not self._check_needs_approval(session=session):
            return True

        pending_approvals = list(self.approvals_pending(auth_user=auth_user, session=session))
        if len(pending_approvals):
            # TODO Signal for approvals?
            if self._model_instance.status != LifecycleStatus.APPROVAL:
                logger.info(f"Initiating activation of "
                            f"{self.model.type_name} Interest {self.id} {self.name} "
                            f"pending Required Approvals")
                self._model_instance.status = LifecycleStatus.APPROVAL
            else:
                logger.debug(f"{self.model.type_name} Interest {self.id} {self.name} "
                             f"is still pending approvals. Not activating.")
            return False
        else:
            return True

    @with_db
    def unapprove(self, session=None):
        msg = f"Approval shortfall for {self.model.type_name} Interest {self.id} {self.name}"
        logger.info(msg)
        self.model_instance.status = LifecycleStatus.APPROVAL
        return msg

    @with_db
    @require_permission('read_approvals', strip_auth=False, required=False)
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

    @with_db
    def _get_approval_subject(self, subject, session=None):
        if isinstance(subject, int):
            from tendril.interests import type_codes
            subject = get_interest(id=subject, session=session)
            subject = type_codes[subject.type_name](subject)
        return subject

    def _check_if_done(self, candidates):
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) == 0:
            raise ApprovalTypeUnrecognized()
        else:
            raise ApprovalTypeAmbiguity()

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
    def _get_approvals(self, subject_id, auth_user=None, session=None):
        ac = ApprovalCollector()
        ac.add_approvals(get_approval(context=self.id, subject=subject_id, session=session))
        ac.process()
        return ac

    @with_db
    @require_state(LifecycleStatus.ACTIVE)
    @require_permission('read_approvals', strip_auth=False)
    def get_approvals(self, subject, auth_user=None, session=None):
        # TODO Work out caching.
        #  Might want to put this in redis.
        #  Cache invalidation needs to get correctly routed here.
        subject = self._get_approval_subject(subject, session=session)
        # if not hasattr(self, '_approvals'):
        #     self._approvals = {}
        # if subject.id not in self._approvals.keys():
        #     self._approvals[subject.id] = ApprovalCollector()
        #     self._approvals[subject.id].add_approvals(get_approval(subject=self, session=session))
        #     self._approvals[subject.id].process()
        # return self._approvals[subject.id]
        return self._get_approvals(subject.id, auth_user=auth_user, session=session)

    @with_db
    def check_approval(self, subject, required_approval, auth_user=None, session=None):
        subject = self._get_approval_subject(subject, session=session)
        ac = self._get_approvals(subject.id, session=session)

        rejections = ac.approvals(subject=subject.id, context=self.id,
                                  name=required_approval.name, approved=False)
        if len(rejections):
            return False

        if not required_approval.spread:
            return True

        if required_approval.spread < 0:
            raise NotImplementedError("We currently only accept simple approval "
                                      "spread requirements")

        approvals = ac.approvals(subject=subject.id, context=self.id,
                                 name=required_approval.name)
        if len(approvals) >= required_approval.spread:
            return True

        return False

    @with_db
    @require_state(LifecycleStatus.ACTIVE)
    @require_permission('grant_approvals', strip_auth=False)
    def approval_grant(self, subject, approval_type=None, auth_user=None, session=None):
        subject = self._get_approval_subject(subject, session=session)
        subject.check_accepts_approval(session=session)
        approval_type = self.approval_type_discriminator(subject=subject, approval_type=approval_type,
                                                         auth_user=auth_user, session=session)
        result = register_approval(approval_type, self.model_instance,
                                   subject.model_instance, user=auth_user, session=session)
        subject.signal_approval_granted(result, session=session)
        return result

    @with_db
    @require_state(LifecycleStatus.ACTIVE)
    @require_permission('grant_approvals', strip_auth=False)
    def approval_withdraw(self, subject, approval_type=None, auth_user=None, session=None):
        subject = self._get_approval_subject(subject, session=session)
        approval_type = self.approval_type_discriminator(subject=subject, approval_type=approval_type,
                                                         auth_user=auth_user, session=session)
        result = withdraw_approval(approval_type, self.model_instance,
                                   subject.model_instance, user=auth_user, session=session)
        subject.signal_approval_withdrawn(result, session=session)
        return f"Approval/Rejection of type {approval_type.name} withdrawn."

    @with_db
    @require_state(LifecycleStatus.ACTIVE)
    @require_permission('grant_approvals', strip_auth=False)
    def approval_reject(self, subject, approval_type=None, auth_user=None, session=None):
        subject = self._get_approval_subject(subject, session=session)
        approval_type = self.approval_type_discriminator(subject=subject, approval_type=approval_type,
                                                         auth_user=auth_user, session=session)
        result = register_approval(approval_type, self.model_instance,
                                   subject.model_instance, user=auth_user, reject=True, session=session)
        subject.signal_approval_rejected(result, session=session)
        return result

    @with_db
    def approvals_validate(self, auth_user=None, session=None):
        raise NotImplementedError

    @with_db
    def approvals_prune(self, auth_user=None, session=None):
        raise NotImplementedError
