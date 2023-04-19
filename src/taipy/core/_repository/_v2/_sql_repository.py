# Copyright 2023 Avaiga Private Limited
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
# an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

import json
import pathlib
import uuid
from typing import Any, Dict, Generic, Iterable, List, Optional, Type, TypeVar, Union

# from app.encoders import jsonable_encoder
# from pydantic import BaseModel
from sqlalchemy.exc import NoResultFound

from src.taipy.core.common.typing import Converter, Entity, Json, ModelType

from ...exceptions import ModelNotFound
from ._abstract_repository import _AbstractRepository
from .db._sql_session import SessionLocal


class _SQLRepository(_AbstractRepository[ModelType, Entity]):
    def __init__(self, model: Type[ModelType], converter: Type[Converter], session=SessionLocal()):
        """
        CRUD object with default methods to Create, Read, Update, Delete (CRUD).
        **Parameters**
        * `model`: A Taipy model class
        * `converter`: A class that handles conversion to and from a database backend
        * `db_table`: A SQLAlchemy model class
        """
        self.model = model
        self.db = session
        self.converter = converter

    def _save(self, entity: Entity):
        obj = self.converter._entity_to_model(entity)
        if entry := self.db.query(self.model).filter_by(id=obj.id).first():
            self.__update_entry(entry, obj)
            return
        self.__insert_model(obj)

    def _load(self, model_id: Any) -> Optional[ModelType]:
        if entry := self.db.query(self.model).filter(self.model.id == model_id).first():
            return self.converter._model_to_entity(entry)
        return None

    def _load_all(self, filters: Optional[List[Dict]] = None) -> List[Entity]:
        query = self.db.query(self.model)
        try:
            if filters:
                query.filter(filters)
            return [self.converter._model_to_entity(m) for m in query.all()]
        except NoResultFound:
            return []

    def _delete(self, entity_id: str):
        number_of_deleted_entries = self.db.query(self.model).filter_by(id=entity_id).delete()
        if not number_of_deleted_entries:
            raise ModelNotFound(str(self.model.__name__), entity_id)
        self.db.commit()

    def _delete_all(self):
        self.db.query(self.model).delete()
        self.db.commit()

    def _delete_many(self, ids: Iterable[str]):
        for entity_id in ids:
            self._delete(entity_id)

    def _delete_by(self, attribute: str, value: str):
        while entity := self._search(attribute, value):
            self._delete(entity.id)

    def _search(self, attribute: str, value: Any, filters: Optional[List[Dict]] = None) -> Optional[Entity]:
        query = self.db.query(self.model).filter_by(**{attribute: value})

        if filters:
            query.filter(filters)

        if entry := query.first():
            return self.converter._model_to_entity(entry)
        return None

    def _export(self, entity_id: str, folder_path: Union[str, pathlib.Path]):
        if isinstance(folder_path, str):
            folder: pathlib.Path = pathlib.Path(folder_path)
        else:
            folder = folder_path

        export_dir = folder / self.model.__table__.name
        if not export_dir.exists():
            export_dir.mkdir(parents=True)

        export_path = export_dir / f"{entity_id}.json"

        entry = self.db.query(self.model).filter_by(id=entity_id).first()
        if entry is None:
            raise ModelNotFound(self.model, entity_id)  # type: ignore

        with open(export_path, "w", encoding="utf-8") as export_file:
            export_file.write(json.dumps(entry.to_dict()))

    def get_by_config(self, config_id: Any) -> Optional[ModelType]:
        return self.db.query(self.model).filter(self.model.config_id == config_id).first()

    def get_multi(self, *, skip: int = 0, limit: int = 100) -> List[ModelType]:
        return self.db.query(self.model).offset(skip).limit(limit).all()

    def __insert_model(self, obj: ModelType):
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)

    def __update_entry(self, entry, model):
        for field in entry:
            if hasattr(field, model):
                setattr(entry, field, model[field])
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
