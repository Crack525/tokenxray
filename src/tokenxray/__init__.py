"""TokenXRay — See where your AI coding tokens actually go."""

try:
    from importlib.metadata import version
    __version__ = version("tokenxray")
except Exception:
    __version__ = "unknown"
