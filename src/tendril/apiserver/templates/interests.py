

from fastapi import APIRouter
from fastapi import Request
from fastapi import Depends

from tendril.authn.users import auth_spec
from tendril.authn.users import AuthUserModel
from tendril.authn.users import authn_dependency

from tendril.authn.users import UserStubTMixin
from tendril.utils.pydantic import TendrilTBaseModel

from .base import ApiRouterGenerator


class InterestRouterGenerator(ApiRouterGenerator):
    def __init__(self, actual):
        super(InterestRouterGenerator, self).__init__()
        self._actual = actual

    async def items(self, request: Request,
                    user: AuthUserModel = auth_spec()):
        return self._actual.items()

    def generate(self, name):
        desc = f'{name} Interest API'
        read_router = APIRouter(prefix=f'/{name}', tags=[desc],
                                # dependencies=[Depends(authn_dependency),
                                #               auth_spec(scopes=['interests:common'])]
                                )
        read_router.add_api_route("/", self.items, methods=["GET"])
        return [read_router]
