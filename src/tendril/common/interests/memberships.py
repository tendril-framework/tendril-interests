

import polars
from polars.exceptions import ColumnNotFoundError
from typing import Dict
from typing import List
from tendril import interests
from tendril.utils.pydantic import TendrilTBaseModel
from tendril.common.states import LifecycleStatus
from tendril.db.controllers.interests import get_interest
from tendril.utils.db import with_db


class UserMembershipTModel(TendrilTBaseModel):
    role: str
    delegated: bool
    inherited: bool


class UserMembershipsInterestTModel(TendrilTBaseModel):
    id: int
    name: str
    status: LifecycleStatus
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
                               'interest.status': interest.status.value,
                               'role.name': role,
                               'role.delegated': delegated,
                               'role.inherited': inherited})

    def process(self):
        self.df = polars.DataFrame(self._raw_data)

    def apply_status_filter(self, include_statuses):
        # TODO This will mess with caching!
        self.df = self.df.filter(polars.col('interest.status').is_in(include_statuses))

    def apply_role_filter(self, include_roles):
        # TODO This will mess with caching!
        self.df = self.df.filter(polars.col('role.name').is_in(include_roles))

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
                 'status': df[0]['interest.status'].item(),
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
        try:
            for itype in self.df.select(polars.col("type").unique()).rows():
                itype_df = self.df.filter(polars.col("type") == itype[0])\
                                  .select(['interest.id', 'interest.name', 'interest.status',
                                           'role.name', 'role.delegated', 'role.inherited'])
                rv[itype[0]] = self._pack_itype_memberships(itype_df)
            return rv
        except ColumnNotFoundError:
            return {}

    def interest_ids(self):
        if not self.df.select(polars.count()).item():
            return []
        return list(self.df.select(polars.col('interest.id').unique()).get_column(name='interest.id'))

    @with_db
    def _get_interest(self, iid, itype, session=None):
        interest_type = interests.type_codes[itype]
        return interest_type(get_interest(id=iid, type=interest_type.model, session=session))

    @with_db
    def interests(self, filter_criteria=None, sort_heuristics=None, session=None):
        if not self.df.select(polars.count()).item():
            return []
        i_itype = self.df.select(polars.col(['interest.id', 'type'])).unique()
        cand_interests = [self._get_interest(iid=iid, itype=type_name, session=session)
                          for iid, type_name in i_itype.rows()]
        if filter_criteria:
            cand_interests = [x for x in cand_interests
                              if all([getattr(x, acc)(**kw) for acc, kw in filter_criteria])]
        if sort_heuristics:
            for acc, reflist in sort_heuristics:
                ranks = dict((value, idx) for idx, value in enumerate(reflist))
                cand_interests = sorted(cand_interests, key=lambda x: ranks[x.type_name])
        return cand_interests


def _rewrap_interest(model):
    type_name = model.type
    return interests.type_codes[type_name](model)


@with_db
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


@with_db
def user_memberships(user_id, interest_types=None,
                     include_statuses=None, include_roles=None,
                     include_delegated=True, include_inherited=True,
                     session=None):
    from tendril.interests import possible_ancestors
    from tendril.db.controllers import interests

    parent_types = None
    if interest_types:
        parent_types = set(interest_types)
        for t in interest_types:
            parent_types.update(possible_ancestors[t])

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
    if include_roles:
        rv.apply_role_filter(include_roles)
    if include_statuses:
        rv.apply_status_filter(include_statuses)
    return rv
