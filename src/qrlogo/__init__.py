"""qrlogo: QR codes with a logo in the middle, for the web, print and e-mail."""
from .core import Style, LogoSpec, Result, generate
from . import payloads

__all__ = ["Style", "LogoSpec", "Result", "generate", "payloads"]
__version__ = "0.1.0"
