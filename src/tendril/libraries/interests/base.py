

import os
import csv
from functools import cached_property

from tendril.config import AUDIT_PATH
from tendril.utils.fsutils import VersionedOutputFile

from tendril.utils.db import with_db
from tendril.db.controllers.interests import get_interests
from tendril.db.controllers.interests import get_interest
from tendril.interests import InterestBase
from tendril.apiserver.templates.interests import InterestRouterGenerator


class GenericInterestLibrary(object):
    _interest_class = InterestBase

    @property
    def type_name(self):
        return self._interest_class.model.type_name

    def idents(self):
        pass

    @with_db
    def items(self, session=None):
        return [self._interest_class(x) for x in
                get_interests(type=self._interest_class.model, session=session)]

    @with_db
    def item(self, id=None, name=None, session=None):
        return get_interest(id=id, name=name, type=self._interest_class, session=session)

    @with_db
    def add_item(self, item, session=None):
        pass

    @with_db
    def delete_item(self, id=None, name=None, session=None):
        raise NotImplementedError

    def api_generator(self):
        return InterestRouterGenerator(self)

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
