import logging
from logging.handlers import RotatingFileHandler

def setup_logging():
    """
    Configura el servicio de logging.
    
    Permite la visualización por consola y el almacenamiento en archivos
    rotativos.

    Returns:
        logging.Logger: Instancia configurada del logger.
    """
    logger = logging.getLogger("SCA")
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(
                        "sistema.log",
                        maxBytes=5*1024*1024,
                        backupCount=3
                    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

log = setup_logging()
