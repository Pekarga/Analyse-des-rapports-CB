"""Lecture des rapports scannés (PDF image) par reconnaissance optique de caractères (OCR).

Principe :
1. chaque page est convertie en image (300 dpi) et redressée si elle est pivotée (annexes à l'italienne) ;
2. les zones à fond sombre (bandeaux de titres, en-têtes noirs des tableaux 7 et 8) sont inversées ;
3. les tableaux sont repérés grâce aux traits de leur quadrillage, découpés en cellules (lignes × colonnes)
   et chaque mot reconnu est rangé dans la cellule qui le contient ;
4. le texte hors tableaux est reconnu ligne par ligne.

Dépendances : Tesseract OCR (avec la langue française « fra »), pytesseract, opencv-python-headless,
pypdfium2 (installé avec pdfplumber).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

RESOLUTION = 300
VERSION_CACHE = 9


class OCRIndisponible(RuntimeError):
    pass


def ocr_disponible() -> tuple[bool, str]:
    try:
        import cv2  # noqa: F401  (vérifie seulement la présence du module)
        import pytesseract
        from .ressources import configurer_tesseract
        configurer_tesseract()
    except ImportError as exc:
        return False, (f"module Python manquant ({exc.name or exc}) : pip install pytesseract opencv-python-headless")
    try:
        langues = pytesseract.get_languages(config="")
    except Exception:
        return False, ("logiciel Tesseract OCR introuvable : installez-le (Windows : https://github.com/UB-Mannheim/"
                       "tesseract/wiki, en cochant la langue française) puis relancez")
    if "fra" not in langues:
        return False, "Tesseract est installé mais pas la langue française (fra)"
    return True, ""


# ------------------------------------------------------------------ cache
def _dossier_cache() -> Path:
    base = os.environ.get("ANALYSE_CB_CACHE") or (Path.home() / ".cache" / "analyse_cb")
    d = Path(base)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _empreinte(chemin: Path) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for morceau in iter(lambda: f.read(1 << 20), b""):
            h.update(morceau)
    return h.hexdigest()[:32]


# ------------------------------------------------------------------ OCR d'un document
def ocr_pdf(chemin: str | Path, progression=None) -> list[dict]:
    """Renvoie, pour chaque page, la liste ordonnée des éléments : {"type": "p"|"tableau", ...}."""
    ok, message = ocr_disponible()
    if not ok:
        raise OCRIndisponible(message)
    chemin = Path(chemin)
    fichier_cache = _dossier_cache() / f"{_empreinte(chemin)}_v{VERSION_CACHE}.json"
    if fichier_cache.exists():
        try:
            return json.loads(fichier_cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(chemin))
    pages = []
    try:
        for i in range(len(pdf)):
            if progression:
                progression(i + 1, len(pdf))
            image = pdf[i].render(scale=RESOLUTION / 72, grayscale=True).to_pil()
            pages.append(ocr_page(image))
    finally:
        pdf.close()
    try:
        fichier_cache.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return pages


def _redresser(gris):
    """Détecte l'orientation (pages à l'italienne, scans à l'envers) avec l'OSD de Tesseract."""
    import cv2
    import pytesseract

    petit = cv2.resize(gris, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    try:
        osd = pytesseract.image_to_osd(petit, config="--psm 0 -c min_characters_to_try=20",
                                       output_type=pytesseract.Output.DICT)
    except Exception:
        return gris
    angle = int(osd.get("rotate", 0))
    if angle == 0 or float(osd.get("orientation_conf", 0)) < 1.5:
        return gris
    codes = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
    return cv2.rotate(gris, codes[angle])


def _inverser_fonds_sombres(gris):
    """Inverse les zones pleines sombres (bandeaux de titres, en-têtes noirs) : texte blanc → texte noir."""
    import cv2
    import numpy as np

    _, sombre = cv2.threshold(gris, 140, 255, cv2.THRESH_BINARY_INV)
    pleins = cv2.morphologyEx(sombre, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (31, 31)))
    if not pleins.any():
        return gris
    sortie = gris.copy()
    n, _, stats, _ = cv2.connectedComponentsWithStats(pleins)
    rects = [list(stats[i][:4]) for i in range(1, n)
             if stats[i][2] >= 60 and stats[i][3] >= 30 and stats[i][4] >= 0.4 * stats[i][2] * stats[i][3]]
    # Un bandeau de titre est coupé en morceaux par les lettres blanches : on réunit les morceaux
    # situés sur la même bande horizontale (même hauteur, même ordonnée).
    rects.sort(key=lambda r: (r[1], r[0]))
    fusion: list[list[int]] = []
    for x, y, w, h in rects:
        for f in fusion:
            if abs(f[1] - y) <= 15 and abs(f[3] - h) <= 15:
                x0, x1 = min(f[0], x), max(f[0] + f[2], x + w)
                f[0], f[2] = x0, x1 - x0
                break
        else:
            fusion.append([x, y, w, h])
    for x, y, w, h in fusion:
        # Le rectangle entier est inversé (y compris les lettres blanches). Un cadre fin est tracé sur son
        # pourtour : l'en-tête noir d'un tableau devient ainsi une ligne de cellules ordinaire, et un bandeau
        # de titre isolé un simple cadre (écarté de la détection des tableaux, son texte est lu normalement).
        inverse = 255 - gris[y:y + h, x:x + w]
        inverse[inverse > 120] = 255  # l'ancien fond gris foncé devient blanc franc
        sortie[y:y + h, x:x + w] = inverse
        cv2.rectangle(sortie, (int(x), int(y)), (int(x + w - 1), int(y + h - 1)), 0, 3)
    # contraste : le fond inversé (gris clair) est ramené au blanc
    return np.ascontiguousarray(sortie)


def _desincliner(gris):
    """Corrige la légère inclinaison des scans (méthode du profil de projection horizontal)."""
    import cv2
    import numpy as np

    petit = cv2.resize(gris, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    _, b = cv2.threshold(petit, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    h, w = b.shape
    centre = (w / 2, h / 2)

    def score(angle):
        m = cv2.getRotationMatrix2D(centre, angle, 1.0)
        r = cv2.warpAffine(b, m, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        profil = r.sum(axis=1, dtype=np.float64)
        return float(np.sum(np.diff(profil) ** 2))

    angles = np.arange(-3.0, 3.01, 0.25)
    meilleur = max(angles, key=score)
    fins = np.arange(meilleur - 0.25, meilleur + 0.26, 0.05)
    meilleur = float(max(fins, key=score))
    if abs(meilleur) < 0.05:
        return gris
    H, W = gris.shape
    m = cv2.getRotationMatrix2D((W / 2, H / 2), meilleur, 1.0)
    return cv2.warpAffine(gris, m, (W, H), flags=cv2.INTER_CUBIC, borderValue=255)


def _regrouper(valeurs: list[int], ecart: int) -> list[tuple[int, int]]:
    """Regroupe des positions proches en segments (début, fin)."""
    segments: list[list[int]] = []
    for v in sorted(valeurs):
        if segments and v - segments[-1][1] <= ecart:
            segments[-1][1] = v
        else:
            segments.append([v, v])
    return [(a, b) for a, b in segments]


def _tableaux(binaire):
    """Repère les tableaux (quadrillages) et renvoie leurs grilles (bornes des lignes et colonnes)."""
    import cv2
    import numpy as np

    h, w = binaire.shape
    horiz = cv2.morphologyEx(binaire, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(40, w // 25), 1)))
    vert = cv2.morphologyEx(binaire, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(30, h // 60))))
    traits = cv2.dilate(cv2.bitwise_or(horiz, vert), cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)))
    contours, _ = cv2.findContours(traits, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    grilles = []
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw < w * 0.25 or ch < 40:
            continue
        zone_h = horiz[y:y + ch, x:x + cw]
        zone_v = vert[y:y + ch, x:x + cw]
        # bornes des lignes : rangées de pixels couvertes par un trait horizontal sur ≥ 30 % de la largeur
        lignes_y = [i for i in range(ch) if np.count_nonzero(zone_h[i]) > 0.3 * cw]
        cols_x = [j for j in range(cw) if np.count_nonzero(zone_v[:, j]) > 0.25 * ch]
        ys = [(a + b) // 2 + y for a, b in _regrouper(lignes_y, 8)]
        xs = [(a + b) // 2 + x for a, b in _regrouper(cols_x, 8)]
        if len(ys) < 2 or len(xs) < 2:
            continue
        # bornes extérieures manquantes (tableaux ouverts sur les côtés)
        if xs[0] - x > 20:
            xs.insert(0, x)
        if x + cw - xs[-1] > 20:
            xs.append(x + cw)
        if ys and ys[0] - y > 20:  # bord supérieur effacé (en-tête sombre inversé)
            ys.insert(0, y)
        if ys and y + ch - ys[-1] > 20:
            ys.append(y + ch)
        if len(ys) - 1 < 2 or len(xs) - 1 < 2:
            # Un seul rectangle (bandeau de titre, cadre de page de garde) : ce n'est pas un tableau.
            continue
        grilles.append({"bbox": (x, y, x + cw, y + ch), "ys": ys, "xs": xs})
    return grilles, cv2.bitwise_or(horiz, vert)


def _mots(image, psm: int, decalage=(0, 0)):
    import pytesseract

    d = pytesseract.image_to_data(image, lang="fra", config=f"--psm {psm} --oem 1 -c preserve_interword_spaces=1",
                                  output_type=pytesseract.Output.DICT)
    mots = []
    for i, t in enumerate(d["text"]):
        t = (t or "").strip()
        if not t or float(d["conf"][i]) < 0:
            continue
        mots.append({"t": t, "x": d["left"][i] + decalage[0], "y": d["top"][i] + decalage[1],
                     "w": d["width"][i], "h": d["height"][i], "conf": float(d["conf"][i]),
                     "cle": (d["block_num"][i], d["par_num"][i], d["line_num"][i])})
    return mots


def _nettoyer_cellule(texte: str) -> str:
    t = re.sub(r"\s+", " ", texte).strip(" |_")
    # Cellules chiffrées : corrections usuelles de l'OCR (O→0, l→1…) et espaces parasites avant la virgule.
    if re.fullmatch(r"[\dOoIl|.,%\s'’-]+", t) and sum(c.isdigit() for c in t) >= 1:
        t = t.translate(str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "|": "1", "'": "", "’": ""}))
        t = re.sub(r"\s+([,.%])", r"\1", t)
        t = re.sub(r"([,.])\s+", r"\1", t)
    return t


def _ordonner(mots: list[dict]) -> str:
    """Remet les mots d'une cellule dans l'ordre de lecture (lignes de haut en bas, puis gauche à droite)."""
    mots = sorted(mots, key=lambda m: m["y"] + m["h"] / 2)
    lignes: list[list[dict]] = []
    for m in mots:
        cy = m["y"] + m["h"] / 2
        if lignes and abs(cy - (lignes[-1][0]["y"] + lignes[-1][0]["h"] / 2)) <= max(8, 0.5 * m["h"]):
            lignes[-1].append(m)
        else:
            lignes.append([m])
    return " ".join(" ".join(x["t"] for x in sorted(l, key=lambda m: m["x"])) for l in lignes)


_MOTS_CANEVAS = re.compile(r"prevision|recouvr|ordonnanc|modification|montant|budget|motif|variation|taux|"
                           r"realisation|execution|nombre|dotation|ecart", re.I)


def _tableau_du_canevas(cellules: list[list[str]]) -> bool:
    """Les cellules chiffrées ne sont relues finement que pour les tableaux d'analyse (pas les annexes)."""
    import unicodedata

    entete = " ".join(" ".join(l) for l in cellules[:3])
    entete = "".join(ch for ch in unicodedata.normalize("NFKD", entete) if not unicodedata.combining(ch))
    return bool(_MOTS_CANEVAS.search(entete)) and len(cellules) <= 60


