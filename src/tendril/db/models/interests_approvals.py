

from sqlalchemy import Enum
from sqlalchemy import Column
from sqlalchemy import String
from sqlalchemy import Integer
from sqlalchemy import Boolean
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from tendril.common.states import LifecycleStatus
from tendril.authz.approvals.interests import InterestApprovalSpec

from tendril.utils.db import DeclBase
from tendril.utils.db import BaseMixin
from tendril.utils.db import TimestampMixin
from tendril.authn.db.mixins import UserMixin


class InterestModelApprovalMixin(object):
    approval_spec = InterestApprovalSpec()


class InterestModelApprovalContextMixin(object):
    pass


class ApprovalTypeModel(DeclBase, BaseMixin):
    name = Column(String, nullable=False)
    role_id = Column(Integer, ForeignKey('InterestRole.id'))
    role = relationship('InterestRoleModel', lazy='selectin', foreign_keys=role_id)
    states = Column(ARRAY(Enum(LifecycleStatus, create_constraint=False, native_enum=False)))
    context_type = Column(String)


class InterestApprovalModel(DeclBase, BaseMixin, UserMixin, TimestampMixin):
    interest_id: Mapped[int] = mapped_column(ForeignKey('Interest.id'), nullable=False)
    interest = relationship('InterestModel', back_populates='approvals',
                            lazy='selectin', foreign_keys=interest_id)

    context_id: Mapped[int] = mapped_column(ForeignKey('Interest.id'), nullable=False)
    context = relationship('InterestModel', back_populates='child_approvals',
                           lazy='selectin', foreign_keys=context_id)

    approval_type_id = Column(Integer, ForeignKey('ApprovalType.id'), nullable=False)
    approval_type = relationship('ApprovalTypeModel', lazy='selectin')

    approved = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint('interest_id', 'context_id', 'approval_type_id', 'user_id'),
    )
