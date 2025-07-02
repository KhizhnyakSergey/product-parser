
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


class IEKAPI:

    API: str = 'https://www.iek.md/'

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
            'accept-language': 'ru-RU,ru;q=0.8',
        }

    async def __aenter__(self) -> "IEKAPI":
        return self
    
    async def __aexit__(self, *args) -> None:
        await self._session.close()

    async def get_categories(self) -> Dict[str, Any]:

        self._headers['user-agent'] = get_user_agent()
        
        response = await self._session(
            'GET', 
            f'{self.API}product-category/01-modulnoe-oborudovanie/', 
            headers=self._headers, 
        )
        
        soup = BeautifulSoup(response, "lxml")

        categories = {}

        for li in soup.select("ul.product-categories > li.cat-item"):  # Берем только li верхнего уровня
            a_tag = li.find("a", href=True)
            if a_tag and a_tag["href"].startswith("https://www.iek.md/product-category/"):
                category_name = a_tag.text.strip()
                category_link = a_tag["href"]
                categories[category_name] = category_link

        return categories
    
    
    async def get_all_products(self, url: str) -> List[str]:

        async def _make_request(url: str, page: int = None) -> str:
            """Универсальный метод для выполнения запроса."""
            full_url = f"{url}/page{page}/" if page else url
            self._headers['user-agent'] = get_user_agent()  # Предполагается, что get_user_agent() определен
            cookies = {'shop_per_page': '72',}
            params = {
                '_pjax': '.main-page-wrapper',
            }

            response = await self._session(
                    'GET', 
                    f'{full_url}', 
                    headers=self._headers, 
                    cookies=cookies,
                    params=params
                )
            
            return response

        async def check_page_num(url: str) -> int:

            html = await _make_request(url)
            soup = BeautifulSoup(html, "lxml")
            pages = soup.find('ul', attrs={'class': 'page-numbers'})
            if not pages:
                return 1
            
            page_links = [a["href"] for a in soup.select('a.page-numbers:not(.next)')]
            
            return 1 + len(page_links)

        
        async def fetch_page(page: int = 1) -> List[str]:

            html = await _make_request(url, page)
            soup = BeautifulSoup(html, "lxml")
            product_links = []
            for div in soup.select("div.product-list-content.wd-scroll"):
                h3 = div.select_one("h3.wd-entities-title")  # Ищем h3 внутри div
                if h3:
                    a = h3.select_one("a")  # Берем ссылку из h3
                    if a and "href" in a.attrs:
                        product_links.append(a["href"])
            
            return product_links

        number_pages = await check_page_num(url)
        data = []

        for page in range(1, number_pages + 1):
            self.logger.info(f"Собираю ссылки со страницы {page}")
            products = await fetch_page(page)
            data.extend(products)
        
        return data


    
    async def get_html_product(self, url: str):

        self._headers['user-agent'] = get_user_agent()

        response = await self._session(
            'GET', 
            f'{url}', 
            headers=self._headers, 
        )

        return response


    
    # async def get_product_data(self, url: str):
        
    #     self._headers['user-agent'] = get_user_agent()

    #     response = await self._session(
    #         'GET', 
    #         f'{url}', 
    #         headers=self._headers, 
    #     )

    #     try:
    #         tree = lxml.html.fromstring(response)

    #         title_element = tree.xpath("//h1[@class='product_title']/text()")
    #         if not title_element:
    #             return None

    #         # Извлечение артикула
    #         articul = tree.xpath("//div[@class='product_meta']//span[@class='sku']/text()")
    #         articul = articul[0].strip() if articul else None

    #         # Извлечение категории и цены
    #         category = tree.xpath("//a[contains(@class, 'breadcrumb-link-last')]/text()")
    #         price = tree.xpath("//p[@class='price']/text()")

    #         data = {
    #             "Название": title_element[0].strip(),
    #             "Артикул": articul,
    #             "Категория": category[0].strip() if category else None,
    #             "price": price[0].strip() if price else None
    #         }

    #         # Поиск блока "Технические характеристики"
    #         detail_docs = tree.xpath("//div[contains(@class, 'wc-tab-inner wd-scroll-content')]")
    #         for doc in detail_docs:
    #             if "Технические характеристики" in doc.text_content():
    #                 table = doc.xpath(".//table")[0] if doc.xpath(".//table") else None
    #                 if table:
    #                     rows = table.xpath(".//tbody/tr")
    #                     for row in rows:
    #                         key = row.xpath("./td[1]//text()")
    #                         value = row.xpath("./td[2]//text()")
    #                         if key and value:
    #                             data[key[0].strip()] = value[0].strip()
    #                         elif key:
    #                             data[key[0].strip()] = None  # Если нет значения, но есть ключ
    #                 break

    #         return data
    #     except Exception as e:
    #         print(f"Error parsing HTML: {e}")
    #         return None

    