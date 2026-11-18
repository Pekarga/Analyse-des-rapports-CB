"""Identification des tableaux 1 à 8 du canevas et contrôles arithmétiques.

Contrôles de fiabilité (internes à chaque tableau) :
- Montant actuel = Montant initial + Modifications (tableaux 3 et 4) ;
- Taux de réalisation = Recouvrement / Prévision finale (tableau 5), écart = Prévision − Recouvrement ;
- Taux d'exécution = Ordonnancement / Budget actuel (tableau 6) ;
- Variation = N − (N−1) et taux de variation (tableau 1) ;
- Sous-totaux = somme des lignes du groupe, Total général = somme des lignes ;
- Taux des motifs de différés / rejets (tableaux 7 et 8).

Contrôles de cohérence (entre tableaux) :
- Budget N et N−1 identiques dans les tableaux 1 et 2 ;
- Total des ressources (T3) = total des emplois (T4) = budget N (T1) ;
- Prévisions des tableaux d'exécution (T5, T6) = montants des tableaux de présentation (T3, T4).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .canevas import TABLEAU_PAR_CODE
from .lecture import Bloc, DocumentRapport
from .texte import decimales, format_montant, format_taux, lire_nombre, normaliser


@dataclass
class Constat:
    """Anomalie (ou information) relevée par un contrôle automatique."""
    rubrique: str
    controle: str
    message: str
    gravite: str = "Majeure"  # Majeure, Mineure, Information
    nature: str = "fiabilite"  # fiabilite, coherence, forme, delai
    tableau: str = ""
    ligne: str = ""
    attendu: str = ""
    constate: str = ""


@dataclass
class LigneTableau:
    libelle: str
    type: str  # ligne, groupe, sous_total, total, vide
    valeurs: dict[str, float] = field(default_factory=dict)
    brut: dict[str, str] = field(default_factory=dict)


@dataclass
class TableauAnalyse:
    code: str | None
    bloc: Bloc
    colonnes: dict[str, int] = field(default_factory=dict)
    lignes: list[LigneTableau] = field(default_factory=list)
    nb_lignes_entete: int = 1

    @property
    def nom(self) -> str:
        if self.code:
            return f"Tableau {TABLEAU_PAR_CODE[self.code].numero} ({TABLEAU_PAR_CODE[self.code].libelle})"
        return "Tableau non identifié"

    def total(self, role: str) -> float | None:
        """Total général déclaré, ou à défaut somme des lignes de détail."""
        for l in self.lignes:
            if l.type == "total" and role in l.valeurs:
                return l.valeurs[role]
        details = [l.valeurs[role] for l in self.lignes if l.type == "ligne" and role in l.valeurs]
        if details:
            return sum(details)
        sous_totaux = [l.valeurs[role] for l in self.lignes if l.type == "sous_total" and role in l.valeurs]
        return sum(sous_totaux) if sous_totaux else None

    def somme_groupe(self, motif: str, role: str) -> float | None:
        """Somme d'un groupe (ex. « ressources propres », « personnel ») pour un rôle de colonne."""
        groupe, total, vu = None, 0.0, False
        valeur_entete = None
        for l in self.lignes:
            n = normaliser(l.libelle)
            if l.type == "groupe":
                if groupe and vu:
                    break
                groupe = re.search(motif, n) is not None
                valeur_entete = l.valeurs.get(role) if groupe else None
                continue
            if not groupe:
                continue
            if l.type == "sous_total" and role in l.valeurs:
                return l.valeurs[role]
            if l.type == "ligne" and role in l.valeurs:
                total += l.valeurs[role]
                vu = True
            if l.type == "total":
                break
        if vu:
            return total
        return valeur_entete


# ------------------------------------------------------------------ identification
RE_GROUPE = re.compile(
    r"^(\d\s*[-.)]?\s*)?((depenses|charges) (de |d.)?)?(personnel|biens et services|transferts?|investissements?|"
    r"fonctionnement)\b(?!.*\d{4})|"
    r"^(ressources|recettes) (du budget general|propres|de l.etat|exterieures|d.emprunt)\s*:?$|^autres (ressources|recettes)\s*:?$")
