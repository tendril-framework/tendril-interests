

from sqlalchemy import Column
from sqlalchemy import String
from sqlalchemy import Integer
from sqlalchemy_json import mutable_json_type
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import backref


from tendril.utils.db import DeclBase
from tendril.utils.db import BaseMixin
from tendril.utils.db import TimestampMixin
from tendril.authn.db.mixins import UserMixin


from tendril.utils import log
logger = log.get_logger(__name__, log.DEFAULT)


class InterestModel(DeclBase, BaseMixin, TimestampMixin):
    type_name = "interest"
    roles = ['Owner', 'Member']
    role_delegations = {'Owner': ['Member']}
    allowed_children = ['interest']

    type = Column(String(50), nullable=False, default=type_name)
    name = Column(String(255), nullable=False)
    info = Column(mutable_json_type(dbtype=JSONB))

    @declared_attr
    def parent_id(cls):
        return Column(Integer, ForeignKey('Interest.id'))

    # @declared_attr
    # def parent(cls):
    #     return relationship("InterestModel", remote_side=[cls.id])

    @declared_attr
    def children(cls):
        return relationship("InterestModel", backref=backref("parent", remote_side=[cls.id]))

    @declared_attr
    def logs(cls):
        return relationship("InterestLogEntryModel", back_populates="interest")

    __mapper_args__ = {
        "polymorphic_identity": type_name,
        "polymorphic_on": type
    }

    # Name actually needs to be unique.
    # Controllers need to be fixed to allow type based variation
    __table_args__ = (
        UniqueConstraint('type', 'name'),
    )


class InterestLogEntryModel(DeclBase, BaseMixin, TimestampMixin, UserMixin):
    action = Column(String(50), nullable=False)
    reference = Column(mutable_json_type(dbtype=JSONB))
    interest_id = Column(Integer(),
                         ForeignKey('Interest.id'), nullable=False)
    interest = relationship("InterestModel", back_populates="logs")


class InterestRoleModel(DeclBase, BaseMixin):
    name = Column(String(50), nullable=False, unique=True)
    description = Column(String(255))


class InterestMembershipModel(DeclBase, BaseMixin, TimestampMixin):
    id = None
    user_id = Column(Integer, ForeignKey('User.id'), primary_key=True)
    interest_id = Column(Integer, ForeignKey('Interest.id'), primary_key=True)
    role_id = Column(Integer, ForeignKey('InterestRole.id'), primary_key=True)
    reference = Column(mutable_json_type(dbtype=JSONB))

    UniqueConstraint('user_id', 'interest_id', 'role_id')
    relationship('User', uselist=False, backref='memberships', lazy='dynamic')
    relationship('InterestModel', uselist=False, backref='memberships', lazy='dynamic')
    relationship('InterestRoleModel', uselist=False, backref='memberships', lazy='dynamic')
