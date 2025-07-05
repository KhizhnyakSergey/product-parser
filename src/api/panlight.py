import asyncio
from typing import (
    List, 
    Optional,
    Dict, 
    Any,
)

from bs4 import BeautifulSoup

from src.session.aiohttp import AiohttpSession
from src.utils.user_agent import get_user_agent
from src.core.settings import load_settings
from src.utils.logger import Logger


class PanlightAPI:

    API: str = 'https://www.panlight.md/ru'

    def __init__(
            self, 
            tasks_starts_at_once: int = 50, 
            proxy: Optional[str] = None,
            logger: Optional[Logger] = None
    ) -> None:
        self._session = AiohttpSession(api=self.API, proxy=proxy)
        self._semaphore = asyncio.Semaphore(tasks_starts_at_once)
        self.settings = load_settings()
        self.logger = logger or Logger()
        self._headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.7',
        }
        self._cookies = {}

    async def __aenter__(self) -> "PanlightAPI":
        return self
    
    async def __aexit__(self, *args) -> None:
        await self._session.close()

    async def _make_request(self, url: str, page: int = None) -> str:
        """Универсальный метод для выполнения запроса."""
        
        full_url = f"{url}?page={page}" if page else url
        self._headers['user-agent'] = get_user_agent() 
        if page:
            self._cookies['count_per_page'] = (
                'eyJpdiI6ImpmMlNxdnFaeE01MHpSRXdEQmdCeXc9PSIsInZhbHVlIjoiUG9DQ2RCelEzdFZsc2xPN3ll'
                'bk1mWkJORGQyanAvMGV1Q0E5ais0cHlXMTM3VFFkUFF6TzlEd1VyUUd3MGw0TCIsIm1hYyI6IjU2OGZh'
                'NjRlNDBlNjAxMmU5N2UzY2E2ZDY4ODhkMWViY2FiYzU5OTcxM2IzYWYyODNkZDI1M2Q3NWNmNTgxYWQi'
                'LCJ0YWciOiIifQ%3D%3D'
            )
        response = await self._session(
                'GET', 
                full_url, 
                headers=self._headers, 
                cookies=self._cookies,
            )
        
        return response

    async def get_categories(self) -> Dict[str, Any]:

        html = await self._make_request(self.API)
        soup = BeautifulSoup(html, "lxml")

        categories = {}

        categories_a_tags = soup.find_all('a', attrs={'class': 'header-catalog-main'})
        for a in categories_a_tags:  
            url = a.get('href')
            name = a.text.strip()
            if url and name:
                categories[name] = url
        
        return categories
    
    async def get_all_urls_in_category(self, url: str):
        
        html = await self._make_request(url)
        if not html:
            return None

        categories_data = {}
        soup = BeautifulSoup(html, "lxml")
        subcatalog = soup.find_all('a', attrs={'class': 'catalog-categories-item'})
    
        if not subcatalog:
            # print('тут уже каталог товаров')
            pass
        else:
            for category in subcatalog:
                div_name = category.find('h3')
                name = div_name.text.strip()
                url = category.get('href')
                categories_data[name] = f'{url}'
                self.logger.info(f'📌Добавил категорию: {name}')

            # for n,u in list(categories_data.items()):
            #     result = await self.get_all_urls_in_category(u)
            #     if result: 
            #         categories_data.pop(n)
            #         categories_data.update(result) 

        return categories_data

    async def check_page_num(self, url: str) -> List[Any]:

        html = await self._make_request(url)
        soup = BeautifulSoup(html, "lxml")

        products = soup.find_all('a', class_='product-card__description')
        if not products:
            end = url.split('/')[-1]
            html = await self._make_request(f'{url}/{end}')
            soup = BeautifulSoup(html, "lxml")
            url = f'{url}/{end}'
        
        # with open(f"debug_{enn}.html", 'w', encoding='utf-8') as f:
        #     f.write(html)

        # Находим блок пагинации
        pagination = soup.find('div', class_='pagination-bar')
        if not pagination:
            print(f"Пагинация не найдена для URL: {url}")
            return None

        # Ищем все кнопки страниц внутри nav-buttons__wrapper
        nav_buttons_wrapper = pagination.find('div', class_='nav-buttons__wrapper')
        if not nav_buttons_wrapper:
            print(f"Блок кнопок не найден для URL: {url}")
            return None

        # Извлекаем все элементы пагинации
        pages = nav_buttons_wrapper.find_all('div', class_='nav-button')
        last_page_div = pages[-1]
        last_page = last_page_div.get_text(strip=True)

        return [int(last_page), url]

    
    async def get_all_products(self, url: str) -> List[str]:
        
        # pages, valid_href = await self.check_page_num(url)
        # self.logger.info(f'** {url}  Pages ->  {pages} {valid_href}')

        product_links = []
        for page in range(100):
            html = await self._make_request(url, page + 1)
            soup = BeautifulSoup(html, "lxml")
            products = soup.find_all('div', class_='goods-item-content')
            if not products:
                # self.logger.info(f'PAge not found... no products {page + 1}')
                break
            
            for div in products:
                a_tag = div.find('a')
                href = a_tag.get('href')
                product_links.append(f'{href}')

        # self.logger.info(f'{url} products -> {len(product_links)}')
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
