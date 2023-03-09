

from typing import List
from typing import Dict

from fastapi import APIRouter
from fastapi import Request
from fastapi import Depends
from fastapi.responses import JSONResponse

from tendril.authn.users import auth_spec
from tendril.authn.users import AuthUserModel
from tendril.authn.users import authn_dependency

from tendril.authz.roles.interests import MembershipInfoTModel
from tendril.utils.db import get_session

from .base import ApiRouterGenerator


class InterestLibraryRouterGenerator(ApiRouterGenerator):
    def __init__(self, actual):
        super(InterestLibraryRouterGenerator, self).__init__()
        self._actual = actual

    async def items(self, request: Request,
                    user: AuthUserModel = auth_spec(),
                    include_roles: bool = False,
                    include_permissions: bool = False):
        with get_session() as session:
            rv = [x.export(auth_user=user, session=session,
                           include_roles=include_roles,
                           include_permissions=include_permissions)
                  for x in self._actual.items(user=user, session=session)]
        return rv

    async def item(self, request: Request, id: int,
                   user: AuthUserModel = auth_spec(),
                   include_roles: bool = False,
                   include_permissions: bool = False):
        with get_session() as session:
            rv = self._actual.item(id=id, session=session).\
                export(auth_user=user, session=session,
                       include_roles=include_roles,
                       include_permissions=include_permissions)
        return rv

    async def item_members(self, request: Request, id: int,
                           user: AuthUserModel = auth_spec(),
                           include_effective: bool=False,
                           include_inherited: bool=True):
        with get_session() as session:
            item = self._actual.item(id=id, session=session)
            rv = item.memberships(auth_user=user, session=session,
                                  include_effective=include_effective,
                                  include_inherited=include_inherited)
        return rv

    async def item_role_members(self, request: Request,
                                id: int, role: str,
                                user: AuthUserModel = auth_spec(),
                                include_effective: bool = False,
                                include_inherited: bool = True):
        with get_session() as session:
            item = self._actual.item(id, session=session)
            rv = item.memberships(auth_user=user, role=role, session=session,
                                  include_effective=include_effective,
                                  include_inherited=include_inherited)
        return rv

    async def activate_item(self, request: Request, id: int,
                            user: AuthUserModel = auth_spec()):
        with get_session() as session:
            item = self._actual.item(id, session=session)
            item.activate(auth_user=user, session=session)
        return JSONResponse(
            status_code=200,
            content={'message': f"{self._actual.interest_class.model.role_spec.prefix} "
                                f"{id} Activated"}
        )

    async def create_item(self):
        raise NotImplementedError

    async def update_item(self):
        raise NotImplementedError

    async def delete_item(self):
        raise NotImplementedError

    async def item_children(self):
        raise NotImplementedError

    async def itme_children_of_type(self):
        raise NotImplementedError

    async def add_item_child(self):
        raise NotImplementedError

    def generate(self, name):
        desc = f'{name} Interest API'
        prefix = self._actual.interest_class.model.role_spec.prefix
        router = APIRouter(prefix=f'/{name}', tags=[desc],
                           dependencies=[Depends(authn_dependency)])
        router.add_api_route("", self.items, methods=["GET"],
                             response_model=List[self._actual.interest_class.tmodel],
                             dependencies=[auth_spec(scopes=[f'{prefix}:read'])],)
        router.add_api_route("/{id}", self.item, methods=["GET"],
                             response_model=self._actual.interest_class.tmodel,
                             dependencies=[auth_spec(scopes=[f'{prefix}:read'])],)
        router.add_api_route("/{id}/members", self.item_members, methods=["GET"],
                             response_model=Dict[str, List[MembershipInfoTModel]],
                             dependencies=[auth_spec(scopes=[f'{prefix}:read'])], )
        router.add_api_route("/{id}/members/{role}", self.item_role_members, methods=["GET"],
                             response_model=List[MembershipInfoTModel],
                             dependencies=[auth_spec(scopes=[f'{prefix}:read'])], )
        router.add_api_route("/{id}/activate", self.activate_item, methods=['POST'],
                             dependencies=[auth_spec(scopes=[f'{prefix}:write'])])
        return [router]
