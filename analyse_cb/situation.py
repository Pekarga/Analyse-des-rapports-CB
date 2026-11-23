"""Situation d'exécution du budget de l'EPN à la date de la période du rapport, et rapprochement avec le rapport.

La situation d'exécution est la donnée de référence (extraction du système d'information budgétaire,
situation de l'Ordonnateur ou de l'Agent Comptable). Formats acceptés :
- classeur Excel (.xlsx, .xlsm) : une ou plusieurs feuilles (ex. « Recettes » et « Dépenses ») ;
- fichier CSV (séparateur « ; » ou « , ») ;
- PDF ou Word contenant les tableaux de la situation.

Un même fichier peut être **consolidé** (tous les EPN) : il suffit d'une colonne « EPN » (ou « Sigle »,
« Établissement ») ; seules les lignes de l'EPN du rapport sont alors retenues.

Les colonnes sont reconnues d'après leur intitulé : code / imputation, libellé, prévision ou crédit initial,
budget actuel (prévision finale), engagements, liquidations, ordonnancements (ou mandats), recouvrements
(ou encaissements). Le sens (recettes / dépenses) est déduit des colonnes, du nom de la feuille ou du code.

Le rapprochement compare, à l'unité près, les montants des tableaux du rapport (tableaux 3 à 6) aux montants de la
situation : totaux, groupes de nature (personnel, biens et services, transferts, investissements, ressources
propres), lignes de même code, taux d'exécution et résultat budgétaire.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .controles import FicheEPN, Periode, lire_date, lire_csv
from .tableaux import Constat, ControleTableaux, TableauAnalyse
from .texte import format_montant, format_taux, lire_nombre, normaliser

CONCORDANT, ECART, NON_COMPARABLE = "Concordant", "Écart", "Non comparable"

# Rôle des colonnes : on teste d'abord les colonnes à ignorer (taux, écarts, disponibles).
ROLES_COLONNES = [
    ("ignorer", r"taux|%|ecart|disponible|solde|reste|variation|observation|commentaire"),
    ("epn", r"^(epn|sigle|etablissement|structure|entite|organisme|code epn|nom epn)\b"),
    ("sens", r"^(sens|type( d.operation)?|recettes? ?/ ?depenses?|r ?/ ?d)$"),
    ("groupe", r"^(nature|categorie|groupe|titre|section|nature de (la )?depense|nature economique|grande nature)$"),
    ("code", r"\bcode\b|compte|imputation|^n[°o]?\s*(de )?(ligne|compte)|^ligne$|^activite$"),
    ("modif", r"modif"),
    ("initial", r"initial|primitif|\bvote"),
    ("actuel", r"actuel|final|definiti|revise|corrige|modifie|dotation|credits? ouverts?"),
    ("engage", r"engag"),
    ("liquide", r"liquid"),
    ("ordonnance", r"ordonnanc|mandat"),
    ("paye", r"pay|paie|decaiss"),
    ("recouvre", r"recouvr|encaiss|realis|mobilis|perception|percu"),
    ("libelle", r"libelle|designation|intitule|nature|activite|rubrique|ressources|recettes|depenses|emplois|compte"),
]
ROLES_MONTANTS = ("initial", "actuel", "engage", "liquide", "ordonnance", "paye", "recouvre", "modif")

GROUPES_DEPENSES = [("personnel", r"personnel|salaires"), ("biens_services", r"biens et services|fonctionnement courant|achats? de biens"),
                    ("transferts", r"transferts?|subventions? (versee|accordee)"), ("investissement", r"investissement|equipement|immobilis")]
GROUPES_RECETTES = [("budget_general", r"budget general|de l.etat|subvention|transferts? recus|dotation"),
                    ("propres", r"propres|prestations|produits|redevances|ventes"),
                    ("autres", r"exterieur|dons|emprunts?|partenaires")]
LIBELLES_GROUPES = {"personnel": "Personnel", "biens_services": "Biens et services", "transferts": "Transferts",
                    "investissement": "Investissements", "budget_general": "Ressources du budget général (État)",
                    "propres": "Ressources propres", "autres": "Autres ressources", "": "Non classé"}


@dataclass
class TableBrute:
    nom: str
    lignes: list[list]


@dataclass
class SourceSituation:
    chemin: Path
    tables: list[TableBrute]
    texte: str = ""
    ocr: bool = False


@dataclass
class LigneSituation:
    sens: str  # "recettes" ou "depenses"
    code: str
    libelle: str
    groupe: str
    valeurs: dict[str, float]
    epn: str = ""
    feuille: str = ""


@dataclass
class SituationExecution:
    chemin: Path
    date_arrete: date | None
    lignes: list[LigneSituation] = field(default_factory=list)
    totaux_declares: dict[str, float] = field(default_factory=dict)
    avertissements: list[str] = field(default_factory=list)
    filtre_epn: str = ""

    def lignes_de(self, sens: str) -> list[LigneSituation]:
        return [l for l in self.lignes if l.sens == sens]

    def somme(self, sens: str, role: str, groupe: str | None = None) -> float | None:
        vals = [l.valeurs[role] for l in self.lignes_de(sens) if role in l.valeurs and (groupe is None or l.groupe == groupe)]
        if vals:
            return sum(vals)
        if groupe is None:
            return self.totaux_declares.get(f"{sens}_{role}")
        return None

    def agregats(self) -> dict[str, float]:
        """Mêmes clés que ControleTableaux.agregats() pour faciliter le rapprochement."""
        a: dict[str, float] = {}

        def poser(cle, v):
            if v is not None:
                a[cle] = v
        poser("recettes_initial", self.somme("recettes", "initial"))
        poser("recettes_final", self.somme("recettes", "actuel"))
        poser("recettes_realise", self.somme("recettes", "recouvre"))
        poser("ressources_propres_final", self.somme("recettes", "actuel", "propres"))
        poser("ressources_propres_realise", self.somme("recettes", "recouvre", "propres"))
        poser("depenses_initial", self.somme("depenses", "initial"))
        poser("depenses_actuel", self.somme("depenses", "actuel"))
        poser("depenses_engage", self.somme("depenses", "engage"))
        poser("depenses_liquide", self.somme("depenses", "liquide"))
        poser("depenses_realise", self.somme("depenses", "ordonnance") if self.somme("depenses", "ordonnance") is not None
              else self.somme("depenses", "liquide"))
        for g in ("personnel", "biens_services", "transferts", "investissement"):
            poser(f"{g}_actuel", self.somme("depenses", "actuel", g))
            poser(f"{g}_engage", self.somme("depenses", "engage", g))
            o = self.somme("depenses", "ordonnance", g)
            poser(f"{g}_realise", o if o is not None else self.somme("depenses", "liquide", g))
        return a


# ------------------------------------------------------------------ lecture du fichier source
def charger_source(chemin: str | Path) -> SourceSituation:
    chemin = Path(chemin)
    ext = chemin.suffix.lower()
    if ext in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(chemin, data_only=True, read_only=True)
        tables = []
        for ws in wb.worksheets:
            lignes = [list(r) for r in ws.iter_rows(values_only=True)]
            lignes = [l for l in lignes if any(v not in (None, "") for v in l)]
            if lignes:
                tables.append(TableBrute(ws.title, lignes))
        wb.close()
        return SourceSituation(chemin, tables, " ".join(t.nom for t in tables))
    if ext == ".xls":
        raise ValueError(f"{chemin.name} : format .xls non pris en charge, enregistrez la situation en .xlsx.")
    if ext in (".csv", ".txt"):
        lignes = lire_csv_brut(chemin)
        return SourceSituation(chemin, [TableBrute(chemin.stem, lignes)])
    if ext in (".pdf", ".docx"):
        from .lecture import lire_rapport
        doc = lire_rapport(chemin)
        tables, precedent = [], ""
        for b in doc.blocs:
            if b.type == "p":
                precedent = b.texte
            else:
                tables.append(TableBrute(b.legende or precedent, b.lignes))
        return SourceSituation(chemin, tables, doc.texte(0, min(len(doc.blocs), 30)), doc.ocr)
    raise ValueError(f"{chemin.name} : format de situation non pris en charge ({ext}). "
                     "Formats acceptés : .xlsx, .csv, .pdf, .docx")


def lire_csv_brut(chemin: Path) -> list[list]:
    import csv
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texte = chemin.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    lignes = [l for l in texte.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    if not lignes:
        return []
    sep = ";" if lignes[0].count(";") >= lignes[0].count(",") else ","
    return [r for r in csv.reader(lignes, delimiter=sep)]


def _role(entete: str) -> str | None:
    if not entete:
        return None
    for role, motif in ROLES_COLONNES:
        if re.search(motif, entete):
            return role
    return None


def _trouver_entete(lignes: list[list]) -> tuple[int, int, list[str]] | None:
    """Renvoie (indice de la 1re ligne d'en-tête, nb de lignes d'en-tête, intitulés normalisés)."""
    for i, l in enumerate(lignes[:25]):
        roles = [_role(normaliser(str(v))) if isinstance(v, str) else None for v in l]
        if sum(1 for r in roles if r in ROLES_MONTANTS) >= 1 and sum(1 for r in roles if r) >= 2:
            entetes = [normaliser(str(v)) if v is not None else "" for v in l]
            nb = 1
            # en-tête sur deux lignes (cellules fusionnées)
            if i + 1 < len(lignes):
                suiv = lignes[i + 1]
                if not any(lire_nombre(v) is not None for v in suiv if v not in (None, "")) and any(
                        isinstance(v, str) and _role(normaliser(v)) for v in suiv):
                    entetes = [(e + " " + (normaliser(str(suiv[j])) if j < len(suiv) and suiv[j] else "")).strip()
                               for j, e in enumerate(entetes + [""] * max(0, len(suiv) - len(entetes)))]
                    nb = 2
            return i, nb, entetes
    return None


def _groupe(sens: str, texte: str, code: str) -> str:
    n = normaliser(texte)
    for g, motif in (GROUPES_DEPENSES if sens == "depenses" else GROUPES_RECETTES):
        if re.search(motif, n):
            return g
    if len(code) == 6:
        if sens == "recettes":
            return "budget_general" if code.startswith("73") else "propres" if code.startswith("7") else ""
        if code.startswith("66"):
            return "personnel"
        if code[:2] in ("60", "61", "62", "63"):
            return "biens_services"
        if code[:2] in ("64", "65"):
            return "transferts"
        if code.startswith("2"):
            return "investissement"
    return ""


def _sens_table(nom: str, roles: dict[str, int], lignes: list[list]) -> str | None:
    if "recouvre" in roles and not ({"engage", "ordonnance", "liquide"} & roles.keys()):
        return "recettes"
    if {"engage", "ordonnance", "liquide"} & roles.keys():
        return "depenses"
    n = normaliser(nom)
    if re.search(r"recette|ressource", n):
        return "recettes"
    if re.search(r"depense|emploi|charge", n):
        return "depenses"
    return None


def extraire_situation(source: SourceSituation, nom_epn: str = "", fiche: FicheEPN | None = None) -> SituationExecution:
    sit = SituationExecution(source.chemin, _date_arrete(source))
    vus: set[tuple] = set()
    valeurs_epn: set[str] = set()
    cibles = [normaliser(x) for x in (fiche.sigle if fiche else "", fiche.denomination if fiche else "", nom_epn) if x]
    m = re.search(r"\(([A-Z0-9\-]{2,12})\)", nom_epn or "")
    if m:
        cibles.append(normaliser(m.group(1)))
    for table in source.tables:
        ent = _trouver_entete(table.lignes)
        if not ent:
            continue
        i0, nb, entetes = ent
        roles: dict[str, int] = {}
        for j, e in enumerate(entetes):
            r = _role(e)
            if r and r != "ignorer":
                if r == "recouvre" and re.search(r"realis", e) and ("engage" in roles or "ordonnance" in roles):
                    r = "ordonnance"  # « réalisations » d'un tableau de dépenses
                roles.setdefault(r, j)
        if "libelle" not in roles and "groupe" in roles and entetes[roles["groupe"]] == "nature":
            roles["libelle"] = roles.pop("groupe")  # seule colonne de libellé : « Nature »
        if "libelle" not in roles:
            libre = [j for j in range(len(entetes)) if j not in roles.values()]
            if libre:
                roles["libelle"] = libre[0]
        sens_table = _sens_table(table.nom, roles, table.lignes)
        groupe_courant = ""
        for brut in table.lignes[i0 + nb:]:
            cell = lambda r: brut[roles[r]] if r in roles and roles[r] < len(brut) else None  # noqa: E731
            libelle = str(cell("libelle") or "").strip()
            code = _code(cell("code")) or _code(libelle)
            n_lib = normaliser(libelle)
            vals = {r: lire_nombre(cell(r)) for r in ROLES_MONTANTS if r in roles}
            vals = {r: v for r, v in vals.items() if v is not None}
            sens = sens_table
            if "sens" in roles:
                s = normaliser(str(cell("sens") or ""))
                sens = "recettes" if re.match(r"r|recette|ressource", s) else "depenses" if re.match(r"d|depense|emploi", s) else sens
            if sens is None and code:
                sens = "recettes" if code.startswith("7") and len(code) == 6 else "depenses"
            if "epn" in roles:
                v = str(cell("epn") or "").strip()
                if v:
                    valeurs_epn.add(v)
                nv = normaliser(v)
                if cibles and not any(c and (c == nv or re.search(r"\b" + re.escape(c) + r"\b", nv) or (len(nv) > 3 and nv in c))
                                      for c in cibles):
                    continue
                sit.filtre_epn = v
            if not vals:
                if libelle:
                    groupe_courant = _groupe(sens or "depenses", libelle, "") or groupe_courant
                continue
            if re.match(r"^(total|totaux)( general| global| des (recettes|ressources|depenses|emplois))?\s*:?$|^total general",
                        n_lib):
                for r, v in vals.items():
                    sit.totaux_declares.setdefault(f"{sens}_{r}", v)
                continue
            if re.match(r"^(sous[- ]?totale?|s/t|total)\b", n_lib) or not (libelle or code):
                continue
            if sens is None:
                continue
            groupe = _groupe(sens, str(cell("groupe") or ""), "") if "groupe" in roles else ""
            groupe = groupe or groupe_courant or _groupe(sens, libelle, code)
            cle = (sens, code or n_lib, tuple(sorted(vals.items())))
            if cle in vus:
                continue  # même ligne reprise dans une autre feuille
            vus.add(cle)
            sit.lignes.append(LigneSituation(sens, code, libelle, groupe, vals, sit.filtre_epn, table.nom))
    if valeurs_epn and not sit.lignes:
        sit.avertissements.append(
            "Situation d'exécution consolidée : aucune ligne pour cet EPN (valeurs trouvées : "
            + ", ".join(sorted(valeurs_epn)[:12]) + "). Vérifier le sigle dans le référentiel des EPN.")
    elif not sit.lignes and not sit.totaux_declares:
        sit.avertissements.append(f"{source.chemin.name} : aucune ligne de situation d'exécution reconnue "
                                  "(colonnes attendues : libellé/code, prévisions, engagements, ordonnancements, recouvrements).")
    return sit


def _date_arrete(source: SourceSituation) -> date | None:
    morceaux = [source.texte, source.chemin.stem.replace("_", " ")]
    for t in source.tables:
        morceaux.append(t.nom)
        for l in t.lignes[:8]:
            morceaux.extend(str(v) for v in l if v not in (None, ""))
    texte = normaliser(" ".join(morceaux))
    m = re.search(r"(?:au|arretee?\s+au|a la date du|fin|jusqu.au|periode du .{0,25}? au)\s+"
                  r"(\d{1,2}\s*(?:er)?\s+[a-z]+\s+(?:19|20)\d\d|\d{1,2}\s*[/.-]\s*\d{1,2}\s*[/.-]\s*(?:19|20)\d\d)", texte)
    if m:
        return lire_date(m.group(1))
    return None


# ------------------------------------------------------------------ choix de la situation d'un EPN
def situation_pour(sources: list[SourceSituation], nom_epn: str, fiche: FicheEPN | None,
                   unique: bool = False) -> SituationExecution | None:
    """Sélectionne la situation de l'EPN : fichier consolidé filtré, ou fichier dont le nom/contenu cite l'EPN."""
    cibles = [normaliser(x) for x in (fiche.sigle if fiche else "", fiche.denomination if fiche else "", nom_epn) if x]
    m = re.search(r"\(([A-Z0-9\-]{2,12})\)", nom_epn or "")
    if m:
        cibles.append(normaliser(m.group(1)))
    candidats = []
    for src in sources:
        sit = extraire_situation(src, nom_epn, fiche)
        if sit.filtre_epn and sit.lignes:
            return sit  # fichier consolidé : lignes de l'EPN trouvées
        zone = normaliser(src.chemin.stem.replace("_", " ") + " " + src.texte + " " + " ".join(t.nom for t in src.tables))
        if any(c and re.search(r"\b" + re.escape(c) + r"\b", zone) for c in cibles):
            return sit
        candidats.append(sit)
    if unique and len(sources) == 1:
        return candidats[0] if candidats else None
    return None


# ------------------------------------------------------------------ rapprochement
@dataclass
class LigneRapprochement:
    libelle: str
    tableau: str
    rapport: float | None
    situation: float | None
    statut: str
    taux: bool = False
    code: str = ""

    @property
    def ecart(self) -> float | None:
        if self.rapport is None or self.situation is None:
            return None
        return self.rapport - self.situation


class Rapprochement:
    def __init__(self, sit: SituationExecution, tableaux: ControleTableaux, periode: Periode, ocr: bool = False):
        self.sit, self.t, self.periode, self.ocr = sit, tableaux, periode, ocr
        self.agregats_sit = sit.agregats()
        self.agregats_rap = tableaux.agregats()
        self.lignes: list[LigneRapprochement] = []
        self.detail: list[LigneRapprochement] = []
        self.codes_absents_rapport: list[str] = []
        self.codes_absents_situation: list[str] = []
        self.constats: list[Constat] = []
        self.date_conforme: bool | None = None
        self._date()
        self._agregats()
        self._detail()

    @property
    def nb_ecarts(self) -> int:
        return sum(1 for l in self.lignes + self.detail if l.statut == ECART)

    @property
    def nb_concordants(self) -> int:
        return sum(1 for l in self.lignes if l.statut == CONCORDANT)

    @property
    def synthese(self) -> str:
        comparables = [l for l in self.lignes if l.statut != NON_COMPARABLE]
        if not comparables:
            return "Aucun montant comparable entre le rapport et la situation d'exécution."
        ec = [l for l in comparables if l.statut == ECART]
        txt = (f"{len(comparables) - len(ec)}/{len(comparables)} agrégat(s) concordant(s) avec la situation d'exécution"
               + (f" arrêtée au {self.sit.date_arrete:%d/%m/%Y}" if self.sit.date_arrete else "") + ".")
        if ec:
            txt += " Écarts : " + " ; ".join(
                f"{l.libelle} ({format_taux(l.rapport) if l.taux else format_montant(l.rapport)} au rapport contre "
                f"{format_taux(l.situation) if l.taux else format_montant(l.situation)})" for l in ec[:4])
            txt += " ; …" if len(ec) > 4 else "."
        nd = sum(1 for l in self.detail if l.statut == ECART)
        if nd:
            txt += f" {nd} écart(s) au niveau des lignes (codes)."
        return txt

    def _date(self) -> None:
        d = self.sit.date_arrete
        if d is None:
            self.sit.avertissements.append("Date d'arrêté de la situation d'exécution non trouvée : vérifier qu'elle "
                                           f"correspond bien à la fin de la période ({self.periode.fin:%d/%m/%Y}).")
            return
        self.date_conforme = d == self.periode.fin
        if not self.date_conforme:
            self.constats.append(Constat(
                "analyse_execution", "Date de la situation d'exécution",
                f"La situation d'exécution fournie est arrêtée au {d:%d/%m/%Y} alors que le rapport couvre la période "
                f"au {self.periode.fin:%d/%m/%Y} : les écarts éventuels peuvent provenir de ce décalage.",
                "Information", "coherence", attendu=f"{self.periode.fin:%d/%m/%Y}", constate=f"{d:%d/%m/%Y}"))

    def _comparer(self, libelle, code_tab, cle_rap, cle_sit, rubrique, valeur_rap=None, taux=False):
        tab = self.t.par_code.get(code_tab) if code_tab else None
        v_rap = valeur_rap if valeur_rap is not None else self.agregats_rap.get(cle_rap)
        v_sit = self.agregats_sit.get(cle_sit) if isinstance(cle_sit, str) else cle_sit
        nom = tab.nom if tab else (code_tab or "Rapport")
        if v_rap is None or v_sit is None:
            if v_sit is not None:
                self.lignes.append(LigneRapprochement(libelle, nom, v_rap, v_sit, NON_COMPARABLE, taux))
            return
        tol = 0.05 if taux else 1.0
        ok = abs(v_rap - v_sit) <= tol
        self.lignes.append(LigneRapprochement(libelle, nom, v_rap, v_sit, CONCORDANT if ok else ECART, taux))
        if ok:
            return
        rel = abs(v_rap - v_sit) / abs(v_sit) if v_sit else 1
        gravite = "Majeure" if (rel > 0.01 or (taux and abs(v_rap - v_sit) > 1)) and self.date_conforme is not False else "Mineure"
        fmt = format_taux if taux else format_montant
        self.constats.append(Constat(
            rubrique, "Concordance avec la situation d'exécution",
            f"{libelle} : {fmt(v_rap)} dans le rapport ({nom}) contre {fmt(v_sit)} dans la situation d'exécution "
            f"(écart {fmt(v_rap - v_sit)}" + ("" if taux else f", soit {rel * 100:.2f} %".replace(".", ",")) + ")."
            + (" [OCR]" if self.ocr else ""),
            gravite, "fiabilite", nom if tab else "", attendu=fmt(v_sit), constate=fmt(v_rap)))

    def _agregats(self) -> None:
        a = self.agregats_sit
        t3, t4 = self.t.par_code.get("T3"), self.t.par_code.get("T4")
        self._comparer("Prévisions initiales de recettes", "T5", "recettes_initial", "recettes_initial", "exec_recettes")
        self._comparer("Prévisions finales de recettes (budget actuel)", "T5", "recettes_final", "recettes_final", "exec_recettes")
        if t3:
            self._comparer("Ressources – montant actuel", "T3", None, "recettes_final", "pres_ressources",
                           valeur_rap=t3.total("actuel"))
        self._comparer("Recouvrements", "T5", "recettes_realise", "recettes_realise", "exec_recettes")
        self._comparer("Ressources propres recouvrées", "T5", "ressources_propres_realise", "ressources_propres_realise",
                       "exec_recettes")
        self._comparer("Crédits initiaux de dépenses", "T6", "depenses_initial", "depenses_initial", "exec_depenses")
        self._comparer("Budget actuel de dépenses", "T6", "depenses_actuel", "depenses_actuel", "exec_depenses")
        if t4:
            self._comparer("Emplois – montant actuel", "T4", None, "depenses_actuel", "pres_emplois",
                           valeur_rap=t4.total("actuel"))
        self._comparer("Engagements", "T6", "depenses_engage", "depenses_engage", "exec_depenses")
        self._comparer("Ordonnancements", "T6", "depenses_realise", "depenses_realise", "exec_depenses")
        for g in ("personnel", "biens_services", "transferts", "investissement"):
            self._comparer(f"Ordonnancements – {LIBELLES_GROUPES[g]}", "T6", f"{g}_realise", f"{g}_realise", "exec_depenses")
        # Taux et résultat
        r = self.agregats_rap
        if a.get("recettes_final") and "recettes_realise" in a:
            self._comparer("Taux de réalisation des recettes", "T5", None, a["recettes_realise"] / a["recettes_final"] * 100,
                           "exec_recettes", valeur_rap=(r["recettes_realise"] / r["recettes_final"] * 100)
                           if r.get("recettes_final") and "recettes_realise" in r else None, taux=True)
        if a.get("depenses_actuel") and "depenses_realise" in a:
            self._comparer("Taux d'exécution des dépenses", "T6", None, a["depenses_realise"] / a["depenses_actuel"] * 100,
                           "exec_depenses", valeur_rap=(r["depenses_realise"] / r["depenses_actuel"] * 100)
                           if r.get("depenses_actuel") and "depenses_realise" in r else None, taux=True)
        if "recettes_realise" in a and "depenses_realise" in a:
            res_rap = (r["recettes_realise"] - r["depenses_realise"]) if "recettes_realise" in r and "depenses_realise" in r else None
            self._comparer("Résultat budgétaire (recouvrements − ordonnancements)", "", None,
                           a["recettes_realise"] - a["depenses_realise"], "resultat_budgetaire", valeur_rap=res_rap)

    def _detail(self) -> None:
        """Rapprochement ligne à ligne, par code (nature économique ou activité)."""
        for code_tab, sens, paires in (("T5", "recettes", (("final", "actuel"), ("realise", "recouvre"))),
                                       ("T6", "depenses", (("actuel", "actuel"), ("engage", "engage"),
                                                           ("realise", "ordonnance")))):
            tab = self.t.par_code.get(code_tab)
            lignes_sit = {l.code: l for l in self.sit.lignes_de(sens) if l.code}
            if not tab or not lignes_sit:
                continue
            lignes_rap = {}
            for l in tab.lignes:
                if l.type == "ligne":
                    c = _code(l.libelle)
                    if c:
                        lignes_rap[c] = l
            if not lignes_rap:
                continue
            ecarts = []
            for c, lr in lignes_rap.items():
                ls = lignes_sit.get(c)
                if not ls:
                    self.codes_absents_situation.append(f"{code_tab} {c}")
                    continue
                for role_rap, role_sit in paires:
                    if role_sit == "ordonnance" and "ordonnance" not in ls.valeurs:
                        role_sit = "liquide"
                    v_rap, v_sit = lr.valeurs.get(role_rap), ls.valeurs.get(role_sit)
                    if v_rap is None or v_sit is None:
                        continue
                    ok = abs(v_rap - v_sit) <= 1
                    lr_obj = LigneRapprochement(f"{lr.libelle[:70]} – {_LIB_ROLE[role_rap]}", tab.nom, v_rap, v_sit,
                                                CONCORDANT if ok else ECART, code=c)
                    self.detail.append(lr_obj)
                    if not ok:
                        ecarts.append(lr_obj)
            self.codes_absents_rapport += [f"{code_tab} {c} – {l.libelle[:60]}" for c, l in lignes_sit.items()
                                           if c not in lignes_rap and any(abs(v) > 0 for v in l.valeurs.values())]
            if ecarts:
                self.constats.append(Constat(
                    "exec_recettes" if sens == "recettes" else "exec_depenses",
                    "Concordance des lignes avec la situation d'exécution",
                    f"{len(ecarts)} montant(s) du {tab.nom} diffère(nt) de la situation d'exécution, ex. : "
                    + " ; ".join(f"{e.code} {e.libelle.split(' – ')[-1]} {format_montant(e.rapport)} contre "
                                 f"{format_montant(e.situation)}" for e in ecarts[:3]) + ("…" if len(ecarts) > 3 else "."),
                    "Mineure", "fiabilite", tab.nom, attendu="situation d'exécution", constate=f"{len(ecarts)} écart(s)"))


_LIB_ROLE = {"final": "prévision finale", "actuel": "budget actuel", "realise": "réalisation", "engage": "engagements"}


def _code(valeur) -> str:
    """Code de nature économique (6 chiffres) ou d'activité (11 chiffres) contenu dans une cellule."""
    v = str(valeur or "").strip()
    if isinstance(valeur, (int, float)) and float(valeur).is_integer():
        return str(int(valeur))
    m = re.search(r"\b(\d{11}|\d{6})\b", v)
    return m.group(1) if m else ""