RE_TOTAL = re.compile(r"^(total|total general|total global|total des (ressources|recettes|depenses|emplois)|"
                      r"total budget|total general des \w+)\s*:?$|^total general")
RE_SOUS_TOTAL = re.compile(r"^(sous[- ]?totale?|s/total|s/t\b|total\s+\S)")

SIGNATURES = [
    ("T7", lambda h, l: "motif" in h and "differe" in (h + l)),
    ("T8", lambda h, l: "motif" in h and "rejet" in (h + l)),
    ("T5", lambda h, l: "recouvr" in h or ("prevision" in h and ("realis" in h or "encaiss" in h))),
    ("T6", lambda h, l: "ordonnanc" in h or "taux d.execution" in h or ("budget actuel" in h and "engag" in h)),
    ("T2", lambda h, l: "n-2" in h.replace(" ", "") or "trois derniers" in l),
    ("T1", lambda h, l: "variation" in h or ("n-1" in h.replace(" ", "") and "modification" not in h)),
    ("T3", lambda h, l: "modification" in h and ("ressource" in h or "recette" in h or "ressources" in l)),
    ("T4", lambda h, l: "modification" in h and ("depense" in h or "activit" in h or "emploi" in h or "emplois" in l)),
]

SIGNATURES_LEGENDE = [
    ("T7", r"differe"), ("T8", r"rejet"), ("T5", r"execution .{0,25}recettes|recouvrement"),
    ("T6", r"execution .{0,25}depenses"), ("T2", r"trois derniers"), ("T1", r"annee precedente|compare"),
    ("T3", r"ressources"), ("T4", r"emplois|depenses"),
]


def _entete(lignes: list[list[str]]) -> int:
    """Nombre de lignes d'en-tête : lignes sans valeur chiffrée dont les colonnes 2+ portent des intitulés.

    S'arrête à la première ligne chiffrée ou à une ligne de regroupement (seule la 1re colonne remplie).
    """
    for i, l in enumerate(lignes[:4]):
        if i == 0:
            continue
        chiffree = any(lire_nombre(c) is not None for c in l[1:] if c and not re.fullmatch(r"(19|20)\d\d", c.strip()))
        intitules = any(c for c in l[1:])
        if chiffree or not intitules:
            return i
    return 1


def identifier(bloc: Bloc) -> TableauAnalyse:
    nb_entete = _entete(bloc.lignes)
    largeur = max(len(l) for l in bloc.lignes)
    entetes = []
    for j in range(largeur):
        morceaux = [l[j] for l in bloc.lignes[:nb_entete] if j < len(l) and l[j]]
        entetes.append(normaliser(" ".join(dict.fromkeys(morceaux))))
    h = " | ".join(entetes)
    leg = normaliser(bloc.legende)
    code = None
    for c, test in SIGNATURES:
        if test(h, leg):
            code = c
            break
    if code is None and leg:
        for c, motif in SIGNATURES_LEGENDE:
            if re.search(motif, leg):
                code = c
                break
    tab = TableauAnalyse(code, bloc, nb_lignes_entete=nb_entete)
    if code:
        tab.colonnes = _roles(code, entetes)
        _lire_lignes(tab)
    return tab


