__path__ = __import__('pkgutil').extend_path(__path__, __name__)


from .manager import PolicyTemplatesManager
_manager = PolicyTemplatesManager(prefix='tendril.policies')


import sys
sys.modules[__name__] = _manager
_manager.finalize()
