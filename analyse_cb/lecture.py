"""Lecture des rapports des Contrôleurs Budgétaires (.docx et .pdf) dans un modèle commun.

Le document est représenté par une liste ordonnée de blocs (paragraphes et tableaux),
ce qui permet ensuite de retrouver les rubriques du canevas et leur contenu.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .texte import normaliser

RE_LIGNE_SOMMAIRE = re.compile(r"(\.{4,}|…{2,}|_{4,})\s*\d{1,3}\s*$|\s\d{1,3}\s*$")
RE_LEGENDE = re.compile(r"^\s*tableau\s*(n\s*[°o]?\s*)?(\d+)", re.I)
# Puces Word/PDF : tiret, puces Unicode et puces de la police Symbol (zone privée U+F0xx)
RE_PUCE = re.compile("^\\s*(?:[-\u2013\u2022\u25cf\u25aa\u27a2*\uf000-\uf0ff]+|\\d+[.)]|[a-z][.)])\\s+")


@dataclass
class Bloc:
    index: int
    type: str  # "p" ou "tableau"
    texte: str = ""
    style: str = ""
    gras: bool = False
    page: int | None = None
    lignes: list[list[str]] = field(default_factory=list)  # pour les tableaux
    legende: str = ""
    sommaire: bool = False  # ligne de la table des matières
    largeur: float = 0.0  # PDF : largeur de la dernière ligne de texte (pour reconstituer les paragraphes)

    @property
    def norm(self) -> str:
        return normaliser(self.texte)

    @property
    def niveau_titre(self) -> int | None:
        """Niveau de titre déclaré par le style Word (Titre 1, Heading 2…)."""
        m = re.search(r"(heading|titre)\s*(\d)", normaliser(self.style))
        return int(m.group(2)) if m else None

    @property
    def candidat_titre(self) -> bool:
        if self.type != "p" or self.sommaire:
            return False
        t = self.texte.strip()
        if not t or len(t) > 140:
            return False
        if re.search(r"[;,]\s*$", t):
            return False  # élément d'énumération (ex. plan annoncé dans l'introduction : « II-Analyse … ; »)
        if self.niveau_titre is not None or normaliser(self.style) in ("title", "titre"):
            return True
        if self.gras and len(t) <= 120:
            return True
        # Numérotation : I. / II.1- / 1. / A) / X-1-
        # (l'OCR lit souvent « II » comme « Il », « I1 » ou « 11 », et les chiffres romains en minuscules « iv-1 »)
        if re.match(r"^\s*([IVXLivxl1]{1,5}|\d{1,2}|[A-H])\s*([.\-)]|\.\d)", t) and len(t) <= 120:
            return True
        if t.isupper() and 3 < len(t) <= 100 and sum(c.isalpha() for c in t) >= 4:
            return True
        return False


@dataclass
class DocumentRapport:
    chemin: Path
    blocs: list[Bloc]
    avertissements: list[str] = field(default_factory=list)
    nb_pages: int | None = None
    images_derniere_page: int = 0  # indice de présence de signature/cachet (PDF)
    ocr: bool = False  # texte obtenu par reconnaissance optique (document scanné)

    @property
    def paragraphes(self) -> list[Bloc]:
        return [b for b in self.blocs if b.type == "p"]

    @property
    def tableaux(self) -> list[Bloc]:
        return [b for b in self.blocs if b.type == "tableau"]

    def texte(self, debut: int = 0, fin: int | None = None, avec_tableaux: bool = False) -> str:
        fin = len(self.blocs) if fin is None else fin
        morceaux = []
        for b in self.blocs[debut:fin]:
            if b.type == "p" and not b.sommaire:
                morceaux.append(b.texte)
            elif avec_tableaux and b.type == "tableau":
                morceaux.extend(" | ".join(l) for l in b.lignes)
        return "\n".join(morceaux)

    @property
    def texte_complet(self) -> str:
        return self.texte()


def lire_rapport(chemin: str | Path) -> DocumentRapport:
    chemin = Path(chemin)
    ext = chemin.suffix.lower()
    if ext == ".docx":
        doc = _lire_docx(chemin)
    elif ext == ".pdf":
        doc = _lire_pdf(chemin)
    elif ext == ".doc":
        raise ValueError(f"{chemin.name} : format .doc non pris en charge, enregistrez-le en .docx "
                         "(ou convertissez-le avec LibreOffice : soffice --headless --convert-to docx).")
    else:
        raise ValueError(f"{chemin.name} : format non pris en charge ({ext}). Formats acceptés : .docx, .pdf")
    _marquer_sommaire(doc)
    _associer_legendes(doc)
    return doc


# --------------------------------------------------------------------------- DOCX
def _lire_docx(chemin: Path) -> DocumentRapport:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    d = docx.Document(str(chemin))
    blocs: list[Bloc] = []

    def ajouter_paragraphe(p: Paragraph):
        texte = p.text.strip()
        if not texte:
            return
        runs = [r for r in p.runs if r.text.strip()]
        gras = bool(runs) and all(
            (r.bold or (r.style is not None and r.style.font.bold) or (p.style is not None and p.style.font.bold))
            for r in runs)
        style = p.style.name if p.style is not None else ""
        blocs.append(Bloc(len(blocs), "p", texte, style, gras))

    def ajouter_tableau(t: Table):
        lignes = []
        for row in t.rows:
            cellules, precedente = [], None
            for c in row.cells:
                # Les cellules fusionnées sont répétées par python-docx : on les dédoublonne.
                if precedente is not None and c._tc is precedente:
                    continue
                precedente = c._tc
                cellules.append(re.sub(r"\s+", " ", c.text).strip())
            if any(cellules):
                lignes.append(cellules)
        if lignes:
            blocs.append(Bloc(len(blocs), "tableau", lignes=lignes))

    for element in d.element.body.iterchildren():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "p":
            ajouter_paragraphe(Paragraph(element, d))
        elif tag == "tbl":
            ajouter_tableau(Table(element, d))
        elif tag == "sdt":  # table des matières automatique de Word
            for p in element.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                par = Paragraph(p, d)
                if par.text.strip():
                    b = Bloc(len(blocs), "p", par.text.strip(), "TOC", False, sommaire=True)
                    blocs.append(b)

    # En-têtes/pieds de page ignorés. Images en fin de document : indice de signature scannée.
    images = len(d.inline_shapes)
    doc = DocumentRapport(chemin, blocs)
    doc.images_derniere_page = images
    return doc


# --------------------------------------------------------------------------- PDF
def _lire_pdf(chemin: Path) -> DocumentRapport:
    import pdfplumber

    blocs: list[Bloc] = []
    avertissements: list[str] = []
    with pdfplumber.open(str(chemin)) as pdf:
        nb_pages = len(pdf.pages)
        images_derniere = len(pdf.pages[-1].images) if pdf.pages else 0
        for num, page in enumerate(pdf.pages, start=1):
            elements = []  # (top, type, contenu)
            try:
                tables = page.find_tables()
            except Exception:  # pragma: no cover - PDF exotiques
                tables = []
            zones = [t.bbox for t in tables]
            for t in tables:
                lignes = [[re.sub(r"\s+", " ", c or "").strip() for c in row] for row in t.extract()]
                lignes = [l for l in lignes if any(l)]
                if lignes:
                    elements.append((t.bbox[1], "tableau", lignes))

            def hors_tableau(obj):
                x = (obj["x0"] + obj["x1"]) / 2
                y = (obj["top"] + obj["bottom"]) / 2
                return not any(z[0] <= x <= z[2] and z[1] <= y <= z[3] for z in zones)

            texte_page = page.filter(hors_tableau) if zones else page
            for ligne in texte_page.extract_text_lines(keep_blank_chars=False):
                t = ligne["text"].strip()
                if not t or re.fullmatch(r"(page\s*)?\d+(\s*(sur|/)\s*\d+)?", t, re.I):
                    continue  # numéros de page
                chars = ligne.get("chars") or []
                gras = bool(chars) and all("bold" in (c.get("fontname") or "").lower() for c in chars if c["text"].strip())
                taille = max((c.get("size", 0) for c in chars), default=0)
                elements.append((ligne["top"], "p", (t, gras, taille, ligne["x1"] - ligne["x0"])))
            elements.sort(key=lambda e: e[0])
            for _, typ, contenu in elements:
                if typ == "tableau":
                    blocs.append(Bloc(len(blocs), "tableau", page=num, lignes=contenu))
                else:
                    t, gras, taille, largeur = contenu
                    blocs.append(Bloc(len(blocs), "p", t, f"taille {taille:.0f}", gras, page=num, largeur=largeur))

    ocr = False
    if sum(len(b.texte) for b in blocs) < 60 * max(1, nb_pages):
        # PDF scanné (image) : reconnaissance optique des caractères.
        from .ocr import OCRIndisponible, ocr_pdf

        try:
            pages = ocr_pdf(chemin, progression=_PROGRESSION_OCR)
        except OCRIndisponible as exc:
            raise DocumentIllisible(
                f"{chemin.name} est un PDF scanné (image, sans texte) et l'OCR n'est pas disponible : {exc}. "
                "À défaut, demandez la version Word du rapport.") from None
        ocr = True
        blocs = []
        for num, elements in enumerate(pages, start=1):
            for e in elements:
                if e["type"] == "tableau":
                    blocs.append(Bloc(len(blocs), "tableau", page=num, lignes=e["lignes"]))
                elif not re.fullmatch(r"(page\s*)?\d+(\s*(sur|/)\s*\d+)?", e["texte"].strip(), re.I):
                    blocs.append(Bloc(len(blocs), "p", e["texte"], f"ocr {e.get('hauteur', 0)}", False, page=num,
                                      largeur=e.get("largeur", 0.0)))
        avertissements.append(
            "Rapport scanné : le texte et les tableaux ont été lus par reconnaissance optique (OCR). Les anomalies "
            "chiffrées sont à confirmer sur le document original (erreur de lecture possible).")
    doc = DocumentRapport(chemin, blocs, avertissements, nb_pages, ocr=ocr)
    doc.images_derniere_page = images_derniere
    _fusionner_lignes_pdf(doc)
    return doc


class DocumentIllisible(ValueError):
    pass


def _PROGRESSION_OCR(page: int, total: int) -> None:  # remplacée par l'interface (barre de progression)
    if RAPPEL_PROGRESSION is not None:
        RAPPEL_PROGRESSION(page, total)


RAPPEL_PROGRESSION = None


def _fusionner_lignes_pdf(doc: DocumentRapport) -> None:
    """Regroupe les lignes de texte d'un même paragraphe PDF (hors titres et puces)."""
    largeur_page: dict[int, float] = {}
    for b in doc.blocs:
        if b.type == "p" and b.page is not None:
            largeur_page[b.page] = max(largeur_page.get(b.page, 0.0), b.largeur)
    fusion: list[Bloc] = []
    for b in doc.blocs:
        prec = fusion[-1] if fusion else None
        # Tableau coupé par un saut de page : on recolle la suite au tableau précédent.
        if (prec is not None and b.type == "tableau" and prec.type == "tableau" and b.page
                and prec.page is not None and b.page == prec.page + 1
                and len(b.lignes[0]) == len(prec.lignes[0])):
            prec.lignes.extend(b.lignes)
            continue
        if (prec is not None and b.type == "p" and prec.type == "p" and prec.page == b.page
                and not prec.candidat_titre and not b.candidat_titre
                and prec.largeur >= 0.75 * largeur_page.get(b.page, 0.0)  # ligne précédente pleine
                and not RE_PUCE.match(b.texte)
                and not RE_LEGENDE.match(b.texte) and not prec.norm.startswith("source")
                and not re.search(r"(\.{4,}|…{2,}|_{4,})\s*\d{1,3}\s*$", prec.texte)
                and not re.search(r"[.:;!?]$", prec.texte.strip())):
            prec.texte = prec.texte.rstrip() + " " + b.texte.lstrip()
            prec.largeur = b.largeur
            continue
        fusion.append(b)
    for i, b in enumerate(fusion):
        b.index = i
    doc.blocs = fusion


