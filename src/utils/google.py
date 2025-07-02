import json
import re
import gspread
import pandas as pd
import time
import random
import gspread.exceptions
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from oauth2client.service_account import ServiceAccountCredentials
from gspread_dataframe import set_with_dataframe, get_as_dataframe

from src.utils.logger import Logger


class GoogleSheetsWriter:
    def __init__(self, creds_file: str, sheet_name: str, worksheet_name: str, rows: int, cols: int, logger: Optional[Logger] = None):
        self.rows = rows
        self.cols = cols
        self.logger = logger or Logger()
        self.load_credentials(creds_file)
        self.sheet = self.create_or_open_sheet(sheet_name)
        self.worksheet = self.create_or_open_worksheet(worksheet_name)
        

    def load_credentials(self, creds_file: str):
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        with open(creds_file, 'r') as file:
            creds_data = json.load(file)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_data, scope)
        self.client = gspread.authorize(creds)

    def create_or_open_sheet(self, sheet_name: str):
        try:
            return self.client.open(sheet_name)
        except gspread.exceptions.SpreadsheetNotFound:
            sheet = self.client.create(sheet_name)
            self.logger.info(f"Создана новая таблица: {sheet_name}")
            return sheet

    def create_or_open_worksheet(self, worksheet_name: str):
        try:
            return self.sheet.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            # worksheet = self.sheet.add_worksheet(title=worksheet_name, rows="6000", cols="130")
            worksheet = self.sheet.add_worksheet(title=worksheet_name, rows=f"{self.rows}", cols=f"{self.cols}")
            self.logger.info(f"Создан новый лист: {worksheet_name}")
            return worksheet
        
    def format_worksheet(self):
        header_format = {
            "horizontalAlignment": "CENTER",
            "textFormat": {"bold": True}
        }
        data_format = {"horizontalAlignment": "LEFT"}
        
        all_values = self.worksheet.get_all_values()
        num_rows = len(all_values)
        num_cols = len(all_values[0]) if num_rows > 0 else 0

        if num_cols > 0:
            last_col_letter = gspread.utils.rowcol_to_a1(1, num_cols).replace("1", "")

            max_retries = 5  # Максимальное количество попыток
            for attempt in range(max_retries):
                try:
                    self.worksheet.format(f"A1:{last_col_letter}1", header_format)
                    self.worksheet.format(f"A2:{last_col_letter}{num_rows}", data_format)
                    self.worksheet.columns_auto_resize(0, num_cols)
                    break  # Если всё прошло успешно, выходим из цикла
                except gspread.exceptions.APIError as e:
                    if "503" in str(e):
                        wait_time = (2 ** attempt) + random.uniform(0, 1)  # Экспоненциальное увеличение задержки
                        self.logger.warning(f"Google API временно недоступен. Попытка {attempt + 1} из {max_retries}. Ожидание {wait_time:.2f} сек...")
                        time.sleep(wait_time)
                    else:
                        # raise  # Если ошибка не 503, выбрасываем её снова
                        pass


    def batch_highlight_cells(self, highlight_cells):
        requests = []
        colors = {"green": {"red": 0.7, "green": 1.0, "blue": 0.7}, "red": {"red": 1.0, "green": 0.7, "blue": 0.7}}
        
        for row, col, color in highlight_cells:
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": self.worksheet.id,
                        "startRowIndex": row - 1,
                        "endRowIndex": row,
                        "startColumnIndex": col - 1,
                        "endColumnIndex": col
                    },
                    "cell": {"userEnteredFormat": {"backgroundColor": colors[color]}},
                    "fields": "userEnteredFormat.backgroundColor"
                }
            })
        
        if requests:
            self.worksheet.spreadsheet.batch_update({"requests": requests})


    # Universal  DataFrame is highly fragmented. 
    # async def write_to_google_sheets(self, data: Dict[str, Any], currency: str):
    #     current_date = datetime.now().strftime('%Y-%m-%d')
    #     price_column_name = f"Цена \n {current_date}"

    #     existing_df = get_as_dataframe(self.worksheet)
    #     if existing_df.empty:
    #         existing_df = pd.DataFrame()

    #     if price_column_name not in existing_df.columns:
    #         existing_df[price_column_name] = None

    #     for url, details in data.items():
    #         if details is None:
    #             continue

    #         current_price = str(details.pop("price", "")) if "price" in details else ""
    #         current_price_num = re.search(r'\d+(\.\d+)?', current_price)
    #         current_price_num = float(current_price_num.group()) if current_price_num else None

    #         if not existing_df.empty and url in existing_df["URL"].values:
    #             row_index = existing_df.index[existing_df["URL"] == url].tolist()[0]
    #             existing_df.at[row_index, price_column_name] = current_price
    #         else:
    #             new_row = details.copy()
    #             new_row["URL"] = url
    #             new_row[price_column_name] = current_price
    #             existing_df = pd.concat([existing_df, pd.DataFrame([new_row])], ignore_index=True)

    #     # Обновляем список фиксированных колонок
    #     fixed_columns = ["URL", "Название", "Название на русском", "Артикул", "Категория"]

    #     # Сортировка колонок с ценами по дате
    #     price_columns = [col for col in existing_df.columns if re.search(r"\d{4}-\d{2}-\d{2}", col)]
    #     price_columns.sort(key=lambda x: datetime.strptime(re.search(r"\d{4}-\d{2}-\d{2}", x).group(), '%Y-%m-%d'))

    #     # Удаление столбца "Цена", если он существует
    #     if "Цена" in existing_df.columns:
    #         existing_df.drop(columns=["Цена"], inplace=True)

    #     # Проверяем, если "Название на русском" отсутствует в столбцах, добавляем его
    #     # if "Название на русском" not in existing_df.columns:
    #     #     existing_df["Название на русском"] = None  # Добавляем новый столбец с пустыми значениями

    #     # Остальные колонки, не входящие в fixed_columns или price_columns
    #     other_columns = [col for col in existing_df.columns if col not in fixed_columns + price_columns]

    #     # Объединяем все колонки в нужном порядке
    #     ordered_columns = fixed_columns + price_columns + other_columns
    #     existing_df = existing_df[ordered_columns]

    #     # Теперь добавляем формулы в столбец "Название на русском" для всех строк
    #     name_index = fixed_columns.index("Название на русском")  # Индекс столбца "Название на русском"
    #     name_column_index = fixed_columns.index("Название")  # Индекс столбца "Название" (для ссылки в формуле)

    #     for i in range(len(existing_df)):
    #         # Если ячейка в "Название на русском" не пуста и не содержит формулу, добавляем формулу
    #         if pd.isna(existing_df.iloc[i]["Название на русском"]):  # Ячейка пуста
    #             row_number = i + 2  # Поскольку первая строка - это заголовок
    #             col_letter_name = gspread.utils.rowcol_to_a1(1, name_column_index + 1).replace("1", "")  # Получаем букву колонки "Название"
    #             formula = f'=GOOGLETRANSLATE({col_letter_name}{row_number}; "auto"; "ru")'  # Формула для перевода
    #             existing_df.iat[i, name_index] = formula  # Вставляем формулу в соответствующую ячейку "Название на русском"
    #         elif existing_df.iloc[i]["Название на русском"] and "GOOGLETRANSLATE" not in str(existing_df.iloc[i]["Название на русском"]):
    #             # Если формулы нет, добавляем её
    #             row_number = i + 2
    #             col_letter_name = gspread.utils.rowcol_to_a1(1, name_column_index + 1).replace("1", "")
    #             formula = f'=GOOGLETRANSLATE({col_letter_name}{row_number}; "auto"; "ru")'
    #             existing_df.iat[i, name_index] = formula
        

    #     previous_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    #     previous_price_column_name = f"Цена \n {previous_date}"

    #     highlight_cells = []

    #     if previous_price_column_name in existing_df.columns:
    #         for row_index, row in existing_df.iterrows():
    #             current_price = row[price_column_name]
    #             previous_price = row[previous_price_column_name]

    #             # Используем регулярку для извлечения числовых значений цен
    #             # current_price_num = re.search(r'\d+(\,\d+)?|\d+(\.\d+)?', str(current_price))
    #             # previous_price_num = re.search(r'\d+(\,\d+)?|\d+(\.\d+)?', str(previous_price))
    #             current_price_num = re.search(r'\d+(?:[.,]\d+)?', str(current_price))
    #             previous_price_num = re.search(r'\d+(?:[.,]\d+)?', str(previous_price))

    #             if not current_price_num or not previous_price_num:
    #                 continue

    #             # Извлекаем числовые значения, удаляя запятую, если она есть
    #             current_price_num = current_price_num.group().replace(',', '.')
    #             previous_price_num = previous_price_num.group().replace(',', '.')

    #             try:
    #                 current_price_num = float(current_price_num)
    #                 previous_price_num = float(previous_price_num)
    #             except (ValueError, TypeError):
    #                 continue

    #             price_diff = abs(current_price_num - previous_price_num)
    #             decimal_places = 2 if '.' in str(current_price_num) else 0
                

    #             # Обработка цен
    #             if current_price_num > previous_price_num:
    #                 updated_text = f"{current_price_num:.{decimal_places}f} (> на {price_diff:.2f})"
    #                 highlight_cells.append((row_index + 2, existing_df.columns.get_loc(price_column_name) + 1, "green"))
    #             elif current_price_num < previous_price_num:
    #                 updated_text = f"{current_price_num:.{decimal_places}f} (< на {price_diff:.2f})"
    #                 highlight_cells.append((row_index + 2, existing_df.columns.get_loc(price_column_name) + 1, "red"))
    #             else:
    #                 updated_text = f"{current_price_num:.{decimal_places}f}"

    #             # Заменяем точку на запятую для вывода в правильном формате
    #             updated_text = updated_text.replace('.', ',')

    #             # Обновление DataFrame
    #             existing_df.at[row_index, price_column_name] = updated_text

    #     self.worksheet.clear()
        
    #     set_with_dataframe(self.worksheet, existing_df)

    #     now = datetime.now()
    #     updated_at = now.strftime("Обновлено: %d.%m.%Y в %H:%M")
    #     self.worksheet.insert_note("A1", updated_at)


    #     self.batch_highlight_cells(highlight_cells)
    #     self.format_worksheet()

    #     self.logger.info(f"Данные успешно загружены в Google Таблицу!")
    #     self.logger.info(f"Ссылка на таблицу: https://docs.google.com/spreadsheets/d/{self.sheet.id}")



    async def write_to_google_sheets(self, data: Dict[str, Any], currency: str):
        current_date = datetime.now().strftime('%Y-%m-%d')
        price_column_name = f"Цена \n {current_date}"

        existing_df = get_as_dataframe(self.worksheet)
        if existing_df.empty:
            existing_df = pd.DataFrame()

        fixed_columns = ["URL", "Название", "Название на русском", "Название на румынском", "Артикул", "Категория"]

        if price_column_name not in existing_df.columns:
            existing_df[price_column_name] = None

        for url, details in data.items():
            if details is None:
                continue

            current_price = str(details.pop("price", "")) if "price" in details else ""
            current_price_num = re.search(r'\d+(\.\d+)?', current_price)
            current_price_num = float(current_price_num.group()) if current_price_num else None

            if not existing_df.empty and url in existing_df["URL"].values:
                row_index = existing_df.index[existing_df["URL"] == url].tolist()[0]
                existing_df.at[row_index, price_column_name] = current_price
            else:
                new_row = details.copy()
                new_row["URL"] = url
                new_row[price_column_name] = current_price
                existing_df = pd.concat([existing_df, pd.DataFrame([new_row])], ignore_index=True)

        price_columns = [col for col in existing_df.columns if re.search(r"\d{4}-\d{2}-\d{2}", col)]
        price_columns.sort(key=lambda x: datetime.strptime(re.search(r"\d{4}-\d{2}-\d{2}", x).group(), '%Y-%m-%d'))

        if "Цена" in existing_df.columns:
            existing_df.drop(columns=["Цена"], inplace=True)

        other_columns = [col for col in existing_df.columns if col not in fixed_columns + price_columns]
        ordered_columns = fixed_columns + price_columns + other_columns
        existing_df = existing_df.reindex(columns=ordered_columns)

        # Добавление переводов
        name_index_ru = existing_df.columns.get_loc("Название на русском")
        name_index_ro = existing_df.columns.get_loc("Название на румынском")
        name_column_index = existing_df.columns.get_loc("Название")

        # Приводим к строковому типу, чтобы избежать конфликтов с формулами
        existing_df["Название на русском"] = existing_df["Название на русском"].astype(str)
        existing_df["Название на румынском"] = existing_df["Название на румынском"].astype(str)

        for i in range(len(existing_df)):
            row_number = i + 2
            col_letter_name = gspread.utils.rowcol_to_a1(1, name_column_index + 1).replace("1", "")

            if pd.isna(existing_df.iat[i, name_index_ru]):
                formula_ru = f'=GOOGLETRANSLATE({col_letter_name}{row_number}; "auto"; "ru")'
                existing_df.iat[i, name_index_ru] = formula_ru
            elif "GOOGLETRANSLATE" not in str(existing_df.iat[i, name_index_ru]):
                formula_ru = f'=GOOGLETRANSLATE({col_letter_name}{row_number}; "auto"; "ru")'
                existing_df.iat[i, name_index_ru] = formula_ru

            if pd.isna(existing_df.iat[i, name_index_ro]):
                formula_ro = f'=GOOGLETRANSLATE({col_letter_name}{row_number}; "auto"; "ro")'
                existing_df.iat[i, name_index_ro] = formula_ro
            elif "GOOGLETRANSLATE" not in str(existing_df.iat[i, name_index_ro]):
                formula_ro = f'=GOOGLETRANSLATE({col_letter_name}{row_number}; "auto"; "ro")'
                existing_df.iat[i, name_index_ro] = formula_ro

        # Сравнение с последним днём
        highlight_cells = []
        price_changed = False

        if len(price_columns) >= 2:
            last_column_name = price_columns[-2]
            for row_index, row in existing_df.iterrows():
                current_price = row[price_column_name]
                previous_price = row[last_column_name]

                current_price_num = re.search(r'\d+(?:[.,]\d+)?', str(current_price))
                previous_price_num = re.search(r'\d+(?:[.,]\d+)?', str(previous_price))

                if not current_price_num or not previous_price_num:
                    continue

                current_price_num = current_price_num.group().replace(',', '.')
                previous_price_num = previous_price_num.group().replace(',', '.')

                try:
                    current_price_num = float(current_price_num)
                    previous_price_num = float(previous_price_num)
                except (ValueError, TypeError):
                    continue

                price_diff = abs(current_price_num - previous_price_num)
                decimal_places = 2 if '.' in str(current_price_num) else 0

                if current_price_num > previous_price_num:
                    updated_text = f"{current_price_num:.{decimal_places}f} (> на {price_diff:.2f})"
                    highlight_cells.append((row_index + 2, existing_df.columns.get_loc(price_column_name) + 1, "green"))
                    price_changed = True
                elif current_price_num < previous_price_num:
                    updated_text = f"{current_price_num:.{decimal_places}f} (< на {price_diff:.2f})"
                    highlight_cells.append((row_index + 2, existing_df.columns.get_loc(price_column_name) + 1, "red"))
                    price_changed = True
                else:
                    updated_text = f"{current_price_num:.{decimal_places}f}"

                updated_text = updated_text.replace('.', ',')
                existing_df.at[row_index, price_column_name] = updated_text
        else:
            # Если нет хотя бы одной предыдущей даты — считаем что изменения есть, чтобы создать таблицу
            price_changed = True

        now = datetime.now()

        if existing_df.empty or len(existing_df) == 0:
            set_with_dataframe(self.worksheet, existing_df)
            updated_at = now.strftime("Создан новый лист и добавлены данные: %d.%m.%Y в %H:%M")
            self.worksheet.insert_note("A1", updated_at)
            self.logger.info(updated_at)
            return

        if not price_changed:
            updated_at = now.strftime("Цены не поменялись: %d.%m.%Y в %H:%M")
            self.worksheet.insert_note("A1", updated_at)
            self.logger.info("Цены не изменились — новый столбец не будет добавлен.")
            return

        # Записываем обновлённый датафрейм
        self.worksheet.clear()
        set_with_dataframe(self.worksheet, existing_df)

        updated_at = now.strftime("Обновлено: %d.%m.%Y в %H:%M")
        self.worksheet.insert_note("A1", updated_at)

        self.batch_highlight_cells(highlight_cells)
        self.format_worksheet()

        self.logger.info("Данные успешно загружены в Google Таблицу!")
        self.logger.info(f"Ссылка на таблицу: https://docs.google.com/spreadsheets/d/{self.sheet.id}")
