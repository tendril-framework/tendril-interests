

from abc import ABC
from typing import Type
from typing import Dict
from tendril.interests.base import InterestModel
from tendril.authz.roles.interests import InterestRoleSpec
from tendril.common.states import LifecycleStatus


class InterestMixinBase(ABC):
    model: Type[InterestModel]
    role_spec: InterestRoleSpec
    model_instance: InterestModel

    id: int
    type_name: str
    name: str
    descriptive_name: str
    status: LifecycleStatus
    info: Dict
