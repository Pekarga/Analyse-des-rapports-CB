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
    principal: bool = True  # premier tableau du rapport rattaché à ce tableau du canevas

    @property
    def nom(self) -> str:
        if self.code and self.principal:
            return f"Tableau {TABLEAU_PAR_CODE[self.code].numero} ({TABLEAU_PAR_CODE[self.code].libelle})"
        if self.code:
            leg = re.sub(r"\s+", " ", self.bloc.legende).strip()
            return (f"« {leg[:80]} »" if leg else "Tableau sans titre") + f" [format du tableau {TABLEAU_PAR_CODE[self.code].numero}]"
        return "Tableau non identifié"

    @property
    def rubrique(self) -> str:
        if not self.code:
            return ""
        if not self.principal:
            leg = normaliser(self.bloc.legende)
            if re.search(r"ressource|recette|financement", leg):
                return "pres_ressources" if self.code in ("T1", "T2", "T3") else TABLEAU_PAR_CODE[self.code].rubrique
            if re.search(r"depense|emploi|activit", leg):
                return "pres_emplois" if self.code in ("T1", "T2", "T4") else TABLEAU_PAR_CODE[self.code].rubrique
        return TABLEAU_PAR_CODE[self.code].rubrique

    def total(self, role: str) -> float | None:
        """Total général déclaré, ou à défaut somme des lignes de détail."""
        for l in self.lignes:
            if l.type == "total" and role in l.valeurs:
                return l.valeurs[role]
        if self.code in ("T1", "T2"):
            # Tableau présentant à la fois une ligne « Recettes » et une ligne « Dépenses » : le budget est
            # le montant de l'une d'elles (et non leur somme).
            for l in self.lignes:
                if re.match(r"^(budget|recettes|ressources)\b", normaliser(l.libelle)) and role in l.valeurs:
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
        if valeur_entete is not None:
            return valeur_entete
        # Nature présentée sur une seule ligne chiffrée (« 1 Personnel | 50 000 000 »), sans lignes de détail
        for l in self.lignes:
            n = normaliser(l.libelle)
            if l.type == "ligne" and role in l.valeurs and RE_GROUPE.match(n) and re.search(motif, n):
                return l.valeurs[role]
        return None


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
    ("T5", lambda h, l: "recouvr" in h or ("prevision" in h and re.search(r"realis|encaiss|vise|pris\w* en charge", h))),
    ("T6", lambda h, l: "ordonnanc" in h or re.search(r"taux d.execution", h) is not None
     or (re.search(r"budget (actuel|final|definitif)", h) is not None and re.search(r"engag|execution", h) is not None)),
    # Modifications du budget en recettes présentées en « budget voté / budget actuel / variation »
    ("T3", lambda h, l: re.search(r"vote|initial", h) is not None and re.search(r"actuel|final|definitif|revise", h) is not None
     and re.search(r"ressource|recette|source", h + " " + l) is not None and "depense" not in l),
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
        prendre("initial", r"initial|vote")
        prendre("modif", r"modif|variation")
        prendre("actuel", r"actuel|final|definitif|revise|corrige")
    elif code == "T5":
        prendre("initial", r"initial")
        prendre("final", r"final|definitiv|actuel|revise|corrige")
        prendre("realise", r"recouvr|encaiss|realis(e|ee|ees|es|ations?)\b(?!.*taux)", r"\bvise", r"pris\w*[- ]en[- ]charge",
                exclure=r"taux")
        prendre("paye", r"pris\w*[- ]en[- ]charge|paye|paiement")
        prendre("taux", r"taux")
        prendre("ecart", r"ecart|reste|disponible")
    elif code == "T6":
        prendre("initial", r"initial")
        prendre("actuel", r"actuel|final|definitif|revise|corrige")
        prendre("engage", r"engag", exclure=r"taux")
        prendre("realise", r"ordonnanc|liquid|mandat|execut", exclure=r"taux")
        prendre("paye", r"pris\w*[- ]en[- ]charge|paye|paiement")
        prendre("taux", r"taux")
        prendre("ecart", r"disponible|reste|solde")
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
        elif RE_GROUPE.match(n) and not (tab.code in ("T3", "T5") and not re.match(r"^(ressources|recettes|autres)", n)):
            ligne.type = "groupe"  # (dans un tableau de ressources, « Dépenses de personnel » est une ligne de ressource)
        elif not ligne.valeurs:
            ligne.type = "vide"
        tab.lignes.append(ligne)
    # Ligne de nature chiffrée sans détail (« 1 Personnel | 50 000 000 » suivie directement de « 2 Biens et services »,
    # ou « Dépenses de personnel » dans un tableau de ressources) : c'est une ligne, pas un en-tête de groupe.
    utiles = [l for l in tab.lignes if l.type != "vide"]
    for k, l in enumerate(utiles):
        if l.type == "groupe" and l.valeurs:
            suivante = utiles[k + 1] if k + 1 < len(utiles) else None
            if suivante is None or suivante.type in ("groupe", "total", "sous_total"):
                l.type = "ligne"


