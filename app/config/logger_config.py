import logging.config
import os
from pathlib import Path

import yaml


def setup_logging(name: str, config_path: str = "logging.yml", log_dir: str = "logs"):
    """
    Setup and configure logging based on an optional YAML configuration file.
    
    This function creates the log directory if it doesn't exist, loads a logging
    configuration from a YAML file if provided, or applies basic logging configuration
    with both file and stream handlers if no config file exists.
    
    Args:
        name (str): The name of the logger to configure and return.
            This is typically the module name (__name__) but can be customized.
            The returned logger will be stored under this name in the logging system.
        config_path (str, optional): Path to the YAML configuration file for logging setup.
            If the file exists, its configuration will be loaded.
            Defaults to "logging.yml".
        log_dir (str, optional): Directory path where log files will be stored.
            The directory is created automatically if it doesn't exist.
            Defaults to "logs".
    
    Returns:
        logging.Logger: A logger instance from the current module's name (__name__).
            The logger is configured with the specified handlers and formatting.
    """
    CONFIG_FILE = Path(__file__).resolve().with_name(config_path)

    CONFIG_DIR = Path(__file__).resolve().parent
    APP_DIR = CONFIG_DIR.parent
    PROJECT_ROOT = APP_DIR.parent
    LOG_DIR = PROJECT_ROOT / log_dir

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f.read())
            config["handlers"]["file"]["filename"] = str(LOG_DIR / "app.log")

            logging.config.dictConfig(config)
    else:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(f'{log_dir}/app.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
    
    return logging.getLogger(name)