"""Outils de normalisation du texte et de lecture des nombres au format français."""
from __future__ import annotations

import re
import unicodedata

_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "`": "'", "´": "'", " ": " ", " ": " ",
                              "–": "-", "—": "-", "‐": "-", "\t": " "})


def normaliser(texte: str | None) -> str:
    """Minuscules, sans accents, apostrophes et espaces harmonisés."""
    if not texte:
        return ""
    t = texte.translate(_APOSTROPHES)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("œ", "oe").replace("Œ", "oe").lower()
    return re.sub(r"\s+", " ", t).strip()


def nb_mots(texte: str) -> int:
    return len(re.findall(r"\w{2,}", texte or ""))


def extrait(texte: str, longueur: int = 180) -> str:
    t = re.sub(r"\s+", " ", texte or "").strip()
    return t if len(t) <= longueur else t[: longueur - 1].rsplit(" ", 1)[0] + "…"


_RE_NOMBRE = re.compile(r"^\(?[-+]?[\d\s.,]*\d[\d\s.,]*\)?\s*%?$")


def lire_nombre(valeur, taux: bool = False) -> float | None:
    """Convertit « 1 234 567 », « 12,5 % », « (3 000) », « 1.234.567 » en nombre.

    Renvoie None si la cellule ne contient pas un nombre.
    """
    if valeur is None:
        return None
    if isinstance(valeur, (int, float)):
        return float(valeur)
    s = str(valeur).translate(_APOSTROPHES).strip()
    s = s.replace("FCFA", "").replace("F CFA", "").replace("XOF", "").strip()
    if not s or not _RE_NOMBRE.match(s):
        return None
    negatif = s.startswith("(") and s.endswith(")") or s.lstrip("(").startswith("-")
    s = s.strip("()%+- ").replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        if s.count(",") > 1:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    elif "." in s:
        if s.count(".") > 1:
            s = s.replace(".", "")
        else:
            entier, dec = s.split(".")
            if len(dec) == 3 and not taux and entier not in ("", "0"):
                s = entier + dec  # séparateur de milliers
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if negatif else v


def decimales(valeur) -> int:
    """Nombre de décimales affichées dans une cellule (pour la tolérance d'arrondi)."""
    s = str(valeur or "").strip().rstrip("%").strip()
    m = re.search(r"[.,](\d+)$", s)
    if not m or (len(m.group(1)) == 3 and "%" not in str(valeur)):
        return 0
    return len(m.group(1))


def format_montant(v: float | None) -> str:
    if v is None:
        return "—"
    if abs(v - round(v)) < 1e-9:
        return f"{v:,.0f}".replace(",", " ")
    return f"{v:,.2f}".replace(",", " ").replace(".", ",")


def format_taux(v: float | None) -> str:
    return "—" if v is None else f"{v:.2f} %".replace(".", ",")
