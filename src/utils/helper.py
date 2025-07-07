import lxml.html
from typing import List
import re

from bs4 import BeautifulSoup



def get_proxies(proxy_path: str) -> List[str]:
    with open(proxy_path, 'r', encoding='utf-8') as file:
        return [line for raw in file.readlines() if (line := raw.strip())]
    

async def normalize_name(data: dict) -> dict:
    name = data.get("Название")
    if not name:
        return data

    # Заменить слова типа "Светодиодный", "Светодиодная" и т.п. на "LED"
    name = re.sub(r'[Сс]ветодиодн[^\s]*', 'LED', name, flags=re.IGNORECASE)

    # Заменить "Вт" на "W"
    name = name.replace('Вт', 'W')

    # Заменить символ * на x
    name = name.replace('*', 'x')

    # Обновляем значение в словаре
    data["Название"] = name
    return data
    

# faster than BeautifulSoup
async def data_extraction_supraten(response):
    try:
        # Парсим только <main> с помощью lxml напрямую
        tree = lxml.html.fromstring(response)

        # Находим главный div
        main_div = tree.find('.//div[@class="sp-page-content"]')
        if main_div is None:
            return None

        # ul.sp-breadcrumbs__list
        cat = tree.find('.//ul[@class="sp-breadcrumbs__list"]')
        category = None
        if cat is not None:
            breadcrumb_items = cat.findall('.//li[@class="sp-breadcrumbs__item"]')
            if len(breadcrumb_items) >= 2:
                category = breadcrumb_items[-2].text_content().strip()
        
        price = main_div.find('.//p[@class="sp-single-product__price-current"]').text_content().strip().split("лей")[0]
        

        data = {
            "Название": main_div.find('.//h1[@class="sp-single-product__title"]').text_content().strip(),
            "Артикул": main_div.find('.//div[@class="sp-single-product__sku"]').text_content().strip().split(":")[-1].strip(),
            "Категория": category,
            # "img_url": main_div.find('.//a[@data-lightbox="product-slider"]').get('href'),
            "price": price.replace(".", ",") if price else None
        }

        # Парсим характеристики
        characteristics_section = main_div.find('.//*[@id="characteristic"]')
        if characteristics_section is not None:
            table = characteristics_section.find('.//table[@class="table table-bordered"]')
            if table is not None:
                rows = table.findall('.//tbody/tr')
                characteristics = {}
                for row in rows:
                    cells = row.findall('.//td')
                    if len(cells) >= 2:
                        characteristics[cells[0].text_content().strip()] = cells[1].text_content().strip()
                data.update(characteristics)

        # Парсим характеристики
        # characteristics_section = main_div.find('.//*[@id="characteristic"]')
        # if characteristics_section is not None:
        #     table = characteristics_section.find('.//table[@class="table table-bordered"]')
        #     if table is not None:
        #         rows = table.findall('.//tbody/tr')
        #         characteristics_list = []
        #         for row in rows:
        #             cells = row.findall('.//td')
        #             if len(cells) >= 2:
        #                 key = cells[0].text_content().strip()
        #                 value = cells[1].text_content().strip()
        #                 characteristics_list.append(f"{key}: {value}")
        #         # Объединяем характеристики в строку через запятую
        #         characteristics_str = ", ".join(characteristics_list)
        #         data["Характеристики"] = characteristics_str
        data = await normalize_name(data)
        return data
    except Exception as e:
        print(f"Error parsing HTML: {e}")
        return None

