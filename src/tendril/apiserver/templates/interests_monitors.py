

from pprint import pprint
from inflection import singularize
from inflection import titleize

from fastapi import APIRouter
from fastapi import Request
from fastapi import Depends

from tendril.authn.users import auth_spec
from tendril.authn.users import AuthUserModel
from tendril.authn.users import authn_dependency

from tendril.apiserver.templates.base import ApiRouterGenerator
from tendril.utils.db import get_session

from tendril.interests.mixins.monitors import MonitorsQueryTModel


class InterestMonitorsRouterGenerator(ApiRouterGenerator):
    def __init__(self, actual):
        super(InterestMonitorsRouterGenerator, self).__init__()
        self._actual = actual

    async def get_monitors_specs(self, id: int,
                                 user: AuthUserModel = auth_spec()):
        with get_session() as session:
            item = self._actual.item(id, session=session)
            return item.monitors_spec_render()

    async def get_monitors_current(self, id: int,
                                   user: AuthUserModel = auth_spec()):
        with get_session() as session:
            item = self._actual.item(id, session=session)
            return item.monitors_export()

    async def get_monitors_historical(self, id:int,
                                      query: MonitorsQueryTModel,
                                      user:AuthUserModel = auth_spec()):
        with get_session() as session:
            item = self._actual.item(id, session=session)
            return await item.monitors_export_historical(query)


    def generate(self, name):
        desc = f'Monitors API for {titleize(singularize(name))} Interests'
        prefix = self._actual.interest_class.model.role_spec.prefix
        router = APIRouter(prefix=f'/{name}', tags=[desc],
                           dependencies=[Depends(authn_dependency)])

        router.add_api_route("/{id}/monitors/spec", self.get_monitors_specs, methods=["GET"],
                             # response_model=List[self._actual.interest_class.export_tmodel_unified()],
                             # response_model_exclude_none=True,
                             dependencies=[auth_spec(scopes=[f'{prefix}:read'])],)

        router.add_api_route("/{id}/monitors/current", self.get_monitors_current, methods=["GET"],
                             # response_model=List[self._actual.interest_class.export_tmodel_unified()],
                             response_model_exclude_none=True,
                             dependencies=[auth_spec(scopes=[f'{prefix}:read'])], )

        router.add_api_route("/{id}/monitors/historical", self.get_monitors_historical, methods=["POST"],
                             # response_model=List[self._actual.interest_class.export_tmodel_unified()],
                             response_model_exclude_none=True,
                             dependencies=[auth_spec(scopes=[f'{prefix}:read'])], )

        return [router]