import re


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