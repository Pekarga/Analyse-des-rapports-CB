"""Contrôles transverses : période, délai, signature, version du canevas, cohérence texte/tableaux,
résultat budgétaire, ratios de gestion, référentiel des EPN, difficultés et suggestions."""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .lecture import RE_PUCE, DocumentRapport
from .structure import AnalyseStructure, Detection
from .tableaux import Constat, ControleTableaux, _comparer_taux
from .texte import format_montant, format_taux, lire_nombre, normaliser

MOIS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}
RE_DATE_LETTRES = re.compile(r"\b(\d{1,2})\s*(?:er)?\s+(" + "|".join(MOIS) + r")\s+((?:19|20)\d\d)\b")
RE_DATE_CHIFFRES = re.compile(r"\b(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*((?:19|20)\d\d)\b")


def lire_date(texte) -> date | None:
    """Lit une date « 04 août 2023 », « 04/08/2023 », « 2023-08-04 » ou un objet date."""
    if texte is None or texte == "":
        return None
    if isinstance(texte, datetime):
        return texte.date()
    if isinstance(texte, date):
        return texte
    s = normaliser(str(texte))
    m = re.match(r"^((?:19|20)\d\d)-(\d{1,2})-(\d{1,2})", s)
    try:
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = RE_DATE_CHIFFRES.search(s)
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        m = RE_DATE_LETTRES.search(s)
        if m:
            return date(int(m.group(3)), MOIS[m.group(2)], int(m.group(1)))
    except ValueError:
        return None
    return None


# ------------------------------------------------------------------ période
@dataclass
class Periode:
    type: str  # "etape" (semestriel, au 30 juin) ou "annuel"
    annee: int
    libelle: str
    detectee: bool = True

    @property
    def fin(self) -> date:
        return date(self.annee, 6, 30) if self.type == "etape" else date(self.annee, 12, 31)

    @property
    def annuel(self) -> bool:
        return self.type == "annuel"


def detecter_periode(doc: DocumentRapport, imposee: str | None = None) -> Periode:
    if imposee:
        n = normaliser(imposee)
        annee = re.search(r"(19|20)\d\d", n)
        an = int(annee.group(0)) if annee else date.today().year
        etape = bool(re.search(r"semestr|etape|juin|s1\b|30/06", n)) and not re.search(r"(2e|2eme|deuxieme|second) semestre", n)
        return Periode("etape" if etape else "annuel", an,
                       f"Rapport d'étape au 30 juin {an}" if etape else f"Rapport annuel, exercice {an}")
    debut = normaliser(doc.texte(0, min(len(doc.blocs), 40)))
    for zone in (debut, normaliser(doc.texte_complet)[:20000]):
        m = re.search(r"(1er|premier|1e|1ere|1)\s+semestre\s+(?:de l.(?:annee|exercice)\s+|de la gestion\s+|budgetaire\s+)?((?:19|20)\d\d)", zone) \
            or re.search(r"(?:au|arrete au|a fin|fin|au titre du)\s+(?:30 juin|30/06/|30-06-)\s*((?:19|20)\d\d)", zone) \
            or re.search(r"rapport d.etape[^.]{0,60}?((?:19|20)\d\d)", zone)
        if m:
            an = int(m.groups()[-1])
            return Periode("etape", an, f"Rapport d'étape au 30 juin {an}")
        m = re.search(r"(?:exercice|gestion|annee)\s+(?:budgetaire\s+)?((?:19|20)\d\d)", zone) \
            or re.search(r"rapport annuel[^.]{0,40}?((?:19|20)\d\d)", zone) \
            or re.search(r"(?:au|arrete au)\s+31\s*(?:decembre|/12/)\s*((?:19|20)\d\d)", zone)
        if m:
            an = int(m.group(1))
            return Periode("annuel", an, f"Rapport annuel, exercice {an}")
    an = date.today().year - 1
    return Periode("annuel", an, f"Période non détectée (exercice {an} supposé)", detectee=False)


def date_limite(periode: Periode, parametres: dict) -> date:
    d = parametres.get("delais", {})
    if periode.type == "etape":
        jj, mm = (int(x) for x in d.get("rapport_etape_date_limite", "31/07").split("/"))
        return date(periode.annee, mm, jj)
    jj, mm = (int(x) for x in d.get("rapport_annuel_date_limite", "30/04").split("/"))
    return date(periode.annee + 1, mm, jj)


