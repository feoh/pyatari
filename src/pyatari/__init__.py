"""PyAtari -- Educational Atari 800XL Emulator in Python."""

from pyatari.antic import ANTIC
from pyatari.audio import AudioOutput
from pyatari.clock import MasterClock
from pyatari.display import DisplaySurface
from pyatari.gtia import GTIA
from pyatari.machine import Machine
from pyatari.pia import PIA
from pyatari.pokey import POKEY

__version__ = "0.1.0"

__all__ = ["ANTIC", "AudioOutput", "DisplaySurface", "GTIA", "Machine", "MasterClock", "PIA", "POKEY", "__version__"]
