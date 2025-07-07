import asyncio
import random
from typing import Optional, Tuple
from datetime import datetime

from aiohttp import ClientConnectorError

from src.session.errors import NetworkError, NotFoundError, APIError
from src.api.iek import IEKAPI
from src.utils.logger import Logger
from src.utils.helper import data_extraction_iek
from src.core.settings import load_settings, Settings, path
from src.utils.google import GoogleSheetsWriter


class ApplicationIek:
    
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

        retries = 3  
        async with IEKAPI() as ses:
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


    async def _task_html_to_data(self, url: str, count: int) -> tuple[str, str] | None:
        async with self.semaphore:
            retries = 3
            for attempt in range(retries):
                async with IEKAPI() as api:
                    try:
                        await asyncio.sleep(random.uniform(0.1, 2.0))
                        response = await api.get_html_product(url)
                        if response:
                            data = await data_extraction_iek(response) 
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
        to_parse = self.settings.google.iek_index_to_parse
        if to_parse == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]:
            name_list = f'IEK ALL'
        else:
            name_list = f'IEK {to_parse}'
        self.logger.info(r'''
             __   _______  __  ___ 
            |  | |   ____||  |/  / 
            |  | |  |__   |  '  /  
            |  | |   __|  |    <   
            |  | |  |____ |  .  \  
            |__| |_______||__|\__\ 
        ''')
        self.logger.info(f'Начало парсинга {formatted_date} {to_parse}')

        for category in to_parse:
            name_category, url = await self.choise_category(category)

            async with IEKAPI() as ses:
                self.data = await ses.get_all_products(url)

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
            cols=320
        )
        await write.write_to_google_sheets(self.final_data, currency='MDL')
        self.logger.info(f'Парсинг завершено {name_list} ...\n')