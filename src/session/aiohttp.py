from __future__ import annotations

import asyncio
import ssl
import json
from typing import (
    Any,
    AsyncGenerator,
    Dict,
    Iterable,
    List,
    TypeAlias,
    Optional,
    Tuple,
    Type,
    Union,
    cast,
)

import certifi
from pydantic import BaseModel
from aiohttp import (
    BasicAuth,
    ClientError,
    ClientSession,
    TCPConnector,
    FormData,
)

from src.session.response import ResultType, Response
from src.session.base import _RequestMethod, BaseSession
from src.session import errors as err


_ProxyBasic: TypeAlias = Union[str, Tuple[str, BasicAuth]]
_ProxyChain: TypeAlias = Iterable[_ProxyBasic]
_ProxyType: TypeAlias = Union[_ProxyChain, _ProxyBasic]


def _retrieve_basic(basic: _ProxyBasic) -> Dict[str, Any]:
    from aiohttp_socks.utils import parse_proxy_url  # type: ignore

    proxy_auth: Optional[BasicAuth] = None

    if isinstance(basic, str):
        proxy_url = basic
    else:
        proxy_url, proxy_auth = basic

    proxy_type, host, port, username, password = parse_proxy_url(proxy_url)
    if isinstance(proxy_auth, BasicAuth):
        username = proxy_auth.login
        password = proxy_auth.password

    return {
        "proxy_type": proxy_type,
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "rdns": True,
    }


def _prepare_connector(
        chain_or_plain: _ProxyType
) -> Tuple[Type["TCPConnector"], Dict[str, Any]]:

    from aiohttp_socks import (  # type: ignore
        ChainProxyConnector,
        ProxyConnector,
        ProxyInfo,
    )

    if isinstance(chain_or_plain, str) or (
        isinstance(chain_or_plain, tuple) and len(chain_or_plain) == 2
    ):
        chain_or_plain = cast(_ProxyBasic, chain_or_plain)
        return ProxyConnector, _retrieve_basic(chain_or_plain)

    chain_or_plain = cast(_ProxyChain, chain_or_plain)
    infos: List[ProxyInfo] = []
    for basic in chain_or_plain:
        infos.append(ProxyInfo(**_retrieve_basic(basic)))

    return ChainProxyConnector, {"proxy_infos": infos}


class AiohttpSession(BaseSession):

    def __init__(self, proxy: Optional[_ProxyType] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._session: Optional[ClientSession] = None
        self._connector_type: Type[TCPConnector] = TCPConnector
        self._connector_init: Dict[str, Any] = {
            "ssl": ssl.create_default_context(cafile=certifi.where())
        }
        self._should_reset_connector = True
        self._proxy = proxy
        if proxy is not None:
            try:
                self._setup_proxy_connector(proxy)
            except ImportError as exc:  
                raise RuntimeError(
                    "In order to use aiohttp client for proxy requests, install "
                    "https://pypi.org/project/aiohttp-socks/"
                ) from exc
            
    def _setup_proxy_connector(self, proxy: _ProxyType) -> None:
        self._connector_type, self._connector_init = _prepare_connector(proxy)
        self._proxy = proxy
    
    @property
    def proxy(self) -> Optional[_ProxyType]:
        return self._proxy
    
    @proxy.setter
    def proxy(self, value: _ProxyType) -> None:
        self._setup_proxy_connector(value)
        self._should_reset_connector = True
    
    def build_data(self, method: Union[BaseModel, Dict[str, Any]]) -> Union[FormData, bytes, str]:
        form = FormData()
        if isinstance(method, BaseModel):
            method = method.model_dump(
                warnings=False, 
                exclude_none=True, 
                exclude_unset=True
            )
        elif isinstance(method, bytes):
            return method
        elif isinstance(method, dict):
            pass
        elif isinstance(method, str):
            return method
        else:
            raise err.NotValidMethodError(f'Expected BaseModel instance, dict, str or bytes, not {type(method)}')
        for key, value in method.items():
            value = self.prepare_value(value)
            if not value:
                continue
            form.add_field(key, value)

        return form

    async def create_session(self) -> ClientSession:

        if self._should_reset_connector:
            await self.close()
        
        if self._session is None or self._session.closed:
            self._session = ClientSession(
                connector=self._connector_type(**self._connector_init)
            )
            self._should_reset_connector = False
        
        return self._session
    
    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
    
    async def _make_request(
            self, 
            method: _RequestMethod,
            endpoint: str,
            timeout: Optional[int] = None,
            **kwargs: Any
    ) -> ResultType:
        
        session = await self.create_session()
        if method == 'POST':
            if 'data' in kwargs:
                kwargs['data'] = self.build_data(kwargs.get('data', {}))
                if 'json' in kwargs:
                    del kwargs['json']  
            # kwargs['data'] = self.build_data(kwargs.get('data', {}))
        if '://' in endpoint:
            url = endpoint
        else:
            url = self.api + endpoint
        methods = {
            'GET': session.get,
            'POST': session.post
        }
        try:
            async with methods[method.upper()](
                url=url, timeout=self.timeout if timeout is None else timeout, **kwargs
            ) as resp:
                raw_result = await resp.text()
                # raw_result = await resp.json()
        except asyncio.TimeoutError:
            raise err.NetworkError('Request timeout error')
        except ClientError as e:
            raise err.NetworkError(f'{type(e).__name__}: {e}')
        
        response: Response[ResultType] = self.check_response(
            method=method, status_code=resp.status, content=raw_result
        )

        await session.close() # close session

        return cast(ResultType, response.result)
    
    async def stream_content(
            self, 
            url: str, 
            headers: Optional[Dict[str, Any]] = None, 
            timeout: int = 30, 
            chunk_size: int = 65536, 
            raise_for_status: bool = True
    ) -> AsyncGenerator[bytes, None]:
        
        if headers is None:
            headers = {}

        session = await self.create_session()

        async with session.get(
            url, timeout=timeout, headers=headers, raise_for_status=raise_for_status
        ) as resp:
            async for chunk in resp.content.iter_chunked(chunk_size):
                yield chunk

    async def __aenter__(self) -> AiohttpSession:
        await self.create_session()
        return self
    