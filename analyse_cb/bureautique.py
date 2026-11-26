"""Conversion des documents Word 97-2003 (.doc) en .docx, pour pouvoir les lire.

Le format .doc (binaire) n'est pas lisible directement : il est converti avec Microsoft Word, piloté sans
fenêtre par PowerShell (poste Windows où Word est installé), à défaut avec LibreOffice. La conversion est faite une
seule fois par document (copie convertie gardée dans le dossier local de l'application, d'après le contenu du fichier).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .ressources import dossier_local

MESSAGE_SANS_CONVERTISSEUR = (
    "le format Word 97-2003 (.doc) n'a pas pu être converti : ni Microsoft Word ni LibreOffice n'est disponible sur ce "
    "poste. Ouvrez le document dans Word puis « Fichier > Enregistrer sous > Document Word (.docx) », et déposez le "
    "fichier .docx obtenu.")

SCRIPT_WORD = r"""
$ErrorActionPreference = 'Stop'
$w = New-Object -ComObject Word.Application
$w.Visible = $false
$w.DisplayAlerts = 0
try {
  $d = $w.Documents.Open($env:CB_SOURCE, $false, $true, $false)
  $d.SaveAs([ref]$env:CB_CIBLE, [ref]16)
  $d.Close([ref]0)
} finally {
  $w.Quit()
}
"""


def _soffice() -> str | None:
    for nom in ("soffice", "libreoffice"):
        trouve = shutil.which(nom)
        if trouve:
            return trouve
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", "")):
        exe = Path(base) / "LibreOffice" / "program" / "soffice.exe"
        if base and exe.is_file():
            return str(exe)
    return None


def _par_word(source: Path, cible: Path) -> bool:
    if not sys.platform.startswith("win"):
        return False
    env = {**os.environ, "CB_SOURCE": str(source), "CB_CIBLE": str(cible)}
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", SCRIPT_WORD],
                       env=env, timeout=180, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return False
    return cible.is_file() and cible.stat().st_size > 0


def _par_libreoffice(source: Path, cible: Path) -> bool:
    exe = _soffice()
    if not exe:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        try:
            subprocess.run([exe, "--headless", "--norestore", f"-env:UserInstallation=file:///{Path(tmp).as_posix().lstrip('/')}/profil",
                            "--convert-to", "docx", "--outdir", tmp, str(source)],
                           timeout=180, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            return False
        produit = Path(tmp) / (source.stem + ".docx")
        if not produit.is_file():
            return False
        shutil.copy2(produit, cible)
    return True


def convertisseur_disponible() -> str | None:
    """« Microsoft Word », « LibreOffice » ou None (indication pour l'interface)."""
    if sys.platform.startswith("win") and shutil.which("powershell"):
        return "Microsoft Word (s'il est installé)" + (" ou LibreOffice" if _soffice() else "")
    return "LibreOffice" if _soffice() else None


def doc_vers_docx(source: str | Path) -> Path:
    """Copie .docx d'un document .doc (ValueError si aucun convertisseur n'est disponible)."""
    source = Path(source)
    empreinte = hashlib.sha256(source.read_bytes()).hexdigest()[:20]
    dossier = dossier_local() / "conversions"
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / f"{empreinte}.docx"
    if cible.is_file() and cible.stat().st_size > 0:
        return cible
    if _par_word(source, cible) or _par_libreoffice(source, cible):
        return cible
    raise ValueError(f"{source.name} : {MESSAGE_SANS_CONVERTISSEUR}")