# ------------------------------------------------------------------ contrôles
def _bases(v: dict, numerateurs, denominateurs) -> list[tuple[str, float]]:
    """Autres bases de calcul possibles d'un taux (pour expliquer un taux déclaré différent du canevas)."""
    noms = {"realise": "réalisation", "paye": "prises en charge", "final": "prévision finale",
            "actuel": "budget actuel", "initial": "prévision/budget initial(e)"}
    out = []
    for n in numerateurs:
        for d in denominateurs:
            if (n, d) != (numerateurs[0], denominateurs[0]) and n in v and v.get(d):
                out.append((f"{noms[n]} / {noms[d]}", v[n] / v[d] * 100))
    return out


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
            elif t.code:
                t.principal = False
        self.constats: list[Constat] = []
        for t in self.tableaux:
            if t.code:
                self._controler(t)
        self._coherence()
        self._codes_en_double()
        self._dedoublonner()

    def _dedoublonner(self) -> None:
        """Une même erreur répercutée sur plusieurs colonnes (ex. initial et actuel) n'est signalée qu'une fois ;
        les anomalies de présentation répétées sur plusieurs lignes d'un tableau sont regroupées."""
        regroupables = ("Signe de la variation", "Signe du taux", "Signe des modifications", "Base de calcul du taux")
        groupes: dict[tuple, list[Constat]] = {}
        autres = []
        for c in self.constats:
            if c.controle in regroupables:
                groupes.setdefault((c.tableau, c.controle), []).append(c)
            else:
                autres.append(c)
        for (tableau, controle), cs in groupes.items():
            if len(cs) == 1:
                autres.append(cs[0])
                continue
            lignes = [c.ligne for c in cs]
            c0 = cs[0]
            libelle = {"Signe de la variation": "baisses présentées sans signe négatif",
                       "Signe du taux": "taux de baisse présentés sans signe négatif",
                       "Signe des modifications": "réductions de crédits présentées sans signe négatif",
                       "Base de calcul du taux": "taux calculés sur une autre base que celle du canevas"}[controle]
            autres.append(Constat(c0.rubrique, controle,
                                  f"{tableau} : {len(cs)} {libelle} (lignes : " + " ; ".join(l[:50] for l in lignes[:6])
                                  + (" ; …" if len(lignes) > 6 else "") + "). Ex. : " + c0.message.split(" : ", 1)[-1],
                                  c0.gravite, c0.nature, tableau, f"{len(cs)} lignes", c0.attendu, c0.constate))
        self.constats = autres
        vus: dict[tuple, Constat] = {}
        uniques = []
        for c in self.constats:
            cle = (c.tableau, c.ligne, c.controle, c.attendu, c.constate)
            if cle in vus:
                if "(même écart" not in vus[cle].message:
                    vus[cle].message += " (même écart sur plusieurs colonnes)"
                continue
            vus[cle] = c
            uniques.append(c)
        self.constats = uniques

    def present(self, code: str) -> bool:
        return code in self.par_code

    def constats_tableau(self, code: str, nature: str | None = None) -> list[Constat]:
        nom = self.par_code[code].nom if code in self.par_code else None
        return [c for c in self.constats if c.tableau == nom and (nature is None or c.nature == nature)]

    def _ajouter(self, tab: TableauAnalyse, controle, ligne, attendu, constate, message,
                 gravite="Majeure", nature="fiabilite"):
        rub = tab.rubrique
        self.constats.append(Constat(rub, controle, message, gravite, nature, tab.nom, ligne, attendu, constate))

    # ------------------------------------------------------------------ fiabilité
    def _controler(self, tab: TableauAnalyse) -> None:
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
                tol = _tol_montant(b["initial"], b["modif"], b["actuel"])
                if abs(attendu - v["actuel"]) > tol and abs(v["initial"] - v["modif"] - v["actuel"]) <= tol:
                    self._ajouter(tab, "Signe des modifications", l.libelle, format_montant(-v["modif"]),
                                  format_montant(v["modif"]),
                                  f"{tab.nom}, ligne « {l.libelle} » : la réduction de crédits est présentée sans signe "
                                  f"négatif ({format_montant(v['modif'])} au lieu de {format_montant(-v['modif'])}).",
                                  "Mineure")
                elif abs(attendu - v["actuel"]) > tol:
                    reduction = v["initial"] - v["modif"]  # modifications présentées comme des réductions
                    if v["modif"] > 0 and abs(reduction - v["actuel"]) < abs(attendu - v["actuel"]):
                        attendu, libelle_calcul = reduction, "montant initial − réduction"
                    else:
                        libelle_calcul = "montant initial + modifications"
                    self._ajouter(tab, "Montant actuel = initial + modifications", l.libelle,
                                  format_montant(attendu), format_montant(v["actuel"]),
                                  f"{tab.nom}, ligne « {l.libelle} » : le montant actuel ({format_montant(v['actuel'])}) "
                                  f"≠ {libelle_calcul} ({format_montant(attendu)}).")
            if tab.code == "T5" and "final" in v and "realise" in v:
                if "taux" in v and v["final"]:
                    self._verifier_taux(tab, l, v["realise"] / v["final"] * 100, "Taux de réalisation = Recouvrement / Prévision finale",
                                        _bases(v, ("realise", "paye"), ("final", "initial")))
                if "ecart" in v:
                    attendu = v["final"] - v["realise"]
                    if min(abs(abs(attendu) - abs(v["ecart"])), abs(attendu - v["ecart"])) > _tol_montant(b["final"], b["realise"], b["ecart"]):
                        self._ajouter(tab, "Écart = Prévision finale − Recouvrement", l.libelle,
                                      format_montant(attendu), format_montant(v["ecart"]),
                                      f"{tab.nom}, ligne « {l.libelle} » : écart déclaré {format_montant(v['ecart'])}, "
                                      f"écart recalculé {format_montant(attendu)}.")
            if tab.code == "T6" and "actuel" in v and "realise" in v and "taux" in v and v["actuel"]:
                self._verifier_taux(tab, l, v["realise"] / v["actuel"] * 100, "Taux d'exécution = Ordonnancement / Budget actuel",
                                    _bases(v, ("realise", "paye"), ("actuel", "initial")))
            if tab.code == "T6" and {"actuel", "realise", "ecart"} <= v.keys():
                attendu = v["actuel"] - v["realise"]
                if abs(attendu - v["ecart"]) > _tol_montant(b["actuel"], b["realise"], b["ecart"]):
                    self._ajouter(tab, "Disponible = Budget actuel − Exécution", l.libelle, format_montant(attendu),
                                  format_montant(v["ecart"]),
                                  f"{tab.nom}, ligne « {l.libelle} » : disponible déclaré {format_montant(v['ecart'])}, "
                                  f"disponible recalculé {format_montant(attendu)}.")
            if tab.code == "T1" and "n" in v and "n1" in v:
                tol = _tol_montant(b["n"], b["n1"], b.get("variation", ""))
                if "variation" in v and abs(v["n"] - v["n1"] - v["variation"]) > tol and abs(abs(v["n"] - v["n1"]) - abs(v["variation"])) <= tol:
                    self._ajouter(tab, "Signe de la variation", l.libelle, format_montant(v["n"] - v["n1"]),
                                  format_montant(v["variation"]),
                                  f"{tab.nom}, ligne « {l.libelle} » : la baisse ({format_montant(v['n'] - v['n1'])}) est "
                                  f"présentée sans signe négatif ({format_montant(v['variation'])}).", "Mineure")
                elif "variation" in v and abs(v["n"] - v["n1"] - v["variation"]) > tol:
                    self._ajouter(tab, "Variation = N − (N−1)", l.libelle, format_montant(v["n"] - v["n1"]),
                                  format_montant(v["variation"]),
                                  f"{tab.nom}, ligne « {l.libelle} » : la variation déclarée ({format_montant(v['variation'])}) ≠ "
                                  f"budget N − budget N−1 ({format_montant(v['n'] - v['n1'])}).")
                if "taux" in v and v["n1"]:
                    self._verifier_taux(tab, l, (v["n"] - v["n1"]) / v["n1"] * 100, "Taux de variation = (N − N−1) / N−1")
        self._sommes(tab)
        if tab.code in ("T7", "T8"):
            self._motifs(tab)

    def _verifier_taux(self, tab, l, attendu, controle, alternatives=()):
        ok, constate = _comparer_taux(attendu, l.valeurs["taux"], l.brut.get("taux", ""))
        if not ok and abs(constate + attendu) <= 0.5 * 10 ** (-decimales(l.brut.get("taux", ""))) + 0.05:
            self._ajouter(tab, "Signe du taux", l.libelle, format_taux(attendu), format_taux(constate),
                          f"{tab.nom}, ligne « {l.libelle} » : taux de baisse présenté sans signe négatif "
                          f"({format_taux(constate)} au lieu de {format_taux(attendu)}).", "Mineure")
            return
        for libelle_base, valeur in alternatives:
            if not ok and _comparer_taux(valeur, l.valeurs["taux"], l.brut.get("taux", ""))[0]:
                self._ajouter(tab, "Base de calcul du taux", l.libelle, format_taux(attendu), format_taux(constate),
                              f"{tab.nom}, ligne « {l.libelle} » : le taux déclaré ({format_taux(constate)}) est calculé "
                              f"sur la base {libelle_base} ; selon le canevas : {format_taux(attendu)}.", "Mineure")
                return
        if not ok and abs(constate) >= 1000:
            self._ajouter(tab, controle, l.libelle, format_taux(attendu), format_montant(l.valeurs["taux"]),
                          f"{tab.nom}, ligne « {l.libelle} » : la colonne des taux contient un montant "
                          f"({format_montant(l.valeurs['taux'])}) au lieu du taux ({format_taux(attendu)}).")
            return
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
            if abs(va - vb) <= 1.0:  # montants en FCFA : l'égalité doit être exacte (à l'arrondi près)
                return
            for ra, rb in alternatives:
                xa, xb = p[code_a].total(ra), p[code_b].total(rb)
                if xa is not None and xb is not None and abs(xa - xb) <= 1.0:
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
        self._activites_t4_t6()
        self._natures_t4_t6()

    def _codes_en_double(self) -> None:
        """Un même code d'activité (ou de nature) ne doit pas désigner deux lignes différentes d'un tableau."""
        for t in self.tableaux:
            vus: dict[str, str] = {}
            doublons = []
            for l in t.lignes:
                m = re.match(r"^\s*(\d[\d ]{5,16}\d)\b", l.libelle)
                if not m or l.type != "ligne":
                    continue
                code = m.group(1).replace(" ", "")
                if len(code) not in (6, 11):
                    continue
                if code in vus and normaliser(vus[code]) != normaliser(l.libelle):
                    doublons.append(f"{code} (« {vus[code][len(m.group(0)):][:45].strip()} » et « {l.libelle[len(m.group(0)):][:45].strip()} »)")
                vus.setdefault(code, l.libelle)
            if doublons:
                self.constats.append(Constat(t.rubrique, "Codes d'activité uniques", f"{t.nom} : un même code "
                                             f"désigne plusieurs lignes différentes : " + " ; ".join(doublons) + ".",
                                             "Mineure", "fiabilite", t.nom, "", "codes distincts", "; ".join(d.split()[0] for d in doublons)))

    def _natures_t4_t6(self) -> None:
        """Répartition du budget initial par grande nature identique dans les tableaux 4 et 6."""
        t4, t6 = self.par_code.get("T4"), self.par_code.get("T6")
        if not t4 or not t6:
            return
        for nom, motif in (("Personnel", r"personnel"), ("Biens et services", r"biens et services"),
                           ("Transferts", r"transfert"), ("Investissements", r"investissement")):
            for role in ("initial", "actuel"):
                a, b = t4.somme_groupe(motif, role), t6.somme_groupe(motif, role)
                if a is None or b is None or abs(a - b) <= 1:
                    continue
                self.constats.append(Constat(
                    "exec_depenses", "Même répartition par nature dans les tableaux 4 et 6",
                    f"{nom} ({_LIBELLE_ROLE[role]}) : {format_montant(a)} au {t4.nom} contre {format_montant(b)} au {t6.nom}.",
                    "Majeure", "coherence", t6.nom, nom, format_montant(a), format_montant(b)))
                break

    def _activites_t4_t6(self) -> None:
        """Les activités (codes budgétaires) présentées au tableau 4 doivent être celles exécutées au tableau 6."""
        if "T4" not in self.par_code or "T6" not in self.par_code:
            return

        def codes(tab):
            res = {}
            for l in tab.lignes:
                m = re.match(r"^\s*(\d{10,12})\b", l.libelle)
                if m and l.type == "ligne":
                    res[m.group(1)] = l.libelle
            return res

        c4, c6 = codes(self.par_code["T4"]), codes(self.par_code["T6"])
        if not c4 or not c6:
            return
        seuls4, seuls6 = sorted(set(c4) - set(c6)), sorted(set(c6) - set(c4))
        if seuls4 or seuls6:
            msg = ("Les activités du tableau 4 (présentation des emplois) et du tableau 6 (exécution des dépenses) ne "
                   "portent pas les mêmes codes."
                   + (f" Uniquement au T4 : {', '.join(seuls4)}." if seuls4 else "")
                   + (f" Uniquement au T6 : {', '.join(seuls6)}." if seuls6 else "")
                   + " Vérifier la nomenclature des activités (budget-programmes).")
            self.constats.append(Constat("exec_depenses", "Mêmes activités dans les tableaux 4 et 6", msg, "Mineure",
                                         "coherence", self.par_code["T6"].nom, "", f"{len(c4)} codes (T4)",
                                         f"{len(c6)} codes (T6)"))

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
                for role in ("actuel", "engage", "realise"):
                    v = t6.somme_groupe(motif, role)
                    if v is not None:
                        a[f"{nom}_{role}"] = v
        return a


_LIBELLE_ROLE = {"initial": "montant/prévision initial(e)", "modif": "modifications", "actuel": "montant actuel",
                 "final": "prévision finale", "realise": "réalisation", "ecart": "écart", "engage": "engagements",
                 "n": "année N", "n1": "année N−1", "n2": "année N−2", "variation": "variation",
                 "nombre": "nombre", "montant": "montant", "paye": "prises en charge"}
