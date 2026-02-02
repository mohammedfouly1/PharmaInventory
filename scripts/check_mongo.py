from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.storage import MONGODB_DB, check_connection  # noqa: E402


def main() -> None:
    ok = check_connection()
    status = "OK" if ok else "FAILED"
    print(f"MongoDB connection {status} (db={MONGODB_DB})")


if __name__ == "__main__":
    main()
