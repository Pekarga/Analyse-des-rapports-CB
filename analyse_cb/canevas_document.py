"""Lecture d'un document de canevas (note de la DCB, Word ou PDF, y compris scanné) pour actualiser le canevas.

Le document est lu comme un rapport (lecture.lire_rapport) ; on en retient :
- la référence du texte (« note n°0580/MBPE/DGBF/DCB du 26 juillet 2023 ») ;
- les éléments du plan : parties (« I. », « INTRODUCTION », titres de niveau 1), sous-parties (« I.1 », « 1. »,
  « a) ») et éléments énumérés (« - Texte de création ; ») ;
- les tableaux prescrits (« Tableau n°3 : Présentation des ressources par nature économique »).
Chaque élément est rapproché des rubriques du canevas en vigueur ; les éléments sans correspondance sont proposés
comme nouvelles rubriques, et les rubriques absentes du document comme « non exigées » (à confirmer).
Rien n'est enregistré ici : les propositions sont appliquées dans la page Paramètres, puis enregistrées.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from . import canevas
from .modele import libelle_norme
from .ressources import dossier_utilisateur
from .texte import normaliser

RE_REFERENCE = re.compile(
    r"\b(note|circulaire|arr[êe]t[ée]|d[ée]cision|instruction)\s+n\s*[°ºo]\s*[\w/.\-]+"
    r"(?:\s+du\s+(?:\d{1,2}(?:er)?\s+[a-zéû]+\s+\d{4}|\d{1,2}[/.]\d{1,2}[/.]\d{4}))?", re.I)
RE_TABLEAU = re.compile(r"^tableau\s*(?:n\s*[°ºo.]?\s*)?(\d{1,2})\s*[:\-–.]?\s*(.*)$")
RE_ROMAIN = re.compile(r"^\s*([IVX]{1,5})\s*[.\-–)]\s*(?!\d)\S")
RE_ROMAIN_SOUS = re.compile(r"^\s*[IVX]{1,5}\s*[.\-]\s*\d")
RE_ARABE = re.compile(r"^\s*\d{1,2}((\s*\.\s*\d+)+\s*[.\-–)]?|\s*[.\-–)])\s*\S")
RE_LETTRE = re.compile(r"^\s*[A-Ha-h]\s*[.)]\s*\S")
RE_PUCE = re.compile(r"^\s*[-–•●▪➢*]\s*\S")
RE_NUMERO = re.compile(r"^\s*(([IVX]{1,5}|\d{1,2}|[A-Ha-h])((\s*\.\s*\d+)+\s*[.\-–)]?|\s*[.\-–)])\s*"
                       r"|[-–•●▪➢*\uf0d8\uf0b7]\s*)+")
PARTIES_HORS_NUMERO = ("introduction", "conclusion", "annexes", "annexe")
PREAMBULE = re.compile(r"ministere|republique|direction|union|canevas|cabinet|^note\b|^objet\b|^reference|"
                       r"controleur budgetaire$|rapport (trimestriel|periodique|du controleur)")
DOSSIER_DOCUMENT = "canevas_document"


def _nettoyer(texte: str) -> str:
    t = RE_NUMERO.sub("", texte).strip()
    t = re.sub(r"\(\s*(le cas [ée]ch[ée]ant|s.il (en )?existe|s.applique[^)]*|[^)]*rapport annuel[^)]*)\s*\)", "", t,
               flags=re.I)
    t = re.sub(r",?\s*le cas [ée]ch[ée]ant", "", t, flags=re.I)
    t = re.sub(r"[\s;:.,]+$", "", t).strip()
    if t.isupper():
        t = t[:1] + t[1:].lower()
    return t[:1].upper() + t[1:] if t else t


def _exigence(texte: str) -> str:
    n = normaliser(texte)
    if re.search(r"le cas echeant|s.il (en )?existe", n):
        return "cas_echeant"
    if re.search(r"rapport annuel", n):
        return "annuel"
    return "obligatoire"


def _niveau(b) -> int | None:
    """1 : partie ; 2 : sous-partie ; 3 : élément énuméré ; None : texte courant."""
    t = b.texte.strip()
    if not t or len(t) > 170 or b.type != "p" or b.sommaire:
        return None
    n = normaliser(RE_NUMERO.sub("", t))
    if RE_ROMAIN.match(t) and not RE_ROMAIN_SOUS.match(t):
        return 1
    if n in PARTIES_HORS_NUMERO or (n.split(" ")[0] in PARTIES_HORS_NUMERO and len(n) < 40):
        return 1
    if b.niveau_titre:
        return min(b.niveau_titre, 3)
    if RE_ROMAIN_SOUS.match(t) or RE_ARABE.match(t) or RE_LETTRE.match(t):
        return 2
    if RE_PUCE.match(t) or re.search(r"\blist|\bliste", normaliser(b.style)):
        return 3  # élément énuméré (tiret, puce, ou style de liste Word)
    if t.isupper() and 3 < len(t) <= 100:
        return 1
    if b.gras and len(t) <= 120:
        return 2
    return None


def _correspond(r, n: str) -> bool:
    if any(re.search(m, n) for m in r.titres):
        return True
    ln = libelle_norme(r.libelle)
    if not ln:
        return False
    court, long_ = sorted((ln, n), key=len)
    return ln == n or (len(court) >= 10 and re.search(rf"(^|\s){re.escape(court)}(\s|$)", long_) is not None)


def _rubrique_pour(n: str, niveau: int, partie: str | None, prises: set[str]):
    libres = [r for r in canevas.RUBRIQUES if r.code not in prises]
    if niveau == 1:
        groupes = [[r for r in libres if r.niveau == 1], libres]
    else:
        groupes = [[r for r in libres if r.parent == partie], [r for r in libres if r.niveau > 1], libres]
    for g in groupes:
        for r in g:
            if _correspond(r, n):
                return r
    if niveau > 1:  # rubriques sans titre dédié (ex. « Texte de création »), d'après leur contenu
        for r in libres:
            if r.parent == partie and r.contenu and any(re.search(m, n) for m in r.contenu):
                return r
    return None


def analyser_document(chemin: Path, nom: str) -> dict:
    """Propositions de mise à jour du canevas d'après un document de canevas."""
    from .lecture import lire_rapport
    canevas.actualiser()
    doc = lire_rapport(chemin)
    texte = doc.texte(avec_tableaux=False)
    m = RE_REFERENCE.search(texte)
    reference = re.sub(r"\s+", " ", m.group(0)).strip() if m else ""
    reference = reference[:1].lower() + reference[1:] if reference else ""

    elements, tableaux = [], []
    debut = False
    for b in doc.blocs:
        lignes = [b.texte] if b.type == "p" else [" ".join(c for c in ligne if c) for ligne in b.lignes]
        for t in lignes:
            sans = normaliser(RE_NUMERO.sub("", t)).strip()
            mt = RE_TABLEAU.match(sans)
            if mt and len(t) <= 200:
                num = int(mt.group(1))
                libelle = _nettoyer(re.sub(r"^\s*tableau\s*(n\s*[°ºo.]?\s*)?\d{1,2}\s*[:\-–.]?\s*", "",
                                           RE_NUMERO.sub("", t), flags=re.I))
                if libelle and num not in {x["numero"] for x in tableaux}:
                    tableaux.append({"numero": num, "libelle": libelle})
                continue
            if b.type != "p":
                continue
            niveau = _niveau(b)
            if niveau is None:
                continue
            libelle = _nettoyer(t)
            n = normaliser(libelle)
            if not n or len(n) < 3 or re.match(r"^(liste des )?tableaux\b|^(nb|n\.b|source)\b", n):
                continue
            if not debut:
                connu = niveau == 1 and any(r.niveau == 1 and _correspond(r, n) for r in canevas.RUBRIQUES)
                if not (connu or (RE_ROMAIN.match(t) and not PREAMBULE.search(n))):
                    continue
                debut = True
            elements.append({"texte": t.strip(), "libelle": libelle, "norme": n, "niveau": niveau,
                             "exigence": _exigence(t)})

    # Rapprochement avec le canevas en vigueur, dans l'ordre du document
    prises: set[str] = set()
    partie = None  # code de la partie courante (rubrique existante ou nouvelle partie proposée)
    derniere_partie = None
    retrouvees, nouvelles = [], []
    for i, e in enumerate(elements):
        r = _rubrique_pour(e["norme"], e["niveau"], partie if e["niveau"] > 1 else None, prises)
        if r is not None:
            prises.add(r.code)
            if r.niveau == 1:
                partie = derniere_partie = r.code
            retrouvees.append({"texte": e["libelle"], "code": r.code, "libelle": r.libelle, "niveau": r.niveau,
                               "libelle_different": libelle_norme(e["libelle"]) != libelle_norme(r.libelle)})
            continue
        cle = f"nouveau_doc_{i}"
        if e["niveau"] == 1:
            nouvelles.append({"cle": cle, "libelle": e["libelle"], "niveau": 1, "parent": None,
                              "apres": derniere_partie, "exigence": e["exigence"], "texte": e["texte"]})
            partie = derniere_partie = cle
        elif partie:
            nouvelles.append({"cle": cle, "libelle": e["libelle"], "niveau": 2, "parent": partie, "apres": None,
                              "exigence": e["exigence"], "texte": e["texte"]})
    libelles_parties = {r.code: r.libelle for r in canevas.RUBRIQUES if r.niveau == 1}
    libelles_parties.update({n["cle"]: n["libelle"] for n in nouvelles if n["niveau"] == 1})
    for n in nouvelles:
        n["parent_libelle"] = libelles_parties.get(n["parent"]) if n["parent"] else None
        n["apres_libelle"] = libelles_parties.get(n["apres"]) if n["apres"] else None
    absentes = [{"code": r.code, "libelle": r.libelle, "niveau": r.niveau,
                 "parent_libelle": libelles_parties.get(r.parent) if r.parent else None}
                for r in canevas.RUBRIQUES if r.code not in prises and not r.ignoree and elements]

    actuels = {t.numero: t for t in canevas.TABLEAUX}
    tabs = []
    for t in sorted(tableaux, key=lambda x: x["numero"]):
        a = actuels.get(t["numero"])
        tabs.append({"numero": t["numero"], "libelle": t["libelle"], "code": a.code if a else None,
                     "libelle_actuel": a.libelle if a else None,
                     "different": bool(a) and libelle_norme(a.libelle) != libelle_norme(t["libelle"])})
    tableaux_absents = [{"code": t.code, "numero": t.numero, "libelle": t.libelle} for t in canevas.TABLEAUX
                        if tableaux and t.numero not in {x["numero"] for x in tableaux} and not t.ignoree]

    document = conserver(chemin, nom)
    return {"nom": nom, "document": document, "reference": reference,
            "reference_actuelle": canevas.reference(), "elements": len(elements),
            "retrouvees": retrouvees, "nouvelles": nouvelles, "absentes": absentes,
            "tableaux": tabs, "tableaux_absents": tableaux_absents,
            "ocr": bool(getattr(doc, "ocr", False))}


# ------------------------------------------------------------------ document de référence conservé
def _dossier() -> Path:
    return dossier_utilisateur() / DOSSIER_DOCUMENT


def conserver(chemin: Path, nom: str) -> dict:
    """Copie du dernier document de canevas importé (consultable depuis les Paramètres)."""
    d = _dossier()
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    cible = d / (re.sub(r'[\\/:*?"<>|]+', "_", Path(nom).name) or "canevas")
    shutil.copy2(chemin, cible)
    info = {"nom": cible.name, "importe_le": datetime.now().isoformat(timespec="seconds")}
    (d / "document.json").write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    return info


def document() -> dict | None:
    try:
        info = json.loads((_dossier() / "document.json").read_text(encoding="utf-8"))
        return info if (_dossier() / info["nom"]).exists() else None
    except (OSError, ValueError, KeyError):
        return None


def chemin_document() -> Path | None:
    info = document()
    return _dossier() / info["nom"] if info else None
