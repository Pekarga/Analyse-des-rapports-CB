"""Fichier d'analyse au format Word (document de restitution).

Le document reprend la structure et les libellés du modèle de fichier d'analyse (grille Excel de la DCB, ou modèle
importé) : identification du rapport, I. délai de transmission, II. analyse de la forme, III. analyse du fond,
IV. difficultés et suggestions, V. appréciation générale et suite à donner.

Il peut s'appuyer sur un modèle Word importé dans les Paramètres (en-tête, logo, pied de page, styles, bloc de
signature) : les champs {{EPN}}, {{CONTROLEUR}}, {{PERIODE}}… y sont remplacés, et la grille d'analyse est insérée à
l'emplacement de {{ANALYSE}} (à la fin du document s'il n'y figure pas).
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .analyse import (A_APPRECIER, A_VERIFIER, COHERENT, CONFORME, FIABLE, INCOHERENT, NON_APPLICABLE,
                      NON_CONFORME, NON_FIABLE, NON_RENSEIGNE, SANS_OBJET)

BLEU_FONCE = "1F4E78"
FOND_STATUT = {CONFORME: "C6EFCE", FIABLE: "C6EFCE", COHERENT: "C6EFCE", "Retenue": "C6EFCE",
               NON_CONFORME: "FFC7CE", NON_FIABLE: "FFC7CE", INCOHERENT: "FFC7CE", NON_RENSEIGNE: "FFC7CE",
               A_VERIFIER: "FFEB9C", A_APPRECIER: "FFEB9C", NON_APPLICABLE: "EDEDED", SANS_OBJET: "EDEDED"}
CHAMPS = (("EPN", "dénomination de l'EPN"), ("CONTROLEUR", "Contrôleur Budgétaire"), ("PERIODE", "période couverte"),
          ("DATE_RECEPTION", "date de réception par la DCB"), ("DATE_LIMITE", "date limite de transmission"),
          ("DELAI", "appréciation du délai"), ("CHARGE_ETUDES", "Chargé d'Études"), ("DATE_ANALYSE", "date de l'analyse"),
          ("RAPPORT", "nom du fichier du rapport"), ("FORME", "taux de conformité de la forme"),
          ("FOND", "taux de fiabilité / cohérence"), ("SUITE_A_DONNER", "suite à donner"),
          ("ANALYSE", "emplacement de la grille d'analyse"))
RE_CHAMP = re.compile(r"\{\{\s*([A-Z_]+)\s*\}\}")
CATEGORIES_DS = (("execution", "Principales contraintes de l'exécution du budget de l'EPN"),
                 ("controle", "Principales contraintes dans le contrôle de l'exécution du budget de l'EPN"),
                 ("gestion", "Contraintes liées à la gestion de l'établissement"))


# ------------------------------------------------------------------ mise en forme
def _ombrer(cellule, couleur: str) -> None:
    tc = cellule._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), couleur)
    tc.append(shd)


def _ecrire(cellule, texte, gras: bool = False, taille: float = 9, centre: bool = False, couleur: str | None = None,
            italique: bool = False, retrait: float = 0) -> None:
    lignes = [l for l in str(texte if texte is not None else "").split("\n")] or [""]
    cellule.text = ""
    p = cellule.paragraphs[0]
    for i, ligne in enumerate(lignes):
        if i:
            p = cellule.add_paragraph()
        p.paragraph_format.space_after = Pt(1)
        if retrait:
            p.paragraph_format.left_indent = Cm(retrait)
        if centre:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(ligne)
        r.font.size = Pt(taille)
        r.bold = gras
        r.italic = italique
        if couleur:
            r.font.color.rgb = RGBColor.from_string(couleur)


def _bordures(table) -> None:
    try:
        table.style = "Table Grid"
        return
    except (KeyError, ValueError):
        pass
    tblPr = table._tbl.tblPr
    bords = OxmlElement("w:tblBorders")
    for cote in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{cote}")
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), "4")
        e.set(qn("w:color"), "999999")
        bords.append(e)
    tblPr.append(bords)


def _grille(t, largeurs: list[float]) -> None:
    """Largeurs de colonnes fixes (respectées par Word comme par LibreOffice)."""
    t.autofit = False
    tblPr = t._tbl.tblPr
    for ancien in tblPr.findall(qn("w:tblLayout")) + tblPr.findall(qn("w:tblW")):
        tblPr.remove(ancien)
    disposition = OxmlElement("w:tblLayout")
    disposition.set(qn("w:type"), "fixed")
    tblPr.append(disposition)
    largeur = OxmlElement("w:tblW")
    largeur.set(qn("w:w"), str(int(sum(Cm(l).twips for l in largeurs))))
    largeur.set(qn("w:type"), "dxa")
    tblPr.append(largeur)
    for colonne, l in zip(t._tbl.tblGrid.findall(qn("w:gridCol")), largeurs):
        colonne.set(qn("w:w"), str(int(Cm(l).twips)))


def _tableau(doc, entetes: list[str], largeurs: list[float]):
    t = doc.add_table(rows=1, cols=len(entetes))
    _bordures(t)
    _grille(t, largeurs)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for c, (titre, l) in enumerate(zip(entetes, largeurs)):
        cell = t.rows[0].cells[c]
        cell.width = Cm(l)
        _ecrire(cell, titre, gras=True, taille=9, centre=True, couleur="FFFFFF")
        _ombrer(cell, BLEU_FONCE)
    trPr = t.rows[0]._tr.get_or_add_trPr()
    repete = OxmlElement("w:tblHeader")  # en-tête répété sur chaque page
    repete.set(qn("w:val"), "true")
    trPr.append(repete)
    return t


def _ligne(t, valeurs: list, largeurs: list[float]):
    cells = t.add_row().cells
    for c, l in zip(cells, largeurs):
        c.width = Cm(l)
    return cells


def _titre_section(doc, texte: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(texte)
    r.bold = True
    r.font.size = Pt(12)
    r.font.color.rgb = RGBColor.from_string(BLEU_FONCE)


def _paragraphes(doc, texte: str, gras: bool = False, taille: float = 10, avant: float = 0) -> None:
    for i, bloc in enumerate(b.strip() for b in str(texte or "").split("\n") if b.strip()):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_after = Pt(4)
        if avant and not i:
            p.paragraph_format.space_before = Pt(avant)
        r = p.add_run(bloc)
        r.bold = gras
        r.font.size = Pt(taille)


# Libellés de la grille de la DCB corrigés (comme dans le fichier Excel) : lignes du COGES et du comité de trésorerie
# intitulées « Contrôle de gestion / de trésorerie », numéros des tableaux 1 et 2 inversés.
CORRECTIONS = {"coges": ("controle de gestion", "COGES / Organes de supervision (Conseil de gestion)"),
               "comite_tresorerie": ("controle de tresorerie", "Comité de trésorerie"),
               "T2": ("tableau 1 : budget des trois derniers", "Tableau 2 : Budgets des trois derniers exercices"),
               "T1": ("tableau 2 : variation du budget", "Tableau 1 : Budget de l'année comparé à celui de l'année précédente")}


def _libelle(texte: str) -> str:
    t = re.sub(r"\s+", " ", str(texte or "")).replace("", "").strip()
    return t[:-1].strip() if t.endswith(":") else t


# ------------------------------------------------------------------ champs du modèle
def _valeurs(res) -> dict[str, str]:
    from .excel import suite_a_donner
    return {
        "EPN": res.infos.epn or "", "CONTROLEUR": res.infos.controleur or "(non identifié)",
        "PERIODE": res.periode.libelle,
        "DATE_RECEPTION": res.infos.date_reception.strftime("%d/%m/%Y") if res.infos.date_reception else "(non renseignée)",
        "DATE_LIMITE": res.date_limite.strftime("%d/%m/%Y") if res.date_limite else "",
        "DELAI": res.appreciation_delai, "CHARGE_ETUDES": res.infos.charge_etudes or "",
        "DATE_ANALYSE": f"{date.today():%d/%m/%Y}", "RAPPORT": res.doc.chemin.name,
        "FORME": f"{res.score_forme:.0f} %", "FOND": f"{res.score_fond:.0f} %" if res.score_fond is not None else "—",
        "SUITE_A_DONNER": suite_a_donner(res),
    }


def _paragraphes_document(doc):
    """Paragraphes du corps, des tableaux, des en-têtes et des pieds de page."""
    def dans(conteneur):
        for p in conteneur.paragraphs:
            yield p
        for t in getattr(conteneur, "tables", []):
            for ligne in t.rows:
                for cellule in ligne.cells:
                    yield from dans(cellule)
    yield from dans(doc)
    for s in doc.sections:
        for partie in (s.header, s.footer, s.first_page_header, s.first_page_footer):
            if partie is not None and not partie.is_linked_to_previous:
                yield from dans(partie)


def _remplacer(p, valeurs: dict[str, str]) -> None:
    texte = p.text
    if "{{" not in texte:
        return
    nouveau = RE_CHAMP.sub(lambda m: valeurs.get(m.group(1), m.group(0)), texte)
    if nouveau == texte or not p.runs:
        return
    p.runs[0].text = nouveau
    for r in p.runs[1:]:
        r.text = ""


def champs_du_modele(chemin: Path) -> list[str]:
    doc = Document(chemin)
    return sorted({m.group(1) for p in _paragraphes_document(doc) for m in RE_CHAMP.finditer(p.text)})


# ------------------------------------------------------------------ document de base (sans modèle importé)
def document_initial(titre: str, institution: dict | None = None, logo: Path | None = None) -> Document:
    """Document de départ : en-tête de l'institution (et logo), titre, identification, {{ANALYSE}}, signature.
    C'est aussi le modèle proposé à l'export, à personnaliser dans Word."""
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(1.8)
    sec.top_margin, sec.bottom_margin = Cm(1.6), Cm(1.6)
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10)
    entete = sec.header.paragraphs[0]
    if logo and Path(logo).suffix.lower() in (".png", ".jpg", ".jpeg", ".gif"):
        try:
            entete.add_run().add_picture(str(logo), height=Cm(1.6))
            entete = sec.header.add_paragraph()
        except Exception:  # image illisible : en-tête sans logo
            pass
    for i, ligne in enumerate(x for x in ((institution or {}).get("ligne1"), (institution or {}).get("ligne2")) if x):
        p = entete if i == 0 else sec.header.add_paragraph()
        r = p.add_run(ligne.upper() if i == 0 else ligne)
        r.bold = i == 0
        r.font.size = Pt(9)
    pied = sec.footer.paragraphs[0]
    pied.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = pied.add_run("Analyse du rapport du Contrôleur Budgétaire – {{EPN}} – {{PERIODE}}")
    r.font.size = Pt(8)
    r.font.color.rgb = RGBColor(0x6B, 0x77, 0x8A)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(10)
    r = p.add_run(titre)
    r.bold = True
    r.font.size = Pt(14)
    r.font.color.rgb = RGBColor.from_string(BLEU_FONCE)
    doc.add_paragraph("{{ANALYSE}}")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.paragraph_format.space_before = Pt(24)
    r = p.add_run("Le Chargé d'Études")
    r.bold = True
    p = doc.add_paragraph("{{CHARGE_ETUDES}}")
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    return doc


# ------------------------------------------------------------------ grille d'analyse
def _ordre_forme(res, plan) -> list:
    """Lignes de la partie II dans l'ordre du modèle ; les rubriques sans ligne dans le modèle (ajoutées dans le
    canevas, par exemple) suivent la dernière ligne de leur partie."""
    from .canevas import PAR_CODE
    avec = sorted((l for l in res.forme if plan.forme.get(l.code)), key=lambda l: plan.forme[l.code])
    sans = [l for l in res.forme if not plan.forme.get(l.code) and l.code in PAR_CODE
            and l.code not in ("justification", "annonce_plan", "annexes") and l.statut != NON_APPLICABLE]
    for l in sans:
        rub = PAR_CODE[l.code]
        famille = {rub.code, rub.parent} | {r.code for r in PAR_CODE.values() if r.parent in (rub.code, rub.parent)}
        pos = max((i for i, x in enumerate(avec) if x.code in famille), default=None)
        if pos is None:  # avant la ligne « Cohérence entre le sommaire… » (fin des rubriques)
            pos = next((i - 1 for i, x in enumerate(avec) if x.code in ("sommaire", "tableaux")), len(avec) - 1)
        avec.insert(pos + 1, l)
    return avec


def _ecrire_grille(doc, res, plan, avec_identification: bool) -> None:
    from .commentaires import aerer
    from .excel import _mention, suite_a_donner
    from .redaction import appreciation_fond, appreciation_forme, appreciation_generale
    lib, a = plan.libelles, plan.ancres

    def libelle_ligne(code, defaut, ligne=None):
        t = lib.get(ligne) if ligne else None
        if t and code in CORRECTIONS:
            from .texte import normaliser
            attendu, correct = CORRECTIONS[code]
            if normaliser(t).strip(" -").startswith(attendu):
                return correct
        return _libelle(t) if t else defaut

    mention = _mention(res)
    p = doc.add_paragraph()
    r = p.add_run((mention + " – " if mention else "") + f"Rapport analysé : {res.doc.chemin.name}"
                  + (" (document scanné)" if res.doc.ocr else "") + f" – analyse du {date.today():%d/%m/%Y}")
    r.italic = True
    r.font.size = Pt(8.5)
    r.font.color.rgb = RGBColor.from_string(BLEU_FONCE)

    # ---- identification
    if avec_identification:
        v = _valeurs(res)
        t = doc.add_table(rows=0, cols=2)
        _bordures(t)
        _grille(t, [6, 11.4])
        lignes = [(a.get("epn"), "EPN", v["EPN"]), (a.get("controleur"), "Contrôleur Budgétaire", v["CONTROLEUR"]),
                  (a.get("periode"), "Période couverte par le présent rapport", v["PERIODE"]),
                  (a.get("reception"), "Date de réception par la DCB", v["DATE_RECEPTION"]),
                  (a.get("charge"), "Chargé d'Études", v["CHARGE_ETUDES"] or "(à renseigner)"),
                  (a.get("canevas"), "Disposer du canevas en vigueur (dernière version)",
                   f"{res.canevas_en_vigueur[0]} – {res.canevas_en_vigueur[1]}")]
        for ligne, defaut, valeur in lignes:
            cells = t.add_row().cells
            cells[0].width, cells[1].width = Cm(6), Cm(11.4)
            _ecrire(cells[0], libelle_ligne(None, defaut, ligne), gras=True, taille=9.5)
            _ombrer(cells[0], "EEF2F7")
            _ecrire(cells[1], valeur, taille=9.5)

    # ---- I. délai
    titre_delai = next((_libelle(t) for r, t in sorted(lib.items()) if re.match(r"^\s*i\s*[.\-)]\s*d", t.lower())),
                       "I. DÉLAI DE TRANSMISSION")
    _titre_section(doc, titre_delai)
    largeurs = [3.2, 3.2, 3.3, 2.2, 5.5]
    t = _tableau(doc, ["Date de fin de période", "Date limite de transmission", "Date effective de transmission",
                       "Écart (jours)", "Appréciation du Chargé d'Études"], largeurs)
    cells = _ligne(t, [], largeurs)
    ecart = res.ecart_jours
    for c, val in zip(cells, [f"{res.periode.fin:%d/%m/%Y}" if res.periode.fin else "",
                              f"{res.date_limite:%d/%m/%Y}" if res.date_limite else "",
                              res.infos.date_reception.strftime("%d/%m/%Y") if res.infos.date_reception else "—",
                              "" if ecart is None else str(ecart), res.appreciation_delai]):
        _ecrire(c, val, centre=True)
    if ecart is not None:
        _ombrer(cells[4], "FFC7CE" if ecart > 0 else "C6EFCE")

    # ---- II. forme
    _titre_section(doc, libelle_ligne(None, "II. ANALYSE DE LA FORME DU RAPPORT", a.get("forme")))
    largeurs = [6.2, 2.9, 8.3]
    t = _tableau(doc, ["Critères", "Conforme / Non conforme", "Préciser"], largeurs)
    from .canevas import PAR_CODE
    for l in _ordre_forme(res, plan):
        ligne = plan.forme.get(l.code)
        rub = PAR_CODE.get(l.code)
        sous = (rub is not None and rub.niveau > 1) or (ligne and str(lib.get(ligne, "")).lstrip().startswith("-")) \
            or (l.code.startswith("T") and l.code[1:].isdigit())
        texte = libelle_ligne(l.code, l.libelle, ligne).lstrip("- ").strip()
        cells = _ligne(t, [], largeurs)
        _ecrire(cells[0], texte, gras=not sous, retrait=0.35 if sous else 0)
        _ecrire(cells[1], l.statut, centre=True, gras=True)
        _ombrer(cells[1], FOND_STATUT.get(l.statut, "FFFFFF"))
        _ecrire(cells[2], l.redige or l.precision, taille=8.5)
    _titre_section(doc, libelle_ligne(None, "Appréciation générale de la forme du rapport", a.get("appreciation_forme")))
    _paragraphes(doc, aerer(appreciation_forme(res)))

    # ---- III. fond
    _titre_section(doc, libelle_ligne(None, "III. ANALYSE DU FOND DU RAPPORT", a.get("fond")))
    largeurs = [5.2, 2.3, 2.3, 7.6]
    t = _tableau(doc, ["Rubriques (parties et sous-parties)", "Fiabilité", "Cohérence", "Commentaires"], largeurs)
    for l in sorted((x for x in res.fond if plan.fond.get(x.code)), key=lambda x: plan.fond[x.code]):
        ligne = plan.fond[l.code]
        rub = PAR_CODE.get(l.code)
        sous = (rub is not None and rub.niveau > 1) or str(lib.get(ligne, "")).lstrip().startswith("-")
        cells = _ligne(t, [], largeurs)
        _ecrire(cells[0], libelle_ligne(l.code, l.libelle, ligne).lstrip("- ").strip(), gras=not sous,
                retrait=0.35 if sous else 0)
        for c, v in ((cells[1], l.fiabilite), (cells[2], l.coherence)):
            _ecrire(c, v, centre=True, gras=True, taille=8.5)
            _ombrer(c, FOND_STATUT.get(v, "FFFFFF"))
        _ecrire(cells[3], l.redige or l.commentaire, taille=8.5)
    titre_fond = libelle_ligne(None, "Appréciation générale du fond du rapport", a.get("appreciation_fond"))
    _titre_section(doc, titre_fond.replace("de la forme", "du fond"))
    _paragraphes(doc, aerer(appreciation_fond(res)))

    # ---- IV. difficultés et suggestions
    titre_ds = next((_libelle(t) for r, t in sorted(lib.items()) if re.match(r"^\s*iv\s*[.\-)]", t.lower())),
                    "IV. ANALYSE DES DIFFICULTÉS ET SUGGESTIONS FORMULÉES PAR LE CB")
    _titre_section(doc, titre_ds)
    appreciation = "Retenue" if res.validation_directe else A_APPRECIER
    for cle, ancre, titre, entetes, largeurs in (
            ("difficultes", "difficultes", "Difficultés formulées par le CB",
             ["Catégorie", "Difficultés formulées", "Élément du rapport qui le justifie", "Appréciation du Chargé d'Études"],
             [4.2, 7.2, 3.4, 2.6]),
            ("suggestions", "suggestions", "Suggestions formulées par le CB",
             ["Catégorie", "Suggestions formulées", "Appréciation du Chargé d'Études"], [4.2, 10.6, 2.6])):
        p = doc.add_paragraph()
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_before = Pt(6)
        r = p.add_run(libelle_ligne(None, titre, a.get(ancre)))
        r.bold = True
        t = _tableau(doc, entetes, largeurs)
        elements = res.difficultes.get(cle, [])
        for cat, defaut in CATEGORIES_DS:
            prefixe = "diff" if cle == "difficultes" else "sugg"
            items = [e for e in elements if e.categorie == cat]
            cells = _ligne(t, [], largeurs)
            _ecrire(cells[0], libelle_ligne(None, defaut, a.get(f"{prefixe}_{cat}")), gras=True, taille=8.5)
            _ecrire(cells[1], "\n".join(f"• {e.texte}" for e in items) if items else "Aucun élément formulé dans cette catégorie.",
                    taille=8.5, italique=not items)
            if cle == "difficultes":
                pages = sorted({e.page for e in items if e.page})
                _ecrire(cells[2], (items[0].rubrique + (f" (p. {', '.join(map(str, pages))})" if pages else "")) if items else "",
                        taille=8.5)
            if items:
                _ecrire(cells[-1], appreciation, centre=True, gras=True, taille=8.5)
                _ombrer(cells[-1], FOND_STATUT.get(appreciation, "FFFFFF"))
        n = len(elements)
        _paragraphes(doc, (f"{n} difficulté(s) extraite(s) du rapport. " + ("Vérifier le classement par catégorie et apprécier leur pertinence." if n else
                           "Aucune difficulté n'a été extraite : vérifier la partie « Difficultés et suggestions »."))
                     if cle == "difficultes" else
                     (f"{n} suggestion(s) extraite(s) du rapport. " + ("Apprécier leur caractère opérationnel et leur lien avec les difficultés." if n else
                      "Aucune suggestion n'a été extraite.")), taille=9, avant=4)

    # ---- V. appréciation générale et suite à donner
    _titre_section(doc, libelle_ligne(None, "V. APPRÉCIATION GÉNÉRALE DU CHARGÉ D'ÉTUDES SUR LE RAPPORT",
                                      a.get("appreciation_generale")))
    _paragraphes(doc, aerer(appreciation_generale(res)))
    _titre_section(doc, libelle_ligne(None, "Suite à donner", a.get("suite")))
    _paragraphes(doc, suite_a_donner(res), gras=True)


def rediger_word(res, sortie: str | Path, modele_word: Path | None = None, institution: dict | None = None,
                 logo: Path | None = None) -> Path:
    """Fichier d'analyse Word d'un rapport analysé."""
    from . import canevas
    plan = canevas.plan()
    titre = _libelle(plan.libelles.get(1) or "Analyse du rapport du Contrôleur Budgétaire")
    doc = Document(modele_word) if modele_word else document_initial(titre, institution, logo)
    valeurs = _valeurs(res)
    paragraphes = list(_paragraphes_document(doc))
    repere = next((p for p in paragraphes if re.search(r"\{\{\s*ANALYSE\s*\}\}", p.text)), None)
    corps = doc.element.body
    avant = set(id(e) for e in corps)
    # identification du rapport dans la grille, sauf si le modèle importé affiche déjà {{EPN}} lui-même
    champ_epn = any(re.search(r"\{\{\s*EPN\s*\}\}", p.text) for p in paragraphes)
    _ecrire_grille(doc, res, plan, avec_identification=modele_word is None or not champ_epn)
    nouveaux = [e for e in corps if id(e) not in avant and e.tag != qn("w:sectPr")]
    if repere is not None and repere._p.getparent() is corps:
        for e in nouveaux:
            repere._p.addprevious(e)
        corps.remove(repere._p)
    for p in _paragraphes_document(doc):
        _remplacer(p, valeurs)
    sortie = Path(sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    doc.save(sortie)
    return sortie


def modele_initial(sortie: Path, institution: dict | None = None, logo: Path | None = None) -> Path:
    """Modèle Word de départ (à personnaliser dans Word, puis à réimporter)."""
    from . import canevas
    titre = _libelle(canevas.plan().libelles.get(1) or "Analyse du rapport du Contrôleur Budgétaire")
    doc = document_initial(titre, institution, logo)
    p = doc.paragraphs[1]  # {{ANALYSE}}
    note = p.insert_paragraph_before()
    r = note.add_run("EPN : {{EPN}} – Contrôleur Budgétaire : {{CONTROLEUR}} – Période : {{PERIODE}} – "
                     "Reçu le {{DATE_RECEPTION}} (date limite : {{DATE_LIMITE}})")
    r.font.size = Pt(9)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    doc.save(sortie)
    return sortie
