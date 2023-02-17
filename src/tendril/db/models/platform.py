from functools import cached_property
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import ForeignKey
from tendril.db.models.interests import InterestModel

from tendril.utils import log
logger = log.get_logger(__name__, log.DEFAULT)


class PlatformModel(InterestModel):
    type_name = "platform"
    allowed_children = ['*']

    id = Column(Integer, ForeignKey("Interest.id"), primary_key=True)

    __mapper_args__ = {
        "polymorphic_identity": type_name,
    }

    @cached_property
    def roles(self):
        from tendril import interests
        return interests.platform_roles

    @cached_property
    def role_delegations(self):
        from tendril import interests
        return interests.platform_role_delegations
