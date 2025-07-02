from __future__ import annotations

import abc
import datetime
import json
from enum import Enum
from http import HTTPStatus
from types import TracebackType
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    Final,
    Optional,
    Type,
    TypeAlias,
    Literal,
)

from src.session.response import Response, ResultType
from src.session import errors as err

_JsonLoads: TypeAlias = Callable[..., Any]
_JsonDumps: TypeAlias = Callable[..., str]
_RequestMethod: TypeAlias = Literal['GET', 'POST']

DEFAULT_TIMEOUT: Final[float] = 60.0


class BaseSession(abc.ABC):

    __slots__ = ('api', 'json_loads', 'json_dumps', 'timeout',)

    def __init__(
            self,
            api: str,
            json_loads: _JsonLoads = json.loads,
            json_dumps: _JsonDumps = json.dumps,
            timeout: float = DEFAULT_TIMEOUT
    ) -> None:
       self.api = api
       self.json_loads = json_loads
       self.json_dumps = json_dumps
       self.timeout = timeout

    def check_response(
        self,
        method: _RequestMethod,
        status_code: int,
        content: Any,
        **kwargs: Any
    ) -> Response[ResultType]:
        
        # Check if content is a dictionary
        if isinstance(content, dict):
            data = content  # No need to decode, it's already a dict
        else:
            try:
                data = self.json_loads(content)
            except Exception as e:
                if method.upper() == 'GET':
                    data = content
                else:
                    raise err.ClientDecodeError("Failed to decode object", e, content)

        # Continue with status code checks
        if HTTPStatus.OK <= status_code <= HTTPStatus.IM_USED:
            return Response(
                status_code=status_code,
                result=data,
                **kwargs
            )

        # Handle specific HTTP errors as before
        if status_code == HTTPStatus.BAD_REQUEST:
            raise err.BadRequestError(
                status_code=status_code, content=data, message='Bad request'
            )
        if status_code == HTTPStatus.TOO_MANY_REQUESTS:
            raise err.TooManyRequestsError(
                status_code=status_code, content=data, message='Too many requests'
            )
        if status_code == HTTPStatus.NOT_FOUND:
            raise err.NotFoundError(
                status_code=status_code, content=data, message='Not found'
            )
        if status_code == HTTPStatus.CONFLICT:
            raise err.ConflictError(
                status_code=status_code, content=data, message='Conflict'
            )
        if status_code == HTTPStatus.UNAUTHORIZED:
            raise err.UnauthorizedError(
                status_code=status_code, content=data, message='Auth is required'
            )
        if status_code == HTTPStatus.FORBIDDEN:
            raise err.ForbiddenError(
                status_code=status_code, content=data, message='You have no permissions'
            )
        if status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE:
            raise err.EntityTooLarge(
                status_code=status_code, content=data, message='Too large content'
            )
        if status_code == HTTPStatus.INTERNAL_SERVER_ERROR:
            raise err.ServerError(
                status_code=status_code, content=data, message='Server is disabled or you are banned'
            )

        raise err.APIError(
            status_code=status_code, content=data, message='Unknown Error'
        )
        
    @abc.abstractmethod
    async def close(self) -> None:
        raise NotImplementedError
    
    @abc.abstractmethod
    async def _make_request(
        self,
        method: _RequestMethod,
        endpoint: str,
        timeout: Optional[int] = None,
        **kwargs: Any
    ) -> ResultType:
        raise NotImplementedError
    
    @abc.abstractmethod
    async def stream_content(
        self,
        url: str,
        headers: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True
    ) -> AsyncGenerator[bytes, None]:
        yield b""

    def prepare_value(
            self,
            value: Any,
            _dumps_json: bool = True
    ) -> Any:
        
        if value is None:
            return None 
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            value = {
                key: prepared_item
                for key, item in value.items()
                if (
                    prepared_item := self.prepare_value(
                        item, _dumps_json=False
                    )
                )
                is not None
            }
            if _dumps_json:
                return self.json_dumps(value)
            return value
        if isinstance(value, list):
            value = [
                prepared_item
                for item in value
                if (
                    prepared_item := self.prepare_value(
                        item, _dumps_json=False
                    )
                )
                is not None
            ]
            if _dumps_json:
                return self.json_dumps(value)
            return value
        if isinstance(value, datetime.timedelta):
            now = datetime.datetime.now()
            return str(round((now + value).timestamp()))
        if isinstance(value, datetime.datetime):
            return str(round(value.timestamp()))
        if isinstance(value, Enum):
            return self.prepare_value(value.value)
        
        if _dumps_json:
            return self.json_dumps(value)
        
        return value
    
    async def __call__(
            self, 
            method: _RequestMethod, 
            endpoint: str, 
            timeout: Optional[int] = None,
            **kwargs: Any
    ) -> ResultType:
        return await self._make_request(method=method, endpoint=endpoint, timeout=timeout, **kwargs)
    
    async def __aenter__(self) -> BaseSession:
        return self
    
    async def __aexit__(
            self,
            exc_type: Optional[Type[BaseException]],
            exc_value: Optional[BaseException],
            traceback: Optional[TracebackType],
    ) -> None:
        await self.close()
