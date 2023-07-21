

from typing import List
from typing import Optional

from fastapi import APIRouter
from fastapi import Request
from fastapi import Depends

from tendril.authn.users import auth_spec
from tendril.authn.users import AuthUserModel
from tendril.authn.users import authn_dependency

from tendril.apiserver.templates.base import ApiRouterGenerator
from tendril.common.interests.approvals import ApprovalRequirementTModel
from tendril.common.interests.approvals import InterestApprovalStatusTModel

from tendril.utils.db import get_session


class InterestApprovalRouterGenerator(ApiRouterGenerator):
    def __init__(self, actual):
        super(InterestApprovalRouterGenerator, self).__init__()
        self._actual = actual

    async def get_required_approvals(self, request: Request, id: int,
                                     user: AuthUserModel = auth_spec()):
        with get_session() as session:
            item = self._actual.item(id, session=session)
            return [x._asdict() for x in item.approvals_required(auth_user=user, session=session)]

    async def get_enabled_approvals(self, request: Request, id: int,
                                    user: AuthUserModel = auth_spec()):
        with get_session() as session:
            item = self._actual.item(id, session=session)
            return [x._asdict() for x in item.approvals_enabled(auth_user=user, session=session)]

    async def get_approvals_status(self, request: Request, id: int,
                                   user: AuthUserModel = auth_spec()):
        with get_session() as session:
            item = self._actual.item(id, session=session)
            result = item.approvals(auth_user=user, session=session).render_subject_perspective()
            if len(result):
                return result[0]
            else:
                return {'subject': id, 'contexts': []}

    def generate(self, name):
        desc = f'Approvals API for {name} Interests'
        prefix = self._actual.interest_class.model.role_spec.prefix
        router = APIRouter(prefix=f'/{name}', tags=[desc],
                           dependencies=[Depends(authn_dependency)])

        router.add_api_route("/{id}/approvals/required", self.get_required_approvals, methods=["GET"],
                             response_model=List[ApprovalRequirementTModel],
                             response_model_exclude_none=True,
                             dependencies=[auth_spec(scopes=[f'{prefix}:read'])])

        router.add_api_route("/{id}/approvals/enabled", self.get_enabled_approvals, methods=["GET"],
                             response_model=List[ApprovalRequirementTModel],
                             response_model_exclude_none=True,
                             dependencies=[auth_spec(scopes=[f'{prefix}:read'])])

        router.add_api_route("/{id}/approvals/status", self.get_approvals_status, methods=["GET"],
                             response_model=InterestApprovalStatusTModel,
                             response_model_exclude_none=True,
                             dependencies=[auth_spec(scopes=[f'{prefix}:read'])])

        return [router]


class InterestApprovalContextRouterGenerator(ApiRouterGenerator):
    def __init__(self, actual):
        super(InterestApprovalContextRouterGenerator, self).__init__()
        self._actual = actual

    async def get_approvals(self, request: Request, id: int,
                            subject_id: int, approval_type: Optional[str] = None,
                            user: AuthUserModel = auth_spec()):
        with get_session() as session:
            context = self._actual.item(id, session=session)
            ac = context.get_approvals(subject_id, auth_user=user, session=session)
            if approval_type:
                ac.apply_approval_filter([approval_type])
            result = ac.render_context_perspective()
            if len(result):
                return result[0]
            else:
                return {'subject': id, 'contexts': []}

    async def grant_approval(self, request: Request, id: int,
                             subject_id: int, approval_type: str = None,
                             user: AuthUserModel = auth_spec()):
        with get_session() as session:
            context = self._actual.item(id, session=session)
            return context.approval_grant(subject_id, approval_type, auth_user=user, session=session)

    async def reject_approval(self, request: Request, id: int,
                              subject_id: int, approval_type: str = None,
                              user: AuthUserModel = auth_spec()):
        with get_session() as session:
            context = self._actual.item(id, session=session)
            return context.approval_reject(subject_id, approval_type, auth_user=user, session=session)

    async def withdraw_approval(self, request: Request, id: int,
                                subject_id: int, approval_type: str = None,
                                user: AuthUserModel = auth_spec()):
        with get_session() as session:
            context = self._actual.item(id, session=session)
            return context.approval_withdraw(subject_id, approval_type, auth_user=user, session=session)

    def generate(self, name):
        desc = f'Approval Context API for {name} Interests'
        prefix = self._actual.interest_class.model.role_spec.prefix
        router = APIRouter(prefix=f'/{name}', tags=[desc],
                           dependencies=[Depends(authn_dependency)])

        router.add_api_route("/{id}/approvals/{subject_id}/status",
                             self.get_approvals, methods=["GET"],
                             # response_model=[],
                             response_model_exclude_none=True,
                             dependencies=[auth_spec(scopes=[f'{prefix}:read'])])

        router.add_api_route("/{id}/approvals/{subject_id}/grant", self.grant_approval, methods=["POST"],
                             # response_model=[],
                             response_model_exclude_none=True,
                             dependencies=[auth_spec(scopes=[f'{prefix}:write'])])

        router.add_api_route("/{id}/approvals/{subject_id}/reject", self.reject_approval, methods=["POST"],
                             # response_model=[],
                             response_model_exclude_none=True,
                             dependencies=[auth_spec(scopes=[f'{prefix}:write'])])

        router.add_api_route("/{id}/approvals/{subject_id}/withdraw", self.withdraw_approval, methods=["POST"],
                             # response_model=[],
                             response_model_exclude_none=True,
                             dependencies=[auth_spec(scopes=[f'{prefix}:write'])])

        return [router]


