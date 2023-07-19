

import importlib

from tendril.utils.versions import get_namespace_package_names
from tendril.utils import log
logger = log.get_logger(__name__, log.DEFAULT)


class ApprovalTypesManager(object):
    def __init__(self, prefix):
        self._prefix = prefix
        self._approval_types = {}
        self._find_approval_types()
        self.finalized = False

    def _find_approval_types(self):
        logger.debug("Loading approval types from {0}".format(self._prefix))
        modules = list(get_namespace_package_names(self._prefix))
        for m_name in modules:
            if m_name == __name__:
                continue
            m = importlib.import_module(m_name)
            logger.debug("Loading approval types from {0}".format(m_name))
            self._approval_types.update(m.approval_types)

    def finalize(self):
        self.finalized = True

    @property
    def approval_types(self):
        return self._approval_types
