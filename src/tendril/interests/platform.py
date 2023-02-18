

from tendril.interests.base import InterestBase
from tendril.db.models.platform import PlatformModel


class Platform(InterestBase):
    model = PlatformModel


def load(manager):
    manager.register_interest_type('Platform', Platform)
