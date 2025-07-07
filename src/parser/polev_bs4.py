from bs4 import BeautifulSoup

from src.utils.normalize_data import normalize_name


async def data_extraction(response):

    soup = BeautifulSoup(response, "lxml")
    main_info = soup.find('div', attrs={'class': 'jshop productfull'})
    if not main_info:
        print('***********************')
        return None 
    
    form = soup.find('form', attrs={'name': 'product'})
    name = form.find('h1')

    price_span = soup.find('span', id='block_price')
    price = await extract_price(price_span)

    category = soup.find('ul', class_='breadcrumb')
    category_items = category.find_all("a")

    articul_text = form.find('span', id='product_code')
    articul = articul_text.text.split(':')[-1].strip()

    manufacturer_text = form.find('div', class_='manufacturer_name')
    manufacturer = manufacturer_text.find('span')

    tabs_container = soup.find('div', id='tabs_container')
    desc_div = tabs_container.find('div', class_='jshop_prod_description')


    data = {
        "Название": name.text.strip() if name else None,
        "price": price if price else None,
        "Категория": category_items[-1].get_text(strip=True) if len(category_items) > 1 else None,
        "Артикул": articul if articul else None,
        "Производитель": manufacturer.text.strip() if manufacturer else None,
        "Описание": desc_div.text.strip() if desc_div else None,
    }

    data = await normalize_name(data)

    return data


async def extract_price(price_element):
    
    # Получаем текст элемента и очищаем его
    price_text = price_element.get_text(strip=True)  # "278,00 MDL"
    price_only = price_text.split(' MDL')[0]  # "278,00"
    price_cleaned = price_only.replace(' ', '').strip()  # "278,00"

    return price_cleaned  
    
