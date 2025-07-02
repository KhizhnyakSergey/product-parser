import logging
import os
from logging import Handler
from logging.handlers import RotatingFileHandler

from src.core.settings import path


class Logger(logging.Logger):
    def __init__(
        self,
        name: str = "root",
        level: int = logging.DEBUG,
        use_default_handlers: bool = True,
    ) -> None:
        super().__init__(name, level)
        os.makedirs(path("logs"), exist_ok=True)
        if use_default_handlers:
            self.set_default_handlers()

    def set_default_handlers(self) -> None:
        file: Handler = RotatingFileHandler(
            # filename=path("logs", f"app.log"),
            filename=path("logs", "root.log"),
            encoding="utf-8",
            backupCount=0,
            maxBytes=104857600,  # 100 MB as 1024^2 when 1 MB = 1024
            errors="warning",
        )
        file.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(name)s %(levelname)s -> %(message)s",
                datefmt="%Y.%m.%d %H:%M",
            )
        )
        stream: Handler = logging.StreamHandler()
        stream.setFormatter(
            logging.Formatter(
                fmt="%(levelname)s %(name)s -> %(message)s", datefmt="%Y.%m.%d %H:%M"
            )
        )
        for handler in (stream, file):
            self.handlers.append(handler)
