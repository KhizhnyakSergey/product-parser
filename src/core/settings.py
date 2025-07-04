import os
from pathlib import Path
from typing import (
    Optional,
    Union,
    List,
)

from pydantic_settings import BaseSettings, SettingsConfigDict


_PathLike = Union[os.PathLike[str], str, Path]


def root_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent 


def path(*paths: _PathLike, base_path: Optional[_PathLike] = None) -> str:
    if base_path is None:
        base_path = root_dir()

    return os.path.join(base_path, *paths)


class GoogleSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="./.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # env_prefix="HOURS_",
        extra="ignore",
    )

    repeat_in_seconds: int
    table_name: str
    supraten_index_to_parse: List[int]
    iek_index_to_parse: List[int]
    habsev_index_to_parse: List[int]
    luminaled_index_to_parse: List[int]
    electromotor_index_to_parse: List[int]
    volta_index_to_parse: List[int]
    panlight_index_to_parse: List[int]
    
    json_name: str
    # data_type: str
    # time_range: str
    # list_name: str

    
class Settings(BaseSettings):

    google: GoogleSettings


def load_settings(
        google: Optional[GoogleSettings] = None,

) -> Settings:
    return Settings(
        google=google or GoogleSettings(),
    )

