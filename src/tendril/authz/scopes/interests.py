

from tendril import interests

scopes = {
    'interests:common': "Interests API Common Access",
}

for itype in interests.types.values():
    scopes.update(itype.model.role_spec.scopes)
