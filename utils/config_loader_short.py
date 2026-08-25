import configparser
from pathlib import Path
from typing import TYPE_CHECKING, Union

ROOT_DIR = Path(__file__).resolve().parent.parent
config = configparser.ConfigParser()
config_path = ROOT_DIR / "config" / "config.ini"

if not config_path.exists():
    raise FileNotFoundError(f"Critical configuration missing at: {config_path}")

config.read(config_path)


def __getattr__(name: str) -> Union[Path, str, int]:
    """Dynamically resolves INI keys to system paths, configuration strings, or numeric limits."""
    ini_key = name.lower()

    # SECTION 1: Absolute Directories (Creates folders automatically)
    if "DIRECTORIES" in config and ini_key in config["DIRECTORIES"]:
        resolved_path = ROOT_DIR / config["DIRECTORIES"][ini_key]
        resolved_path.mkdir(parents=True, exist_ok=True)
        return resolved_path

    # SECTION 2: Static File Handles
    if "FILES" in config and ini_key in config["FILES"]:
        return ROOT_DIR / config["FILES"][ini_key]

    # SECTION 3: Raw Strings / Ollama Connection (Returns plain string)
    if "OLLAMA" in config and ini_key in config["OLLAMA"]:
        return config["OLLAMA"][ini_key]

    # SECTION 4: Numeric Limits (Returns int)
    if "EXPERIMENT" in config and ini_key in config["EXPERIMENT"]:
        return config.getint("EXPERIMENT", ini_key)

    raise AttributeError(f"Module '{__name__}' has no configuration attribute '{name}'")


if TYPE_CHECKING:
    RESULTS_DIR: Path
    LOGS_DIR: Path
    LOG_FILE_ENTRY: Path
    KNOWLEDGE_PATH: Path
    OPENAI_BASE_URL: str
    OPENAI_API_KEY: str
    MAX_TOTAL_TASKS: int
