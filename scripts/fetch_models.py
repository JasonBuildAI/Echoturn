"""Install the optional models, for a clone that has not been installed itself."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from echoturn.models import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
