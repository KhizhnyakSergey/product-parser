import re
import asyncio
from typing import List, Optional, Dict, Any

from bs4 import BeautifulSoup

from src.session.aiohttp import AiohttpSession
from src.utils.user_agent import get_user_agent
from src.core.settings import load_settings
from src.utils.logger import Logger


class PolevAPI:

    API: str = 'https://polev.md'

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
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'accept-language': 'ru-RU,ru;q=0.8',
        }
        self._cookies = {}

    async def __aenter__(self) -> "PolevAPI":
        return self
    
    async def __aexit__(self, *args) -> None:
        await self._session.close()

    async def _make_request(self, url: str, start: int = None) -> str:
        """Универсальный метод для выполнения запроса."""
        
        full_url = f"{url}?start={start}" if start else url
        self._headers['user-agent'] = get_user_agent() 

        response = await self._session(
                'GET', 
                full_url, 
                headers=self._headers, 
                cookies=self._cookies,
            )
        
        return response

    async def get_categories(self) -> Dict[str, Any]:

        html = await self._make_request(f'{self.API}/ru/tovary.html')
        soup = BeautifulSoup(html, "lxml")

        categories = {}
        modcontent_div = soup.find('aside', attrs={'class': 'col-md-3 col-sm-4'})
        categories_a_tags = modcontent_div.find_all('a')
        for a in categories_a_tags[:7]:  
            url = a.get('href')
            name = a.text.strip()
            if url and name:
                categories[name] = f'{self.API}{url}'
        
        return categories
        
    
    async def get_all_urls_in_category(self, url: str):
        
        html = await self._make_request(url)
        if not html:
            return None

        categories_data = {}
        soup = BeautifulSoup(html, "lxml")
        subcatalog = soup.find_all('a', attrs={'class': 'product_link'})
    
        if not subcatalog:
            if url == 'https://polev.md/ru/tovary/tools.html':
                self.logger.info(f'📌Добавил категорию: Инструменты')
                categories_data["Инструменты"] = url  
            # print('тут уже каталог товаров')
            pass
        else:
            for category in subcatalog:
                # div_name = category.find('div', attrs={'class': 'categories-page__title'})
                name = category.text.strip()
                url = category.get('href')
                categories_data[name] = f'{self.API}{url}'
                self.logger.info(f'📌Добавил категорию: {name}')

            for n,u in list(categories_data.items()):
                result = await self.get_all_urls_in_category(u)
                if result: 
                    categories_data.pop(n)
                    categories_data.update(result) 

        return categories_data


    async def check_page_num(self, url: str) -> int:
        """Определяет количество страниц с товарами через параметр start в пагинации.
        Возвращает общее количество страниц (не значение start последней страницы)."""
        
        html = await self._make_request(url)
        soup = BeautifulSoup(html, "lxml")

        table = soup.find('table', class_='jshop_pagination')
        if not table:
            return 1  # если нет пагинации - только 1 страница
        
        pages = table.find_all('a')
        if not pages:
            return 1
            
        # Получаем ссылку последней страницы
        last_page_a = pages[-1]
        last_page_url = last_page_a.get('href')
        
        # Извлекаем параметр start
        match = re.search(r'start=(\d+)', last_page_url)
        if not match:
            return 1
            
        start_value = int(match.group(1))
        page_number = (start_value // 12) + 1  # предполагаем, что шаг пагинации 12
        
        return page_number

    async def get_all_products(self, url: str) -> List[str]:
        """Собирает ссылки на все товары со всех страниц категории."""
        
        total_pages = await self.check_page_num(url)

        product_links = []
        for page in range(total_pages):
            # Формируем URL для каждой страницы
            page_url = f"{url}?start={page * 12}" if page > 0 else url
            
            try:
                html = await self._make_request(page_url)
                soup = BeautifulSoup(html, "lxml")
                products = soup.find_all('td', class_='block_product')
                
                for product in products:
                    div_name = product.find('div', class_='name')
                    a_tag = div_name.find('a')
                    product_url = a_tag.get('href')
                    if product_url:
                        product_links.append(f'{self.API}{product_url}')
                        
            except Exception as e:
                self.logger.error(f"Error processing page {page + 1}: {str(e)}")
                continue
                
        return product_links


    async def get_html_product(self, url: str):

        response = await self._make_request(url)

        return response
