

from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import NoResultFound
from sqlalchemy.exc import MultipleResultsFound

from tendril.interests.base import InterestBase
from tendril.db.controllers.interests import preprocess_user
from tendril.db.controllers.interests import preprocess_interest
from tendril.db.controllers.interests import get_interest_role
from tendril.db.models.interests_approvals import ApprovalTypeModel
from tendril.db.models.interests_approvals import InterestApprovalModel
from tendril.utils.db import with_db


@with_db
def get_approval_type(name, session=None):
    q = session.query(ApprovalTypeModel).filter_by(name=name)
    return q.one()


@with_db
def register_approval_type(approval_type, session=None):
    if approval_type.name is None:
        raise AttributeError("name cannot be None")

    try:
        existing = get_approval_type(approval_type.name, session=session)
    except NoResultFound:
        role = get_interest_role(approval_type.role, session=session)
        atype = ApprovalTypeModel(name=approval_type.name,
                                  role=role,
                                  states=[x.value for x in approval_type.states],
                                  context_type=approval_type.context_type)
    else:
        atype = existing
    session.add(atype)


@with_db
def preprocess_approval_type(approval_type, session=None):
    if isinstance(approval_type, int):
        return approval_type
    if not isinstance(approval_type, ApprovalTypeModel):
        if not isinstance(approval_type, str):
            approval_type = approval_type.name
        approval_type = get_approval_type(approval_type, session=session)
    return approval_type.id


@with_db
def get_approval(approval_type=None, context=None, subject=None, user=None, session=None):
    filters = []

    if approval_type:
        approval_type = preprocess_approval_type(approval_type, session=session)
        filters.append(InterestApprovalModel.approval_type_id == approval_type)
    if context:
        context = preprocess_interest(context, session=session)
        filters.append(InterestApprovalModel.context_id == context)
    if subject:
        subject = preprocess_interest(subject, session=session)
        filters.append(InterestApprovalModel.interest_id == subject)
    if user:
        user = preprocess_user(user, session=session)
        filters.append(InterestApprovalModel.user_id == user)

    if len(filters) == 4:
        one = True
    else:
        one = False

    q = session.query(InterestApprovalModel).filter(*filters)
    if one:
        return q.one()
    else:
        return q.all()

@with_db
def register_approval(approval_type, context, subject, user, reject=False, session=None):
    approval_type = preprocess_approval_type(approval_type, session=session)
    context = preprocess_interest(context, session=session)
    subject = preprocess_interest(subject, session=session)
    user = preprocess_user(user, session=session)

    try:
        existing_approval = get_approval(approval_type=approval_type,
                                         context=context, subject=subject,
                                         user=user, session=session)
    except NoResultFound:
        pass
    else:
        raise ValueError("User has already provided an approval or rejection for this combination of "
                         "context, subject, and approval_type. Withdraw the existing approval first "
                         "and try again.")

    new_approval = InterestApprovalModel(
        approval_type_id=approval_type,
        context_id=context,
        interest_id=subject,
        user_id=user,
        approved=not reject
    )

    session.add(new_approval)
    session.flush()
    return new_approval

@with_db
def withdraw_approval(approval_type, context, subject, user, session=None):
    approval_type = preprocess_approval_type(approval_type, session=session)
    context = preprocess_interest(context, session=session)
    subject = preprocess_interest(subject, session=session)
    user = preprocess_user(user, session=session)
    try:
        existing_approval = get_approval(approval_type=approval_type,
                                         context=context, subject=subject,
                                         user=user, session=session)
        session.delete(existing_approval)
        session.flush()
        return existing_approval
    except NoResultFound:
        raise ValueError("User does not seem to have provided an approval or rejection for this combination "
                         "of context, subject, and approval_type. Nothing to withdraw.")
