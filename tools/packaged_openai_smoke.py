"""Offline smoke test for the OpenAI SDK inside a PyInstaller bundle."""

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))


def main():
    import jiter
    import pydantic
    import pydantic_core
    from model_provider import sdk_runtime_self_test

    payload = {
        "jiter": bool(jiter),
        "pydantic": pydantic.__version__,
        "pydantic_core": pydantic_core.__version__,
        "success": sdk_runtime_self_test(),
    }
    print(json.dumps(payload, ensure_ascii=False))
    if not payload["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
