import asyncio
import json
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


class CabluAPI:

    API: str = 'https://cablu.md'

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
            'Accept-Language': 'ru-RU,ru;q=0.5',
        }
        self._cookies = {
            'currency': 'MDL',
            'language': 'ru',
        }

    async def __aenter__(self) -> "CabluAPI":
        return self
    
    async def __aexit__(self, *args) -> None:
        await self._session.close()

    async def _make_request(self, url: str, page: int = None) -> str:
        """Универсальный метод для выполнения запроса."""
        
        full_url = f"{url}?limit=100&page={page}" if page else url
        self._headers['user-agent'] = get_user_agent() 
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

        # Находим все элементы верхнего уровня меню
        main_categories = soup.select('ul.display-menu > li.menu_item.level-1')

        for category in main_categories:
            # Извлекаем название основной категории
            category_name = category.select_one('a.title_menu_parent span').text.strip()
            
            # Находим все подкатегории (ссылки внутри dropdown)
            subcategories = []
            for link in category.select('div.edropdown a.parent'):
                subcategories.append(link['href'])
            
            # Добавляем в результат, если есть подкатегории
            if subcategories:
                categories[category_name] = subcategories

        # Форматируем вывод как JSON
        formatted_result = json.dumps(categories, ensure_ascii=False, indent=2)
        # print(formatted_result)
        
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

            # with open(f"debug_{1}.html", 'w', encoding='utf-8') as f:
            #     f.write(html)
            products_ul = soup.find('ul', id='product-list-grid')
            if not products_ul:
                break

            products = products_ul.find_all('div', class_='name')
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
