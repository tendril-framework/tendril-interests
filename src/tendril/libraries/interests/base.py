

import os
import csv
from functools import cached_property

from tendril.config import AUDIT_PATH
from tendril.utils.fsutils import VersionedOutputFile

from tendril.utils.db import with_db

from tendril.db.controllers.interests import get_interest
from tendril.db.controllers.interests import get_interests
from tendril.db.controllers.interests import get_user_memberships
from tendril.interests import InterestBase
from tendril.apiserver.templates.interests import InterestLibraryRouterGenerator

from tendril.common.interests.memberships import user_memberships
from tendril.common.interests.exceptions import TypeMismatchError

from tendril.utils import log
logger = log.get_logger(__name__, log.DEFAULT)


class GenericInterestLibrary(object):
    interest_class = InterestBase

    @property
    def type_name(self):
        return self.interest_class.model.type_name

    def idents(self):
        return [x.ident for x in self.items()]

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
        return self.interest_class(
            get_interest(id=id, name=name, type=self.interest_class, session=session))

    @with_db
    def add_item(self, item, session=None):
        if item.type != self.interest_class.model.type_name:
            raise TypeMismatchError(item.type, self.interest_class.model.type_name)
        item = self.interest_class(item.name, must_create=True, session=session)
        return item

    @with_db
    def delete_item(self, id=None, name=None, session=None):
        raise NotImplementedError

    def api_generator(self):
        return InterestLibraryRouterGenerator(self)

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
