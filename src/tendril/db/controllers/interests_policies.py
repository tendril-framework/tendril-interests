

from sqlalchemy.exc import NoResultFound
from tendril.db.controllers.interests import preprocess_user
from tendril.db.controllers.interests import preprocess_interest

from tendril.db.models.interests_policies import PolicyTypeModel
from tendril.db.models.interests_policies import InterestPolicyModel
from tendril.utils.db import with_db


@with_db
def get_policy_type(name, session=None):
    q = session.query(PolicyTypeModel).filter_by(name=name)
    return q.one()


@with_db
def register_policy_type(policy_type, session=None):
    if policy_type.name is None:
        raise AttributeError("name cannot be None")

    try:
        existing = get_policy_type(policy_type.name, session=session)
    except NoResultFound:
        ptype = PolicyTypeModel(name=policy_type.name)
    else:
        ptype = existing
    session.add(ptype)

@with_db
def preprocess_policy_type(policy_type, session=None):
    if isinstance(policy_type, int):
        return policy_type
    if not isinstance(policy_type, PolicyTypeModel):
        if not isinstance(policy_type, str):
            policy_type = policy_type.name
        policy_type = get_policy_type(policy_type, session=session)
    return policy_type.id

@with_db
def get_policy(policy_type=None, interest=None, user=None, required=False, session=None):
    filters = []

    if policy_type:
        policy_type = preprocess_policy_type(policy_type, session=session)
        filters.append(InterestPolicyModel.policy_type_id == policy_type)
    if interest:
        interest = preprocess_interest(interest, session=session)
        filters.append(InterestPolicyModel.interest_id == interest)
    if user:
        user = preprocess_user(user, session=session)
        filters.append(InterestPolicyModel.user_id == user)

    if (policy_type is not None) and (interest is not None):
        one = True
    else:
        one = False

    q = session.query(InterestPolicyModel).filter(*filters)
    try:
        if one:
            return q.one()
        else:
            return q.all()
    except NoResultFound:
        if not required:
            return None
        raise


@with_db
def upsert_policy(policy_type, interest, user, policy, session=None):
    policy_type = preprocess_policy_type(policy_type, session=session)
    interest = preprocess_interest(interest, session=session)
    user = preprocess_user(user, session=session)

    try:
        existing = get_policy(policy_type=policy_type,
                              interest=interest, required=True,
                              user=user, session=session)

        existing.policy = policy
        policy_obj = existing
    except NoResultFound:
        new = InterestPolicyModel(
            policy_type_id=policy_type,
            interest_id=interest,
            policy=policy,
            user_id=user
        )
        policy_obj = new

    session.add(policy_obj)
    session.flush()
    return policy_obj


@with_db
def clear_policy(policy_type, interest, session=None):
    policy_type = preprocess_policy_type(policy_type, session=session)
    interest = preprocess_interest(interest, session=session)

    try:
        existing = get_policy(policy_type=policy_type,
                              interest=interest, required=True,
                              session=session)
        session.delete(existing)
        session.flush()
        return existing
    except NoResultFound:
        pass
