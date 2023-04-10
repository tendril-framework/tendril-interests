

import importlib
from functools import cached_property
from sqlalchemy.exc import NoResultFound

from tendril.db.controllers.interests import get_interest
from tendril.common.interests.exceptions import InterestNotFound
from tendril.utils.versions import get_namespace_package_names
from tendril.utils import log
logger = log.get_logger(__name__, log.DEBUG)


class InterestLibraryManager(object):
    def __init__(self, prefix):
        self._prefix = prefix
        self._libraries = {}
        self._exc_classes = {}
        self._load_libraries()

    def recognized_idents(self):
        rv = []
        for lib in self._libraries.values():
            rv.extend(lib.idents())
        return rv

    def recognized_names(self):
        rv = {}
        for lname, lib in self._libraries.items():
            rv.update({x: lname for x in lib.names()})
        return rv

    def name_available(self, name):
        i = get_interest(name=name, raise_if_none=False)
        if i is None:
            return True
        else:
            return False

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
    def libraries(self):
        return list(self._libraries.keys())

    @cached_property
    def libraries_by_typename(self):
        return {x.type_name: x for x in self._libraries.values()}

    def install_exc_class(self, name, exc_class):
        self._exc_classes[name] = exc_class

    def find_library(self, id):
        try:
            return self.libraries_by_typename[get_interest(id=id).type]
        except NoResultFound:
            raise InterestNotFound('<unspecified>', '<unspecified>', id=id)

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
