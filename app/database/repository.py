"""
Generic Repository Module

This module provides a generic repository for database operations.
It supports basic CRUD operations and additional methods for querying and updating data.
"""

from sqlalchemy import desc
from sqlalchemy.orm import Session


class GenericRepository[T]:
    def __init__(self, session: Session, model: type[T]):
        self.session = session
        self.model = model

    def create(self, obj: T) -> T:
        self.session.add(obj)
        self.session.commit()
        return obj

    def get(
        self,
        obj_id: str,
    ) -> T | None:
        return self.session.query(self.model).filter(self.model.id == obj_id).first()

    def get_all(
        self,
    ) -> list[T]:
        return self.session.query(self.model).all()

    def update(
        self,
        obj: T,
    ) -> T:
        self.session.merge(obj)
        self.session.commit()
        return obj

    def delete(
        self,
        obj_id: str,
    ) -> None:
        obj = self.get(obj_id)
        if obj:
            self.session.delete(obj)
            self.session.commit()

    def get_latest(
        self,
        n: int = 1,
    ) -> list[T]:
        return (
            self.session.query(self.model).order_by(desc(self.model.id)).limit(n).all()
        )

    def count(
        self,
    ) -> int:
        return self.session.query(self.model).count()

    def exists(
        self,
        **kwargs,
    ) -> bool:
        return (
            self.session.query(self.model).filter_by(**kwargs).first() is not None
        )
