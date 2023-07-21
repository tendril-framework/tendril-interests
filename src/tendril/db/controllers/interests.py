

from sqlalchemy.orm.exc import NoResultFound
from tendril.utils.db import with_db

from tendril.authn.db.model import User
from tendril.authn.db.controller import preprocess_user

from tendril.db.models.interests import InterestModel
from tendril.db.models.interests import InterestRoleModel
from tendril.db.models.interests import InterestMembershipModel
from tendril.db.models.interests import InterestAssociationModel
from tendril.db.models.interests import InterestLogEntryModel

from tendril.common.interests.exceptions import InterestAlreadyExists
from tendril.common.interests.exceptions import InterestNotFound

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


def _type_discriminator(type):
    if not type:
        return InterestModel
    if isinstance(type, str):
        from tendril.interests import type_codes
        return type_codes[type].model
    elif hasattr(type, 'model'):
        type = getattr(type, 'model')
    if issubclass(type, InterestModel):
        qmodel = type
    return qmodel


@with_db
def get_interests(type=None, state=None, session=None):
    filters = []
    qmodel = _type_discriminator(type)
    if state:
        filters.append(qmodel.status == state)
    q = session.query(qmodel).filter(*filters)
    return q.all()


@with_db
def get_interest(id=None, name=None, type=None, raise_if_none=True, session=None):
    filters = []
    qmodel = _type_discriminator(type)
    if id:
        filters.append(qmodel.id == id)
    elif name:
        filters.append(qmodel.name == name)
    q = session.query(qmodel).filter(*filters)
    try:
        return q.one()
    except NoResultFound:
        if raise_if_none:
            raise
        return None


@with_db
def upsert_interest(id=None, name=None, status=None, info=None, type=None,
                    descriptive_name=None, must_create=False, can_create=True, session=None,
                    **kwargs):
    # kwargs are the additional fields which apply to the individual
    # interest classes. A more robust way to deal with them is needed.
    # Maybe actually use ORM the way it was meant to instead of this
    # horrible chimera.
    if name is None:
        raise AttributeError("name cannot be None")
    try:
        existing = get_interest(id=id, name=name, type=type, session=session)
        interest = existing
        if must_create:
            raise InterestAlreadyExists(type, name)
    except NoResultFound:
        if id or not can_create:
            raise InterestNotFound(type_name=type, name=name, id=id)
        qmodel = _type_discriminator(type)
        interest = qmodel(name=name, info=info)
    if name:
        interest.name = name
    if info:
        interest.info = info
    if status:
        interest.status = status.value
    if descriptive_name:
        interest.descriptive_name = descriptive_name
    for k, v in kwargs.items():
        if v:
            setattr(interest, k, v)
    session.add(interest)
    session.flush()
    return interest


@with_db
def preprocess_interest(interest, type=None, session=None):
    if isinstance(interest, int):
        return interest
    elif isinstance(interest, str):
        interest = get_interest(name=interest, type=type, session=session)
        return interest.id
    elif isinstance(interest, InterestModel):
        return interest.id
    elif hasattr(interest, 'id'):
        return interest.id

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
def assign_role(interest, user, role, reference=None, session=None):
    kwargs = {
        'interest_id': preprocess_interest(interest, session=session),
        'user_id': preprocess_user(user, session=session),
        'role_id': preprocess_role(role, session=session)
    }
    if reference:
        kwargs['reference'] = reference

    try:
        existing = get_membership(interest=kwargs['interest_id'],
                                  user=kwargs['user_id'],
                                  role=kwargs['role_id'], session=session)
        membership = existing
    except NoResultFound:
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
    # TODO this is weird. Figure out why.
    rv = q.all()
    if len(rv):
        return rv[0]
    else:
        return rv


@with_db
def get_user_memberships(user, interest_type=None, session=None):
    user_id = preprocess_user(user, session=session)
    q = session.query(InterestMembershipModel).\
        filter_by(user_id=user_id)

    if interest_type:
        qmodel = _type_discriminator(interest_type)
        q = q.join(InterestModel).\
        filter_by(type=qmodel.type_name)

    return q.all()


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
def get_association(parent, child, session=None):
    kwargs = {
        'parent_id': preprocess_interest(parent, session=session),
        'child_id': preprocess_interest(child, session=session),
    }
    q = session.query(InterestAssociationModel)\
        .filter_by(parent_id=kwargs['parent_id'])\
        .filter_by(child_id=kwargs['child_id'])
    return q.one()


@with_db
def add_child(child, interest, type=None, limited=False, session=None):
    kwargs = {
        'parent_id': preprocess_interest(interest, session=session),
        'child_id': preprocess_interest(child, session=session),
        'limited': limited,
    }

    interest = get_interest(kwargs['parent_id'], type=type, session=session)
    child = get_interest(kwargs['child_id'], session=session)
    if not any(x in interest.role_spec.allowed_children for x in ['*', child.type_name]):
        raise TypeError(f"'{child.type}' not an allowed child type for '{interest.type}'")

    try:
        existing = get_association(parent=kwargs['parent_id'],
                                   child=kwargs['child_id'], session=session)
        if not existing.limited and limited:
            existing.limited = True
        association = existing
    except NoResultFound:
        association = InterestAssociationModel(**kwargs)
    session.add(association)
    return association


@with_db
def get_parents(interest, type=None, limited=None, session=None):
    if limited is None:
        interest = get_interest(interest, type, session=session)
        return interest.parents
    filters = []
    interest_id = preprocess_interest(interest, session=session)

    q = session.query(InterestModel)\
        .join(InterestAssociationModel, onclause=(InterestModel.id == InterestAssociationModel.parent_id))

    filters.append(InterestAssociationModel.child_id == interest_id)
    filters.append(InterestAssociationModel.limited == limited)

    return q.filter(*filters).all()


@with_db
def get_children(interest, type=None, child_type=None, limited=None, session=None):
    if not limited and not child_type:
        interest = get_interest(interest, type, session=session)
        return interest.children
    filters = []
    interest_id = preprocess_interest(interest, session=session)

    q = session.query(InterestModel)\
        .join(InterestAssociationModel, onclause=(InterestModel.id == InterestAssociationModel.child_id))

    filters.append(InterestAssociationModel.parent_id == interest_id)
    if limited is not None:
        filters.append(InterestAssociationModel.limited == limited)
    if child_type is not None:
        filters.append(InterestModel.type == child_type)

    return q.filter(*filters).all()


@with_db
def get_artefacts():
    pass


@with_db
def add_artefact():
    pass


@with_db
def remove_artefact():
    pass
