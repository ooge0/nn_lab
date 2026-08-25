import os
import json
from loguru import logger  # reuse the same logger configured in streamlit_app.py


class AppUtils:
    def load_archetypes(self, file_path: str):
        """
        Load archetypes JSON definition from the given file path.
        Returns a dictionary with archetype definitions.
        """
        # 1. Path existence check
        if not os.path.exists(file_path):
            abs_path = os.path.abspath(file_path)
            logger.error(f"Knowledge file not found: {abs_path}")
            raise FileNotFoundError(f"Knowledge file not found: {abs_path}")

        # 2. Open JSON and load sys_prompts data
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                logger.error("Archetypes JSON must be a dictionary at the top level.")
                raise ValueError("Archetypes JSON must be a dictionary at the top level.")

            logger.info(f"Successfully loaded archetypes from {file_path} with {len(data.keys())} entries.")
            return data

        except Exception as e:
            logger.exception(f"Failed to read archetypes file: {e}")
            raise RuntimeError(f"Failed to read archetypes file: {e}")
