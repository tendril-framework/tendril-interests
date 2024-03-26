

from tendril.apiserver.templates.interests_policies import InterestPolicyRouterGenerator


class PolicyLibraryMixin(object):
    _additional_api_generators = [InterestPolicyRouterGenerator]
