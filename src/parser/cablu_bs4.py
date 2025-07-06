import re
import json
import html

from bs4 import BeautifulSoup

from src.utils.normalize_data import normalize_name


async def data_extraction(response):

    soup = BeautifulSoup(response, "lxml")
    

    main_info = soup.find('div', attrs={'class': 'product-info'})
    if not main_info:
        print('***********************')
        return None 
    
    
    name = soup.find('h1', attrs={'class': 'item name fn'})

    price_div = soup.find('div', class_='price')
    price = await extract_price(price_div)

    category_items = soup.select('.breadcrumb li a span')
    category = category_items[-2].get_text(strip=True) if len(category_items) > 1 else None

    data = {
        "Название": name.text.strip() if name else None,
        "price": price if price else None,
        "Категория": category,
    }

    product_description = soup.select('table.product-description tr')
    for row in product_description:
        # Получаем название поля (первая ячейка)
        field_name = row.select_one('td span').text.strip().lower()
        
        # Получаем значение (вторая ячейка)
        if field_name == 'бренд:':
            brand = row.select_one('td.description-right a').text.strip()
            data['Бренд'] = brand
        elif field_name == 'код продукта:':
            product_code = row.select_one('td.description-right').text.strip()
            data['Артикул'] = product_code

    characteristics_table = soup.find(
        'div', 
        id='tab-attribute'
    ).find('table', class_='attribute') if soup.find('div', id='tab-attribute') else None
    if characteristics_table:
        rows = characteristics_table.find_all('tr')
        for row in rows[1:]:  # Пропускаем заголовок "Характеристики"
            cols = row.find_all('td')
            if len(cols) == 2:
                key = cols[0].get_text(strip=True).replace('­', '').strip()
                val = cols[1].get_text(strip=True)
                
                # Обработка дубликатов
                if key in data:
                    if isinstance(data[key], list):
                        data[key].append(val)
                    else:
                        data[key] = [data[key], val]
                else:
                    data[key] = val

    data = await normalize_name(data)
    # print(data)

    return data


    
async def extract_price(price_element):
    # Получаем текст элемента и очищаем его
    price_text = price_element.get_text(strip=True)  # "Цена: 21,00 LEI / шт."
    
    # Удаляем "Цена:", "LEI" и лишние пробелы
    price_only = price_text.replace('Цена:', '').replace('LEI', '').strip()  # "21,00 / шт."
    
    # Извлекаем только числовую часть с разделителем
    price_part = price_only.split('/')[0].strip()  # "21,00"
    price_part = price_part.replace('.','')
    
    return price_part