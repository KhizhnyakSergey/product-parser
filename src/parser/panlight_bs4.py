import re
import json
import html

from bs4 import BeautifulSoup

from src.utils.normalize_data import normalize_name


async def data_extraction(response):

    soup = BeautifulSoup(response, "lxml")
    
    return 


    
