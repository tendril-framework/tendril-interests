

import os
import csv
from functools import cached_property

from tendril.config import AUDIT_PATH
from tendril.utils.fsutils import VersionedOutputFile

from tendril.interests import InterestBase


class GenericInterestLibrary(object):
    _interest_class = InterestBase

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
