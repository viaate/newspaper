"""Send the PDF to the printer: CUPS on Linux/macOS, SumatraPDF on Windows."""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _sumatra():
    found = shutil.which("SumatraPDF")
    if found:
        return found
    for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", "")):
        candidate = Path(base) / "SumatraPDF" / "SumatraPDF.exe"
        if base and candidate.exists():
            return str(candidate)
    return None


def send(pdf, printer=""):
    pdf = str(pdf)
    if sys.platform == "win32":
        sumatra = _sumatra()
        if not sumatra:
            raise SystemExit("Install SumatraPDF (https://www.sumatrapdfreader.org) so the paper can print silently.")
        target = ["-print-to", printer] if printer else ["-print-to-default"]
        subprocess.run([sumatra, *target, "-print-settings", "fit", "-silent", pdf], check=True)
        return
    cmd = ["lp", "-o", "media=Letter", "-o", "fit-to-page"]
    if printer:
        cmd += ["-d", printer]
    subprocess.run([*cmd, pdf], check=True)
