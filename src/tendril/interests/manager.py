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


import copy
import importlib
import networkx

from tendril.utils.db import with_db
from tendril.utils.db import register_for_create
from tendril.utils.versions import get_namespace_package_names

from tendril.db.controllers.interests import register_interest_role
from tendril.db.controllers.interests_approvals import register_approval_type
from tendril.authz.approvals.interests import ApprovalRequirement

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
        self.possible_ancestors = {}
        self._approval_types = {}
        self.all_actions = {}
        self._roles = {}
        self._docs = []
        self._load_interests()

    def _load_interests(self):
        logger.info("Loading interest types from {0}".format(self._prefix))
        modules = list(get_namespace_package_names(self._prefix))
        for m_name in modules:
            if m_name in [__name__, f"{self._prefix}.db",
                          f"{self._prefix}.template",
                          f'{self._prefix}.mixins']:
                continue
            m = importlib.import_module(m_name)
            m.load(self)
        logger.info("Done loading interest types from {0}".format(self._prefix))

    def register_interest_type(self, name, interest, doc=None):
        logger.info(f"Registering <{interest.__name__}> to handle Interest type '{name}'")
        self._types[name] = interest
        self._docs.append((name, doc))

    def register_interest_role(self, name, doc=None):
        logger.info(f"Registering Interest Role '{name}'")
        self._roles[name] = doc

    @with_db
    def commit_interest_roles(self, session=None):
        for name, doc in self._roles.items():
            register_interest_role(name, doc, session=session)

    def register_approval_type(self, approval_type: ApprovalRequirement):
        logger.info(f"Registering Interest Approval Type '{approval_type.name}'")
        if approval_type.name in self._approval_types.keys():
            pass
        self._approval_types[approval_type.name] = approval_type

    def extract_approval_types(self):
        for interest_type_name, interest_type in self._types.items():
            if hasattr(interest_type, 'approval_spec'):
                for approval_type in interest_type.model.approval_spec.recognized_approvals:
                    self.register_approval_type(approval_type)

    @with_db
    def commit_approval_types(self, session=None):
        for name, approval_type in self._approval_types.items():
            register_approval_type(approval_type, session=session)

    @property
    def types(self):
        return self._types

    def _create_tree_edges(self):
        """Creates a graph from the spec dict
        """
        list_of_edges = []
        for item in self._type_spec.keys():
            allowed_children = copy.copy(self._type_spec[item]['allowed_children'])
            if allowed_children == ["*"]:
                allowed_children = [itemtype for itemtype in self._type_spec.keys()]
            while item in allowed_children:
                allowed_children.remove(item)
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
        paths = networkx.all_simple_paths(self.type_tree, self._tree_root(), type_name)
        parents = []
        [parents.append(x[-2])
         for x in sorted(paths, key=lambda x: len(x), reverse=True)
         if x[-2] not in parents]
        if type_name in self._type_spec[type_name]['allowed_children']:
            parents.append(type_name)
        return parents

    def _possible_type_paths(self, type_name):
        return list(networkx.all_simple_paths(self.type_tree, self._tree_root(), type_name))

    def _possible_type_ancestors(self, type_name):
        return networkx.ancestors(self.type_tree, type_name)

    def _tree_root(self):
        return list(networkx.topological_sort(self.type_tree))[0]

    def finalize(self):
        self._type_codes = {
                x.model.type_name: x
                for x in self._types.values()
        }

        self._type_spec = {
            key:
                {'roles': cls.model().role_spec.roles,
                 'allowed_children': cls.model.role_spec.allowed_children}
            for key, cls in self._type_codes.items()
        }

        if len(self._type_spec.keys()) > 1:
            self.type_tree = self._generate_tree()

            self.possible_parents = {x: self._possible_type_parents(x)
                                     for x in self._type_codes}

            self.possible_paths = {x: self._possible_type_paths(x)
                                   for x in self._type_codes}

            self.possible_ancestors = {x: self._possible_type_ancestors(x)
                                       for x in self._type_codes}

        [self.all_actions.update(
            {f'{t.model.type_name}:{a}': r
             for a, r in t.model.role_spec.actions.items()})
            for t in self._types.values()]

        self.extract_approval_types()

        register_for_create(self.commit_interest_roles)
        register_for_create(self.commit_approval_types)

    def __getattr__(self, item):
        if item == '__file__':
            return None
        if item == '__path__':
            return None
        if item == '__len__':
            return len(self._types.keys())
        if item == '__spec__':
            return None
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
