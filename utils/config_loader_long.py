import configparser
from pathlib import Path

# Get the absolute path of the directory containing this file
BASE_DIR = Path(__file__).resolve().parent

# Initialize and read the configuration file
_config = configparser.ConfigParser()
_config.read(BASE_DIR / "config/config.ini")

# Safely extract directories and convert them to system-agnostic absolute paths
RESULTS_DIR = BASE_DIR / _config.get("DIRECTORIES", "results_dir", fallback="results/lab_experiment_results")
LOGS_DIR = BASE_DIR / _config.get("DIRECTORIES", "logs_dir", fallback="logs")

# Automatically ensure the physical directories exist on the hard drive
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
