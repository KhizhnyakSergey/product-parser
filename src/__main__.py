import asyncio
import time

from src.core import (
    ApplicationSupraten, 
    load_settings, 
    ApplicationIek, 
    ApplicationHabsev, 
    ApplicationLuminaled,
    ApplicationElectromotor,
    ApplicationVolta,
    ApplicationPanlight,
    ApplicationCablu,
    ApplicationOkm,
    ApplicationPolev,
)
from src.core.settings import load_settings


settings = load_settings()

async def scheduler():
    try:
        while True:
            await main()
            time.sleep(settings.google.repeat_in_seconds)
    except asyncio.CancelledError:
        print("Завдання планувальника скасовано.")
    except KeyboardInterrupt:
        print("Планувальник перервав користувач (Ctrl + C).")

async def start_application(app_class):
    app = app_class()
    await app.start()
    await asyncio.sleep(2)

async def main() -> None:
    app_classes = [
        ApplicationSupraten,
        ApplicationIek,
        ApplicationHabsev,
        ApplicationLuminaled,
        ApplicationElectromotor,
        ApplicationVolta,
        ApplicationPanlight,
        ApplicationCablu,
        ApplicationOkm,
        ApplicationPolev
    ]

    for app_class in app_classes:
        await start_application(app_class)

    print("Итерация завершена \n")
    

if __name__ == "__main__":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        # asyncio.run(main())
        asyncio.run(scheduler())
    except KeyboardInterrupt:
        print("Завершення роботи користувачем.")

