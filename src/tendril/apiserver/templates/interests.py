

from typing import List

from fastapi import APIRouter
from fastapi import Request
from fastapi import Depends

from tendril.authn.users import auth_spec
from tendril.authn.users import AuthUserModel
from tendril.authn.users import authn_dependency

from tendril.authn.users import UserStubTMixin
from tendril.utils.pydantic import TendrilTBaseModel

from tendril.utils.db import get_session

from .base import ApiRouterGenerator


class InterestRouterGenerator(ApiRouterGenerator):
    def __init__(self, actual):
        super(InterestRouterGenerator, self).__init__()
        self._actual = actual

    async def items(self, request: Request,
                    # user: AuthUserModel = auth_spec(),
                    ):
        with get_session() as session:
            rv = [x.export() for x in self._actual.items(session=session)]
        return rv

    async def item(self, request: Request, id: int,
                   # user: AuthUserModel = auth_spec()
                   ):
        with get_session() as session:
            rv = self._actual.item(id=id, session=session).export()
        return rv

    def generate(self, name):
        desc = f'{name} Interest API'
        read_router = APIRouter(prefix=f'/{name}', tags=[desc],
                                # dependencies=[Depends(authn_dependency),
                                #               auth_spec(scopes=['interests:common'])]
                                )
        read_router.add_api_route("", self.items, methods=["GET"],
                                  response_model=List[self._actual.interest_class.tmodel])
        read_router.add_api_route("/{id}", self.item, methods=["GET"],
                                  response_model=self._actual.interest_class.tmodel)
        return [read_router]