def _relire_chiffres(image, ys, xs, cellules) -> None:
    """Deuxième lecture des cellules chiffrées (ou vides mais encrées) en mode « chiffres uniquement »."""
    import numpy as np
    import pytesseract

    config = "--psm 7 --oem 1 -c tessedit_char_whitelist=0123456789,.%-"
    for r in range(len(ys) - 1):
        for c in range(1, len(xs) - 1):
            texte = cellules[r][c]
            numerique = re.fullmatch(r"[\dOoIl|.,%\s()'’-]*", texte or "") is not None
            if not numerique or (texte and not re.search(r"[\dOo]", texte)):
                continue
            y0, y1, x0, x1 = ys[r] + 4, ys[r + 1] - 3, xs[c] + 4, xs[c + 1] - 3
            if y1 - y0 < 12 or x1 - x0 < 12:
                continue
            zone = image[y0:y1, x0:x1]
            if np.count_nonzero(zone < 128) < 15:
                continue  # cellule réellement vide
            zone = np.pad(zone, 12, constant_values=255)
            try:
                lu = pytesseract.image_to_string(zone, lang="fra", config=config).strip()
            except Exception:
                continue
            lu = re.sub(r"\s+", " ", lu)
            if re.search(r"\d", lu):
                cellules[r][c] = lu


