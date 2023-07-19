

from typing import List
from typing import NamedTuple
from pydantic import create_model_from_namedtuple
from tendril.common.states import LifecycleStatus


class ApprovalRequirement(NamedTuple):
    name: str
    role: str
    spread: int  # -1 : All, 0: No Minimum
    states: List[LifecycleStatus]
    context_type: str


ApprovalRequirementTModel = create_model_from_namedtuple(ApprovalRequirement)
