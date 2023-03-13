

from tendril import interests
from tendril.config import INTERESTS_API_ENABLED

if INTERESTS_API_ENABLED:
    scopes = {
        'interests:common': "Interests API Common Access",
    }
    for itype in interests.types.values():
        scopes.update(itype.model.role_spec.scopes)
    default_scopes = ['interests:common']
else:
    scopes = {}
    default_scopes = []
