

from typing import List

from fastapi import APIRouter
from fastapi import Request
from fastapi import Depends

from tendril.authn.users import auth_spec
from tendril.authn.users import AuthUserModel
from tendril.authn.users import authn_dependency

from tendril.authn.pydantic import UserStubTMixin
from tendril.utils.pydantic import TendrilTBaseModel

from tendril.utils.db import get_session

from .base import ApiRouterGenerator


class InterestLibraryRouterGenerator(ApiRouterGenerator):
    def __init__(self, actual):
        super(InterestLibraryRouterGenerator, self).__init__()
        self._actual = actual

    async def items(self, request: Request,
                    user: AuthUserModel = auth_spec(),
                    include_roles: bool = False,
                    include_permissions: bool = False,
                    ):
        with get_session() as session:
            rv = [x.export(user=user, session=session,
                           include_roles=include_roles,
                           include_permissions=include_permissions)
                  for x in self._actual.items(user=user, session=session)]
        return rv

    async def item(self, request: Request, id: int,
                   user: AuthUserModel = auth_spec(),
                   include_roles: bool = False,
                   include_permissions: bool = False,
                   ):
        with get_session() as session:
            rv = self._actual.item(id=id, session=session).\
                export(user=user, session=session,
                       include_roles=include_roles,
                       include_permissions=include_permissions)
        return rv

    async def create_item(self):
        raise NotImplementedError

    async def update_item(self):
        raise NotImplementedError

    async def delete_item(self):
        raise NotImplementedError

    async def item_members(self):
        raise NotImplementedError

    async def item_user_role(self):
        raise NotImplementedError

    async def item_children(self):
        raise NotImplementedError

    async def itme_children_of_type(self):
        raise NotImplementedError

    async def add_item_child(self):
        raise NotImplementedError

    def generate(self, name):
        desc = f'{name} Interest API'
        read_router = APIRouter(prefix=f'/{name}', tags=[desc],
                                dependencies=[Depends(authn_dependency)])
        read_router.add_api_route("", self.items, methods=["GET"],
                                  response_model=List[self._actual.interest_class.tmodel])
        read_router.add_api_route("/{id}", self.item, methods=["GET"],
                                  response_model=self._actual.interest_class.tmodel)
        return [read_router]