def ocr_page(image) -> list[dict]:
    import cv2
    import numpy as np

    gris = np.array(image.convert("L"))
    gris = _redresser(gris)
    gris = _desincliner(gris)
    gris = _inverser_fonds_sombres(gris)
    _, binaire = cv2.threshold(gris, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    grilles, traits = _tableaux(binaire)
    largeur_page = gris.shape[1]

    # Image sans les traits de tableaux (meilleure reconnaissance des chiffres dans les cellules)
    propre = gris.copy()
    propre[cv2.dilate(traits, np.ones((3, 3), np.uint8)) > 0] = 255

    elements = []
    masque_texte = propre.copy()
    for g in grilles:
        x0, y0, x1, y1 = g["bbox"]
        masque_texte[y0:y1, x0:x1] = 255
        mots = _mots(propre[y0:y1, x0:x1], 11, (x0, y0))
        ys, xs = g["ys"], g["xs"]
        par_cellule: dict[tuple[int, int], list[dict]] = {}
        for m in mots:
            cx, cy = m["x"] + m["w"] / 2, m["y"] + m["h"] / 2
            r = next((i for i in range(len(ys) - 1) if ys[i] <= cy < ys[i + 1]), None)
            c = next((j for j in range(len(xs) - 1) if xs[j] <= cx < xs[j + 1]), None)
            if r is not None and c is not None:
                par_cellule.setdefault((r, c), []).append(m)
        cellules = [["" for _ in range(len(xs) - 1)] for _ in range(len(ys) - 1)]
        for (r, c), ms in par_cellule.items():
            cellules[r][c] = _ordonner(ms)
        if _tableau_du_canevas(cellules):
            _relire_chiffres(propre, ys, xs, cellules)
        cellules = [[_nettoyer_cellule(c) for c in ligne] for ligne in cellules]
        cellules = [l for l in cellules if any(l)]
        # colonnes entièrement vides (traits doubles) supprimées
        if cellules:
            garder = [j for j in range(len(cellules[0])) if any(l[j] for l in cellules)]
            cellules = [[l[j] for j in garder] for l in cellules]
        if len(cellules) >= 1 and cellules and len(cellules[0]) >= 2:
            elements.append({"type": "tableau", "top": y0, "lignes": cellules})
        elif cellules:  # cadre sans structure de tableau : on garde le texte
            for l in cellules:
                elements.append({"type": "p", "top": y0, "texte": " ".join(c for c in l if c), "largeur": x1 - x0,
                                 "hauteur": 0})

    # Texte hors tableaux, ligne par ligne
    lignes: dict[tuple, list[dict]] = {}
    for m in _mots(masque_texte, 3):
        lignes.setdefault(m["cle"], []).append(m)
    for mots in lignes.values():
        mots.sort(key=lambda m: m["x"])
        texte = " ".join(m["t"] for m in mots).strip()
        if not texte or (len(texte) <= 2 and not texte.isalnum()):
            continue
        if sum(m["conf"] for m in mots) / len(mots) < 35 and len(texte) < 6:
            continue  # bruit (traces de perforation, tampons)
        x0 = min(m["x"] for m in mots)
        x1 = max(m["x"] + m["w"] for m in mots)
        hauteur = sorted(m["h"] for m in mots)[len(mots) // 2]
        elements.append({"type": "p", "top": min(m["y"] for m in mots), "texte": texte,
                         "largeur": (x1 - x0) * 72 / RESOLUTION, "hauteur": hauteur,
                         "x0": x0 / largeur_page})
    elements.sort(key=lambda e: e["top"])
    return elements
