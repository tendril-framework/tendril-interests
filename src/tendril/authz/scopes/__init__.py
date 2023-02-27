from pkgutil import extend_path
__path__ = extend_path(__path__, __name__)

from .manager import ScopesManager
_manager = ScopesManager(prefix='tendril.authz.scopes')

import sys
sys.modules[__name__] = _manager
_manager.finalize()