async def data_extraction_iek(response):

    soup = BeautifulSoup(response, "lxml")
    
    title_element = soup.select_one("h1.product_title")
    if not title_element:
        return None 
    
    product_meta = soup.find("div", class_="product_meta")
    if product_meta:
        articul = product_meta.find("span", class_="sku").text.strip()


    category = soup.find("a", class_="breadcrumb-link breadcrumb-link-last").get_text(strip=True)
    price = soup.find("p", class_="price").text.split("MDL")[0].strip()
    if price:
        price = price.replace(",", "")

    data = {
        "Название": soup.select_one("h1.product_title").get_text(strip=True),
        "Артикул": articul if articul else None,
        "Категория": category if category else None,
        "price": price.replace(".", ",") if price else None
    }

    detail_doc = soup.find_all("div", attrs={'class': 'wc-tab-inner wd-scroll-content'})
    for doc_title_div in detail_doc:
        if "Технические характеристики" in doc_title_div.get_text():
            table = doc_title_div.find_next("table")
            if table:
                rows = table.select("tbody tr")
                for row in rows:
                    key = row.select_one("td:nth-of-type(1)").get_text(strip=True)
                    value_td = row.select_one("td:nth-of-type(2)")
                    if value_td:
                        value = value_td.get_text(strip=True)
                        data[key] = value
                    else:
                        data[key] = None  
            break
    data = await normalize_name(data)
    return data


async def data_extraction_habsev(response):

    soup = BeautifulSoup(response, "lxml")
    
    product_page = soup.select_one("#product__page")
    if not product_page:
        return None  

    name = product_page.select_one("h1.product__title")
    articul = product_page.select_one("div.product__code")
    price = product_page.select_one("div.product__prices.product__prices")
    price_text = price.get_text(strip=True).split('лей')[0].strip() if price else None
    description = soup.select_one("div.description__section div.content")
    category_items = soup.select("ol.breadcrumb__items li.breadcrumb__item")

    data = {
        "Название": name.get_text(strip=True) if name else None,
        "Артикул": articul.get_text(strip=True).split(":")[-1].strip() if articul else None,
        "Категория": category_items[-2].get_text(strip=True) if len(category_items) > 1 else None,
        "price":  price_text.replace(".", ",") if price_text else None,
        "Описание": description.get_text(strip=True) if description else None,
    }
    data = await normalize_name(data)
    return data



async def data_extraction_luminaled(response):

    soup = BeautifulSoup(response, "lxml")
    
    product_page = soup.select_one("#product")
    if not product_page:
        return None  

    name = product_page.select_one("h1.product-item__title")
    articul = product_page.select_one("span.changeSkuTo")
    price = product_page.select_one("span.changePriceTo")
    price_text = price.get_text(strip=True) if price else None
    category_items = soup.find_all("li", class_="breadcrumb-item")
    characteristics = soup.find_all("div", class_="row feature fz-sm mb-4")

    data = {
        "Название": name.get_text(strip=True) if name else None,
        "Артикул": articul.get_text(strip=True).split(":")[-1].strip() if articul else None,
        "Категория": category_items[-2].get_text(strip=True) if len(category_items) > 1 else None,
        "price": price_text.replace(".", ",") if price_text else None,
    }

    for feature in characteristics:
        title = feature.find("div", class_="feature__title")
        value = feature.find("div", class_="feature__description")

        if title and value:
            key = title.get_text(strip=True)
            val = value.get_text(strip=True)
            
            if key in data:
                if isinstance(characteristics[key], list):
                    data[key].append(val)
                else:
                    data[key] = [data[key], val]
            else:
                data[key] = val
    data = await normalize_name(data)
    return data