# ------------------------------------------------------------------ référentiel EPN
@dataclass
class FicheEPN:
    sigle: str
    denomination: str
    texte_creation: str = ""
    tutelle: str = ""
    controleur: str = ""


def lire_csv(chemin: str | Path) -> list[dict[str, str]]:
    chemin = Path(chemin)
    if not chemin.exists():
        return []
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
    lecteur = csv.DictReader(lignes, delimiter=sep)
    return [{normaliser(k).replace(" ", "_"): (v or "").strip() for k, v in row.items() if k} for row in lecteur]


def charger_referentiel(chemin: str | Path) -> list[FicheEPN]:
    return [FicheEPN(r.get("sigle", ""), r.get("denomination", ""), r.get("texte_creation", ""),
                     r.get("tutelle", ""), r.get("controleur", "")) for r in lire_csv(chemin)
            if r.get("sigle") or r.get("denomination")]


def identifier_epn(doc: DocumentRapport, referentiel: list[FicheEPN]) -> tuple[str, FicheEPN | None]:
    debut = doc.texte(0, min(len(doc.blocs), 40))
    nd = normaliser(debut)
    for fiche in referentiel:
        if fiche.denomination and normaliser(fiche.denomination) in nd:
            return fiche.denomination, fiche
    for fiche in referentiel:
        if fiche.sigle and re.search(r"\b" + re.escape(normaliser(fiche.sigle)) + r"\b", nd):
            return fiche.denomination or fiche.sigle, fiche
    generiques = re.compile(r"ministere|republique|union|direction|rapport|controleur|semestre|exercice|"
                            r"^epn$|logo|table des|sommaire|budget|^\W*$|^(de|du|la|le)\b")
    for b in doc.paragraphes[:25]:
        n = b.norm
        if b.sommaire or generiques.search(n) or len(n) < 4 or len(n) > 120:
            continue
        if re.search(r"(office|agence|institut|ecole|centre|fonds|universite|caisse|conseil|autorite|"
                     r"etablissement|societe|laboratoire|bureau|programme|chu|hopital|\([A-Z]{2,}\))", b.texte, re.I):
            return b.texte.strip(), None
    return doc.chemin.stem, None


def identifier_controleur(doc: DocumentRapport) -> str:
    paras = doc.paragraphes
    for b in paras[:40]:
        m = re.search(r"contr[oô]leur budg[eé]taire\s*:\s*(.+)$", b.texte, re.I)
        if m and len(m.group(1)) > 3:
            return m.group(1).strip()
    fin = paras[-25:]
    for i, b in enumerate(fin):
        if re.search(r"(le|la)\s+contr[oô]leu[rs]e?\s+budg[eé]taire", b.texte, re.I):
            for suivant in fin[i + 1:i + 4]:
                t = suivant.texte.strip()
                if 2 <= len(t.split()) <= 6 and not re.search(r"\d", t) and len(t) < 60:
                    return t
    return ""


# ------------------------------------------------------------------ signature
def controle_signature(doc: DocumentRapport) -> tuple[str, str, date | None]:
    fin = doc.paragraphes[-30:]
    texte_fin = "\n".join(b.texte for b in fin)
    nf = normaliser(texte_fin)
    date_rapport = None
    for m in re.finditer(r"(?:fait\s+a\s+\w+|abidjan|yamoussoukro|bouake|[a-z]+)\s*,?\s*le\s+([^\n]{6,30})", nf):
        date_rapport = lire_date(m.group(1))
        if date_rapport:
            break
    signataire = identifier_controleur(doc) if re.search(r"controleu[rs]e? budgetaire", nf) else ""
    images = doc.images_derniere_page
    if date_rapport and signataire:
        precision = (f"Rapport daté du {date_rapport:%d/%m/%Y}, signataire : {signataire}."
                     + ("" if images else " Aucune image de signature/cachet détectée : vérifier la signature manuscrite."))
        return ("Conforme" if images else "À vérifier"), precision, date_rapport
    if date_rapport:
        return "À vérifier", f"Rapport daté du {date_rapport:%d/%m/%Y} mais nom/qualité du signataire non trouvés.", date_rapport
    if signataire:
        return "Non conforme", f"Signataire identifié ({signataire}) mais le rapport n'est pas daté.", None
    return "Non conforme", "Ni date ni bloc de signature détectés en fin de rapport.", None


