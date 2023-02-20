

from tendril.interests.base import InterestBase
from tendril.interests.base import InterestBaseTModel
from tendril.db.models.platform import PlatformModel


class PlatformTModel(InterestBaseTModel):
    pass


class Platform(InterestBase):
    model = PlatformModel
    tmodel = PlatformTModel


def load(manager):
    manager.register_interest_type('Platform', Platform)
