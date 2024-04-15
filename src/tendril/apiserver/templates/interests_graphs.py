

from inflection import singularize
from inflection import titleize

from fastapi import APIRouter
from fastapi import Depends

from tendril.authn.users import auth_spec
from tendril.authn.users import AuthUserModel
from tendril.authn.users import authn_dependency

from tendril.apiserver.templates.base import ApiRouterGenerator
from tendril.utils.db import get_session


class InterestGraphsRouterGenerator(ApiRouterGenerator):
    def __init__(self, actual):
        super(InterestGraphsRouterGenerator, self).__init__()
        self._actual = actual

    async def get_graphs(self, id: int,
                               user: AuthUserModel = auth_spec()):
        with get_session() as session:
            item = self._actual.item(id, session=session)
            response = await item.graphs()
            return response

    def generate(self, name):
        desc = f'Embedded Graphs API for {titleize(singularize(name))} Interests'
        prefix = self._actual.interest_class.model.role_spec.prefix
        router = APIRouter(prefix=f'/{name}', tags=[desc],
                           dependencies=[Depends(authn_dependency)])

        router.add_api_route("/{id}/graphs", self.get_graphs, methods=["GET"],
                             # response_model=List[self._actual.interest_class.export_tmodel_unified()],
                             # response_model_exclude_none=True,
                             dependencies=[auth_spec(scopes=[f'{prefix}:read'])],)

        return [router]
