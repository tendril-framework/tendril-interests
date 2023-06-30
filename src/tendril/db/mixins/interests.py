

from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declared_attr


class InterestMixin(object):
    @declared_attr
    def interest_id(cls):
        return Column(Integer(), ForeignKey('Interest.id'), nullable=True)

    @declared_attr
    def interest(cls):
        return relationship("InterestModel")
