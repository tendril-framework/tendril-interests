

from sqlalchemy import Enum
from sqlalchemy import Column
from sqlalchemy import String
from sqlalchemy import Boolean
from sqlalchemy import Integer
from sqlalchemy import ForeignKey
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.orm import mapped_column
from sqlalchemy_json import mutable_json_type
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.dialects.postgresql import JSONB

from tendril.authz.roles.interests import InterestRoleSpec

from tendril.common.states import LifecycleStatus

from tendril.utils.db import DeclBase
from tendril.utils.db import BaseMixin
from tendril.utils.db import TimestampMixin
from tendril.authn.db.mixins import UserMixin

from tendril.utils import log
logger = log.get_logger(__name__, log.DEFAULT)


class InterestAssociationModel(DeclBase, BaseMixin, TimestampMixin):
    id = None
    parent_id = mapped_column(ForeignKey("Interest.id"), primary_key=True)
    child_id = mapped_column(ForeignKey("Interest.id"), primary_key=True)
    limited = Column(Boolean, default=False, nullable=False)


class InterestModel(DeclBase, BaseMixin, TimestampMixin):
    type_name = "interest"
    role_spec = InterestRoleSpec()

    type = Column(String(50), nullable=False, default=type_name)
    name = Column(String(255), nullable=False)
    descriptive_name = Column(String(255), nullable=True)

    status = Column(Enum(LifecycleStatus), nullable=False,
                    default=LifecycleStatus.NEW)
    info = Column(mutable_json_type(dbtype=JSONB))

    @property
    def actual(self):
        if not hasattr(self, '_actual'):
            from tendril.interests import type_codes
            self._actual = type_codes[self.type_name](self)
        return self._actual

    # @declared_attr
    # def parent(cls):
    #     return relationship("InterestModel", remote_side=[cls.id])

    @declared_attr
    def memberships(cls):
        return relationship("InterestMembershipModel", back_populates='interest', lazy='dynamic')

    @declared_attr
    def approvals(cls):
        return relationship("InterestApprovalModel", back_populates='context', lazy='select',
                            foreign_keys='InterestApprovalModel.interest_id')

    @declared_attr
    def child_approvals(cls):
        return relationship("InterestApprovalModel", back_populates='interest', lazy='select',
                            foreign_keys='InterestApprovalModel.context_id')

    @declared_attr
    def children(cls):
        return relationship("InterestModel", secondary="InterestAssociation",
                            primaryjoin="InterestModel.id == InterestAssociationModel.parent_id",
                            secondaryjoin="InterestModel.id == InterestAssociationModel.child_id",
                            backref="parents", lazy='dynamic')

    # @declared_attr
    # def artefacts(cls):
    #     return relationship('ArtefactModel', back_populates="interest")

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

    @property
    def recognized_artefact_labels(self):
        return {x.label: x for x in self.recognized_artefacts}


class InterestLogEntryModel(DeclBase, BaseMixin, TimestampMixin, UserMixin):
    action = Column(String(50), nullable=False)
    reference = Column(mutable_json_type(dbtype=JSONB))
    interest_id = Column(Integer(),
                         ForeignKey('Interest.id'), nullable=False)
    interest = relationship("InterestModel", back_populates="logs")


class InterestRoleModel(DeclBase, BaseMixin):
    name = Column(String(50), nullable=False, unique=True)
    description = Column(String(255))
    memberships = relationship("InterestMembershipModel", back_populates='role', lazy='dynamic')


class InterestMembershipModel(DeclBase, BaseMixin, TimestampMixin):
    id = None
    user_id = Column(Integer, ForeignKey('User.id'), primary_key=True)
    interest_id = Column(Integer, ForeignKey('Interest.id'), primary_key=True)
    role_id = Column(Integer, ForeignKey('InterestRole.id'), primary_key=True)
    reference = Column(mutable_json_type(dbtype=JSONB))

    UniqueConstraint('user_id', 'interest_id', 'role_id')
    user = relationship('User', uselist=False)
    interest = relationship('InterestModel', uselist=False, back_populates='memberships')
    role = relationship('InterestRoleModel', uselist=False, back_populates='memberships')
