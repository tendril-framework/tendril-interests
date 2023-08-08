

from itertools import chain
from collections.abc import Iterator

from tendril.utils.pydantic import TendrilTBaseModel
from tendril.common.states import LifecycleStatus
from tendril.authz.roles.interests import require_state
from tendril.authz.roles.interests import require_permission

from tendril.authz.approvals.interests import InterestApprovalSpec
from tendril.authz.approvals.interests import ApprovalRequirement
from tendril.common.interests.approvals import ApprovalCollector

from tendril.common.interests.exceptions import ActivationError
from tendril.db.models.interests_approvals import InterestApprovalModel
from tendril.db.controllers.interests import get_interest
from tendril.db.controllers.interests_approvals import get_approval
from tendril.db.controllers.interests_approvals import register_approval
from tendril.db.controllers.interests_approvals import withdraw_approval
from tendril.common.interests.representations import ExportLevel

from .base import InterestMixinBase

from tendril.utils.db import with_db
from tendril.utils import log
logger = log.get_logger(__name__, log.DEFAULT)


class InterestBaseApprovalTMixin(TendrilTBaseModel):
    has_required_approvals: bool


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
        logger.debug(f"Checking {self.type_name} {self.id} for {required_approval.name}")
        possible_contexts = []
        if required_approval.context_type == self.model_instance.type_name:
            possible_contexts.append(self.id)
        for ancestor in self.ancestors(session=session):
            # logger.debug(f"Trying Ancestor  : {ancestor.type_name} {ancestor.id}")
            if ancestor.model_instance.type_name == required_approval.context_type:
                # logger.debug(f"Found Possible Context {ancestor.type_name} {ancestor.id}")
                possible_contexts.append(ancestor.id)

        if len(possible_contexts) == 0:
            logger.debug(f"Found no possible contexts of type "
                         f"{required_approval.context_type} "
                         f"the hierarchy for {self.id}.")
            logger.debug(f"Got Ancestors : {self.ancestors(session=session)}")
            return True

        approvals = []
        for context in possible_contexts:
            rejections = self.approvals(session=session).\
                approvals(subject=self.id, context=context,
                          name=required_approval.name, approved=False)
            if len(rejections):
                logger.debug("Rejections present. Not checking further. Not activating.")
                return False
            approvals += self.approvals(session=session).\
                approvals(subject=self.id, context=context,
                          name=required_approval.name)

        if required_approval.spread == 0:
            # logger.debug(f"Required spread is 0. Not checking for approvals.")
            return True

        if required_approval.spread < 0:
            raise NotImplementedError

        if len(approvals) >= required_approval.spread:
            # logger.debug(f"Found {len(approvals)} approvals, require {required_approval.spread}. Approved.")
            return True

        # logger.debug("No Approval")
        return False

    @with_db
    def _validate_approval(self, approval: InterestApprovalModel, session=None):
        pass

    @with_db
    @require_permission('read_approvals', strip_auth=False, required=False)
    def approvals_pending(self, auth_user=None, session=None) -> Iterator[ApprovalRequirement]:
        # logger.debug(f"Checking for pending approvals for interest {self.id}")
        for required_approval in self.approvals_required(auth_user=auth_user, session=session):
            # logger.debug(f"Checking for {required_approval}")
            if not self._check_approval(required_approval, session=session):
                # logger.debug(f"Found a pending approval {required_approval.name}")
                yield required_approval

    @with_db
    @require_state([LifecycleStatus.ACTIVE, LifecycleStatus.APPROVAL])
    def check_accepts_approval(self, session=None):
        return True

    @with_db
    @require_permission('read_approvals', strip_auth=False, required=False)
    def check_activation_approvals(self, auth_user=None, session=None):
        if not self._check_needs_approval(session=session):
            logger.debug(f"No approvals needed for activation of {self.type_name} {self.id}")
            return True

        pending_approvals = list(self.approvals_pending(auth_user=auth_user, session=session))
        if len(pending_approvals):
            # TODO Signal for approvals?
            if self._model_instance.status != LifecycleStatus.APPROVAL:
                logger.info(f"Initiating requests for required approvals of "
                            f"{self.model.type_name} {self.id} {self.name}")
                self._model_instance.status = LifecycleStatus.APPROVAL
                return False
            else:
                logger.debug(f"{self.model.type_name} {self.id} {self.name} "
                             f"is still pending approvals. Cannot activate.")
            return False
        else:
            return True

    @with_db
    @require_state(LifecycleStatus.NEW)
    @require_permission('edit', strip_auth=False, required=False)
    def request_approvals(self, auth_user=None, session=None):
        self._check_activation_requirements(session=session)

        for check_fn_orig in self._additional_activation_checks:
            if check_fn_orig == 'check_activation_approvals':
                continue

            if not callable(check_fn_orig):
                check_fn = getattr(self, check_fn_orig)
            else:
                check_fn = check_fn_orig
            result = check_fn(auth_user=auth_user, session=session)
            if not result:
                msg = f"Additional activation check '{check_fn_orig}' failed. " \
                      f"Cannot activate, will not request approvals in this condition."
                return msg

        can_activate = self.check_activation_approvals(auth_user=auth_user, session=session)
        if can_activate:
            return f"No further approvals needed for activation of {self.type_name} {self.id}"
        else:
            return f"Approval requests initiated for {self.type_name} {self.id}"

    @with_db
    def unapprove(self, session=None):
        msg = f"Approval shortfall for {self.model.type_name} Interest {self.id} {self.name}"
        logger.info(msg)
        self.model_instance.status = LifecycleStatus.APPROVAL
        return msg

    @with_db
    @require_permission('read_approvals', strip_auth=False, required=False)
    def export(self, export_level=ExportLevel.NORMAL,
               session=None, auth_user=None, **kwargs):
        rv = {}
        if hasattr(super(), 'export'):
            rv.update(super().export(export_level=export_level, session=session,
                                     auth_user=auth_user, **kwargs))

        try:
            self._check_activation_requirements(session=session)
            if next(self.approvals_pending(auth_user=auth_user, session=session), None):
                rv['has_required_approvals'] = False
            else:
                rv['has_required_approvals'] = True
        except ActivationError:
            rv['has_required_approvals'] = False
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
