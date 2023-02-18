

import importlib

from tendril.utils.versions import get_namespace_package_names
from tendril.utils import log
logger = log.get_logger(__name__, log.DEBUG)


class InterestLibraryManager(object):
    def __init__(self, prefix):
        self._prefix = prefix
        self._libraries = {}
        self._exc_classes = {}
        self._load_libraries()

    def _load_libraries(self):
        logger.info("Installing interest libraries from {0}".format(self._prefix))
        modules = list(get_namespace_package_names(self._prefix))
        for m_name in modules:
            if m_name == __name__:
                continue
            m = importlib.import_module(m_name)
            m.load(self)
        logger.info("Done installing interest libraries modules from {0}".format(self._prefix))

    def install_library(self, name, library):
        logger.info("Installing interest library '{0}'".format(name))
        self._libraries[name] = library
        
    @property
    def defined_types(self):
        return list(self._libraries.keys())

    def install_exc_class(self, name, exc_class):
        self._exc_classes[name] = exc_class

    def __getattr__(self, item):
        if item in self._libraries.keys():
            return self._libraries[item]
        if item in self._exc_classes.keys():
            return self._exc_classes[item]
        raise AttributeError('No attribute {0} in {1}!'
                             ''.format(item, self.__class__.__name__))

    def export_audits(self):
        for name, library in self._libraries.items():
            library.export_audit(name)
