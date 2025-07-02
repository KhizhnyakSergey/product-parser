import asyncio
import time
from typing import Optional, Dict, Tuple, Any
from datetime import datetime
from itertools import cycle

from python_socks._errors import ProxyError
from aiohttp import ClientConnectorError
from src.session.errors import NetworkError, APIError

from src.api.electromotor import ElectromotorAPI
from src.core.settings import Settings
from src.utils.logger import Logger
from src.utils.helper import data_extraction_electromotor
from src.core.settings import load_settings, Settings, path
from src.utils.google import GoogleSheetsWriter



class ApplicationElectromotor:
    
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

        async with ElectromotorAPI() as ses:
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
        to_parse = self.settings.google.electromotor_index_to_parse
        name_list = f'ELECTROMOTOR {to_parse}'
        self.logger.info(f'⏩ELECTROMOTOR⏪')
        self.logger.info(f'Початок парсингу {formatted_date} {to_parse}')

        for category in to_parse:
            tasks = []
            name, url = await self.choise_category(category)

            async with ElectromotorAPI() as ses:
                categories = await ses.get_all_urls_in_category(url)
                # print(categories)

            for n, url in categories.items():
                async with ElectromotorAPI() as api:
                    task = asyncio.create_task(self._task_all_products(api, url))
                    tasks.append(task)

            results = await asyncio.gather(*tasks)
            
            for result in results:
                self.data.extend(result)
            tasks.clear()


            self.logger.info(f"Всего товаров найдено: {len(self.data)}")
            for count, url in enumerate(self.data, 1):
                async with ElectromotorAPI() as api:
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
            self.logger.info(f'Парсинг категории {name} завершено ...\n')
            self.data.clear()
            
        self.logger.info(f'Начинаю запись в гугл таблицу...')
        self.logger.info(f'Всего товаров {len(self.final_data)}\n')
        rows = len(self.final_data.items())
        write = GoogleSheetsWriter(
            creds_file=path(self.settings.google.json_name),
            sheet_name=self.settings.google.table_name,
            worksheet_name=name_list,
            logger=self.logger,
            rows=rows + 100,
            cols=110
        )
        await write.write_to_google_sheets(self.final_data, currency='MDL')
        self.final_data.clear()
        self.logger.info(f'Парсинг завершено {name_list} ...\n')



    async def _task_html_data(self, api: ElectromotorAPI, url: str, count: int) -> None:
        async with self.semaphore:  # Use semaphore here
            retries = 5  # Количество попыток
            for attempt in range(retries):
                try:
                    result = await api.get_html_product(url)
                    self.logger.info(f'{count} Запрос на товар -> {url}')
                    return url, result 
                except (ClientConnectorError, NetworkError, APIError) as e:
                    if attempt < retries - 1:
                        await asyncio.sleep(5)
                        self.logger.info(f'{count} Запрос на товар -> {url}')
                except KeyboardInterrupt:
                    self.logger.error(f'Завершение таски по запросу пользователя.')
                except Exception as e:
                    self.logger.exception(f'{type(e).__name__} -> {e}')
            # return None
        

    async def _task_parse_html(self, url: str, response, count: int) -> None:

        result = await data_extraction_electromotor(response) 
        if url in self.final_data:
            self.logger.warning(f"⚠️ Дубликат URL: {url} (перезаписывается!)")
        self.final_data[url] = result
        await asyncio.sleep(0,3)
        self.logger.info(f' {count} Готово -> {url} ✅')

    # async def _task_all_products(self, api: ElectromotorAPI, url: str) -> None:
    #     async with self.semaphore:  # Use semaphore here
    #         retries = 5  # Количество попыток
    #         for attempt in range(retries):
    #             try:
    #                 result = await api.get_all_products(url) 
    #                 return result if result is not None else []
    #             except (ClientConnectorError, NetworkError, TimeoutError, APIError) as e:
    #                 if attempt < retries - 1:
    #                     await asyncio.sleep(6)
    #                     result = await api.get_all_products(url) 
    #                     return result if result is not None else []
    #             except KeyboardInterrupt:
    #                 self.logger.error(f'Завершение таски по запросу пользователя.')
    #             except Exception as e:
    #                 self.logger.exception(f'{type(e).__name__} -> {e}')

    async def _task_all_products(self, api: ElectromotorAPI, url: str) -> None:
        async with self.semaphore:  # Используем семафор
            retries = 6  # Количество попыток
            for attempt in range(retries):
                try:
                    result = await api.get_all_products(url)
                    return result if result is not None else []
                except (ClientConnectorError, NetworkError, TimeoutError, APIError) as e:
                    self.logger.warning(f"Попытка {attempt+1}/{retries}: {e}")
                    if attempt < retries - 1:
                        await asyncio.sleep(6)  # Ждем перед новой попыткой
                    else:
                        self.logger.error(f"Не удалось получить данные с {url} после {retries} попыток")
                        return []  # Возвращаем пустой список в случае неудачи
                except KeyboardInterrupt:
                    self.logger.error(f"Завершение таски по запросу пользователя.")
                    return []
                except Exception as e:
                    self.logger.exception(f"{type(e).__name__} -> {e}")
                    return []
        

    # async def _task_get_product_data(self, api: HabsevAPI, url: str, count: int) -> None:
    #     async with self.semaphore:  # Use semaphore here
    #         retries = 10  # Количество попыток
    #         for attempt in range(retries):
    #             try:
    #                 result = await api.get_product_data(url)
    #                 self.final_data[url] = result
    #                 self.logger.info(f'{count} Запрос на товар -> {url}')
    #                 return True
    #             except (ClientConnectorError, NetworkError) as e:
    #                 if attempt < retries - 1:
    #                     await asyncio.sleep(5)
    #                     result = await api.get_product_data(url)
    #                     self.final_data[url] = result
    #                     self.logger.info(f'{count} Запрос на товар -> {url}')
    #                     return True  # Задержка перед повторной попыткой
    #             except KeyboardInterrupt:
    #                 self.logger.error(f'Завершение таски по запросу пользователя.')
    #             except Exception as e:
    #                 self.logger.exception(f'{type(e).__name__} -> {e}')
    #         return None