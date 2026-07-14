"""Headless core smoke-check entry point."""

from __future__ import annotations

import json

from app.services.llm.manager import LLMServiceManager
from app.services.llm.providers import register_all_providers


def main() -> None:
    register_all_providers()
    print(
        json.dumps(
            {
                "status": "ready",
                "mode": "headless",
                "message": "NarratoAI core is ready; no web console is bundled.",
                "providers": LLMServiceManager.get_registered_providers_info(),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
