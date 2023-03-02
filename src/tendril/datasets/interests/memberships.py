

import polars
from typing import Dict
from typing import List
from tendril.utils.pydantic import TendrilTBaseModel
from tendril.utils.db import get_session


class UserMembershipTModel(TendrilTBaseModel):
    role: str
    delegated: bool
    inherited: bool


class UserMembershipsInterestTModel(TendrilTBaseModel):
    id: int
    name: str
    roles: List[UserMembershipTModel]


UserMembershipsInterestsContainerTModel = List[UserMembershipsInterestTModel]
UserMembershipsTModel = Dict[str, UserMembershipsInterestsContainerTModel]


class UserMembershipCollector(object):
    def __init__(self):
        self._raw_data = []
        self.df = None

    def add_membership(self, interest, role, delegated, inherited):
        self._raw_data.append({'type': interest.type_name,
                               'interest.id': interest.id,
                               'interest.name': interest.name,
                               'role.name': role,
                               'role.delegated': delegated,
                               'role.inherited': inherited})

    def process(self):
        self.df = polars.DataFrame(self._raw_data)

    def _pack_interest_role(self, df):
        # TODO This calculation is wrong.
        return {'role': df[0]['role.name'].item(),
                'delegated': bool(df.select(polars.col('role.delegated')).min().item()),
                'inherited': bool(df.select(polars.col('role.inherited')).min().item())}

    def _pack_interest_memberships(self, df):
        roles = []
        for role in df.select(polars.col('role.name').unique()).rows():
            role_df = df.filter(polars.col('role.name') == role[0])\
                        .select(['role.name', 'role.delegated', 'role.inherited'])
            roles.append(self._pack_interest_role(role_df))
        idict = {'id': df[0]['interest.id'].item(),
                 'name': df[0]['interest.name'].item(),
                 'roles': roles}
        return idict

    def _pack_itype_memberships(self, df):
        rv = []
        for interest_id in df.select(polars.col('interest.id').unique()).rows():
            interest_df = df.filter(polars.col('interest.id') == interest_id[0])
            rv.append(self._pack_interest_memberships(interest_df))
        return rv

    def render(self):
        rv = {}
        for itype in self.df.select(polars.col("type").unique()).rows():
            itype_df = self.df.filter(polars.col("type") == itype[0])\
                              .select(['interest.id', 'interest.name',
                                       'role.name', 'role.delegated', 'role.inherited'])
            rv[itype[0]] = self._pack_itype_memberships(itype_df)
        return rv


def user_memberships(user_id,
                     include_delegated=True,
                     include_inherited=True):
    from tendril.db.controllers import interests
    from tendril.interests import type_codes
    with get_session() as session:
        memberships = interests.get_user_memberships(user=user_id, session=session)
        rv = UserMembershipCollector()
        for m in memberships:
            rv.add_membership(m.interest, m.role.name, False, False)
            if include_delegated:
                type_code = m.interest.type
                interest_rs = type_codes[type_code].model.role_spec
                for role in interest_rs.get_delegated_roles(m.role.name):
                    rv.add_membership(m.interest, role, True, False)
        rv.process()
    return rv.render()
