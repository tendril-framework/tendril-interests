from pkgutil import extend_path
__path__ = extend_path(__path__, __name__)

from .manager import InterestLibraryManager
_manager = InterestLibraryManager(prefix='tendril.libraries.interests')

import sys
sys.modules[__name__] = _manager
