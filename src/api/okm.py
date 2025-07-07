import asyncio
from typing import (
    List, 
    Optional,
    Dict, 
    Any,
)

from src.session.aiohttp import AiohttpSession
from src.utils.user_agent import get_user_agent
from src.core.settings import load_settings
from src.utils.logger import Logger


class OkmAPI:

    API: str = 'https://okm.md/'

    def __init__(
            self, 
            tasks_starts_at_once: int = 50, 
            proxy: Optional[str] = None,
            logger: Optional[Logger] = None
    ) -> None:
        self._session = AiohttpSession(api=self.API, proxy=proxy)
        self._semaphore = asyncio.Semaphore(tasks_starts_at_once)
        self.settings = load_settings()
        self.logger = logger or Logger()
        self._headers = {
            'accept': '*/*',
            'accept-language': 'ru',
        }
        self._cookies = {}

    async def __aenter__(self) -> "OkmAPI":
        return self
    
    async def __aexit__(self, *args) -> None:
        await self._session.close()

    async def _make_request(self, url: str, page: int = None, slug: str = None) -> str:
        """Универсальный метод для выполнения запроса."""
        
        full_url = url
        self._headers['user-agent'] = get_user_agent() 
        if slug and page:
            params = {
                'parent_slug': f'{slug}',
                'parent_type': 'category',
                'is_stock': 'false',
                # 'price__lte': '61600',
                'page': f'{page}',
                'order_by': 'popularity',
            }
            response = await self._session(
                'GET', 
                full_url, 
                headers=self._headers, 
                params=params
            )
        else:    
            response = await self._session(
                    'GET', 
                    full_url, 
                    headers=self._headers, 
                )
        
        return response

    async def get_categories(self) -> Dict[str, Any]:
  
        categories_list = await self._make_request('https://api.okm.md/api/core/menu-items/')
        if not isinstance(categories_list, list):
            raise ValueError("Expected list response from API")
        
        categories = {}
        for category in categories_list:
            # Добавляем основную категорию
            categories[category['title']] = category['slug']
        
        return categories
    
    
    async def get_all_products(self, slug: str) -> List[str]:
        
        pages = await self._make_request('https://api.okm.md/api/products/items/', 1, slug)
        total_pages = pages['pages']['total_pages']

        product_links = []
        for page in range(total_pages):
            data = await self._make_request('https://api.okm.md/api/products/items/', page + 1, slug)
            
            results = data['results']
            for product in results:
                slug_product = product['slug']
                product_links.append(slug_product)

        return product_links


    async def get_data_product(self, slug: str):

        data = await self._make_request(f'https://api.okm.md/api/products/items/{slug}/')

        brand = None
        if data.get('brand') is not None: 
            brand = data['brand'].get('title')  
            
        category = None
        if data.get('breadcrumbs') and data['breadcrumbs'].get('category'):
            category = data['breadcrumbs']['category'].get('title')

        subcategory = None
        if data.get('breadcrumbs') and data['breadcrumbs'].get('subcategory'):
            subcategory = data['breadcrumbs']['subcategory'].get('title')

        price = data.get('price')
        if price:
            price = str(price).replace('.', ',')

        result = {
            "URL": f'https://okm.md/ru/product/{slug}',
            "Название": data.get('title'),
            "price": str(price) if price else None,
            "Категория": category,
            "Субкатегория": subcategory,
            "Артикул": data.get('code'),  
            "Бренд": brand
        }

        # Обработка атрибутов
        product_attributes = data.get('product_attributes', [])
        for attribute in product_attributes:
            name = attribute.get('attribute')
            value = attribute.get('attribute_value')
            if name and value: 
                result[name] = value

        return result
