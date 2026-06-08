import logging
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from database.database_utils import DatabaseUtils

Base = declarative_base()

_ENGINE = None


def _get_engine():
    global _ENGINE  # pylint: disable=global-statement
    if _ENGINE is None:
        _ENGINE = create_engine(DatabaseUtils.get_connection_string())
    return _ENGINE


def db_session() -> Generator:
    session: Session = sessionmaker(
        autocommit=False, autoflush=False, bind=_get_engine()
    )()
    try:
        yield session
        session.commit()
    except Exception as ex:
        session.rollback()
        logging.error(ex)
        raise ex
    finally:
        session.close()
