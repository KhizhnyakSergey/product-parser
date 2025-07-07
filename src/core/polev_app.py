import asyncio
import random
from typing import Optional, Dict, Tuple
from datetime import datetime

from aiohttp import ClientConnectorError

from src.api.polev import PolevAPI
from src.core.settings import load_settings, Settings, path
from src.parser.polev_bs4 import data_extraction
from src.utils.logger import Logger
from src.utils.google import GoogleSheetsWriter
from src.session.errors import (
    NetworkError, 
    NotFoundError, 
    APIError, 
    ServerError,
)


class ApplicationPolev:
    
    def __init__(
            self, 
            max_concurrent_sessions: int = 15,
            settings: Optional[Settings] = None, 
            logger: Optional[Logger] = None
    ) -> None:
        self.logger = logger or Logger()
        self.settings = settings or load_settings()
        self.semaphore = asyncio.Semaphore(max_concurrent_sessions)
        self.data = [] 
        self.final_data = {}


    async def choise_category(self, category_num: int) -> Tuple[str]:

        retries = 3  
        async with PolevAPI() as ses:
            categories = None
            for attempt in range(retries):
                try:
                    categories = await ses.get_categories()  
                    break  # Если запрос успешен, выходим из цикла
                except (ClientConnectorError, NetworkError, TimeoutError, APIError) as e:
                    self.logger.warning(f"{attempt + 1}/{retries} Ошибка: {type(e).__name__}")
                    if attempt < retries - 1:
                        await asyncio.sleep(5)  
                    else:
                        self.logger.error(f"Не удалось получить категории.")
                except Exception as e:
                    self.logger.exception(f"Непредвиденная ошибка: {type(e).__name__} -> {e}")

        categories_list = list(categories.items())
        if not 1 <= category_num <= len(categories_list):
            return 'None', 'https://www.google.com/'

        selected_name, selected_url = categories_list[category_num - 1]
        self.logger.info(f"➡️ Выбрано: {selected_name} ({selected_url})")
        return selected_name, selected_url


    async def _task_html_data(self, url: str, count: int) -> None:
        async with self.semaphore:  # Use semaphore here
            retries = 5  # Количество попыток
            for attempt in range(retries):
                async with PolevAPI() as api:
                    try:
                        result = await api.get_html_product(url)
                        self.logger.info(f'{count} Запрос на товар -> {url}')
                        return url, result 
                    except (ClientConnectorError, NetworkError, NotFoundError, APIError) as e:
                        if attempt < retries - 1:
                            self.logger.info(f'{count} ({attempt})Повторный запрос на товар -> {url}')
                            await asyncio.sleep(5)
                    except KeyboardInterrupt:
                        self.logger.error(f'Завершение таски по запросу пользователя.')
                    except Exception as e:
                        self.logger.exception(f'{type(e).__name__} -> {e}')
        

    async def _task_parse_html(self, url: str, response, count: int) -> None:
        async with asyncio.Semaphore(100):
            result = await data_extraction(response) 
            self.final_data[url] = result
            await asyncio.sleep(0,3)
            self.logger.info(f' {count} Готово -> {url} ✅')


    async def _task_all_products(self, url: str) -> None:
        async with self.semaphore:  # Use semaphore here
            retries = 3  # Количество попыток
            for attempt in range(retries):
                async with PolevAPI() as api:
                    try:
                        result = await api.get_all_products(url) 
                        self.logger.info(f'Спарсил страницы -> {url} ✅')
                        return result if result is not None else []
                    except (ClientConnectorError, NetworkError, TimeoutError, APIError) as e:
                        if attempt < retries - 1:
                            retry_delay = random.uniform(2.0, 4.0)
                            self.logger.warning(
                                f'({attempt + 1}/{retries}) Повтор через {retry_delay:.1f} сек. Ошибка: {type(e).__name__}'
                            )
                    except KeyboardInterrupt:
                        self.logger.error(f'Завершение таски по запросу пользователя.')
                    except Exception as e:
                        self.logger.exception(f'{type(e).__name__} -> {e}')
        

    async def get_all_urls_in_category_with_retry(self, url: str) -> Dict[str, str]:
        retries = 3  
        categories = None
        for attempt in range(retries):
            try:
                async with PolevAPI() as ses:
                    categories = await ses.get_all_urls_in_category(url)
                    return categories
            except (ClientConnectorError, 
                    NetworkError, 
                    TimeoutError, 
                    APIError, 
                    ServerError
                ) as e:
                self.logger.warning(f"Попытка {attempt + 1}/{retries} не удалась: {type(e).__name__}")
                if attempt < retries - 1:
                    await asyncio.sleep(4)  
                else:
                    self.logger.error(f"Не удалось получить категории после {retries} попыток.")
            except Exception as e:
                self.logger.exception(f"Непредвиденная ошибка: {type(e).__name__} -> {e}")
        return None
    

    async def _task_html_to_data(self, url: str, count: int) -> tuple[str, str] | None:
        async with self.semaphore:
            retries = 3
            for attempt in range(retries):
                async with PolevAPI() as api:
                    try:
                        await asyncio.sleep(random.uniform(0.1, 1.3))
                        response = await api.get_html_product(url)
                        if response:
                            data = await data_extraction(response) 
                        else:
                            continue
                        self.final_data[url] = data
                        self.logger.info(f' {count} Готово -> {url} ✅')
                        return True
                    except (ClientConnectorError, NetworkError, NotFoundError, APIError) as e:
                        if attempt < retries - 1:
                            retry_delay = random.uniform(3.0, 5.0)
                            self.logger.warning(
                                f'{count} ({attempt + 1}/{retries}) Повтор через {retry_delay:.1f} сек. Ошибка: {type(e).__name__}'
                            )
                            await asyncio.sleep(retry_delay)
                            continue
                        self.logger.error(f'{count} Превышены попытки для {url}')
                    except KeyboardInterrupt:
                        self.logger.error("Остановлено пользователем")
                        raise
                    except Exception as e:
                        self.logger.exception(f'{count} Критическая ошибка: {type(e).__name__}')
                        if attempt == retries - 1:  
                            return None
        
        return None
    

    async def start(self):

        carrent_date = datetime.now()
        formatted_date = carrent_date.strftime("%Y-%m-%d %H:%M:%S")
        to_parse = self.settings.google.polev_index_to_parse
        name_list = f'Polev {to_parse}'
        self.logger.info(r'''
        .______     ______    __       _______ ____    ____ 
        |   _  \   /  __  \  |  |     |   ____|\   \  /   / 
        |  |_)  | |  |  |  | |  |     |  |__    \   \/   /  
        |   ___/  |  |  |  | |  |     |   __|    \      /   
        |  |      |  `--'  | |  `----.|  |____    \    /    
        | _|       \______/  |_______||_______|    \__/     
        ''')
        self.logger.info(f'Начало парсинга {formatted_date} {to_parse}')

        for category in to_parse:
            tasks = []
            name_category, url = await self.choise_category(category)
            
            categories = await self.get_all_urls_in_category_with_retry(url)
            if not categories:
                self.logger.info(f'Не смог собрать ссылки с категории {name_category}')
                continue

            for name, url_category in categories.items():
                task = asyncio.create_task(self._task_all_products(f'{url_category}'))
                tasks.append(task)

            results = await asyncio.gather(*tasks)
            for result in results:
                self.data.extend(result)
            tasks.clear()

            tasks_html_data = []
            self.logger.info(f"Всего товаров найдено: {len(self.data)}")
    
            for count, url in enumerate(self.data, 1):
                task = asyncio.create_task(self._task_html_to_data(url, count))
                tasks_html_data.append(task)

            await asyncio.gather(*tasks_html_data)
            self.logger.info(f'Парсинг категории {name_category} завершено ...\n')
            self.data.clear()
            tasks_html_data.clear()
            
        self.logger.info(f'Начинаю запись в гугл таблицу...\n')
        self.logger.info(f'Всего товаров {len(self.final_data)}\n')
        rows = len(self.final_data.items())
        write = GoogleSheetsWriter(
            creds_file=path(self.settings.google.json_name),
            sheet_name=self.settings.google.table_name,
            worksheet_name=name_list,
            logger=self.logger,
            rows=rows + 100,
            cols=80
        )
        await write.write_to_google_sheets(self.final_data, currency='MDL')
        self.logger.info(f'Парсинг завершено {name_list} ...\n')