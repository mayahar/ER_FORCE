import builtins
import sys


_ORIGINAL_PRINT = builtins.print


def safe_print(*args, **kwargs):
    try:
        _ORIGINAL_PRINT(*args, **kwargs)
    except UnicodeEncodeError:
        stream = kwargs.get("file") or sys.stdout
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


def install_safe_stdio() -> None:
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
