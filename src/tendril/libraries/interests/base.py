

import os
import csv
from functools import cached_property
from sqlalchemy.exc import NoResultFound

from tendril.config import AUDIT_PATH
from tendril.utils.fsutils import VersionedOutputFile

from tendril import interests
from tendril.interests import InterestBase

from tendril.db.controllers.interests import get_interest
from tendril.db.controllers.interests import get_interests
from tendril.db.controllers.interests import get_user_memberships
from tendril.apiserver.templates.interests import InterestLibraryRouterGenerator

from tendril.common.interests.memberships import user_memberships
from tendril.common.interests.exceptions import TypeMismatchError
from tendril.common.interests.exceptions import InterestNotFound

from tendril.utils.db import with_db
from tendril.utils import log
logger = log.get_logger(__name__, log.DEFAULT)


class GenericInterestLibrary(object):
    interest_class = InterestBase
    enable_creation_api = True
    enable_activation_api = True
    enable_membership_api = True
    enable_membership_edit_api = True

    _additional_api_generators = []

    @property
    def type_name(self):
        return self.interest_class.model.type_name

    def idents(self):
        return [x.ident for x in self.items()]

    def names(self):
        return [x.name for x in self.items()]

    @with_db
    def items(self, user=None, state=None, include_inherited=False, session=None):
        if not user:
            return [self.interest_class(x) for x in
                    get_interests(type=self.interest_class,
                                  state=state,
                                  session=session)]
        if not include_inherited:
            if state:
                logger.warning("State filtering is not implemented "
                               "for user interests retrieval")
            return [self.interest_class(x.interest) for x in
                    get_user_memberships(user,
                                         interest_type=self.interest_class.model,
                                         session=session)]
        else:
            if state:
                logger.warning("State filtering is not implemented "
                               "for inherited user interests retrieval")
            iids = user_memberships(
                user_id=user,
                interest_types=[self.interest_class.model.type_name],
                include_inherited=include_inherited,
            ).interest_ids()
            return [self.interest_class(get_interest(id=x, session=session))
                    for x in iids]

    @with_db
    def item(self, id=None, name=None, session=None):
        try:
            return self.interest_class(
                get_interest(id=id, name=name, type=self.interest_class, session=session))
        except NoResultFound:
            if not name:
                name = '<unspecified>'
            if not id:
                id = '<unspecified>'
            raise InterestNotFound(type_name=self.type_name, name=name, id=id)

    @with_db
    def add_item(self, item, session=None):
        if item.type != self.interest_class.model.type_name:
            raise TypeMismatchError(item.type, self.interest_class.model.type_name)
        kwargs = {x: getattr(item, x) for x in self.interest_class.additional_creation_fields}
        created = self.interest_class(item.name, **kwargs, must_create=True, session=session)
        if item.descriptive_name:
            created.set_descriptive_name(item.descriptive_name, session=session)
        session.flush()
        return created

    @with_db
    def delete_item(self, id=None, name=None, session=None):
        raise NotImplementedError

    @with_db
    def possible_parents(self, user=None, session=None):
        parent_types = interests.possible_parents[self.type_name]
        if self.type_name in self.interest_class.model.role_spec.allowed_children:
            parent_types.append(self.type_name)
        candidate_memberships = user_memberships(user_id=user, interest_types=parent_types,
                                                 session=session)
        candidate_interests = candidate_memberships.interests(
            filter_criteria=[('check_user_access', {'user': user, 'session': session,
                                                    'action': f'add_child:{self.type_name}'})],
            sort_heuristics=[('type_name', parent_types)])
        return candidate_interests

    @property
    def additional_api_generators(self):
        try:
            mro = list(self.__class__.__mro__)
        except AttributeError:
            print(f"There isn't an __mro__ on {self.__class__}. "
                  f"This is probably a classic class. We don't support this.")
            return self._additional_api_generators
        rv = []
        for cls in mro:
            if hasattr(cls, '_additional_api_generators'):
                for generator in cls._additional_api_generators:
                    if generator not in rv:
                        rv.append(generator)
        return rv

    def api_generators(self):
        rv = [InterestLibraryRouterGenerator(self)]
        for generator in self.additional_api_generators:
            rv.append(generator(self))
        return rv

    # def export_audit(self, name):
    #     auditfname = os.path.join(
    #         AUDIT_PATH, 'projectlib-{0}.audit.csv'.format(name)
    #     )
    #     outf = VersionedOutputFile(auditfname)
    #     outw = csv.writer(outf)
    #     outw.writerow(['ident', 'name', 'folder', 'status',
    #                    'description', 'maintainer'])
    #     for project in self.projects:
    #         outw.writerow(
    #             [project.ident, project.projectname, project.projectfolder, project.status,
    #              project.description, project.maintainer]
    #         )
    #
    #     outf.close()


def load(manager):
    # manager.install_exc_class('ProjectNotFoundError', ProjectNotFoundError)
    pass
