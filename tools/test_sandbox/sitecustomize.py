"""Keep CPU test subprocesses on loopback; dependency installation runs separately."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from offline import install
install()