# ------------------------------------------------------------------ cohérence texte / tableaux
RE_POURCENT = re.compile(r"(\d{1,3}(?:[.,]\d{1,3})?)\s*%")


def _phrases(texte: str) -> list[str]:
    return [p for p in re.split(r"(?<=[.;!?])\s+|\n", texte) if p.strip()]


def pourcentages_cites(texte: str, motif: str) -> list[tuple[float, str]]:
    res = []
    for ph in _phrases(texte):
        n = normaliser(ph)
        if re.search(motif, n):
            for m in RE_POURCENT.finditer(ph):
                v = lire_nombre(m.group(1), taux=True)
                if v is not None:
                    res.append((v, ph.strip()))
    return res


@dataclass
class Ratio:
    code: str
    libelle: str
    formule: str
    calcule: dict[str, float] = field(default_factory=dict)  # base -> valeur
    cite: float | None = None
    phrase: str = ""
    coherent: bool | None = None


class ControlesTransverses:
    def __init__(self, doc: DocumentRapport, structure: AnalyseStructure, tableaux: ControleTableaux,
                 periode: Periode, fiche: FicheEPN | None):
        self.doc, self.s, self.t, self.periode, self.fiche = doc, structure, tableaux, periode, fiche
        self.constats: list[Constat] = []
        self.ratios: list[Ratio] = []
        self.resultat: dict = {}
        self.agregats = tableaux.agregats()
        self._taux_cites()
        self._resultat_budgetaire()
        self._ratios()
        self._texte_creation()

    def _ajouter(self, rubrique, controle, message, gravite="Mineure", nature="coherence", attendu="", constate=""):
        self.constats.append(Constat(rubrique, controle, message, gravite, nature, "", "", attendu, constate))

    # -- taux cités dans le texte
    def _taux_cites(self) -> None:
        for code_rub, code_tab, num, den, motif, nom in (
            ("exec_recettes", "T5", "realise", "final",
             r"taux (de |d.)?(recouvrement|realisation|mobilisation|execution)", "taux de réalisation des recettes"),
            ("exec_depenses", "T6", "realise", "actuel",
             r"taux (de |d.)?(execution|consommation|realisation|ordonnancement)", "taux d'exécution des dépenses"),
        ):
            tab = self.t.par_code.get(code_tab)
            texte = self.s.texte_section(code_rub)
            if not tab or not texte:
                continue
            valeurs_tableau = []
            n_tot, d_tot = tab.total(num), tab.total(den)
            if n_tot is not None and d_tot:
                valeurs_tableau.append(n_tot / d_tot * 100)
            for l in tab.lignes:
                if num in l.valeurs and l.valeurs.get(den):
                    valeurs_tableau.append(l.valeurs[num] / l.valeurs[den] * 100)
                if "taux" in l.valeurs:
                    valeurs_tableau.append(l.valeurs["taux"] * (100 if l.valeurs["taux"] <= 1.5 else 1))
            if not valeurs_tableau:
                continue
            for valeur, phrase in pourcentages_cites(texte, motif):
                if not any(abs(valeur - v) <= 0.6 for v in valeurs_tableau):
                    global_ = valeurs_tableau[0] if n_tot is not None and d_tot else None
                    self._ajouter(code_rub, f"Cohérence du {nom} cité dans le texte",
                                  f"Le {nom} cité ({format_taux(valeur)}) ne correspond à aucun taux du {tab.nom}"
                                  + (f" (taux global recalculé : {format_taux(global_)})" if global_ is not None else "")
                                  + f". Phrase : « {phrase[:200]} »",
                                  "Majeure", attendu=format_taux(global_) if global_ is not None else "",
                                  constate=format_taux(valeur))

    # -- résultat budgétaire
    def _resultat_budgetaire(self) -> None:
        a = self.agregats
        texte = self.s.texte_section("resultat_budgetaire")
        if "recettes_realise" not in a or "depenses_realise" not in a:
            return
        r, d = a["recettes_realise"], a["depenses_realise"]
        res = r - d
        self.resultat = {"recettes": r, "depenses": d, "resultat": res,
                         "sens": "excédentaire" if res > 0 else "déficitaire" if res < 0 else "équilibré"}
        if not texte:
            return
        n = normaliser(texte)
        excedent = bool(re.search(r"excedent", n))
        deficit = bool(re.search(r"deficit", n))
        self.resultat["sens_cite"] = ("excédentaire" if excedent and not deficit else
                                      "déficitaire" if deficit and not excedent else "")
        if excedent != deficit:
            cite_excedent = excedent
            if (res > 0) != cite_excedent and res != 0:
                self._ajouter("resultat_budgetaire", "Sens du résultat budgétaire",
                              f"Le rapport qualifie le résultat de « {self.resultat['sens_cite']} » alors que "
                              f"recouvrements ({format_montant(r)}) − ordonnancements ({format_montant(d)}) = "
                              f"{format_montant(res)} (résultat {self.resultat['sens']}).", "Majeure",
                              attendu=self.resultat["sens"], constate=self.resultat["sens_cite"])
        montants = [lire_nombre(m.group(0)) for m in re.finditer(r"\d{1,3}(?:[  .]\d{3})+(?:,\d+)?|\d{4,}", texte)]
        montants = [m for m in montants if m and m >= 1000]
        self.resultat["montant_retrouve"] = any(abs(abs(m) - abs(res)) <= max(1.0, 0.0005 * abs(res)) for m in montants)
        if montants and not self.resultat["montant_retrouve"] and abs(res) >= 1:
            self._ajouter("resultat_budgetaire", "Montant du résultat budgétaire",
                          f"Le montant du résultat budgétaire issu des tableaux ({format_montant(res)}) n'est pas "
                          "retrouvé dans la rubrique « Analyse du résultat budgétaire » (vérifier le calcul ou la "
                          "définition retenue).", "Mineure", attendu=format_montant(res))

    # -- ratios
    def _ratios(self) -> None:
        a = self.agregats
        texte = self.s.texte_section("ratios") or self.s.texte_section("resultat_budgetaire")

        def div(x, y):
            return x / y * 100 if x is not None and y else None

        dep_base = {"engagements": a.get("depenses_engage"), "ordonnancements": a.get("depenses_realise")}
        comp = {
            "RRP": ("Ratio de Ressources Propres", "Σ Ressources propres / Total des ressources",
                    {"réalisations": div(a.get("ressources_propres_realise"), a.get("recettes_realise")),
                     "prévisions": div(a.get("ressources_propres_final"), a.get("recettes_final"))},
                    r"\brrp\b|ressources propres"),
            "RDP": ("Ratio des Dépenses du Personnel", "Dépenses de personnel / Σ Dépenses engagées",
                    {"engagements": div(a.get("personnel_engage"), dep_base["engagements"]),
                     "ordonnancements": div(a.get("personnel_realise"), dep_base["ordonnancements"])},
                    r"\brdp\b|(depenses|charges) (de|du) personnel"),
            "RDF": ("Ratio des Dépenses de Fonctionnement", "Dépenses de fonctionnement / Σ Dépenses engagées",
                    {base: div(sum(v for v in (a.get(f"personnel_{k}"), a.get(f"biens_services_{k}"),
                                                a.get(f"transferts_{k}")) if v is not None) or None, dep_base[base])
                     for base, k in (("engagements", "engage"), ("ordonnancements", "realise"))},
                    r"\brdf\b|depenses de fonctionnement"),
            "RDI": ("Ratio des Dépenses d'Investissement", "Dépenses d'investissement / Σ Dépenses engagées",
                    {"engagements": div(a.get("investissement_engage"), dep_base["engagements"]),
                     "ordonnancements": div(a.get("investissement_realise"), dep_base["ordonnancements"])},
                    r"\brdi\b|depenses d.investissement"),
            "RDA": ("Ratio des Dépenses d'Abonnement", "Dépenses d'abonnement / Dépenses de fonctionnement", {},
                    r"\brda\b|abonnement"),
        }
        for code, (libelle, formule, valeurs, motif) in comp.items():
            ratio = Ratio(code, libelle, formule, {k: v for k, v in valeurs.items() if v is not None})
            cites = pourcentages_cites(texte, motif) if texte else []
            if cites:
                ratio.cite, ratio.phrase = cites[0]
                if ratio.calcule:
                    ratio.coherent = any(abs(c - v) <= 0.6 for c, _ in cites for v in ratio.calcule.values())
                    if not ratio.coherent:
                        self._ajouter("ratios", f"Cohérence du {code}",
                                      f"{libelle} cité : {format_taux(ratio.cite)} ; valeur(s) recalculée(s) à partir "
                                      f"des tableaux : " + ", ".join(f"{format_taux(v)} ({b})" for b, v in ratio.calcule.items())
                                      + ".", "Mineure", attendu=format_taux(next(iter(ratio.calcule.values()))),
                                      constate=format_taux(ratio.cite))
            self.ratios.append(ratio)

    # -- texte de création vs référentiel
    def _texte_creation(self) -> None:
        if not self.fiche or not self.fiche.texte_creation:
            return
        ref = normaliser(self.fiche.texte_creation)
        numeros = re.findall(r"(?:19|20)\d\d\s*-\s*\d+", ref)
        if not numeros:
            return
        zone = normaliser(self.s.texte_section("introduction") + "\n" + self.s["texte_creation"].texte)
        zone = re.sub(r"\s*-\s*", "-", zone)
        if not any(num.replace(" ", "") in zone for num in numeros):
            self._ajouter("texte_creation", "Texte de création conforme au référentiel",
                          f"Le texte de création de référence ({self.fiche.texte_creation}) n'est pas cité dans "
                          "l'introduction du rapport.", "Majeure", "fiabilite", attendu=self.fiche.texte_creation)

    def texte_creation_verifie(self) -> bool | None:
        if not self.fiche or not self.fiche.texte_creation:
            return None
        return not any(c.rubrique == "texte_creation" for c in self.constats)


