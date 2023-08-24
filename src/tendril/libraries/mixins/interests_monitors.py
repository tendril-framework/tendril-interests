

from tendril.apiserver.templates.interests_monitors import InterestMonitorsRouterGenerator


class MonitorsLibraryMixin(object):
    _additional_api_generators = [InterestMonitorsRouterGenerator]
