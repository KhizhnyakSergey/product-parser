import asyncio
from typing import Optional, Tuple
from datetime import datetime

from aiohttp import ClientConnectorError

from src.session.errors import NetworkError, NotFoundError, APIError
from src.api.okm import OkmAPI
from src.core.settings import load_settings, Settings, path
from src.utils.logger import Logger
from src.utils.google import GoogleSheetsWriter


class ApplicationOkm:
    
    def __init__(
            self, 
            max_concurrent_sessions: int = 30,
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
        async with OkmAPI() as ses:
            categories = None
            for attempt in range(retries):
                try:
                    categories = await ses.get_categories()  
                    break  # Если запрос успешен, выходим из цикла
                except (ClientConnectorError, NetworkError, TimeoutError, APIError) as e:
                    self.logger.warning(f"Попытка {attempt + 1}/{retries} не удалась: {type(e).__name__}")
                    if attempt < retries - 1:
                        await asyncio.sleep(5)  
                    else:
                        self.logger.error(f"Не удалось получить категории после {retries} попыток.")
                except Exception as e:
                    self.logger.exception(f"Непредвиденная ошибка: {type(e).__name__} -> {e}")

        categories_list = list(categories.items())
        if not 1 <= category_num <= len(categories_list):
            raise ValueError("Некорректный номер категории")

        selected_name, selected_url = categories_list[category_num - 1]
        self.logger.info(f"➡️ Выбрано: {selected_name} ({selected_url})")
        return selected_name, selected_url


    async def _task_all_products(self, slug: str) -> None:
        async with self.semaphore:  
            retries = 3  
            for attempt in range(retries):
                try:
                    async with OkmAPI() as api:
                        result = await api.get_all_products(slug) 
                        self.logger.info(f'Спарсил страницы -> {slug} ✅')
                        return result if result is not None else []
                except (ClientConnectorError, NetworkError, TimeoutError, APIError) as e:
                    if attempt < retries - 1:
                        await asyncio.sleep(5)
                        self.logger.error(f'Ошибка task_all_products {type(e).__name__} ')
                except KeyboardInterrupt:
                    self.logger.error(f'Завершение таски по запросу пользователя.')
                except Exception as e:
                    self.logger.exception(f'{type(e).__name__} -> {e}')


    async def _task_html_data(self, slug: str, count: int) -> None:
        async with self.semaphore:  # Use semaphore here
            retries = 3  # Количество попыток
            for attempt in range(retries):
                async with OkmAPI() as api:
                    try:
                        result = await api.get_data_product(slug)
                        self.final_data[f'https://okm.md/ru/product/{slug}'] = result
                        self.logger.info(f' {count} Готово -> {slug} ✅')
                        return True
                    except (ClientConnectorError, NetworkError, NotFoundError, APIError) as e:
                        if attempt < retries - 1:
                            self.logger.info(f'{count} ({attempt})Повторный запрос на товар -> {slug}')
                            await asyncio.sleep(4)
                    except KeyboardInterrupt:
                        self.logger.error(f'Завершение таски по запросу пользователя.')
                    except Exception as e:
                        self.logger.exception(f'{type(e).__name__} -> {e}')
            

    async def start(self):

        carrent_date = datetime.now()
        formatted_date = carrent_date.strftime("%Y-%m-%d %H:%M:%S")
        to_parse = self.settings.google.okm_index_to_parse
        name_list = f'Okm {to_parse}'
        self.logger.info(r'''
          ______    __  ___ .___  ___. 
         /  __  \  |  |/  / |   \/   | 
        |  |  |  | |  '  /  |  \  /  | 
        |  |  |  | |    <   |  |\/|  | 
        |  `--'  | |  .  \  |  |  |  | 
         \______/  |__|\__\ |__|  |__|                                               
        ''')
        self.logger.info(f'Начало парсинга {formatted_date} {to_parse}')

        for category in to_parse:
            tasks = []
            name_category, slug = await self.choise_category(category)
            # categories = await self.get_all_urls_in_category_with_retry(url)
            if not slug:
                self.logger.info(f'Не смог собрать категорию {name_category}')
                continue
            
            task = asyncio.create_task(self._task_all_products(slug))
            tasks.append(task)
            
            results = await asyncio.gather(*tasks)
            for result in results:
                if result:
                    self.data.extend(result)
            tasks.clear()
            self.logger.info(f"Всего товаров найдено: {len(self.data)}")

            tasks_html_data = []
            for count, slug in enumerate(self.data, 1):
                task = asyncio.create_task(self._task_html_data(slug, count))
                tasks_html_data.append(task)
                
            results = await asyncio.gather(*tasks_html_data)
            tasks_html_data.clear()
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
            cols=100
        )
        await write.write_to_google_sheets(self.final_data, currency='лей')
        self.logger.info(f'Парсинг завершено {name_list} ...\n')