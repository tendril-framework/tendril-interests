

from tendril.interests import Platform
from tendril.utils.db import with_db
from tendril.db.controllers.interests import get_interest
from sqlalchemy.orm.exc import NoResultFound


@with_db
def upsert_platform(name, info, session=None):
    if name is None:
        raise AttributeError("name cannot be None")
    try:
        existing = get_interest(name, type='platform', session=session)
        existing.info = info
        platform = existing
    except NoResultFound:
        platform = Platform._model(name=name, info=info)
    session.add(platform)
    return platform
