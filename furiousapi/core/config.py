from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, Generic, Optional, TypeVar, Union, get_type_hints

from pydantic import BaseModel, Field, validator

from furiousapi.pydantic import PYDANTIC_V2, BaseSettings, MultiHostDsn

if PYDANTIC_V2:
    from pydantic import model_validator

    GenericModel = BaseModel
else:
    from pydantic import validator
    from pydantic.generics import GenericModel

# noinspection PyTypeHints
TConnectionString = TypeVar("TConnectionString", bound=MultiHostDsn)
# noinspection PyTypeHints
TConnectionOptions = TypeVar("TConnectionOptions", bound=BaseModel)


class BaseConnectionSettings(GenericModel, Generic[TConnectionString, TConnectionOptions]):
    user: Optional[str]
    password: Optional[str]
    connection_string: TConnectionString
    options: Optional[TConnectionOptions]

    if PYDANTIC_V2:
        # Use RootValidator for Pydantic v2
        @classmethod
        @model_validator(mode="before")
        def db_connection(cls, values: Dict[str, Any]) -> Dict[str, Any]:
            connection_string = values.get("connection_string")
            c_str_cls = get_type_hints(cls)["connection_string"]

            # Accessing the MultiHostDsn parsing mechanism
            kwargs = c_str_cls(url=connection_string).hosts()

            user = values.get("user")
            password = values.get("password")

            if user and not kwargs[0].get("username") and password and not kwargs[0].get("password"):
                scheme, sep, url = str(connection_string).partition("://")
                values["connection_string"] = f"{scheme}{sep}{user}:{password}@{url}"

            return values

    else:
        # Use validator for Pydantic v1
        @classmethod
        @validator("connection_string", pre=True)
        def db_connection(cls, v: TConnectionString, values: Dict[str, Any]) -> Union[TConnectionString, str]:
            c_str_cls = get_type_hints(cls)["connection_string"]

            # Accessing the MultiHostDsn parsing mechanism
            kwargs = c_str_cls(url=v).hosts()

            user = values.get("user")
            password = values.get("password")

            if user and not kwargs[0].get("username") and password and not kwargs[0].get("password"):
                scheme, sep, url = v.partition("://")  # type: ignore[attr-defined]
                return f"{scheme}{sep}{user}:{password}@{url}"

            return v


class PaginationSettings(BaseSettings):
    default_size: int = 10
    max_size: int = 50


class Settings(BaseSettings):
    pagination: PaginationSettings = Field(default_factory=PaginationSettings)

    class Config:
        env_nested_delimiter = "__"
        env_prefix: str = "FURIOUS"


@lru_cache
def get_settings() -> Settings:
    return Settings()
