import re
import json
import html

from bs4 import BeautifulSoup

from src.utils.normalize_data import normalize_name


async def data_extraction(response):

    soup = BeautifulSoup(response, "lxml")
    

    main_info = soup.find('div', attrs={'class': 'row space-between slider-buy'})
    if not main_info:
        print('***********************')
        return None 
    
    
    name = soup.find('h1', attrs={'class': 'page-title'})

    price_div = soup.find('div', class_='price')
    price = await extract_price(price_div)

    category = soup.find('div', class_='breadcrumbs')
    category_items = category.find_all("span")

    articul_text = soup.find('div', class_='code')
    articul = articul_text.text.split(':')[-1].strip()

    articul_text = soup.find('div', class_='code')

    data = {
        "Название": name.text.strip() if name else None,
        "price": price if price else None,
        "Категория": category_items[-1].get_text(strip=True) if len(category_items) > 1 else None,
        "Артикул": articul if articul else None,
    }

    characteristics_section = soup.find('div', class_='about-item__features-item')
    characteristics = characteristics_section.find_all('div', class_='item-wrapper')
    for feature in characteristics:
        title = feature.find("div", class_="key")
        value = feature.find("div", class_="value")

        if title and value:
            key = title.get_text(strip=True)
            val = value.get_text(strip=True)
            
            if key in data:
                if isinstance(characteristics_section[key], list):
                    data[key].append(val)
                else:
                    data[key] = [data[key], val]
            else:
                data[key] = val

    data = await normalize_name(data)

    return data


async def extract_price(price_element):
    
    price_text = price_element.get_text(strip=True)
    
    # Ищем числа с разделителями тысяч и дробной частью
    match = re.search(r'(?:\d{1,3}[ \.]?)+(?:,\d+)?|\d+,\d+', price_text.replace('.', ','))
    if not match:
        return None
    
    price_str = match.group(0)
    price_str = price_str.replace(' ', '').replace('.', '')
    
    if ',' in price_str:
        # Для float возвращаем строку с запятой (или float для вычислений)
        return price_str
        # Или: return float(price_str.replace(',', '.'))
    else:
        return int(price_str)
    
