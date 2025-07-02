
import re
import math
import asyncio
import lxml.html
from typing import List, Optional, Dict, Any

from bs4 import BeautifulSoup
from aiohttp import ClientConnectorError

from src.session.aiohttp import AiohttpSession
from src.session.errors import ServerError
from src.utils.user_agent import get_user_agent
from src.core.settings import load_settings
from src.utils.logger import Logger


class LuminaledAPI:

    API: str = 'https://luminaled.md/'

    def __init__(
            self, 
            tasks_starts_at_once: int = 100, 
            proxy: Optional[str] = None,
            logger: Optional[Logger] = None
    ) -> None:
        self._session = AiohttpSession(api=self.API, proxy=proxy)
        self._semaphore = asyncio.Semaphore(tasks_starts_at_once)
        self.settings = load_settings()
        self.logger = logger or Logger()
        self._headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.8',
        }
        self._cookies = {
            'language': 'ru-ru',
            'currency': 'MDL',
        }

    async def __aenter__(self) -> "LuminaledAPI":
        return self
    
    async def __aexit__(self, *args) -> None:
        await self._session.close()

    async def _make_request(self, url: str, page: int = None) -> str:
        """Универсальный метод для выполнения запроса."""
        full_url = f"{url}&limit=1000" if page else url
        self._headers['user-agent'] = get_user_agent()  # Предполагается, что get_user_agent() определен

        response = await self._session(
                'GET', 
                f'{full_url}', 
                headers=self._headers, 
                cookies=self._cookies
            )
        
        return response

    async def get_categories(self) -> Dict[str, Any]:

        html = await self._make_request('https://luminaled.md/index.php?route=common/home')
        soup = BeautifulSoup(html, "lxml")

        categories = {}

        main_div = soup.find('div', attrs={'class': 'sidebar__wrap rounded-10 box-shadow'})
        ul = main_div.find('ul', attrs={'class': 'links-nav__list list-unstyled ms-0 ps-0'})
        cat_li = ul.find_all('li', attrs={'class': 'links-nav__item'})
        
        for a in cat_li:  
            url = a.find("a").get('href')
            name = a.find("a").text.strip()
            if url and name:
                categories[name] = url
        
        to_del = ['На скидках', 'Бренды']
        for category in to_del:
            categories.pop(category)
            
        return categories
    
    async def get_all_urls_in_category(self, url: str):
        
        try:
            html = await self._make_request(url)
        except (ClientConnectorError, ServerError) as e:
            html = await self._make_request(url)
        if not html:
            return None

        categories_data = {}
        soup = BeautifulSoup(html, "lxml")

        subcatalog = soup.find_all('h3', attrs={'class': 'category-list__title fs-6 fw-semi-bold'})
        if not subcatalog:
            # print('тут уже каталог товаров')
            pass
        else:
            for category in subcatalog:
                a = category.find('a', attrs={'class': 'link-dark text-decoration-none'})
                name = a.text.strip()
                url = a.get('href')
                categories_data[name] = url
                self.logger.info(f'📌Добавил категорию: {name}')

            for n,u in list(categories_data.items()):
                result = await self.get_all_urls_in_category(u)
                if result: 
                    categories_data.pop(n)
                    categories_data.update(result) 

        return categories_data

    
    
    async def get_all_products(self, url: str) -> List[str]:

        html = await self._make_request(url, 1)
        soup = BeautifulSoup(html, "lxml")

        product_links = []
        main_div = soup.find('div', attrs={'class': 'row flex-wrap toggleGrid mb-4 products'})
        products = main_div.find_all('a', attrs={'class': 'link-dark text-decoration-none'})
        
        for a in products:
            url = a.get('href')
            product_links.append(url)

        return product_links



    async def get_html_product(self, url: str):

        self._headers['user-agent'] = get_user_agent()

        response = await self._session(
            'GET', 
            f'{url}', 
            headers=self._headers, 
            cookies=self._cookies,
        )

        return response



    