def _roles(code: str, entetes: list[str]) -> dict[str, int]:
    roles: dict[str, int] = {}

    def prendre(role, *motifs, exclure=None):
        for motif in motifs:
            for j, e in enumerate(entetes):
                if j == 0 or j in roles.values():
                    continue
                if re.search(motif, e) and not (exclure and re.search(exclure, e)):
                    roles[role] = j
                    return

    if code in ("T3", "T4"):
        prendre("initial", r"initial")
        prendre("modif", r"modif")
        prendre("actuel", r"actuel|final|definitif|revise|corrige")
    elif code == "T5":
        prendre("initial", r"initial")
        prendre("final", r"final|definitiv|actuel|revise|corrige")
        prendre("realise", r"recouvr|encaiss|realis(e|ee|ees|es|ations?)\b(?!.*taux)", exclure=r"taux")
        prendre("taux", r"taux")
        prendre("ecart", r"ecart|reste")
    elif code == "T6":
        prendre("initial", r"initial")
        prendre("actuel", r"actuel|final|definitif|revise|corrige")
        prendre("engage", r"engag", exclure=r"taux")
        prendre("realise", r"ordonnanc|liquid|mandat|execut", exclure=r"taux")
        prendre("taux", r"taux")
    elif code == "T1":
        prendre("n1", r"n\s*-\s*1|\(a\)")
        prendre("n", r"annee n\b|\(b\)|^n$")
        prendre("variation", r"montant|\(c")
        prendre("taux", r"taux|%")
        _roles_annees(entetes, roles, ["n1", "n"])
    elif code == "T2":
        prendre("n2", r"n\s*-\s*2")
        prendre("n1", r"n\s*-\s*1")
        prendre("n", r"annee n\b|^n$")
        _roles_annees(entetes, roles, ["n2", "n1", "n"])
    elif code in ("T7", "T8"):
        prendre("nombre", r"nombre|nbre|nb\b")
        prendre("montant", r"montant")
        prendre("taux", r"taux|%|poids|proportion")
    return roles


def _roles_annees(entetes, roles, ordre):
    """En-têtes exprimés en années (2022, 2023…) au lieu de N-1, N."""
    if all(r in roles for r in ordre):
        return
    annees = sorted(((int(m.group(0)), j) for j, e in enumerate(entetes)
                     if j > 0 and (m := re.search(r"(19|20)\d\d", e))), key=lambda x: x[0])
    if len(annees) >= len(ordre):
        for role, (_, j) in zip(ordre, annees[-len(ordre):]):
            roles.setdefault(role, j)


def _lire_lignes(tab: TableauAnalyse) -> None:
    for brut in tab.bloc.lignes[tab.nb_lignes_entete:]:
        libelle = next((c for c in brut if c), "")
        n = normaliser(libelle)
        ligne = LigneTableau(libelle, "ligne")
        for role, j in tab.colonnes.items():
            if j < len(brut):
                v = lire_nombre(brut[j], taux=(role == "taux"))
                if v is not None:
                    ligne.valeurs[role] = v
                    ligne.brut[role] = brut[j]
        if RE_TOTAL.match(n):
            ligne.type = "total"
        elif RE_SOUS_TOTAL.match(n):
            ligne.type = "sous_total"
        elif RE_GROUPE.match(n):
            ligne.type = "groupe"
        elif not ligne.valeurs:
            ligne.type = "vide"
        tab.lignes.append(ligne)


# ------------------------------------------------------------------ contrôles
def _tol_montant(*bruts: str, n: int = 1) -> float:
    dec = max((decimales(b) for b in bruts if b), default=0)
    return max(1.0, n * 0.5) * 10 ** (-dec) + 1e-6


def _comparer_taux(attendu: float, constate: float, brut: str) -> tuple[bool, float]:
    """Compare un taux en tenant compte de l'arrondi affiché et d'une éventuelle notation décimale (0,95)."""
    if abs(constate) <= 1.5 and abs(attendu) > 1.5 and "%" not in (brut or ""):
        constate *= 100
        tol = 0.5 * 10 ** (2 - decimales(brut)) + 0.05
    else:
        tol = 0.5 * 10 ** (-decimales(brut)) + 0.05
    return abs(attendu - constate) <= tol, constate


