

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


class GenericInterestLibrary(object):
    interest_class = InterestBase

    @property
    def type_name(self):
        return self.interest_class.model.type_name

    def idents(self):
        return [x.ident for x in self.items()]

    @with_db
    def items(self, user=None, session=None):
        if not user:
            return [self.interest_class(x) for x in
                    get_interests(type=self.interest_class, session=session)]
        else:
            return [self.interest_class(x.interest) for x in
                    get_user_memberships(user,
                                         interest_type=self.interest_class.model,
                                         session=session)]

    @with_db
    def item(self, id=None, name=None, session=None):
        return self.interest_class(
            get_interest(id=id, name=name, type=self.interest_class, session=session))

    @with_db
    def add_item(self, item, session=None):
        pass

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
