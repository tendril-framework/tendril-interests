

from fastapi import APIRouter
from fastapi import Depends

from tendril.authn.users import auth_spec
from tendril.authn.users import authn_dependency

from tendril.libraries import interests
from tendril.interests import type_spec


interests_router = APIRouter(prefix='/interests',
                             tags=["Common Interests API"],
                             # dependencies=[Depends(authn_dependency),
                             #               auth_spec(scopes=['interests:common'])]
                             )


@interests_router.get("/libraries")
async def get_interest_libraries():
    return {'interest_libraries': interests.defined_types}


@interests_router.get("/types")
async def get_interest_types():
    return {'interest_types': type_spec}


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
