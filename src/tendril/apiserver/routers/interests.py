

from fastapi import APIRouter
from fastapi import Depends

from tendril.authn.users import auth_spec
from tendril.authn.users import authn_dependency
from tendril.authn.users import AuthUserModel

from tendril.libraries import interests
from tendril.interests import type_spec
from tendril.datasets.interests.memberships import user_memberships
from tendril.datasets.interests.memberships import UserMembershipsTModel


interests_router = APIRouter(prefix='/interests',
                             tags=["Common Interests API"],
                             dependencies=[Depends(authn_dependency),
                                           auth_spec(scopes=['interests:common'])]
                             )


@interests_router.get("/libraries")
async def get_interest_libraries():
    return {'interest_libraries': interests.defined_types}


@interests_router.get("/types")
async def get_interest_types():
    return {'interest_types': type_spec}


def get_interest_stub(interest):
    return {
        'type_name': interest.type_name,
        'name': interest.name,
        'id': interest.id,
    }


@interests_router.get("/memberships", response_model=UserMembershipsTModel)
async def get_user_memberships(user: AuthUserModel = auth_spec(),
                               include_delegated: bool = False,
                               include_inherited: bool = False):
    return user_memberships(user,
                            include_delegated=include_delegated,
                            include_inherited=include_inherited)


def _generate_routers():
    interest_routers = []
    for itype in interests.defined_types:
        ilib = getattr(interests, itype)
        generated_routers = ilib.api_generator().generate(f'{itype}')
        interest_routers.extend(generated_routers)
    return interest_routers


routers = [
    interests_router
] + _generate_routers()
