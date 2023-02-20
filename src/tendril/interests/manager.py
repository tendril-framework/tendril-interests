#!/usr/bin/env python
# encoding: utf-8

# Copyright (C) 2019-2023 Chintalagiri Shashank
#
# This file is part of tendril.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
Tendril Interest Manager (:mod:`tendril.interest.manager`)
======================================================
"""


import importlib
import networkx

from tendril.utils.db import with_db
from tendril.utils.versions import get_namespace_package_names

from tendril.db.controllers.interests import register_interest_role

from tendril.utils import log
logger = log.get_logger(__name__, log.DEBUG)


class InterestManager(object):
    def __init__(self, prefix):
        self._prefix = prefix
        self._types = {}
        self._type_codes = {}
        self._type_spec = {}
        self.type_tree = None
        self.possible_parents = {}
        self.possible_paths = {}
        self._roles = {}
        self._docs = []
        self._load_interests()

    def _load_interests(self):
        logger.info("Loading interest types from {0}".format(self._prefix))
        modules = list(get_namespace_package_names(self._prefix))
        for m_name in modules:
            if m_name in [__name__, f"{self._prefix}.db", f"{self._prefix}.template"]:
                continue
            m = importlib.import_module(m_name)
            m.load(self)
        logger.info("Done loading interest types from {0}".format(self._prefix))

    def register_interest_type(self, name, interest, doc=None):
        logger.info(f"Registering <{interest.__name__}> to handle Interest type '{name}'")
        self._types[name] = interest
        self._docs.append((name, doc))

    @with_db
    def register_interest_role(self, name, doc=None, session=None):
        logger.info(f"Registering Interest Role '{name}'")
        self._roles[name] = register_interest_role(name, doc, session=session)

    @property
    def platform_roles(self):
        return list(self._roles.keys())

    @property
    def platform_role_delegations(self):
        # TODO Make this actually generic
        return {"Owner": self._roles.keys(),
                "Administrator": self._roles.keys()}

    @property
    def types(self):
        return self._types

    def _create_tree_edges(self):
        """Creates a graph from the spec dict
        """
        list_of_edges = []
        for item in self._type_spec.keys():
            allowed_children = self._type_spec[item]['allowed_children']
            if allowed_children == ["*"]:
                allowed_children = [itemtype for itemtype in self._type_spec.keys()]
            for child in allowed_children:
                list_of_edges.append((item, child))
        return list_of_edges

    def _generate_tree(self):
        """Takes a list of edges and produces a graph. Allows for circular reference
        """
        interest_tree = networkx.DiGraph()
        interest_tree.add_edges_from(self._create_tree_edges())
        return interest_tree

    def _possible_type_parents(self, type_name):
        paths = networkx.all_simple_paths(self.type_tree, "platform", type_name)
        parents = []
        [parents.append(x[-2])
         for x in sorted(paths, key=lambda x: len(x))
         if x[-2] not in parents]
        return parents

    def _possible_type_paths(self, type_name):
        return list(networkx.all_simple_paths(self.type_tree, "platform", type_name))

    def finalize(self):
        self._type_codes = {
                x.model.type_name: x
                for x in self._types.values()
        }

        self._type_spec = {
            key:
                {'roles': cls.model().roles,
                 'allowed_children': cls.model.allowed_children}
            for key, cls in self._type_codes.items()
        }

        self.type_tree = self._generate_tree()

        self.possible_parents = {x: self._possible_type_parents(x)
                                 for x in self._type_codes}

        self.possible_paths = {x: self._possible_type_paths(x)
                               for x in self._type_codes}

    def __getattr__(self, item):
        if item == '__file__':
            return None
        if item == '__path__':
            return None
        if item == '__len__':
            return len(self._types.keys())
        if item == '__all__':
            return list(self._types.keys()) + \
                   ['doc_render']
        if item == 'type_codes':
            return self._type_codes
        if item == 'type_spec':
            return self._type_spec
        return self._types[item]

    def doc_render(self):
        return self._docs

    def __repr__(self):
        return "<InterestManager>"