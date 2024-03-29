

import functools
import importlib

from tendril.utils.versions import get_namespace_package_names
from tendril.db.controllers.interests_policies import register_policy_type
from .base import PolicyBase

from tendril.utils import log
logger = log.get_logger(__name__, log.DEBUG)


class PolicyTemplatesManager(object):
    def __init__(self, prefix):
        self._prefix = prefix
        self._templates : dict[str, PolicyBase] = {}
        self._find_policy_templates()
        self.finalized = False

    def _find_policy_templates(self):
        logger.debug("Loading policy templates from {0}".format(self._prefix))
        modules = list(get_namespace_package_names(self._prefix))
        for m_name in modules:
            if m_name == __name__:
                continue
            m = importlib.import_module(m_name)
            if hasattr(m, 'policy_templates'):
                logger.debug("Loading policy templates from {0}".format(m_name))
                self._templates.update({x.name: x for x in m.policy_templates})

    @functools.lru_cache
    def _find_assignable_templates(self):
        rv = {
            'interests': {}
        }
        for name, policy in self._templates.items():
            can_assign_to = policy.can_assign_to()
            for itype in can_assign_to['interest_types']:
                if itype in rv['interests'].keys():
                    rv['interests'][itype].add(policy)
                else:
                    rv['interests'][itype] = {policy}
        return rv

    def finalize(self):
        for policy_type in self._templates.values():
            logger.debug(f"Registering Policy Type '{policy_type.name}'")
            # TODO This prevents manhole from starting.
            register_policy_type(policy_type)
        self.finalized = True

    @property
    def templates(self):
        return self._templates

    def assignable_templates(self, interest_type=None):
        if interest_type:
            try:
                return self._find_assignable_templates()['interests'][interest_type]
            except KeyError:
                return set()
        return self._find_assignable_templates()
