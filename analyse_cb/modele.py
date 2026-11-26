"""Modèle du fichier d'analyse (document de restitution).

Le modèle utilisé est celui de la DCB fourni avec l'application, ou un modèle importé par l'utilisateur dans les
Paramètres (conservé dans son profil). Les cellules à remplir ne sont pas repérées par des adresses fixes : chaque
ligne est retrouvée d'après son libellé en colonne A (« II. ANALYSE DE LA FORME DU RAPPORT », « Introduction »,
« - Texte de création », « Suite à donner »…). Un modèle dont la disposition a changé (lignes ajoutées pour de nouvelles
rubriques, libellés reformulés, mise en forme, logo) reste ainsi utilisable ; la ligne de chaque rubrique peut aussi
être choisie dans les Paramètres.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .ressources import dossier_ressources, dossier_utilisateur
from .texte import normaliser

MODELE_DCB = dossier_ressources() / "modeles" / "Fichier_analyse_des_rapports_des_CB.xlsx"
NOM_PERSONNALISE = "modele_fichier_analyse.xlsx"
NOM_META = "modele_fichier_analyse.json"

# Repères du modèle : (nom, motif cherché dans le libellé normalisé de la colonne A, repère après lequel chercher,
# obligatoire, désignation). Les repères obligatoires doivent figurer dans tout modèle importé.
ANCRES: tuple[tuple[str, str, str | None, bool, str], ...] = (
    ("epn", r"^epn\b", None, False, "EPN"),
    ("controleur", r"^controleur budgetaire", "epn", False, "Contrôleur Budgétaire"),
    ("periode", r"^periode couverte", "epn", False, "Période couverte par le rapport"),
    ("reception", r"^date de reception", "epn", False, "Date de réception par la DCB"),
    ("charge", r"^charge d.etudes", "epn", False, "Chargé d'Études"),
    ("canevas", r"canevas en vigueur", None, False, "Disposer du canevas en vigueur"),
    ("delai", r"^date de fin de periode", None, False, "Tableau du délai de transmission (« Date de fin de période »)"),
    ("forme", r"^ii\s*[.\-)]?\s*analyse de la forme", None, True, "II. ANALYSE DE LA FORME DU RAPPORT"),
    ("forme_global", r"^presence de toutes les parties", "forme", True,
     "Présence de toutes les parties et sous-parties obligatoires du rapport (partie II)"),
    ("sommaire", r"coherence entre le sommaire", "forme_global", False, "Cohérence entre le sommaire et le contenu"),
    ("tableaux", r"presentation des tableaux", "forme_global", False, "Présentation des tableaux et annexes"),
    ("signature", r"signe et date", "forme_global", False, "Le rapport est signé et daté"),
    ("appreciation_forme", r"^appreciation generale", "forme_global", True,
     "Appréciation générale de la forme du rapport"),
    ("fond", r"^iii\s*[.\-)]?\s*analyse du fond", "appreciation_forme", True, "III. ANALYSE DU FOND DU RAPPORT"),
    ("fond_global", r"^presence de toutes les parties", "fond", True,
     "Présence de toutes les parties et sous-parties obligatoires du rapport (partie III)"),
    ("appreciation_fond", r"^appreciation generale", "fond_global", True, "Appréciation générale du fond du rapport"),
    ("difficultes", r"difficultes formulees", "appreciation_fond", False, "Difficultés formulées par le CB"),
    ("diff_execution", r"contraintes? (de|dans) l.execution du budget", "difficultes", False,
     "Principales contraintes de l'exécution du budget (difficultés)"),
    ("diff_controle", r"contraintes? dans le controle", "difficultes", False,
     "Principales contraintes dans le contrôle de l'exécution (difficultés)"),
    ("diff_gestion", r"gestion de l.etablissement", "difficultes", False,
     "Contraintes liées à la gestion de l'établissement (difficultés)"),
    ("appreciation_difficultes", r"^appreciation generale des difficultes", "difficultes", False,
     "Appréciation générale des difficultés formulées"),
    ("suggestions", r"suggestions formulees", "difficultes", False, "Suggestions formulées par le CB"),
    ("sugg_execution", r"contraintes? (de|dans) l.execution du budget", "suggestions", False,
     "Principales contraintes de l'exécution du budget (suggestions)"),
    ("sugg_controle", r"contraintes? dans le controle", "suggestions", False,
     "Principales contraintes dans le contrôle de l'exécution (suggestions)"),
    ("sugg_gestion", r"gestion de l.etablissement", "suggestions", False,
     "Contraintes liées à la gestion de l'établissement (suggestions)"),
    ("appreciation_suggestions", r"^appreciation generale des suggestions?", "suggestions", False,
     "Appréciation générale des suggestions formulées"),
    ("appreciation_generale", r"^v\s*[.\-)]?\s*appreciation generale", "appreciation_fond", True,
     "V. APPRÉCIATION GÉNÉRALE DU CHARGÉ D'ÉTUDES"),
    ("suite", r"^suite a donner", "appreciation_generale", True, "Suite à donner"),
)
DESIGNATION = {nom: d for nom, _, _, _, d in ANCRES}

# Tableaux du canevas : mots du libellé qui les identifient dans la grille (la grille de la DCB numérote 1 et 2
# à l'inverse du canevas : on se fie au contenu, pas au numéro).
MOTS_TABLEAUX = {"T1": r"variation|compare|annee precedente", "T2": r"trois derniers", "T3": r"ressources",
                 "T4": r"emplois|nature de depenses", "T5": r"execution .*recettes", "T6": r"execution .*depenses",
                 "T7": r"differes", "T8": r"rejets"}


def libelle_norme(texte) -> str:
    """Libellé de la colonne A ramené à l'essentiel (sans puces, numérotation, parenthèses ni « le cas échéant »)."""
    t = normaliser(str(texte or ""))
    t = re.sub(r"\([^)]*\)?", " ", t)
    t = re.sub(r",?\s*le cas echeant", " ", t)
    t = re.sub(r"^[^a-z0-9]+", "", t)
    t = re.sub(r"^([ivx]+|\d+(\.\d+)*)\s*[.\-)]\s*", "", t)
    t = re.sub(r"^(tableau\s*\d+\s*:?\s*)", "", t)
    t = re.sub(r"[\s:;.]+$", "", t)
    return re.sub(r"\s+", " ", t).strip()


