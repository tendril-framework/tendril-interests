

from typing import List
from typing import Dict
from typing import Union
from typing import Optional
from inflection import singularize
from inflection import titleize

from fastapi import APIRouter
from fastapi import Request
from fastapi import Depends
from fastapi import BackgroundTasks
from fastapi.responses import JSONResponse

from tendril.authn.users import auth_spec
from tendril.authn.users import AuthUserModel
from tendril.authn.users import authn_dependency

from tendril.authn.pydantic import UserReferenceTModel
from tendril.authz.roles.interests import MembershipInfoTModel
from tendril.common.states import LifecycleStatus
from tendril.utils.db import get_session
from tendril.common.interests.representations import ExportLevel

from .base import ApiRouterGenerator
from tendril.utils import log
logger = log.get_logger(__name__)


class InterestLibraryRouterGenerator(ApiRouterGenerator):
    def __init__(self, actual):
        super(InterestLibraryRouterGenerator, self).__init__()
        self._actual = actual
        self._item_tmodel = None

    async def items(self, request: Request,
                    user: AuthUserModel = auth_spec(),
                    export_level: Optional[ExportLevel] = ExportLevel.STUB,
                    include_inherited: bool = True):
        """
        Get a list of all items in this library.

        This endpoint enforces interest access control, and returns the
        requested information only if the logged-in user (identified by
        the access token) has access to it.

        Additional controls determine what further information is to be
        included in the response. Note that these additional pieces of
        information may result in performance penalties, so they should
        only be requested when needed.

         - **user :** The requesting user, identified by the access token, whose list of
                      interests is to be provided.
         - **include_inherited : ** Include interests in which the user's access inherited.
        """
        with get_session() as session:
            rv = [x.export(auth_user=user, session=session,
                           export_level=export_level)
                  for x in self._actual.items(user=user, session=session,
                                              include_inherited=include_inherited,)]
        return rv

    async def new_items(self, request: Request,
                        user: AuthUserModel = auth_spec()):
        """
        Get a list of all new items in this library.

        This endpoint does not enforce interest access control, and
        returns all available NEW items.

        Additional controls determine what further information is to be
        included in the response. Note that these additional pieces of
        information may result in performance penalties, so they should
        only be requested when needed.

         - **user :** The requesting user.
         - **include_roles :** Include the user's roles in the response.
         - **include_permissions :** Include the user's permissions in the response.
        """
        with get_session() as session:
            rv = [x.export(session=session, export_level=ExportLevel.STUB)
                  for x in self._actual.items(state=LifecycleStatus.NEW,
                                              session=session)]
        return rv

    async def item(self, request: Request, id: int,
                   user: AuthUserModel = auth_spec(),
                   export_level: Optional[ExportLevel] = ExportLevel.NORMAL):
        """
        Get a specific item from this library.

        This endpoint enforces interest access control, and returns the
        requested information only if the logged-in user (identified by
        the access token) has access to it.

        Additional controls determine what further information is to be
        included in the response. Note that these additional pieces of
        information may result in performance penalties, so they should
        only be requested when needed.

          - **id :** The id of the interest to retrieve
          - **user :** The requesting user, identified by the access token.
        """
        with get_session() as session:
            rv = self._actual.item(id=id, session=session).\
                export(auth_user=user, session=session, export_level=export_level)
        return rv

    async def find_possible_parents(self, request: Request,
                                    user: AuthUserModel = auth_spec(),
                                    export_level: Optional[ExportLevel] = ExportLevel.STUB.value):
        """
        Get possible parents for new items in this library.

        All user memberships in possible parents for this library's interest
        type which allow creation of a child of this type are returned.

        - **user :* The requesting user, identified by the access token.
        """
        with get_session() as session:
            result = self._actual.possible_parents(user=user, session=session)
            return [x.export(auth_user=user, session=session,
                             export_level=export_level) for x in result]

    def _inject_create_model(self, ep):
        return self._inject_model(ep, param='item', model=self._actual.interest_class.tmodel_create)

    def create_item(self, item,
                    user: AuthUserModel = auth_spec(),
                    export_level: Optional[ExportLevel] = ExportLevel.STUB.value):
        """
        Create an Interest.

        This endpoint does not enforce interest access controls, and allows
        any user with the create scope for this interest type to create an
        interest.

        An interest created here is in the NEW state, and needs to be
        prepared using the other interest manipulation endpoints before it
        can be activated. An interest remaining in the NEW state for more
        that a certain period of time may be nuked by backend maintenance
        processes in the future.

        Information regarding the created interest is returned by this
        endpoint, which can be used for further processing.

         - **item :** Details of the interest to be created
         - **user :** The requesting user, identified by the access token.

        """
        with get_session() as session:
            item = self._actual.add_item(item, session=session)
            rv = item.export(export_level=export_level, session=session)
        return rv

    def _inject_edit_model(self, ep):
        return self._inject_model(ep, param='changes', model=self._actual.interest_class.tmodel_edit)

    async def edit_item(self, id:int, changes,
                        user: AuthUserModel = auth_spec(),
                        export_level: Optional[ExportLevel] = ExportLevel.NORMAL.value):
        with get_session() as session:
            item = self._actual.item(id, session=session)
            result = item.edit(changes, auth_user=user, session=session)
            rv = item.export(export_level=export_level, auth_user=user, session=session)
        return rv

    async def activate_item(self, request: Request, id: int,
                            background_tasks: BackgroundTasks,
                            user: AuthUserModel = auth_spec()):
        """
        Activate a specified interest.

        This endpoint enforces interest access control, and executes only if
        the logged-in user (identified by the access token) has the necessary
        permissions.

        Non-activated interests disallow most operations to be carried out
        on them. Usually, only the operations needed to prepare the interest
        for activation will be allowed.

        Activation requires an interest be configured with a miminal set of
        requirements. The requirements may vary between the interest classes,
        but the following are the most common:

          - All interests other than 'platform' need to be linked to a parent
            before activation.
          - All interests require there be atleast one user with the apex role.
            This user can be inherited as well, so linking it to a parent is
            generally enough as long as role inheritence is enabled.
          - Only interests in the NEW or ACTIVE states can be activated using
            this interface. An alternate interface should be implemented to
            manage the other states.

        The endpoint parameters are:

         - **id :** The id of the interest to be activated
         - **user :** The requesting user, identified by the access token.
        """
        with get_session() as session:
            item = self._actual.item(id, session=session)
            result, msg = item.activate(background_tasks=background_tasks,
                                        auth_user=user, session=session)
        if result:
            status_code = 200
        else:
            status_code = 406
        return JSONResponse(
            status_code=status_code,
            content={'message': msg}
        )

    async def deactivate_item(self, request: Request, id: int,
                              user: AuthUserModel = auth_spec()):
        """
        Deactivate a specified interest.

        This endpoint enforces interest access control, and executes only if
        the logged-in user (identified by the access token) has the necessary
        permissions.

        Activated interests disallow most modifying operations to be carried out
        on them. Usually, the operations needed to modify the interest in a
        significant was is only allowed when the interest is new.

        Note that such changes may also (independent of this endpoint) rescind
        approvals granted to the interest in the past.

        The endpoint parameters are:

         - **id :** The id of the interest to be activated
         - **user :** The requesting user, identified by the access token.
        """
        with get_session() as session:
            item = self._actual.item(id, session=session)
            msg = item.deactivate(auth_user=user, session=session)
        return JSONResponse(
            status_code=200,
            content={'message': msg}
        )


    async def item_members(self, request: Request, id: int,
                           user: AuthUserModel = auth_spec(),
                           include_effective: bool=False,
                           include_inherited: bool=True):
        """
        Get all users with privileges for a specified interest.

        This endpoint enforces interest access control, and returns the
        requested information only if the logged-in user (identified by
        the access token) has access to it.

        Additional controls determine which users are to be included in
        the response. Effective memberships include roles that are granted
        to a user because (generally) they hold a superior role. Inherited
        memberships are roles granted to a user because they hold the same
        membership in some parent Interest.

        Note that effective interests (role delegations) are only applied
        horizontally within an interest, while inherited memberships are
        only applied veritically across the interest hierarchy. Note that
        inherited memberships are often likely also effective memberships,
        though the response here will not reflect that since the delegation
        happens at the parent interest, where the user's original access
        level is granted.

        Typcically, by disabling both types of secondary users, you would
        retrieve the members defined local to the interest. By enabling
        both, you would get the list of users with access to the interest.
        Enabling only one or the other is not likely to provide meaningful
        information.

        Note that including inherited memberships is likely to incur a
        moderate performance penalty.

         - **id :** The id of the interest whose memberships are needed
         - **user :** The requesting user, identified by the access token.
         - **include_effective :**  Whether effective memberships are to be included
         - **include_inherited :** Whether inherited memberships are to be included
        """
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
        """
        Get all users with a specified role for a specified interest.

        This endpoint enforces interest access control, and returns the
        requested information only if the logged-in user (identified by
        the access token) has access to it.

        Additional controls determine which users are to be included in
        the response. See item_members() for a more detailed description.

         - **id :** The id of the interest whose memberships are needed
         - **role :** The role whose members are needed
         - **user :** The requesting user, identified by the access token.
         - **include_effective :**  Whether effective memberships are to be included
         - **include_inherited :** Whether inherited memberships are to be included
        """
        with get_session() as session:
            item = self._actual.item(id, session=session)
            rv = item.memberships(auth_user=user, role=role, session=session,
                                  include_effective=include_effective,
                                  include_inherited=include_inherited)
        return rv

    async def item_grant_role(self, request: Request, id: int, role: str,
                              to_user: UserReferenceTModel,
                              user: AuthUserModel = auth_spec()):
        with get_session() as session:
            item = self._actual.item(id, session=session)
            item.assign_role(role=role, user=to_user, auth_user=user, session=session)
            # TODO This response is probably much heavier than it should be
            rv = item.export(auth_user=to_user, session=session, export_level=ExportLevel.DETAILED)
        return rv

    async def item_parents(self, request: Request, id: int,
                           user: AuthUserModel = auth_spec(),
                           export_level: Optional[ExportLevel] = ExportLevel.STUB):
        kwargs = {}
        with get_session() as session:
            item = self._actual.item(id, session=session)
            rv = [x.export(export_level=export_level, auth_user=user, session=session)
                  for x in item.parents(auth_user=user, **kwargs, session=session)]
        return rv

    def item_children(self, request: Request, id: int,
                      user: AuthUserModel = auth_spec(),
                      child_type: str = None,
                      export_level: Optional[ExportLevel] = ExportLevel.STUB):
        kwargs = {}
        rv = []
        if child_type:
            kwargs['child_type'] = child_type
        with get_session() as session:
            item = self._actual.item(id, session=session)
            rv = [x.export(auth_user=user, session=session)
                  for x in item.children(auth_user=user, **kwargs, session=session)]
        return rv

    def item_add_child(self, request: Request, id: int,
                       child_id: int, limited: bool = False,
                       user: AuthUserModel = auth_spec()):
        with get_session() as session:
            item = self._actual.item(id, session=session)
            return item.add_child(child_id, limited=limited,
                                  auth_user=user, session=session)

    async def delete_item(self):
        raise NotImplementedError

    def generate(self, name):
        desc = f'{titleize(singularize(name))} Interest API'
        prefix = self._actual.interest_class.model.role_spec.prefix
        from tendril import interests
        parent_models = [interests.type_codes[x].export_tmodel_stub() for x in interests.possible_parents[prefix]]

        router = APIRouter(prefix=f'/{name}', tags=[desc],
                           dependencies=[Depends(authn_dependency)])

        router.add_api_route("", self.items, methods=["GET"],
                             response_model=List[self._actual.interest_class.export_tmodel_unified()],
                             response_model_exclude_none=True,
                             dependencies=[auth_spec(scopes=[f'{prefix}:read'])],)

        if self._actual.enable_creation_api:
            router.add_api_route("/create", self._inject_create_model(self.create_item), methods=['PUT'],
                                 response_model=self._actual.interest_class.export_tmodel_unified(),
                                 response_model_exclude_none=True,
                                 dependencies=[auth_spec(scopes=[f'{prefix}:create'])], )

        if self._actual.enable_activation_api:
            router.add_api_route("/new", self.new_items, methods=["GET"],
                                 response_model=List[self._actual.interest_class.export_tmodel_unified()],
                                 response_model_exclude_none=True,
                                 dependencies=[auth_spec(scopes=[f'{prefix}:create'])], )

            if len(parent_models):
                router.add_api_route("/possible_parents", self.find_possible_parents, methods=['GET'],
                                     response_model=List[Union[tuple(parent_models)]],
                                     response_model_exclude_none=True,
                                     dependencies=[auth_spec(scopes=[f'{prefix}:create'])])

            router.add_api_route("/{id:int}/activate", self.activate_item, methods=['POST'],
                                 dependencies=[auth_spec(scopes=[f'{prefix}:write'])])
            router.add_api_route("/{id:int}/deactivate", self.deactivate_item, methods=['POST'],
                                 dependencies=[auth_spec(scopes=[f'{prefix}:write'])])

        router.add_api_route("/{id:int}", self.item, methods=["GET"],
                             response_model=self._actual.interest_class.export_tmodel_unified(),
                             response_model_exclude_none=True,
                             dependencies=[auth_spec(scopes=[f'{prefix}:read'])])

        router.add_api_route("/{id:int}/edit", self._inject_edit_model(self.edit_item),
                             methods=["POST"],
                             response_model=self._actual.interest_class.export_tmodel_unified(),
                             response_model_exclude_none=True,
                             dependencies=[auth_spec(scopes=[f'{prefix}:read'])])

        if self._actual.enable_membership_api:
            router.add_api_route("/{id:int}/members", self.item_members, methods=["GET"],
                                 response_model=Dict[str, List[MembershipInfoTModel]],
                                 response_model_exclude_none=True,
                                 dependencies=[auth_spec(scopes=[f'{prefix}:read'])], )
            router.add_api_route("/{id:int}/members/{role}", self.item_role_members, methods=["GET"],
                                 response_model=List[MembershipInfoTModel],
                                 response_model_exclude_none=True,
                                 dependencies=[auth_spec(scopes=[f'{prefix}:read'])], )

        if self._actual.enable_membership_edit_api:
            router.add_api_route("/{id:int}/members/{role}/add", self.item_grant_role, methods=["POST"],
                                 response_model=self._actual.interest_class.export_tmodel_unified(),
                                 response_model_exclude_none=True,
                                 dependencies=[auth_spec(scopes=[f'{prefix}:write'])], )

        if len(parent_models):
            router.add_api_route("/{id:int}/parents", self.item_parents, methods=["GET"],
                                 response_model=List[Union[tuple(parent_models)]],
                                 response_model_exclude_none=True,
                                 dependencies=[auth_spec(scopes=[f'{prefix}:read'])],)

        ac = self._actual.interest_class.model.role_spec.allowed_children
        if '*' in ac:
            ac = interests.type_codes.keys()
        child_models = [interests.type_codes[x].export_tmodel_unified() for x in ac]
        if len(child_models):
            router.add_api_route("/{id:int}/children", self.item_children, methods=["GET"],
                                 response_model=List[Union[tuple(child_models)]],
                                 response_model_exclude_none=True,
                                 dependencies=[auth_spec(scopes=[f'{prefix}:read'])])
            router.add_api_route("/{id:int}/children/add", self.item_add_child, methods=["POST"],
                                 dependencies=[auth_spec(scopes=[f'{prefix}:write'])])
        return [router]
