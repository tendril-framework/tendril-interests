

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

    def interest_ids(self):
        return self.df.select(polars.col('interest.id').unique()).rows()[0]


def _rewrap_interest(model):
    from tendril.interests import type_codes
    type_name = model.type
    return type_codes[type_name](model)


def _get_interest_user_memberships(collector, interest, user_id,
                                   include_delegated=True,
                                   include_inherited=True,
                                   is_inherited=False,
                                   inherited_roles=None,
                                   interest_types=None,
                                   parent_types=None,
                                   session=None):
    # This feels terrible.
    # Also, delegations needs to be tracked down the recursion.
    add_to_result = not interest_types or interest.model.type_name in interest_types
    to_inherit = set()
    if inherited_roles:
        for role in inherited_roles:
            if role not in interest.model.role_spec.roles:
                continue
            to_inherit.add(role)
            if add_to_result:
                collector.add_membership(interest, role, False, True)
    roles = set(interest.get_user_roles(user_id, session=session))
    for role in list(roles):
        to_inherit.add(role)
        if add_to_result:
            collector.add_membership(interest, role, False, is_inherited)
        if include_delegated:
            interest_rs = interest.model.role_spec
            for drole in interest_rs.get_delegated_roles(role):
                to_inherit.add(drole)
                if add_to_result:
                    collector.add_membership(interest, drole, True, is_inherited)
    if include_inherited:
        for child in interest.children(limited=False, session=session):
            if not child.model.role_spec.inherits_from_parent:
                continue
            if parent_types and not child.model.type_name in parent_types:
                continue
            _get_interest_user_memberships(collector, child, user_id,
                                           include_delegated=include_delegated,
                                           include_inherited=include_inherited,
                                           is_inherited=True, inherited_roles=to_inherit,
                                           interest_types=interest_types,
                                           parent_types=parent_types,
                                           session=session)


def user_memberships(user_id, interest_types=None,
                     include_delegated=True,
                     include_inherited=True):
    from tendril.interests import possible_parents
    from tendril.db.controllers import interests

    parent_types = None
    if interest_types:
        parent_types = set(interest_types)
        for t in interest_types:
            parent_types.update(possible_parents[t])

    with get_session() as session:
        memberships = interests.get_user_memberships(user=user_id, session=session)
        rv = UserMembershipCollector()
        for m in memberships:
            if parent_types and m.interest.type_name not in parent_types:
                continue
            _get_interest_user_memberships(rv, _rewrap_interest(m.interest), user_id,
                                           include_delegated=include_delegated,
                                           include_inherited=include_inherited,
                                           is_inherited=False, inherited_roles=[],
                                           interest_types=interest_types,
                                           parent_types=parent_types,
                                           session=session)
        rv.process()
    return rv
