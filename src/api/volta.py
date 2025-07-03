
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


class VoltaAPI:

    API: str = 'https://volta.md'

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
        self._cookies = {
            'G_ENABLED_IDPS': 'google',
        }

    async def __aenter__(self) -> "VoltaAPI":
        return self
    
    async def __aexit__(self, *args) -> None:
        await self._session.close()

    async def _make_request(self, url: str, page: int = None) -> str:
        """Универсальный метод для выполнения запроса."""
        
        full_url = f"{url}?page={page}" if page else url
        self._headers['user-agent'] = get_user_agent() 

        response = await self._session(
                'GET', 
                full_url, 
                headers=self._headers, 
                cookies=self._cookies,
            )
        
        return response

    async def get_categories(self) -> Dict[str, Any]:

        categories = {
            "Освещение": "https://volta.md/ru/categorie-produs/iluminare",
            "Кабель и провод": "https://volta.md/ru/categorie-produs/cablu",
            "Выключатели, розетки и контакторы": "https://volta.md/ru/categorie-produs/intrerupatoare-prize-si-contactoare",
            "Щиты и измерительные приборы": "https://volta.md/ru/categorie-produs/panouri-evidenta-si-aparate-de-masura",
            "Электроинструменты и сварочное оборудование": "https://volta.md/ru/categorie-produs/scule-electrice-si-echipament-de-sudat",
            "Генераторы, компрессоры и насосы": "https://volta.md/ru/categorie-produs/generatoarecompresoare-si-pompe",
            "Стабилизаторы и трансформаторы": "https://volta.md/ru/categorie-produs/stabilizatoare-transformatoare-si-ups",
            "Сад и огород": "https://volta.md/ru/categorie-produs/gradinarit-si-inventar-agricol",
            "Вентиляция, климат и сантехника": "https://volta.md/ru/categorie-produs/ventilareclima-si-instalatii-sanitare",
            "Оборудование и строительство": "https://volta.md/ru/categorie-produs/motoare-si-utilaj-pentru-constructii",
            "Ручные инструменты": "https://volta.md/ru/categorie-produs/scule-manuale",
            "Крепежи и расходники": "https://volta.md/ru/categorie-produs/elemente-de-fixare-si-consumabile",
            "Спецодежда и СИЗ": "https://volta.md/ru/categorie-produs/haine-si-echipament-de-protectie",
            "Системы безопасности": "https://volta.md/ru/categorie-produs/sisteme-de-securitate",
            "Автотранспорт и аксессуары": "https://volta.md/ru/categorie-produs/piese-si-accesorii-auto",
            "Бытовая техника и хозтовары": "https://volta.md/ru/categorie-produs/marfuri-si-tehnica-de-uz-casnic",
            "Солнечные панели и аксессуары": "https://volta.md/ru/categorie-produs/panouri-fotovoltaice-si-accesorii",
            "Отдых и кемпинг": "https://volta.md/ru/categorie-produs/odihna-si-camping",

        }  
        
        return categories
    
    async def get_all_urls_in_category(self, url: str):
        

        html = await self._make_request(url)
        if not html:
            return None

        categories_data = {}
        soup = BeautifulSoup(html, "lxml")
        subcatalog = soup.find_all('a', attrs={'class': 'categories-page__item'})
    
        if not subcatalog:
            # print('тут уже каталог товаров')
            pass
        else:
            for category in subcatalog:
                div_name = category.find('div', attrs={'class': 'categories-page__title'})
                name = div_name.text.strip()
                url = category.get('href')
                categories_data[name] = f'{self.API}{url}'
                self.logger.info(f'📌Добавил категорию: {name}')

            for n,u in list(categories_data.items()):
                result = await self.get_all_urls_in_category(u)
                if result: 
                    categories_data.pop(n)
                    categories_data.update(result) 

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
        
        pages, valid_href = await self.check_page_num(url)
        # self.logger.info(f'** {url}  Pages ->  {pages} {valid_href}')

        product_links = []
        for page in range(pages):

            html = await self._make_request(valid_href, page + 1)
            soup = BeautifulSoup(html, "lxml")
            products = soup.find_all('a', class_='product-card__description')

            for a in products:
                url = a.get('href')
                product_links.append(f'{self.API}{url}')

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
