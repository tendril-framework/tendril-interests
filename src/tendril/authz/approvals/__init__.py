from pkgutil import extend_path
__path__ = extend_path(__path__, __name__)

from .manager import ApprovalTypesManager
_manager = ApprovalTypesManager(prefix='tendril.authz.approvals')

import sys
sys.modules[__name__] = _manager
_manager.finalize()
