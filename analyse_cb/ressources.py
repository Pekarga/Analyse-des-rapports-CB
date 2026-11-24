"""Emplacement des ressources (modèle Excel, paramètres, référentiel, Tesseract), y compris dans l'application
Windows empaquetée (PyInstaller), où les fichiers fournis sont décompressés dans un dossier temporaire et où les
paramètres modifiables par l'utilisateur sont copiés dans son profil (%APPDATA%\\AnalyseRapportsCB)."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

NOM_APPLICATION = "AnalyseRapportsCB"


def empaquete() -> bool:
    return bool(getattr(sys, "frozen", False))


def dossier_ressources() -> Path:
    """Dossier contenant config/, modeles/ (et tesseract/ dans l'application Windows)."""
    if empaquete():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def dossier_utilisateur() -> Path:
    """Dossier des paramètres modifiables par l'utilisateur de l'application."""
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    d = Path(base) / NOM_APPLICATION
    d.mkdir(parents=True, exist_ok=True)
    return d


def dossier_local() -> Path:
    """Dossier des données volumineuses propres au poste (documents déposés, profil d'affichage) : %LOCALAPPDATA%,
    qui n'est pas synchronisé avec les profils itinérants, à défaut le dossier de l'utilisateur."""
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return dossier_utilisateur()
    d = Path(base) / NOM_APPLICATION
    d.mkdir(parents=True, exist_ok=True)
    return d


def fichier_config(nom: str) -> Path:
    """config/<nom> : en développement, le fichier du dépôt ; dans l'application, une copie modifiable dans le
    profil de l'utilisateur (créée au premier lancement à partir de la version fournie)."""
    fourni = dossier_ressources() / "config" / nom
    if not empaquete():
        return fourni
    cible = dossier_utilisateur() / nom
    if not cible.exists() and fourni.exists():
        shutil.copy2(fourni, cible)
    return cible


def configurer_tesseract() -> None:
    """Indique à pytesseract où trouver Tesseract : version intégrée à l'application, puis emplacements
    d'installation usuels sous Windows (sinon, le PATH)."""
    try:
        import pytesseract
    except ImportError:
        return
    candidats = [dossier_ressources() / "tesseract" / "tesseract.exe",
                 Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tesseract.exe",
                 Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe"]
    for exe in candidats:
        if exe.is_file():
            pytesseract.pytesseract.tesseract_cmd = str(exe)
            if (exe.parent / "tessdata").is_dir():
                os.environ.setdefault("TESSDATA_PREFIX", str(exe.parent / "tessdata"))
            return
