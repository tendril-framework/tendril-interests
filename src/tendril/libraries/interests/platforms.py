

from tendril.interests import Platform
from tendril.libraries.interests.base import GenericInterestLibrary
from tendril.libraries.interests.manager import InterestLibraryManager


class PlatformLibrary(GenericInterestLibrary):
    interest_class = Platform


def load(manager: InterestLibraryManager):
    manager.install_library('platforms', PlatformLibrary())
