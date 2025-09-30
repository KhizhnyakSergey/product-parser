
import re
import math
import asyncio
from typing import List, Optional, Dict, Any

from bs4 import BeautifulSoup
from aiohttp import ClientConnectorError
import cloudscraper

from src.session.aiohttp import AiohttpSession
from src.utils.user_agent import get_user_agent
from src.core.settings import load_settings
from src.utils.logger import Logger


class SupratenAPI:

    API: str = 'https://supraten.md/'

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
            'accept-language': 'ru-RU,ru;q=0.6',
        }
        self._cookies = {
            'language': 'ru-ru',
            'res_pushed': '1',
            'languagAlex': 'ru-ru',
        }

    async def __aenter__(self) -> "SupratenAPI":
        return self
    
    async def __aexit__(self, *args) -> None:
        await self._session.close()

    async def get_categories(self) -> Dict[str, Any]:


        scraper = cloudscraper.create_scraper()
        
        # self._headers['user-agent'] = get_user_agent()
        # response = await self._session(
        #     'GET', 
        #     self.API, 
        #     headers=self._headers, 
        #     cookies=self._cookies, 
        # )
        response = scraper.get(self.API)
        
        categories_data = {}
        soup = BeautifulSoup(response.text, "lxml")
        ul_element = soup.find('ul', attrs={'class': 'sp-header-menu-category__list'})
        categories = ul_element.find_all('a', attrs={'class': 'sp-header-menu-category__link'})
        
        for category in categories:
            name = category.text.strip()
            href = category.get('href').strip()
            categories_data[name] = href

        return categories_data
    
    async def get_all_urls_in_category(self, url: str):
        
        self._headers['user-agent'] = get_user_agent()
        scraper = cloudscraper.create_scraper()

        try:
            response = scraper.get(url)
            # response = await self._session(
            #     'GET', 
            #     url, 
            #     headers=self._headers, 
            # )
        except ClientConnectorError as ex:
            await asyncio.sleep(5)
            response = scraper.get(url)
            # response = await self._session(
            #     'GET', 
            #     url, 
            #     headers=self._headers, 
            # )
        

        if not response:
            return None
        
        categories_data = {}
        soup = BeautifulSoup(response.text, "lxml")
        div_cat_list = soup.find('div', attrs={'class': 'row sp-category-list'})

        if div_cat_list is None:
            # print(f"⚠️ Не найден контейнер категорий на {url}")
            return {}

        sub_categories = div_cat_list.find_all(
            'a', attrs={'class': 'sp-category-list__title'}
        )

        for category in sub_categories:
            name = category.text.strip()
            href = category.get('href').strip()

            # print(f"📌 Найдена категория: {name} -> {href}")
            self.logger.info(f"📌 Найдена категория: {name} -> {href}")
            categories_data[name] = href

            # Рекурсивно вызываем для подкатегории
            sub_data = await self.get_all_urls_in_category(href)
            categories_data.update(sub_data)  # Объединяем данные
            # if sub_data:
            #     categories_data.update(sub_data)  # Объединяем данные

        return categories_data
    
    
    async def get_all_products(self, url: str):
        self._headers['user-agent'] = get_user_agent()

        # Функция для получения HTML-контента страницы
        async def fetch_page(page: int = 1):
            scraper = cloudscraper.create_scraper()
            response = scraper.get(f'{url}?limit=90&page={page}&')
            # response = await self._session(
            #     'GET', 
            #     f'{url}?limit=90&page={page}&', 
            #     headers=self._headers, 
            # )
            
            return response.text

        # Функция для извлечения данных о продуктах со страницы
        def parse_products(soup):
            div_sp_products = soup.find('div', attrs={'class': 'sp-products'})
            if div_sp_products is None:
                return []

            links_products = div_sp_products.find_all(
                'div', attrs={'class': 'sp-show-product-vertical'}
            )
            return [product.find('a').get('href') for product in links_products]

        # Шаг 1: Получаем общее количество продуктов и количество страниц
        first_page_response = await fetch_page(page=1)
        soup = BeautifulSoup(first_page_response, "lxml")

        total_products = soup.find('span', attrs={'class': 'c-second-gray fs-14'})
        if total_products:
            digits = re.search(r'\d+', total_products.text)
            if digits:
                total_products = int(digits.group())
                # print(f"Общее количество продуктов: {total_products}")
            else:
                self.logger.info(f"Не удалось извлечь количество продуктов.")
                return []
        else:
            # print(f"Элемент с общим количеством продуктов не найден. {url}")
            return []

        # Вычисляем количество страниц
        total_pages = math.ceil(total_products / 90)
        # print(f"Количество страниц для обработки: {total_pages}")

        # Шаг 2: Собираем данные со всех страниц
        data = []
        for page in range(1, total_pages + 1):
            # print(f"Обработка страницы {page}...")
            page_response = await fetch_page(page)
            soup = BeautifulSoup(page_response, 'lxml')
            products = parse_products(soup)
            data.extend(products)

        self.logger.info(f"Собрано {len(data)} продуктов с {total_pages} страниц. | {url}")
        return data

    
    async def get_html_product(self, url: str):

        self._headers['user-agent'] = get_user_agent()
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url)
        # response = await self._session(
        #     'GET', 
        #     f'{url}', 
        #     headers=self._headers, 
        # )

        if not response:
            response = scraper.get(url)
            # response = await self._session(
            # 'GET', 
            # f'{url}', 
            # headers=self._headers, 

        # )

        return response.text


    
        # async def get_product_data(self, url: str):
        
    #     self._headers['user-agent'] = get_user_agent()

    #     response = await self._session(
    #         'GET', 
    #         f'{url}', 
    #         headers=self._headers, 
    #     )

    #     data = {}

    #     soup = BeautifulSoup(response, 'html.parser')
    #     name = soup.find('h1', attrs={'class': 'sp-single-product__title'})
    #     data['name'] = name.text.strip()

    #     articul = soup.find('div', attrs={'class': 'sp-single-product__sku'})
    #     articul = articul.text.split(':')[-1].strip()
    #     data['articul'] = articul

    #     category = soup.find_all('li', attrs={'class': 'sp-breadcrumbs__item'})
    #     data['category'] = category[-2].text.strip()

    #     img = soup.select('a[data-lightbox="product-slider"]')[0].get("href")
    #     data['img_url'] = img

    #     price = soup.find('p', attrs={'class': 'sp-single-product__price-current'})
    #     data['price'] = price.text.split('/')[0]
        
    #     characteristics = soup.select('#characteristic')[-1]
    #     table = characteristics.find('table', class_='table table-bordered')
    #     rows = table.find('tbody').find_all('tr')

    #     for row in rows:
    #         key = row.find_all('td')[0].get_text(strip=True)  # Первый <td> — ключ
    #         value = row.find_all('td')[1].get_text(strip=True)  # Второй <td> — значение
    #         data[key] = value  

    #     return data