# --------------------------------------------------------------------------- post-traitements
def _marquer_sommaire(doc: DocumentRapport) -> None:
    """Repère les lignes de la table des matières (pour ne pas les confondre avec les vrais titres)."""
    paragraphes = doc.paragraphes
    for i, b in enumerate(paragraphes):
        n = b.norm
        if "toc" in normaliser(b.style) or "table des matieres" in normaliser(b.style):
            b.sommaire = True
        elif re.search(r"(\.{4,}|…{2,}|_{4,})\s*\d{1,3}\s*$", b.texte):
            b.sommaire = True
        elif ((re.search(r"[.…_]{2,}[.…_,/ ]{4,}", b.texte) or re.search(r"[.…_]{3,}\s*\S{0,4}\s*$", b.texte))
              and len(b.texte) < 200
              and (b.page is None or b.page <= 5)):  # points de conduite lus par OCR
            b.sommaire = True
        elif re.search(r"\t\s*\d{1,3}\s*$", b.texte) and len(b.texte) < 150:
            b.sommaire = True
        if n in ("table des matieres", "sommaire", "liste des tableaux", "liste des sigles et abreviations"):
            b.sommaire = True
            # Zone de sommaire : lignes suivantes terminées par un numéro de page.
            sans_numero = 0
            for suivant in paragraphes[i + 1:i + 80]:
                if (re.search(r"(\s|[.…_])\d{1,3}\s*$", suivant.texte)
                        or re.search(r"[.…_]{3,}\s*\S{0,4}\s*$", suivant.texte)) and len(suivant.texte) < 160:
                    suivant.sommaire = True
                    sans_numero = 0
                elif suivant.sommaire:
                    continue
                else:
                    sans_numero += 1
                    if sans_numero >= 3:
                        break


def _associer_legendes(doc: DocumentRapport) -> None:
    for i, b in enumerate(doc.blocs):
        if b.type != "tableau":
            continue
        for j in range(i - 1, max(-1, i - 3), -1):
            prec = doc.blocs[j]
            if prec.type == "p" and RE_LEGENDE.match(prec.texte):
                b.legende = prec.texte
                break
            if prec.type == "tableau":
                break
        if not b.legende and i + 1 < len(doc.blocs):  # légende placée sous le tableau
            suiv = doc.blocs[i + 1]
            if suiv.type == "p" and RE_LEGENDE.match(suiv.texte):
                b.legende = suiv.texte