# ------------------------------------------------------------------ difficultés et suggestions
CATEGORIES = [
    ("controle", "Principales contraintes dans le contrôle de l'exécution du budget de l'EPN",
     r"controle|controleur|\bcb\b|visa|pieces? justificatives?|differe|rejet|dossiers? (transmis|soumis)|"
     r"engagements? (hors|sans)|regularisation|application|logiciel|sigfip|outil|bureau du|moyens (du|de travail)"),
    ("execution", "Principales contraintes de l'exécution du budget de l'EPN",
     r"transfert|subvention|recouvr|mobilis|tresorerie|liquidit|retard (de|dans la) (mise|paiement|deblocage)|"
     r"recettes|ressources|credits?|budget|dotation|arriere|dette|impaye|regulation|gel"),
    ("gestion", "Contraintes liées à la gestion de l'établissement", r".*"),
]


@dataclass
class Element:
    texte: str
    categorie: str
    rubrique: str
    page: int | None = None


def _items(doc: DocumentRapport, det: Detection, exclure: set[int]) -> list[tuple[str, int | None]]:
    if not det.trouvee or det.mode != "titre":
        return []
    items = []
    for b in doc.blocs[det.debut + 1:det.fin]:
        if b.index in exclure or b.type != "p" or b.sommaire:
            continue
        t = b.texte.strip()
        while RE_PUCE.match(t):
            t = RE_PUCE.sub("", t, count=1).strip()
        if len(t) < 12 or (b.candidat_titre and len(t) < 60 and not t.endswith((".", ";"))):
            continue
        items.append((t, b.page))
    return items


def extraire_difficultes_suggestions(doc: DocumentRapport, s: AnalyseStructure) -> dict[str, list[Element]]:
    res: dict[str, list[Element]] = {"difficultes": [], "suggestions": []}
    titres = {d.debut for d in s.detections.values() if d.mode == "titre"}
    for code in ("difficultes", "suggestions"):
        det = s[code]
        source = det if det.trouvee else s["difficultes_suggestions"]
        if not det.trouvee and source.trouvee:
            # Partie X sans sous-titres : on ne sait pas séparer difficultés et suggestions.
            if code == "suggestions":
                continue
        for texte, page in _items(doc, source, titres):
            n = normaliser(texte)
            cat = next(c for c, _, motif in CATEGORIES if re.search(motif, n))
            res[code].append(Element(texte, cat, source.rubrique.libelle, page))
    # Les « autres suggestions » sont rattachées aux suggestions
    for texte, page in _items(doc, s["autres_suggestions"], titres):
        res["suggestions"].append(Element(texte, "gestion", "Autres suggestions", page))
    return res
