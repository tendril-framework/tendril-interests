

from tendril.apiserver.templates.interests_graphs import InterestGraphsRouterGenerator


class GraphsLibraryMixin(object):
    _additional_api_generators = [InterestGraphsRouterGenerator]