async def data_extraction_electromotor(response):

    soup = BeautifulSoup(response, "lxml")
    
    product_page = soup.select_one("div.row.product-image-summary-wrap")
    if not product_page:
        return None  

    summary_inner = soup.select_one("div.summary-inner")
    name = summary_inner.select_one("h1.product_title")
    articul = summary_inner.select_one("span.sku_wrapper")
    category_items = summary_inner.find_all("a", class_="breadcrumb-link")
    characteristics = soup.select("table.woocommerce-product-attributes tr")
    
    price = summary_inner.select_one("p.price span.woocommerce-Price-amount")
    if price:
        price = price.bdi.text.strip()  # Например, '1.725,00 MDL' или '839.00\xa0MDL'
        # price = price.replace("\xa0", "").replace("MDL", "").strip()  # Удаляем неразрывный пробел и валюту
        # price = price.replace(".", "").replace(",", ".").replace("MDL", "").strip()  # Убираем точку (разделитель тысяч), заменяем запятую
        price = price.replace(".", "").replace("MDL", "").strip()  # Убираем точку (разделитель тысяч), заменяем запятую
        # price_text = price.replace(",", ".")
        # print(f'text -> {price}')
        # price = float(price)  # Конвертируем в число
        # print(f'float -> {price}')  # 839.00

    data = {
        "Название": name.get_text(strip=True) if name else None,
        "Артикул": articul.get_text(strip=True).split(":")[-1].strip() if articul else None,
        "Категория": category_items[-1].get_text(strip=True) if len(category_items) > 1 else None,
        "price": price if price else None,
    }

    for row in characteristics:
        label = row.select_one("th.woocommerce-product-attributes-item__label")
        value = row.select_one("td.woocommerce-product-attributes-item__value p")

        if label and value:
            key = label.text.strip()
            val = value.text.strip()
            data[key] = val  # Записываем в словарь
    data = await normalize_name(data)
    return data

# faster than BeautifulSoup
# async def data_extraction_iek(response):

#     try:
#         tree = lxml.html.fromstring(response)

#         title_element = tree.xpath("//h1[@class='product_title']/text()")
#         if not title_element:
#             return None

#         # Извлечение артикула
#         articul = tree.xpath("//div[@class='product_meta']//span[@class='sku']/text()")
#         articul = articul[0].strip() if articul else None

#         # Извлечение категории и цены
#         category = tree.xpath("//a[contains(@class, 'breadcrumb-link-last')]/text()")
#         price = tree.xpath("//p[@class='price']/text()")

#         data = {
#             "Название": title_element[0].strip(),
#             "Артикул": articul,
#             "Категория": category[0].strip() if category else None,
#             "price": price[0].strip() if price else None
#         }

#         # Поиск блока "Технические характеристики"
#         detail_docs = tree.xpath("//div[contains(@class, 'wc-tab-inner wd-scroll-content')]")
#         for doc in detail_docs:
#             if "Технические характеристики" in doc.text_content():
#                 table = doc.xpath(".//table")[0] if doc.xpath(".//table") else None
#                 if table:
#                     rows = table.xpath(".//tbody/tr")
#                     for row in rows:
#                         key = row.xpath("./td[1]//text()")
#                         value = row.xpath("./td[2]//text()")
#                         if key and value:
#                             data[key[0].strip()] = value[0].strip()
#                         elif key:
#                             data[key[0].strip()] = None  # Если нет значения, но есть ключ
#                 break
        
#         return data
#     except Exception as e:
#         print(f"Error parsing HTML: {e}")
#         return None





# async def parse_html_example(response):

#     soup = BeautifulSoup(response, "lxml")
    

#     title_element = soup.select_one("h1.sp-single-product__title")
#     if not title_element:
#         return None 

#     data = {
#         "name": soup.select_one("h1.sp-single-product__title").get_text(strip=True),
#         "articul": soup.select_one("div.sp-single-product__sku").get_text(strip=True).split(":")[-1].strip(),
#         "category": soup.select("li.sp-breadcrumbs__item")[-2].get_text(strip=True) if soup.select("li.sp-breadcrumbs__item") else None,
#         "img_url": soup.select_one('a[data-lightbox="product-slider"]').get("href"),
#         "price": soup.select_one("p.sp-single-product__price-current").get_text(strip=True).split("/")[0]
#     }

#     # Парсим характеристики
#     characteristics_section = soup.select_one("#characteristic")
#     if characteristics_section:
#         table = characteristics_section.select_one("table.table.table-bordered")
#         if table:
#             rows = table.select("tbody tr")
#             data.update({row.select_one("td:nth-of-type(1)").get_text(strip=True): row.select_one("td:nth-of-type(2)").get_text(strip=True) for row in rows})

#     return data

