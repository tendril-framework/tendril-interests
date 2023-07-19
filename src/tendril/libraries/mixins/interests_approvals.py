

from tendril.apiserver.templates.interests_approvals import InterestApprovalRouterGenerator
from tendril.apiserver.templates.interests_approvals import InterestApprovalContextRouterGenerator


class ApprovalsLibraryMixin(object):
    _additional_api_generators = [InterestApprovalRouterGenerator]


class ApprovalContextLibraryMixin(object):
    _additional_api_generators = [InterestApprovalContextRouterGenerator]
