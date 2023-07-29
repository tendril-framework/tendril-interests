

from abc import ABC
from typing import Type
from tendril.interests.base import InterestModel
from tendril.authz.roles.interests import InterestRoleSpec


class InterestMixinBase(ABC):
    model: Type[InterestModel]
    role_spec: InterestRoleSpec
    model_instance: InterestModel

