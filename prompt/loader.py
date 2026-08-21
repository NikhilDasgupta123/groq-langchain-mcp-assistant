from pathlib import Path

import yaml


PROMPT_FILE = Path(__file__).parent / "system.yml"


def load_system_prompt() -> str:
    with PROMPT_FILE.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    return config["assistant"]["system_prompt"]
