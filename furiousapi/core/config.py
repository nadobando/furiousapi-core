from functools import lru_cache
from typing import Any, Dict, Generic, Optional, TypeVar, Union, get_type_hints

from pydantic import BaseModel, BaseSettings, Field
from pydantic import PostgresDsn as _PostgresDsn
from pydantic import validator
from pydantic.generics import GenericModel
from pydantic.networks import MultiHostDsn


class MongoDBDsn(MultiHostDsn):
    allowed_schemes = "mongodb"
    user_required = False


class PostgresDsn(_PostgresDsn):
    user_required = False


# noinspection PyTypeHints
TConnectionString = TypeVar("TConnectionString", MongoDBDsn, PostgresDsn)
# noinspection PyTypeHints
TConnectionOptions = TypeVar("TConnectionOptions", bound=BaseModel)


class BaseConnectionSettings(GenericModel, Generic[TConnectionString, TConnectionOptions]):
    user: Optional[str]
    password: Optional[str]
    connection_string: TConnectionString
    options: Optional[TConnectionOptions]

    @classmethod
    @validator("connection_string", pre=True)
    def db_connection(cls, v: TConnectionString, values: Dict[str, Any]) -> Union[TConnectionString, str]:
        c_str_cls = get_type_hints(cls)["connection_string"]
        kwargs = c_str_cls._match_url(v).groupdict()  # noqa: SLF001

        if ((user := values.get("user")) and not kwargs.get("user")) and (
            (password := values.get("password")) and not kwargs.get("password")
        ):
            scheme, sep, url = v.partition("://")
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
