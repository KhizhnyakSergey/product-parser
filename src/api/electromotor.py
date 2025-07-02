
import re
import math
import asyncio
import lxml.html
from typing import List, Optional, Dict, Any

from bs4 import BeautifulSoup
from aiohttp import ClientConnectorError

from src.session.aiohttp import AiohttpSession
from src.utils.user_agent import get_user_agent
from src.core.settings import load_settings
from src.utils.logger import Logger


class ElectromotorAPI:

    API: str = 'https://electromotor.md/ru/'

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
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'accept-language': 'ru-RU,ru;q=0.9',
        }
        self._cookies = {
            'qtrans_front_language': 'ru',
        }

    async def __aenter__(self) -> "ElectromotorAPI":
        return self
    
    async def __aexit__(self, *args) -> None:
        await self._session.close()

    async def _make_request(self, url: str, page: int = None) -> str:
        """Универсальный метод для выполнения запроса."""
        full_url = f"{url}page/{page}/" if page else url
        self._headers['user-agent'] = get_user_agent()  # Предполагается, что get_user_agent() определен

        response = await self._session(
                'GET', 
                f'{full_url}', 
                headers=self._headers, 
                cookies=self._cookies,
            )
        
        return response

    async def get_categories(self) -> Dict[str, Any]:

        html = await self._make_request('https://electromotor.md/ru/catalog/')
        soup = BeautifulSoup(html, "lxml")

        categories = {}

        categories_div = soup.find_all('div', attrs={'class': 'product-category'})
        for category in categories_div:  
            url = category.find("a", attrs={'class': 'category-link'}).get('href')
            name = category.find("h3", ).text.strip()
            if url and name:
                categories[name] = url
            
        return categories
    
    async def get_all_urls_in_category(self, url: str):
        
        try:
            html = await self._make_request(url)
        except ClientConnectorError:
            html = await self._make_request(url)
        if not html:
            return None

        categories_data = {}
        soup = BeautifulSoup(html, "lxml")

        subcatalog = soup.find_all('div', attrs={'class': 'product-category'})
        if not subcatalog:
            # print('тут уже каталог товаров')
            pass
        else:
            for category in subcatalog:
                a = category.find('a', attrs={'class': 'category-link'})
                name = category.find('h3', attrs={'class': 'category-title'}).text.strip()
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

        first_html = await self._make_request(url)
        soup = BeautifulSoup(first_html, "lxml")
        pagination = soup.find('nav', attrs={'class': 'woocommerce-pagination'})
        if pagination:
            pages = pagination.find_all('a', attrs={'class': 'page-numbers'})
            num_pages = int(pages[-2].text)
        else:
            num_pages = 1


        product_links = []
        
        for page in range(0, num_pages):
            html = await self._make_request(url, page + 1)
            soup = BeautifulSoup(html, "lxml")
            self.logger.info(f'{url}page/{page + 1}/')
            products = soup.find_all('h3', attrs={'class': 'product-title'})
            for elem in products:
                url_a = elem.find('a').get('href')
                product_links.append(url_a)

        return product_links



    async def get_html_product(self, url: str):

        html = await self._make_request(url)

        return html



    