@dataclass
class Plan:
    """Lignes du modèle à remplir."""
    chemin: Path
    libelles: dict[int, str]  # ligne → libellé de la colonne A (lignes non vides)
    ancres: dict[str, int] = field(default_factory=dict)
    forme: dict[str, int] = field(default_factory=dict)  # code → ligne (partie II : rubriques, tableaux, lignes fixes)
    fond: dict[str, int] = field(default_factory=dict)  # code → ligne (partie III)
    manquantes: list[str] = field(default_factory=list)  # repères obligatoires introuvables

    @property
    def valide(self) -> bool:
        return not self.manquantes

    def premiere_vide(self, apres: int, limite: int | None = None) -> int:
        """Première ligne vide (colonne A) après la ligne `apres` : zone de saisie qui suit un intitulé."""
        r = apres + 1
        while r in self.libelles and (limite is None or r < limite):
            r += 1
        return r

    def lignes_zone(self, debut: str, fin: str | tuple[str, ...]) -> list[tuple[int, str]]:
        """Lignes non vides strictement comprises entre deux repères (le premier repère de fin trouvé)."""
        if debut not in self.ancres:
            return []
        fins = [self.ancres[f] for f in ((fin,) if isinstance(fin, str) else fin) if f in self.ancres
                and self.ancres[f] > self.ancres[debut]]
        borne = min(fins) if fins else max(self.libelles, default=0) + 1
        return [(r, t) for r, t in sorted(self.libelles.items()) if self.ancres[debut] < r < borne]


