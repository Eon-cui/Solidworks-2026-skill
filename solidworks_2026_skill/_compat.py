"""Windows GBK terminal compatibility — centralized stdout config."""
import sys


def _configure_stdout():
    """Reconfigure stdout for UTF-8 on Windows GBK terminals."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


_configure_stdout()
