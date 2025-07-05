import re
import json
import html

from bs4 import BeautifulSoup

from src.utils.normalize_data import normalize_name


async def data_extraction(response):

    soup = BeautifulSoup(response, "lxml")
    

    main_info = soup.find('div', attrs={'class': 'product-page-inner'})
    if not main_info:
        print('***********************')
        return None 
    
    
    name = soup.find('div', attrs={'class': 'product-page-title'})

    price_div = soup.find('div', class_='goods-item-current-price')
    price = await extract_price(price_div)

    category = soup.find('ul', class_='breadcrumbs')
    category_items = category.find_all("a")

    # articul_text = soup.find('div', class_='code')
    # articul = articul_text.text.split(':')[-1].strip()

    # articul_text = soup.find('div', class_='code')

    data = {
        "Название": name.text.strip() if name else None,
        "price": price if price else None,
        "Категория": category_items[-1].get_text(strip=True) if len(category_items) > 1 else None,
        # "Артикул": articul if articul else None,
    }

    for item in soup.select('div.product-page-id'):
        text = item.get_text(strip=True)
        if ': ' in text:
            key, value = text.split(': ', 1)
            # Заменяем "Код товара" на "Артикул"
            if key == 'Код товара':
                key = 'Артикул'
            data[key] = value.strip()

    characteristics_section = soup.find('div', class_='product-page-characteristics')
    if not characteristics_section:
        pass
    else:
        characteristics = characteristics_section.find_all('li')
        for feature in characteristics:
            paragraphs = feature.find_all('p')
        
            # Должно быть 2 параграфа - название и значение
            if len(paragraphs) == 2:
                key = paragraphs[0].get_text(strip=True)
                val = paragraphs[1].get_text(strip=True)
                
                # Обработка дубликатов (если такой ключ уже есть)
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
    price_text = price_element.get_text(strip=True)  # "278.00 MDL / шт."
    price_only = price_text.split(' MDL')[0]  # "278.00"
    price_cleaned = price_only.replace('.', ',')  # "278,00"

    return price_cleaned  
    
