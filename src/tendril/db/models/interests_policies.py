


from sqlalchemy import Column
from sqlalchemy import String
from sqlalchemy import Integer
from sqlalchemy import UniqueConstraint

from sqlalchemy import ForeignKey
from sqlalchemy.orm import deferred
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy_json import mutable_json_type
from sqlalchemy.dialects.postgresql import JSONB

from tendril.utils.db import DeclBase
from tendril.utils.db import BaseMixin
from tendril.utils.db import TimestampMixin
from tendril.authn.db.mixins import UserMixin


class PolicyTypeModel(DeclBase, BaseMixin):
    name = Column(String, nullable=False)


class InterestPolicyModel(DeclBase, BaseMixin, UserMixin, TimestampMixin):
    interest_id: Mapped[int] = mapped_column(ForeignKey('Interest.id'), nullable=False)
    interest = relationship('InterestModel', back_populates='policies',
                            lazy='selectin', foreign_keys=interest_id)

    policy_type_id = Column(Integer, ForeignKey('PolicyType.id'), nullable=False)
    policy_type = relationship('PolicyTypeModel', lazy='selectin')

    policy = deferred(Column(mutable_json_type(dbtype=JSONB)))

    __table_args__ = (
        UniqueConstraint('interest_id', 'policy_type_id'),
    )
