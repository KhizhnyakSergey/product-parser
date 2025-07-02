
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


class HabsevAPI:

    API: str = 'https://habsev.md'

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
            'accept-language': 'ru-RU,ru;q=0.7',
        }
        self._cookies = {
            'firstVisit': 'true',
            'i18n_redirected': 'ru',
            'language': 'ru',
            'user-theme': 'light-theme',
            'first_lang_visit': 'true',
            'getPreviousLocale': 'ru',
        }

    async def __aenter__(self) -> "HabsevAPI":
        return self
    
    async def __aexit__(self, *args) -> None:
        await self._session.close()

    async def get_categories(self) -> Dict[str, Any]:

        categories = {
            'Электрические кабели и провода': 'https://habsev.md/ru/cabluri-electrice-si-conductoare',
            'Кабельные системы позиционирования и аксессуары': 'https://habsev.md/ru/accesorii-cablu',
            'Коробки распределительные,электрощитки и аксессуары': 'https://habsev.md/ru/doze-si-tablouri-electrice',
            'Защита электрических цепей': 'https://habsev.md/ru/protectie-si-comutare',
            'Розетки и выключатели': 'https://habsev.md/ru/prize-si-intrerupatoare-1',
            'Контрольно-измерительное оборудование': 'https://habsev.md/ru/scule-si-aparate-de-masura',
            'Освещение': 'https://habsev.md/ru/iluminat',
            'Электрическое отопление': 'https://habsev.md/ru/incalzire-electrica',
            'Средства индивидуальной защиты': 'https://habsev.md/ru/echipament-de-protectie',
            'Заземление / Громоотвод': 'https://habsev.md/ru/impamantare-paratrasnet',
            'Зарядные станции': 'https://habsev.md/ru/statie-de-incarcare',
            'Оборудование для бесперебойного питания': 'https://habsev.md/ru/echipament-electric-de-protectie',
            'Уличное освещение': 'https://habsev.md/ru/iluminat-stradal-lea',
            'Концевые и соединительные муфты до 1 кВ': 'https://habsev.md/ru/recloser',
            'Оборудование 6-35 кВ': 'https://habsev.md/ru/posturi-si-transformatoare',
            'Фотоэлектрические системы': 'https://habsev.md/ru/sisteme-fotovoltaice',
        }
    
        return categories
    
    async def get_all_urls_in_category(self, url: str):
        
        self._headers['user-agent'] = get_user_agent()

        try:
            response = await self._session(
                'GET', 
                url, 
                headers=self._headers, 
                cookies=self._cookies,
            )
        except ClientConnectorError as ex:
            await asyncio.sleep(5)
            response = await self._session(
                'GET', 
                url, 
                headers=self._headers,
                cookies=self._cookies, 
            )
        

        if not response:
            return None
        
        categories_data = {}
        soup = BeautifulSoup(response, "lxml")

        subcatalog = soup.find_all('a', attrs={'class': 'subcatalog__item'})
        if not subcatalog:
            # print('тут уже каталог товаров')
            pass
        else:
            for x in subcatalog:
                name = x.find('div', attrs={'class': 'title'}).text.strip()
                url = x.get('href')
                categories_data[name] = url
                self.logger.info(f'📌Добавил категорию: {name}')
                # print(name, url)

            for n,u in list(categories_data.items()):
                result = await self.get_all_urls_in_category(u)
                if result:  # Проверяем, что результат не пустой
                    # print(f'Del {n}')
                    categories_data.pop(n)
                    categories_data.update(result) 


        return categories_data

    
    
    async def get_all_products(self, url: str) -> List[str]:

        async def _make_request(url: str, page: int = None) -> str:
            """Универсальный метод для выполнения запроса."""
            # full_url = f"https://admin.ecom.md/general/v2/category/{url}/" if page else url
            full_url = f"{url}?page={page}" if page else url
            self._headers['user-agent'] = get_user_agent()  
            # if page:
            #     headers = {
            #         'accept': 'application/json, text/plain, */*',
            #         'accept-language': 'ru',
            #         'origin': 'https://habsev.md',
            #         'priority': 'u=1, i',
            #         'token': 'gmr0nwt*yur3tnu_CKG',
            #     }
            #     params = {
            #         'page': '1',
            #         'sortBy': 'sort_priority-',
            #     }
            response = await self._session(
                    'GET', 
                    f'{full_url}', 
                    headers=self._headers, 
                    cookies=self._cookies,
                )
            
            return response

        async def check_page_num(url: str) -> int:

            html = await _make_request(url)
            soup = BeautifulSoup(html, "lxml")

            pagination_items = soup.find_all('li', class_='pagination__item')
            next_button = soup.find('span', class_='pagination__button-text', text='Следующая')

            if next_button:
                next_item = next_button.find_parent('li', class_='pagination__item')
                next_index = pagination_items.index(next_item)
                previous_item = pagination_items[next_index - 1]
                page_number = int(previous_item.get_text(strip=True))
                # self.logger.info(f'Общее количество страниц: {page_number}')
                return page_number
            else:
                # self.logger.info(f'Общее количество страниц: 1')
                return 1
        
        async def fetch_page(url: str, page: int = 1) -> List[str]:

            html = await _make_request(url, page)
            soup = BeautifulSoup(html, "lxml")
            product_links = []
            products = soup.find_all('div', attrs={'class': 'product__item'})
            
            for div in products:
                url = div.find('a').get('href')
                product_links.append(f'{self.API}{url}')

            return product_links

        number_pages = await check_page_num(url)
        data = []

        for page in range(1, number_pages + 1):
            products = await fetch_page(url, page)
            data.extend(products)
        
        return data


    
    async def get_html_product(self, url: str):

        self._headers['user-agent'] = get_user_agent()

        response = await self._session(
            'GET', 
            f'{url}', 
            headers=self._headers, 
            cookies=self._cookies,
        )

        return response



    