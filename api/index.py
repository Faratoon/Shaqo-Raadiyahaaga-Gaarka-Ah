import sys
from pathlib import Path

# Add project root to sys.path so portal_app and modules can be imported
sys.path.append(str(Path(__file__).resolve().parent.parent))

from portal_app import app