class ControleTableaux:
    def __init__(self, doc: DocumentRapport):
        self.doc = doc
        self.tableaux: list[TableauAnalyse] = [identifier(b) for b in doc.tableaux]
        self.par_code: dict[str, TableauAnalyse] = {}
        for t in self.tableaux:
            if t.code and t.code not in self.par_code:
                self.par_code[t.code] = t
        self.constats: list[Constat] = []
        for t in self.par_code.values():
            self._controler(t)
        self._coherence()

    def present(self, code: str) -> bool:
        return code in self.par_code

    def constats_tableau(self, code: str, nature: str | None = None) -> list[Constat]:
        nom = self.par_code[code].nom if code in self.par_code else None
        return [c for c in self.constats if c.tableau == nom and (nature is None or c.nature == nature)]

    def _ajouter(self, tab: TableauAnalyse, controle, ligne, attendu, constate, message,
                 gravite="Majeure", nature="fiabilite"):
        rub = TABLEAU_PAR_CODE[tab.code].rubrique if tab.code else ""
        self.constats.append(Constat(rub, controle, message, gravite, nature, tab.nom, ligne, attendu, constate))

    # ------------------------------------------------------------------ fiabilité
    def _controler(self, tab: TableauAnalyse) -> None:
        c = tab.colonnes
        if not tab.lignes:
            self._ajouter(tab, "Tableau vide", "", "", "", f"{tab.nom} : tableau présent mais non renseigné.",
                          "Majeure")
            return
        if all(not l.valeurs for l in tab.lignes):
            self._ajouter(tab, "Tableau non renseigné", "", "", "",
                          f"{tab.nom} : aucune valeur chiffrée exploitable.", "Majeure")
            return
        for l in tab.lignes:
            v, b = l.valeurs, l.brut
            if tab.code in ("T3", "T4") and {"initial", "modif", "actuel"} <= v.keys():
                attendu = v["initial"] + v["modif"]
                if abs(attendu - v["actuel"]) > _tol_montant(b["initial"], b["modif"], b["actuel"]):
                    self._ajouter(tab, "Montant actuel = initial + modifications", l.libelle,
                                  format_montant(attendu), format_montant(v["actuel"]),
                                  f"{tab.nom}, ligne « {l.libelle} » : le montant actuel ({format_montant(v['actuel'])}) "
                                  f"≠ montant initial + modifications ({format_montant(attendu)}).")
            if tab.code == "T5" and "final" in v and "realise" in v:
                if "taux" in v and v["final"]:
                    self._verifier_taux(tab, l, v["realise"] / v["final"] * 100, "Taux de réalisation = Recouvrement / Prévision finale")
                if "ecart" in v:
                    attendu = v["final"] - v["realise"]
                    if min(abs(abs(attendu) - abs(v["ecart"])), abs(attendu - v["ecart"])) > _tol_montant(b["final"], b["realise"], b["ecart"]):
                        self._ajouter(tab, "Écart = Prévision finale − Recouvrement", l.libelle,
                                      format_montant(attendu), format_montant(v["ecart"]),
                                      f"{tab.nom}, ligne « {l.libelle} » : écart déclaré {format_montant(v['ecart'])}, "
                                      f"écart recalculé {format_montant(attendu)}.")
            if tab.code == "T6" and "actuel" in v and "realise" in v and "taux" in v and v["actuel"]:
                self._verifier_taux(tab, l, v["realise"] / v["actuel"] * 100, "Taux d'exécution = Ordonnancement / Budget actuel")
            if tab.code == "T1" and "n" in v and "n1" in v:
                if "variation" in v and abs(v["n"] - v["n1"] - v["variation"]) > _tol_montant(b["n"], b["n1"], b["variation"]):
                    self._ajouter(tab, "Variation = N − (N−1)", l.libelle, format_montant(v["n"] - v["n1"]),
                                  format_montant(v["variation"]),
                                  f"{tab.nom} : la variation déclarée ({format_montant(v['variation'])}) ≠ "
                                  f"budget N − budget N−1 ({format_montant(v['n'] - v['n1'])}).")
                if "taux" in v and v["n1"]:
                    self._verifier_taux(tab, l, (v["n"] - v["n1"]) / v["n1"] * 100, "Taux de variation = (N − N−1) / N−1")
        self._sommes(tab)
        if tab.code in ("T7", "T8"):
            self._motifs(tab)

    def _verifier_taux(self, tab, l, attendu, controle):
        ok, constate = _comparer_taux(attendu, l.valeurs["taux"], l.brut.get("taux", ""))
        if not ok:
            ecart = abs(attendu - constate)
            self._ajouter(tab, controle, l.libelle, format_taux(attendu), format_taux(constate),
                          f"{tab.nom}, ligne « {l.libelle} » : taux déclaré {format_taux(constate)}, "
                          f"taux recalculé {format_taux(attendu)}.", "Majeure" if ecart > 1 else "Mineure")

    def _sommes(self, tab: TableauAnalyse) -> None:
        roles_montants = [r for r in tab.colonnes if r not in ("taux",)]
        for role in roles_montants:
            groupe_details: list[LigneTableau] = []
            entete: LigneTableau | None = None
            tous_details: list[LigneTableau] = []
            sous_totaux: list[LigneTableau] = []

            def cloturer():
                if entete is not None and role in entete.valeurs and groupe_details:
                    self._verifier_somme(tab, role, entete, groupe_details, "Total du groupe")

            for l in tab.lignes:
                if l.type == "groupe":
                    cloturer()
                    entete, groupe_details = l, []
                elif l.type == "ligne":
                    groupe_details.append(l)
                    tous_details.append(l)
                elif l.type == "sous_total":
                    if groupe_details and role in l.valeurs:
                        self._verifier_somme(tab, role, l, groupe_details, "Sous-total")
                    sous_totaux.append(l)
                    entete, groupe_details = None, []
                elif l.type == "total":
                    cloturer()
                    entete = None
                    if role not in l.valeurs:
                        continue
                    if any(role in d.valeurs for d in tous_details):
                        self._verifier_somme(tab, role, l, tous_details, "Total général")
                    elif any(role in s.valeurs for s in sous_totaux):
                        self._verifier_somme(tab, role, l, sous_totaux, "Total général")
            cloturer()

    def _verifier_somme(self, tab, role, ligne, details, controle):
        valeurs = [d.valeurs[role] for d in details if role in d.valeurs]
        if not valeurs:
            return
        attendu = sum(valeurs)
        bruts = [d.brut[role] for d in details if role in d.brut] + [ligne.brut[role]]
        if abs(attendu - ligne.valeurs[role]) > _tol_montant(*bruts, n=len(valeurs)):
            self._ajouter(tab, f"{controle} = somme des lignes", ligne.libelle, format_montant(attendu),
                          format_montant(ligne.valeurs[role]),
                          f"{tab.nom}, « {ligne.libelle} » (colonne {_LIBELLE_ROLE.get(role, role)}) : "
                          f"{format_montant(ligne.valeurs[role])} déclaré, somme des lignes = {format_montant(attendu)}.")

    def _motifs(self, tab: TableauAnalyse) -> None:
        details = [l for l in tab.lignes if l.type == "ligne"]
        if not details or "taux" not in tab.colonnes:
            return
        taux = [l.valeurs["taux"] for l in details if "taux" in l.valeurs]
        if not taux:
            return
        bases = {}
        for role in ("montant", "nombre"):
            vals = [l.valeurs.get(role) for l in details]
            if all(v is not None for v in vals) and sum(vals):
                bases[role] = sum(vals)
        # Les taux peuvent être calculés sur le total des dossiers reçus (et non sur le total des motifs) :
        # on ne signale une anomalie que si aucun mode de calcul cohérent n'est retrouvé.
        coherent = abs(sum(taux) - 100) <= 0.6 * len(taux) or abs(sum(taux) - 1) <= 0.01 * len(taux)
        for role, total in bases.items():
            if all(_comparer_taux(l.valeurs[role] / total * 100, l.valeurs["taux"], l.brut.get("taux", ""))[0]
                   for l in details if "taux" in l.valeurs):
                coherent = True
        if not coherent and sum(taux) > 100.6:
            self._ajouter(tab, "Répartition des taux des motifs", "", "≤ 100 %", format_taux(sum(taux)),
                          f"{tab.nom} : la somme des taux des motifs ({format_taux(sum(taux))}) dépasse 100 %.",
                          "Mineure")

    # ------------------------------------------------------------------ cohérence
    def _coherence(self) -> None:
        p = self.par_code

        def comparer(code_a, role_a, code_b, role_b, controle, gravite="Majeure", alternatives=()):
            if code_a not in p or code_b not in p:
                return
            va = p[code_a].total(role_a)
            vb = p[code_b].total(role_b)
            if va is None or vb is None:
                return
            if abs(va - vb) <= max(1.0, 1e-6 * abs(va)):
                return
            for ra, rb in alternatives:
                xa, xb = p[code_a].total(ra), p[code_b].total(rb)
                if xa is not None and xb is not None and abs(xa - xb) <= max(1.0, 1e-6 * abs(xa)):
                    return
            nom_a, nom_b = p[code_a].nom, p[code_b].nom
            self.constats.append(Constat(
                TABLEAU_PAR_CODE[code_a].rubrique, controle,
                f"Incohérence entre {nom_a} ({format_montant(va)}) et {nom_b} ({format_montant(vb)}).",
                gravite, "coherence", nom_a, "", format_montant(vb), format_montant(va)))

        comparer("T1", "n", "T2", "n", "Budget N identique dans les tableaux 1 et 2")
        comparer("T1", "n1", "T2", "n1", "Budget N−1 identique dans les tableaux 1 et 2")
        comparer("T1", "n", "T3", "actuel", "Budget N (T1) = total des ressources (T3)",
                 alternatives=[("n", "initial")])
        comparer("T3", "actuel", "T4", "actuel", "Équilibre budgétaire : total ressources (T3) = total emplois (T4)",
                 alternatives=[])
        comparer("T3", "initial", "T4", "initial", "Équilibre du budget initial : ressources (T3) = emplois (T4)")
        comparer("T5", "final", "T3", "actuel", "Prévisions finales de recettes (T5) = montant actuel des ressources (T3)")
        comparer("T5", "initial", "T3", "initial", "Prévisions initiales de recettes (T5) = montant initial des ressources (T3)",
                 "Mineure")
        comparer("T6", "actuel", "T4", "actuel", "Budget actuel des dépenses (T6) = montant actuel des emplois (T4)")
        comparer("T6", "initial", "T4", "initial", "Budget initial des dépenses (T6) = montant initial des emplois (T4)",
                 "Mineure")

    # ------------------------------------------------------------------ agrégats utiles
    def agregats(self) -> dict[str, float]:
        """Montants clés pour les ratios et le résultat budgétaire."""
        a: dict[str, float] = {}
        t5, t6 = self.par_code.get("T5"), self.par_code.get("T6")
        if t5:
            for role in ("initial", "final", "realise"):
                v = t5.total(role)
                if v is not None:
                    a[f"recettes_{role}"] = v
            v = t5.somme_groupe(r"propres", "realise")
            if v is not None:
                a["ressources_propres_realise"] = v
            v = t5.somme_groupe(r"propres", "final")
            if v is not None:
                a["ressources_propres_final"] = v
        if t6:
            for role in ("initial", "actuel", "engage", "realise"):
                v = t6.total(role)
                if v is not None:
                    a[f"depenses_{role}"] = v
            for nom, motif in (("personnel", r"personnel"), ("biens_services", r"biens et services"),
                               ("transferts", r"transfert"), ("investissement", r"investissement")):
                for role in ("engage", "realise"):
                    v = t6.somme_groupe(motif, role)
                    if v is not None:
                        a[f"{nom}_{role}"] = v
        return a


_LIBELLE_ROLE = {"initial": "montant/prévision initial(e)", "modif": "modifications", "actuel": "montant actuel",
                 "final": "prévision finale", "realise": "réalisation", "ecart": "écart", "engage": "engagements",
                 "n": "année N", "n1": "année N−1", "n2": "année N−2", "variation": "variation",
                 "nombre": "nombre", "montant": "montant"}
