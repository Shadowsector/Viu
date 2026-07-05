import sys
from pathlib import Path

# Гарантируем, что пакет viu импортируется из корня репозитория.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
