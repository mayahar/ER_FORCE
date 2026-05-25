import builtins
import os
import sys


_ORIGINAL_PRINT = builtins.print


def _fallback_stream():
    return open(os.devnull, "w", encoding="utf-8", errors="replace")


def _valid_stream(stream):
    return stream is not None and hasattr(stream, "write")


def safe_print(*args, **kwargs):
    stream = kwargs.get("file") or sys.stdout
    if not _valid_stream(stream):
        return
    try:
        _ORIGINAL_PRINT(*args, **kwargs)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        text = kwargs.get("sep", " ").join(str(arg) for arg in args)
        end = kwargs.get("end", "\n")
        if hasattr(stream, "buffer"):
            stream.buffer.write(text.encode(encoding, errors="replace"))
            stream.buffer.write(end.encode(encoding, errors="replace"))
        else:
            stream.write(
                text.encode(encoding, errors="replace").decode(
                    encoding,
                    errors="replace",
                )
            )
            stream.write(
                end.encode(encoding, errors="replace").decode(
                    encoding,
                    errors="replace",
                )
            )
        if kwargs.get("flush"):
            stream.flush()
    except (AttributeError, OSError, ValueError, TypeError):
        return


def install_safe_stdio() -> None:
    # pythonw.exe sets stdout/stderr to None — Tobii/recorder code must not crash on print.
    if not _valid_stream(sys.stdout):
        sys.stdout = _fallback_stream()
    if not _valid_stream(sys.stderr):
        sys.stderr = _fallback_stream()

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, OSError, ValueError, TypeError):
                pass

    if getattr(install_safe_stdio, "_installed", False):
        return
    install_safe_stdio._installed = True

    builtins.print = safe_print
