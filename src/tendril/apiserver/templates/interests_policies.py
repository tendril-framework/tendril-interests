

from typing import Any, Dict, List, Union, Annotated
from inflection import singularize
from inflection import titleize

from fastapi import APIRouter
from fastapi import Request
from fastapi import Depends
from fastapi import Body

from tendril.authn.users import auth_spec
from tendril.authn.users import AuthUserModel
from tendril.authn.users import authn_dependency

from tendril.apiserver.templates.base import ApiRouterGenerator
from tendril.utils.db import get_session


class InterestPolicyRouterGenerator(ApiRouterGenerator):
    def __init__(self, actual):
        super(InterestPolicyRouterGenerator, self).__init__()
        self._actual = actual

    async def get_policy_spec(self, _request: Request, id: int,
                             _user: AuthUserModel = auth_spec()):
        with get_session() as session:
            item = self._actual.item(id, session=session)
            return item.policies_spec()

    async def get_policies_current(self, _request: Request, id: int,
                                   user: AuthUserModel = auth_spec()):
        with get_session() as session:
            item = self._actual.item(id, session=session)
            return item.policies_current(auth_user=user, session=session)

    async def get_policy(self, _request: Request, id: int, name: str,
                         user: AuthUserModel = auth_spec()):
        with get_session() as session:
            item = self._actual.item(id, session=session)
            return item.policy_get(name=name, auth_user=user, session=session)

    async def set_policy(self, _request: Request, id: int, name: str,
                         policy: Annotated[Any, Body()] = None,
                         user: AuthUserModel = auth_spec()):
        with get_session() as session:
            item = self._actual.item(id, session=session)
            return item.policy_set(name=name, policy=policy, auth_user=user, session=session)

    def generate(self, name):
        desc = f'Policy API for {titleize(singularize(name))} Interests'
        prefix = self._actual.interest_class.model.role_spec.prefix
        router = APIRouter(prefix=f'/{name}', tags=[desc],
                           dependencies=[Depends(authn_dependency)])

        router.add_api_route("/{id}/policy/specs", self.get_policy_spec, methods=["GET"],
                             response_model=Any,
                             response_model_exclude_none=True,
                             dependencies=[auth_spec(scopes=[f'{prefix}:read'])])

        router.add_api_route("/{id}/policy/current", self.get_policies_current, methods=["GET"],
                             response_model=Any,
                             response_model_exclude_none=True,
                             dependencies=[auth_spec(scopes=[f'{prefix}:read'])])

        router.add_api_route("/{id}/policy/{name}/current", self.get_policy, methods=["GET"],
                             response_model=Any,
                             response_model_exclude_none=True,
                             dependencies=[auth_spec(scopes=[f'{prefix}:read'])])

        router.add_api_route("/{id}/policy/{name}/set", self.set_policy, methods=["POST"],
                             response_model=Any,
                             response_model_exclude_none=True,
                             dependencies=[auth_spec(scopes=[f'{prefix}:write'])])

        return [router]
