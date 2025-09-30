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
import numpy as np

from src.utils.logger import Logger


class GoogleSheetsWriter:
    def __init__(self, creds_file: str, sheet_name: str, worksheet_name: str, rows: int, cols: int, logger: Optional[Logger] = None):
        self.rows = rows
        self.cols = cols
        self.logger = logger or Logger()
        self.load_credentials(creds_file)
        self.sheet = self.create_or_open_sheet(sheet_name)
        self.worksheet = self.create_or_open_worksheet(worksheet_name)
        self.current_price_column = "Актуальная цена"
        

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
                        pass


    def batch_highlight_cells(self, highlight_cells):
        requests = []
        colors = {
            "green": {"red": 0.7, "green": 1.0, "blue": 0.7},
            "red": {"red": 1.0, "green": 0.7, "blue": 0.7},
            "white": {"red": 1.0, "green": 1.0, "blue": 1.0}  # Добавлен белый цвет
        }
        
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


    async def write_to_google_sheets(self, data: Dict[str, Any]):
        existing_df = get_as_dataframe(self.worksheet)
        if existing_df.empty:
            existing_df = pd.DataFrame()

        fixed_columns = ["URL", "Название", "Артикул", "Категория"]

        # Убедимся, что колонка с ценами имеет строковый тип
        if self.current_price_column not in existing_df.columns:
            existing_df[self.current_price_column] = pd.Series(dtype='str')
        else:
            existing_df[self.current_price_column] = existing_df[self.current_price_column].astype(str)

        highlight_cells = []
        price_changed = False
        cells_to_clear_highlight = []

        for url, details in data.items():
            if details is None:
                continue

            current_price = str(details.pop("price", "")) if "price" in details else ""
            current_price_num = re.search(r'\d+([.,]\d+)?', current_price)
            current_price_num = float(current_price_num.group().replace(',', '.')) if current_price_num else None

            if not existing_df.empty and url in existing_df["URL"].values:
                row_index = existing_df.index[existing_df["URL"] == url].tolist()[0]
                previous_price = existing_df.at[row_index, self.current_price_column]
                
                # Извлекаем только числовое значение из предыдущей цены (удаляем "> на X.XX" или "< на X.XX")
                clean_previous_price = re.sub(r'\s*[<>] на \d+[,.]\d+\)?', '', previous_price)
                previous_price_num = re.search(r'\d+([.,]\d+)?', clean_previous_price)
                if previous_price_num:
                    previous_price_num = float(previous_price_num.group().replace(',', '.'))
                else:
                    previous_price_num = None

                if current_price_num is not None:
                    decimal_places = 2 if '.' in f"{current_price_num:.2f}" else 0
                    formatted_price = f"{current_price_num:.{decimal_places}f}".replace('.', ',')
                    
                    if previous_price_num is not None:
                        if not np.isclose(current_price_num, previous_price_num):
                            price_diff = abs(current_price_num - previous_price_num)
                            
                            if current_price_num > previous_price_num:
                                formatted_price = f"{current_price_num:.{decimal_places}f} (> на {price_diff:.2f})".replace('.', ',')
                                highlight_cells.append((row_index + 2, existing_df.columns.get_loc(self.current_price_column) + 1, "green"))
                            else:
                                formatted_price = f"{current_price_num:.{decimal_places}f} (< на {price_diff:.2f})".replace('.', ',')
                                highlight_cells.append((row_index + 2, existing_df.columns.get_loc(self.current_price_column) + 1, "red"))
                            
                            price_changed = True
                        else:
                            # Цена не изменилась - убираем разницу и добавляем в список для очистки выделения
                            formatted_price = f"{current_price_num:.{decimal_places}f}".replace('.', ',')
                            cells_to_clear_highlight.append((row_index + 2, existing_df.columns.get_loc(self.current_price_column) + 1))
                    
                    # Обновляем значение в DataFrame (уже как строку)
                    existing_df.at[row_index, self.current_price_column] = formatted_price
                    price_changed = True
            else:
                # Новая запись
                new_row = details.copy()
                new_row["URL"] = url
                if current_price_num is not None:
                    decimal_places = 2 if '.' in f"{current_price_num:.2f}" else 0
                    new_row[self.current_price_column] = f"{current_price_num:.{decimal_places}f}".replace('.', ',')
                else:
                    new_row[self.current_price_column] = current_price
                
                existing_df = pd.concat([existing_df, pd.DataFrame([new_row])], ignore_index=True)
                price_changed = True

        # Упорядочиваем колонки
        other_columns = [col for col in existing_df.columns if col not in fixed_columns + [self.current_price_column]]
        ordered_columns = fixed_columns + [self.current_price_column] + other_columns
        existing_df = existing_df.reindex(columns=ordered_columns)

        now = datetime.now()

        if existing_df.empty or len(existing_df) == 0:
            set_with_dataframe(self.worksheet, existing_df)
            updated_at = now.strftime("Создан новый лист и добавлены данные: %d.%m.%Y в %H:%M")
            self.worksheet.insert_note("A1", updated_at)
            self.logger.info(updated_at)
            return

        self.worksheet.clear()
        set_with_dataframe(self.worksheet, existing_df)

        # Применяем выделение для изменившихся цен
        self.batch_highlight_cells(highlight_cells)
        
        # Очищаем выделение для цен, которые не изменились
        if cells_to_clear_highlight:
            self.batch_highlight_cells([(row, col, "white") for row, col in cells_to_clear_highlight])

        self.format_worksheet()

        if price_changed:
            updated_at = now.strftime("Обновлено: %d.%m.%Y в %H:%M")
            self.logger.info("Данные успешно загружены в Google Таблицу!")
        else:
            updated_at = now.strftime("Цены не поменялись: %d.%m.%Y в %H:%M")
            self.logger.info("Цены не изменились.")
        
        self.worksheet.insert_note("A1", updated_at)
        self.logger.info(f"Ссылка на таблицу: https://docs.google.com/spreadsheets/d/{self.sheet.id}")