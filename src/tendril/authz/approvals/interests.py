

from typing import List
from typing import NamedTuple

from functools import cached_property

from tendril.common.interests.approvals import ApprovalRequirement


class InterestApprovalSpec(object):
    _required_approvals: List[ApprovalRequirement] = []
    _optional_approvals: List[ApprovalRequirement] = []

    def _extract_from_hierarchy(self, prop_name):
        try:
            mro = list(self.__class__.__mro__)
        except AttributeError:
            print(f"There isn't an __mro__ on {self.__class__}. "
                  f"This is probably a classic class. We don't support this.")
            return self._required_approvals
        rv = []
        names = set()
        for cls in mro:
            cls: InterestApprovalSpec
            for required_approval in getattr(cls, prop_name, []):
                if required_approval.name not in names:
                    names.add(required_approval.name)
                    rv.append(required_approval)
                else:
                    # TODO Implement a merge instead
                    pass
                    # raise ValueError(f"Name collision on approval {required_approval} "
                    #                  f"from {prop_name} for {self.__class__}")
        return rv

    @cached_property
    def required_approvals(self):
        return self._extract_from_hierarchy('_required_approvals')

    @cached_property
    def optional_approvals(self):
        return self._extract_from_hierarchy('_optional_approvals')

    @cached_property
    def recognized_approvals(self):
        return self.required_approvals + self.optional_approvals


approval_types = {}
