

from sqlalchemy.orm.exc import NoResultFound
from tendril.utils.db import with_db

from tendril.authn.db.model import User
from tendril.authn.db.controller import preprocess_user

from .model import InterestModel
from .model import InterestRoleModel
from .model import InterestMembershipModel
from .model import InterestLogEntryModel

from tendril.utils import log
logger = log.get_logger(__name__, log.DEFAULT)


@with_db
def get_interest_role(name, session=None):
    q = session.query(InterestRoleModel).filter_by(name=name)
    return q.one()


@with_db
def register_interest_role(name, description="", session=None):
    if name is None:
        raise AttributeError("name cannot be None")

    try:
        existing = get_interest_role(name, session=session)
    except NoResultFound:
        role = InterestRoleModel(name=name, description=description)
    else:
        role = existing
    session.add(role)
    return role


@with_db
def preprocess_role(role, session=None):
    if isinstance(role, int):
        return role
    elif isinstance(role, str):
        role = get_interest_role(role, session=session)
        return role.id
    elif isinstance(role, InterestRoleModel):
        return role.id


@with_db
def get_interest(name, type=None, session=None):
    filters = [InterestModel.name == name]
    if type:
        filters.append(InterestModel.type == type)
    q = session.query(InterestModel).filter(*filters)
    return q.one()


@with_db
def upsert_interest(name, info, type=None, session=None):
    if name is None:
        raise AttributeError("name cannot be None")

    try:
        existing = get_interest(name, type=type, session=session)
        existing.info = info
        interest = existing
    except NoResultFound:
        if type:
            interest = InterestModel(name=name, info=info, type=type)
        else:
            interest = InterestModel(name=name, info=info)
    session.add(interest)
    return interest


@with_db
def preprocess_interest(interest, type=None, session=None):
    if isinstance(interest, int):
        return interest
    elif isinstance(interest, str):
        interest = get_interest(interest, type, session=session)
        return interest.id
    elif isinstance(interest, InterestModel):
        return interest.id


@with_db
def assign_role(interest, user, role, reference=None, session=None):
    kwargs = {
        'interest_id': preprocess_interest(interest, session=session),
        'user_id': preprocess_user(user, session=session),
        'role_id': preprocess_role(role, session=session)
    }
    if reference:
        kwargs['reference'] = reference

    membership = InterestMembershipModel(**kwargs)
    session.add(membership)
    return membership


@with_db
def get_role_users(interest, role, session=None):
    interest_id = preprocess_interest(interest, session=session)
    role_id = preprocess_role(role, session=session)

    q = session.query(User).join(InterestMembershipModel)\
        .filter_by(interest_id=interest_id)\
        .filter_by(role_id=role_id)
    return q.all()


@with_db
def get_user_roles(interest, user, session=None):
    interest_id = preprocess_interest(interest, session=session)
    user_id = preprocess_user(user, session=session)

    q = session.query(InterestRoleModel.name).\
        join(InterestMembershipModel).\
        filter_by(interest_id=interest_id).\
        filter_by(user_id=user_id)
    return q.all()[0]


@with_db
def get_membership(interest, user, role, session=None):
    interest_id = preprocess_interest(interest, session=session)
    user_id = preprocess_user(user, session=session)
    role_id = preprocess_role(role, session=session)
    q = session.query(InterestMembershipModel)\
        .filter_by(interest_id=interest_id)\
        .filter_by(user_id=user_id)\
        .filter_by(role_id=role_id)
    return q.one()


@with_db
def remove_role(interest, user, role, reference=None, session=None):
    membership = get_membership(interest, user, role, session=session)
    session.delete(membership)
    return


@with_db
def remove_user(interest, user, reference=None, session=None):
    interest_id = preprocess_interest(interest, session=session)
    user_id = preprocess_user(user, session=session)

    roles = get_user_roles(interest_id, user_id, session=session)
    for role in roles:
        remove_role(interest_id, user_id, role, reference, session=session)


@with_db
def set_parent(interest, parent, type=None, session=None):
    interest = get_interest(interest, session=session)
    parent_id = preprocess_interest(parent)
    interest.parent_id = parent_id
    session.add(interest)
    return interest


@with_db
def get_parent(interest, type=None, session=None):
    interest = get_interest(interest, type, session=session)
    return interest.parent


@with_db
def get_children(interest, type=None, session=None):
    interest = get_interest(interest, type, session=session)
    return interest.children