def _lire_libelles(chemin: Path) -> dict[int, str]:
    from openpyxl import load_workbook
    wb = load_workbook(chemin, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        out = {}
        for i, ligne in enumerate(ws.iter_rows(min_col=1, max_col=1, values_only=True), start=1):
            v = ligne[0] if ligne else None
            if v is not None and str(v).strip():
                out[i] = str(v)
        return out
    finally:
        wb.close()


def _ancres(libelles: dict[int, str]) -> dict[str, int]:
    trouvees: dict[str, int] = {}
    normes = {r: normaliser(t) for r, t in libelles.items()}
    for nom, motif, apres, _, _ in ANCRES:
        depart = trouvees.get(apres, 0) if apres else 0
        if apres and apres not in trouvees:
            continue
        for r in sorted(normes):
            if r > depart and re.search(motif, normes[r]):
                trouvees[nom] = r
                break
    return trouvees


def _correspond(libelle: str, candidats: set[str], strict: bool) -> bool:
    if libelle in candidats:
        return True
    if strict:
        return False
    for c in candidats:
        court, long_ = sorted((c, libelle), key=len)
        if len(court) >= 10 and re.search(rf"(^|\s){re.escape(court)}(\s|$)", long_):
            return True
    return False


def _aligner(zone: list[tuple[int, str]], rubriques: list, alias: dict[str, set[str]]) -> dict[str, int]:
    """Rubriques du canevas (dans l'ordre) ↔ lignes de la zone : correspondance exacte des libellés en avançant dans
    la grille, à défaut correspondance partielle sur les lignes proches ; puis rubriques ajoutées, partout."""
    normes = [(r, libelle_norme(t)) for r, t in zone]
    affectees: dict[str, int] = {}
    prises: set[int] = set()
    pos = 0
    for rub in [r for r in rubriques if not getattr(r, "perso", False)]:
        candidats = {c for c in alias.get(rub.code, set()) | {libelle_norme(rub.libelle)} if c}
        trouve = None
        for i in range(pos, len(normes)):
            if normes[i][0] not in prises and _correspond(normes[i][1], candidats, True):
                trouve = i
                break
        if trouve is None:
            for i in range(pos, min(pos + 4, len(normes))):
                if normes[i][0] not in prises and _correspond(normes[i][1], candidats, False):
                    trouve = i
                    break
        if trouve is not None:
            affectees[rub.code] = normes[trouve][0]
            prises.add(normes[trouve][0])
            pos = trouve + 1
    for rub in [r for r in rubriques if getattr(r, "perso", False)]:
        candidats = {libelle_norme(rub.libelle)} | {libelle_norme(i) for i in getattr(rub, "intitules", ())}
        for strict in (True, False):
            r = next((r for r, t in normes if r not in prises and _correspond(t, candidats, strict)), None)
            if r is not None:
                affectees[rub.code] = r
                prises.add(r)
                break
    return affectees


def calculer_plan(chemin: Path, rubriques: list, tableaux: list, alias: dict[str, set[str]] | None = None,
                  forcees: dict[str, int] | None = None) -> Plan:
    """Lignes à remplir d'un modèle, pour le canevas donné. `forcees` : ligne choisie dans les Paramètres pour une
    rubrique ou un tableau (0 : aucune ligne)."""
    libelles = _lire_libelles(chemin)
    plan = Plan(Path(chemin), libelles, _ancres(libelles))
    plan.manquantes = [d for nom, _, _, oblig, d in ANCRES if oblig and nom not in plan.ancres]
    alias = alias or {}
    forcees = forcees or {}
    a = plan.ancres
    for code in ("forme_global", "sommaire", "tableaux", "signature"):
        if code in a:
            plan.forme["global_forme" if code == "forme_global" else code] = a[code]
    if "fond_global" in a:
        plan.fond["global_fond"] = a["fond_global"]

    # Partie II : rubriques (avant les lignes sommaire / tableaux / signature), puis tableaux.
    zone_forme = plan.lignes_zone("forme_global", ("sommaire", "tableaux", "signature", "appreciation_forme"))
    plan.forme.update(_aligner(zone_forme, rubriques, alias))
    zone_tab = plan.lignes_zone("tableaux", ("signature", "appreciation_forme"))
    prises = set()
    for tab in tableaux:
        motif = MOTS_TABLEAUX.get(tab.code)
        candidats = {libelle_norme(tab.libelle)}
        for r, t in zone_tab:
            n = libelle_norme(t)
            if r not in prises and ((motif and re.search(motif, n)) or _correspond(n, candidats, False)):
                plan.forme[tab.code] = r
                prises.add(r)
                break

    # Choix faits dans les Paramètres
    for code, ligne in forcees.items():
        if not ligne:
            plan.forme.pop(code, None)
        elif ligne in libelles:
            for autre in [c for c, r in plan.forme.items() if r == ligne and c != code]:
                plan.forme.pop(autre)
            plan.forme[code] = int(ligne)

    # Partie III : mêmes rubriques ; une rubrique dont la ligne de la partie II a été choisie est cherchée d'après
    # le libellé de cette ligne.
    zone_fond = plan.lignes_zone("fond_global", "appreciation_fond")
    alias_fond = {k: set(v) for k, v in alias.items()}
    for code, ligne in forcees.items():
        if ligne and ligne in libelles:
            alias_fond[code] = {libelle_norme(libelles[ligne])}
    rubs_fond = [r for r in rubriques if r.code in plan.forme]
    plan.fond.update(_aligner(zone_fond, rubs_fond, alias_fond))
    return plan


# ------------------------------------------------------------------ modèle en vigueur
def chemin_personnalise() -> Path:
    return dossier_utilisateur() / NOM_PERSONNALISE


def modele_courant() -> Path:
    p = chemin_personnalise()
    return p if p.exists() else MODELE_DCB


def lire_meta() -> dict:
    try:
        return json.loads((dossier_utilisateur() / NOM_META).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def ecrire_meta(meta: dict) -> None:
    (dossier_utilisateur() / NOM_META).write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


def lignes_forcees() -> dict[str, int]:
    return {k: int(v) for k, v in (lire_meta().get("lignes") or {}).items() if isinstance(v, int)}


def info() -> dict:
    perso = chemin_personnalise().exists()
    meta = lire_meta()
    return {"personnalise": perso, "nom": meta.get("nom") if perso else "Modèle de la DCB (fourni avec l'application)",
            "importe_le": meta.get("importe_le") if perso else None, "chemin": str(modele_courant())}


def importer(source: Path, nom: str, rubriques: list, tableaux: list, alias: dict) -> Plan:
    """Vérifie puis adopte un modèle importé. ValueError si des repères indispensables sont introuvables."""
    if Path(nom).suffix.lower() != ".xlsx":
        raise ValueError("Le modèle doit être un classeur Excel (.xlsx).")
    try:
        plan = calculer_plan(Path(source), rubriques, tableaux, alias)
    except Exception as e:  # classeur illisible
        raise ValueError(f"Le fichier n'a pas pu être lu comme classeur Excel ({e}).") from None
    if plan.manquantes:
        raise ValueError("Ce modèle ne peut pas être utilisé : les lignes suivantes sont introuvables dans la "
                         "colonne A de la première feuille : " + " ; ".join(plan.manquantes)
                         + ". Partez du modèle actuel (bouton « Exporter le modèle ») et conservez ces intitulés.")
    shutil.copy2(source, chemin_personnalise())
    ecrire_meta({"nom": Path(nom).name, "importe_le": datetime.now().isoformat(timespec="seconds"), "lignes": {}})
    return plan


def reinitialiser() -> None:
    """Retour au modèle de la DCB (les lignes choisies pour le modèle importé sont oubliées)."""
    for p in (chemin_personnalise(), dossier_utilisateur() / NOM_META):
        if p.exists():
            p.unlink()


def exporter(dossier: Path) -> Path:
    """Copie du modèle en vigueur, à modifier dans Excel puis à réimporter."""
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / ("Modèle du fichier d'analyse" + (" (personnalisé)" if chemin_personnalise().exists() else "")
                       + ".xlsx")
    shutil.copy2(modele_courant(), cible)
    return cible
