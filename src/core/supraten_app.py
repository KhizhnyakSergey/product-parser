import asyncio
import time
from typing import Optional, Dict, Tuple, Any
from datetime import datetime
from itertools import cycle

from python_socks._errors import ProxyError
from aiohttp import ClientConnectorError
from src.session.errors import NetworkError, ForbiddenError, APIError

# from src.binance import BinanceAPI
from src.api.supraten import SupratenAPI
from src.core.settings import Settings
from src.utils.logger import Logger
from src.utils.helper import get_proxies, data_extraction_supraten
from src.core.settings import load_settings, Settings, path
from src.utils.google import GoogleSheetsWriter



class ApplicationSupraten:

    def __init__(
            self, 
            max_concurrent_sessions: int = 10,
            settings: Optional[Settings] = None, 
            logger: Optional[Logger] = None
    ) -> None:
        self.logger = logger or Logger()
        self.settings = settings or load_settings()
        self.semaphore = asyncio.Semaphore(max_concurrent_sessions)
        self.data = [] 
        self.final_data = {}


    async def choise_category(self, category_num: int) -> Tuple[str]:

        retries = 5  # Количество попыток

        async with SupratenAPI() as ses:
            categories = None
            for attempt in range(retries):
                try:
                    categories = await ses.get_categories()  # Запрос категорий
                    break  # Если запрос успешен, выходим из цикла
                except NetworkError as e:
                    self.logger.warning(f"Попытка {attempt + 1}/{retries} не удалась: {type(e).__name__}")
                    if attempt < retries - 1:
                        await asyncio.sleep(5)  # Ждем 5 секунд перед повторной попыткой
                    else:
                        self.logger.error(f"Не удалось получить категории после {retries} попыток.")
                except Exception as e:
                    self.logger.exception(f"Непредвиденная ошибка: {type(e).__name__} -> {e}")

        categories_list = list(categories.keys())
        for idx, name in enumerate(categories_list, 1):
            self.logger.info(f"{idx}. {name}")

        # Выбор пользователем
        while True:
            try:
                choice = category_num - 1
                if 0 <= choice < len(categories_list):
                    selected_name = categories_list[choice]
                    selected_url = categories[selected_name]
                    self.logger.info(f"➡️ Вы выбрали: {selected_name} ({selected_url})")
                    return selected_name, selected_url
                else:
                    self.logger.info(f"Некорректный ввод. Попробуйте снова.")
            except ValueError:
                self.logger.info(f"Введите число!")


    async def start(self):

        
        carrent_date = datetime.now()
        formatted_date = carrent_date.strftime("%Y-%m-%d %H:%M:%S")
        to_parse = self.settings.google.supraten_index_to_parse
        self.logger.info(f'⏩Supraten⏪')
        self.logger.info(f'Початок парсингу {formatted_date} {to_parse}')
        name_list = f'Supraten {to_parse}'
        for category in to_parse:
            tasks = []

            name_category, url = await self.choise_category(category)
            
            categories = await self.get_all_urls_in_category_with_retry(url)
            # async with SupratenAPI() as ses:
            #     categories = await ses.get_all_urls_in_category(url)

            for name, url in categories.items():
                async with SupratenAPI() as api:
                    task = asyncio.create_task(self._task_all_products(api, url))
                    tasks.append(task)

            results = await asyncio.gather(*tasks)
            
            for result in results:
                self.data.extend(result)  


            self.logger.info(f'Всего товаров найдено: {len(self.data)} ...')
            tasks.clear()
            
            for count, url in enumerate(self.data, start=1):
                async with SupratenAPI() as api:
                    task = asyncio.create_task(self._task_html_data(api, url, count))
                    tasks.append(task)

            results = await asyncio.gather(*tasks)
            tasks.clear()

            for count, item in enumerate(results, start=1):
                if item is None:
                    continue  
                url, response = item
                task = asyncio.create_task(self._task_parse_html(url, response, count))
                tasks.append(task)

            await asyncio.gather(*tasks)
            # await asyncio.wait(tasks)
            self.logger.info(f'Парсинг категории {name_category} завершено ...\n')
            self.data.clear()

        self.logger.info(f'Начинаю запись в гугл таблицу...\n')
        self.logger.info(f'Всего товаров {len(self.final_data)}\n')
        rows = len(self.final_data.items())
        write = GoogleSheetsWriter(
            creds_file=path(self.settings.google.json_name),
            sheet_name=self.settings.google.table_name,
            worksheet_name=name_list,
            logger=self.logger,
            rows=rows + 100,
            cols=200
        )
        # await write.write_to_google_sheets(self.final_data)
        await write.write_to_google_sheets(self.final_data, currency='лей')
        self.final_data.clear()
        self.logger.info(f'Парсинг завершено {name_list} ...\n')
        

    
    async def _task_all_products(self, api: SupratenAPI, url: str) -> None:
        async with self.semaphore:  # Use semaphore here
            retries = 3  # Количество попыток
            for attempt in range(retries):
                try:
                    result = await api.get_all_products(url) 
                    return result if result is not None else []
                except (ClientConnectorError, NetworkError) as e:
                    if attempt < retries - 1:
                        await asyncio.sleep(6)
                        result = await api.get_all_products(url) 
                        return result if result is not None else []
                except KeyboardInterrupt:
                    self.logger.error(f'Завершение таски по запросу пользователя.')
                except Exception as e:
                    self.logger.exception(f'{type(e).__name__} -> {e}')


    async def _task_html_data(self, api: SupratenAPI, url: str, count: int) -> None:
        async with self.semaphore:  # Используем семафор
            retries = 6  # Количество попыток

            for attempt in range(retries):
                try:
                    result = await api.get_html_product(url)
                    self.logger.info(f'{count} Запрос на товар -> {url}')
                    return url, result  # Успешный запрос – сразу возвращаем
                except (ClientConnectorError, NetworkError, ForbiddenError, APIError) as e:
                    self.logger.warning(f'Попытка {attempt + 1}/{retries} не удалась: {type(e).__name__} -> {e}')
                    if attempt < retries - 1:
                        await asyncio.sleep(5)  # Ждем перед повторной попыткой
                    else:
                        self.logger.error(f'Не удалось получить данные для {url} после {retries} попыток.')
                except KeyboardInterrupt:
                    self.logger.error(f'Завершение таски по запросу пользователя.')
                    return None
                except Exception as e:
                    self.logger.exception(f'Непредвиденная ошибка: {type(e).__name__} -> {e}')
                    return None  # Прерываем попытки на критической ошибке
            return None  # Если после всех попыток не удалось получить данные

    async def _task_parse_html(self, url: str, response, count: int) -> None:

        result = await data_extraction_supraten(response) 
        self.final_data[url] = result
        await asyncio.sleep(0,3)
        self.logger.info(f' {count} Готово -> {url} ✅')

    async def get_all_urls_in_category_with_retry(self, url: str) -> Dict[str, str]:
        retries = 5  # Количество попыток
        categories = None
        for attempt in range(retries):
            try:
                # Создаем новую сессию для каждой попытки
                async with SupratenAPI() as ses:
                    # Попытка получить все URL из категории
                    categories = await ses.get_all_urls_in_category(url)
                    break  # Если запрос успешен, выходим из цикла
            except (ClientConnectorError, NetworkError, TimeoutError, APIError) as e:
                self.logger.warning(f"Попытка {attempt + 1}/{retries} не удалась: {type(e).__name__}")
                if attempt < retries - 1:
                    await asyncio.sleep(5)  # Ждем 5 секунд перед повторной попыткой
                else:
                    self.logger.error(f"Не удалось получить категории после {retries} попыток.")
            except Exception as e:
                self.logger.exception(f"Непредвиденная ошибка: {type(e).__name__} -> {e}")
        return categories
        