

from fastapi import APIRouter
from fastapi import Depends

from tendril.authn.users import auth_spec
from tendril.authn.users import authn_dependency
from tendril.authn.users import AuthUserModel

from tendril.libraries import interests
from tendril.interests import type_spec
from tendril.common.interests.memberships import user_memberships
from tendril.common.interests.memberships import UserMembershipsTModel
from tendril.config import INTERESTS_API_ENABLED

from tendril.utils import log
logger = log.get_logger(__name__, log.DEFAULT)


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
                            include_inherited=include_inherited).render()


@interests_router.get("/name_available", response_model=bool)
async def check_name_available(name: str):
    return interests.name_available(name)


def _generate_routers():
    interest_routers = []
    for libname in interests.libraries:
        ilib = getattr(interests, libname)
        api_generators = ilib.api_generators()
        for generator in api_generators:
            generated_routers = generator.generate(f'{libname}')
            interest_routers.extend(generated_routers)
    return interest_routers


if INTERESTS_API_ENABLED:
    routers = [
        interests_router
    ] + _generate_routers()
else:
    logger.info("Not creating Interest API routers.")
    routers = []
