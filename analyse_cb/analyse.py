"""Orchestration : lecture du rapport, contrôles, et production des appréciations de la grille."""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

from .canevas import MARQUEURS_CANEVAS_2023, PAR_CODE, RUBRIQUES, TABLEAUX, enfants
from .canevas import actualiser as actualiser_canevas
from .canevas import plan as plan_modele
from .controles import (ControlesTransverses, Element, Periode, controle_signature, date_limite,
                        detecter_periode, extraire_difficultes_suggestions, identifier_controleur,
                        identifier_epn, lire_date, charger_referentiel)
from .decret import ConfrontationDecret, Decret, choisir_decret, lire_decret
from .decret import ECART as D_ECART
from .lecture import DocumentRapport, lire_rapport
from .situation import Rapprochement, SituationExecution, SourceSituation, charger_source, situation_pour
from .structure import AnalyseStructure
from .tableaux import Constat, ControleTableaux

from .ressources import dossier_ressources, fichier_config

RACINE = dossier_ressources()
PARAMETRES_DEFAUT = fichier_config("parametres.toml")
REFERENTIEL_DEFAUT = fichier_config("referentiel_epn.csv")

NOTE_OCR = " [Lecture OCR d'un document scanné : à confirmer sur l'original.]"


def _court(c, n: int = 230) -> str:
    m = c.message.replace(NOTE_OCR, "").replace(" (même écart sur plusieurs colonnes)", "")
    return m if len(m) <= n else m[: n - 1] + "…"


CONFORME, NON_CONFORME, A_VERIFIER, NON_APPLICABLE = "Conforme", "Non conforme", "À vérifier", "Non applicable"
FIABLE, NON_FIABLE = "Fiable", "Non fiable"
COHERENT, INCOHERENT = "Cohérent", "Incohérent"
A_APPRECIER, NON_RENSEIGNE, SANS_OBJET = "À apprécier", "Non renseigné", "Sans objet"


@dataclass
class LigneForme:
    code: str
    libelle: str
    ligne: int | None
    statut: str
    precision: str
    hors_grille: bool = False
    redige: str = ""  # commentaire affiché dans le fichier d'analyse


@dataclass
class LigneFond:
    code: str
    libelle: str
    ligne: int | None
    fiabilite: str
    coherence: str
    commentaire: str
    redige: str = ""  # commentaire affiché dans le fichier d'analyse


@dataclass
class InfosRapport:
    epn: str = ""
    controleur: str = ""
    charge_etudes: str = ""
    date_reception: date | None = None
    periode: str | None = None  # libellé imposé (sinon détecté)


@dataclass
class ResultatAnalyse:
    doc: DocumentRapport
    infos: InfosRapport
    periode: Periode
    date_limite: date
    structure: AnalyseStructure
    tableaux: ControleTableaux
    transverses: ControlesTransverses
    forme: list[LigneForme] = field(default_factory=list)
    fond: list[LigneFond] = field(default_factory=list)
    signature: tuple[str, str, date | None] = ("", "", None)
    canevas_en_vigueur: tuple[str, str] = ("", "")
    thematiques: object = None  # thematiques.Rubriques : gouvernance, patrimoine, contrôle, difficultés
    difficultes: dict[str, list[Element]] = field(default_factory=dict)
    parametres: dict = field(default_factory=dict)
    decret: Decret | None = None
    confrontation: ConfrontationDecret | None = None
    situation: SituationExecution | None = None
    rapprochement: Rapprochement | None = None

    @property
    def validation_directe(self) -> bool:
        return bool(self.parametres.get("analyse", {}).get("validation_directe", True))

    # -------------------------------------------------------------- indicateurs
    @property
    def constats(self) -> list[Constat]:
        return (self.tableaux.constats + self.transverses.constats
                + (self.confrontation.constats if self.confrontation else [])
                + (self.rapprochement.constats if self.rapprochement else []))

    @property
    def appreciation_decret(self) -> str:
        from .commentaires import synthese_decret
        return synthese_decret(self)

    @property
    def decret_conforme(self) -> bool | None:
        if not self.confrontation:
            return None
        return not any(p.statut == D_ECART for p in self.confrontation.points)

    @property
    def appreciation_situation(self) -> str:
        from .commentaires import synthese_situation
        return synthese_situation(self)

    @property
    def ecart_jours(self) -> int | None:
        if not self.infos.date_reception:
            return None
        return (self.infos.date_reception - self.date_limite).days

    @property
    def appreciation_delai(self) -> str:
        e = self.ecart_jours
        if e is None:
            return "Date de réception non renseignée"
        return "Transmis dans les délais" if e <= 0 else f"Hors délai de {e} jour{'s' if e > 1 else ''}"

    @property
    def score_forme(self) -> float:
        lignes = [l for l in self.forme if l.statut in (CONFORME, NON_CONFORME, A_VERIFIER)]
        if not lignes:
            return 0.0
        pts = sum(1 if l.statut == CONFORME else 0.5 if l.statut == A_VERIFIER else 0 for l in lignes)
        return round(100 * pts / len(lignes), 1)

    @property
    def score_fond(self) -> float | None:
        valeurs = []
        for l in self.fond:
            for v in (l.fiabilite, l.coherence):
                if v in (FIABLE, COHERENT):
                    valeurs.append(1)
                elif v in (NON_FIABLE, INCOHERENT, NON_RENSEIGNE):
                    valeurs.append(0)
        return round(100 * sum(valeurs) / len(valeurs), 1) if valeurs else None

    def mention(self, score: float | None) -> str:
        if score is None:
            return "Non évalué"
        seuils = self.parametres.get("appreciation", {})
        if score >= seuils.get("tres_bien", 90):
            return "Très satisfaisant"
        if score >= seuils.get("bien", 75):
            return "Satisfaisant"
        if score >= seuils.get("passable", 50):
            return "Passable"
        return "Insuffisant"

    @property
    def rubriques_absentes(self) -> list[str]:
        return [l.libelle for l in self.forme if l.statut == NON_CONFORME and l.code in PAR_CODE]

    @property
    def nb_anomalies_majeures(self) -> int:
        return sum(1 for c in self.constats if c.gravite == "Majeure")


def charger_parametres(chemin: str | Path | None = None) -> dict:
    chemin = Path(chemin) if chemin else PARAMETRES_DEFAUT
    if not chemin.exists():
        return {}
    with open(chemin, "rb") as f:
        return tomllib.load(f)


def _liste(valeur) -> list:
    if valeur is None:
        return []
    return list(valeur) if isinstance(valeur, (list, tuple)) else [valeur]


def charger_decrets(chemins) -> list[Decret]:
    """Lit un ou plusieurs décrets (fichiers ou dossiers). Les objets Decret déjà lus sont conservés tels quels."""
    out = []
    for c in _liste(chemins):
        if isinstance(c, Decret):
            out.append(c)
            continue
        c = Path(c)
        fichiers = sorted(f for f in c.iterdir() if f.suffix.lower() in (".pdf", ".docx", ".txt")
                          and not f.name.startswith("~$")) if c.is_dir() else [c]
        out += [lire_decret(f) for f in fichiers]
    return out


def charger_situations(chemins) -> list[SourceSituation]:
    out = []
    for c in _liste(chemins):
        if isinstance(c, SourceSituation):
            out.append(c)
            continue
        c = Path(c)
        fichiers = sorted(f for f in c.iterdir() if f.suffix.lower() in (".xlsx", ".xlsm", ".csv", ".pdf", ".docx")
                          and not f.name.startswith("~$")) if c.is_dir() else [c]
        out += [charger_source(f) for f in fichiers]
    return out


def analyser(chemin: str | Path, infos: InfosRapport | None = None, parametres: dict | None = None,
             referentiel: str | Path | None = None, decrets=None, situations=None,
             reference_unique: bool = True) -> ResultatAnalyse:
    """Analyse un rapport.

    decrets / situations : chemin(s) de fichiers ou de dossiers, ou objets déjà chargés (charger_decrets,
    charger_situations). Le décret et la situation de l'EPN sont choisis d'après la dénomination ou le sigle ;
    si reference_unique est vrai et qu'un seul fichier est fourni, il est utilisé même sans correspondance.
    """
    infos = infos or InfosRapport()
    parametres = parametres if parametres is not None else charger_parametres()
    actualiser_canevas()  # canevas et modèle de fichier d'analyse paramétrés
    doc = lire_rapport(chemin)
    fiches = charger_referentiel(referentiel or REFERENTIEL_DEFAUT)
    nom_epn, fiche = identifier_epn(doc, fiches)

    # Décret de création et d'organisation
    liste_decrets = charger_decrets(decrets)
    debut = doc.texte(0, min(len(doc.blocs), 40))
    decret = choisir_decret(liste_decrets, infos.epn or nom_epn, fiche, debut, unique=reference_unique)
    if decret is None and fiche and fiche.fichier_decret and Path(fiche.fichier_decret).exists():
        decret = lire_decret(fiche.fichier_decret)
    if decret and fiche is None:
        if nom_epn == doc.chemin.stem and decret.denomination:
            nom_epn = decret.nom
        fiche = decret.fiche()
    infos.epn = infos.epn or nom_epn
    infos.controleur = infos.controleur or identifier_controleur(doc) or (fiche.controleur if fiche else "")
    periode = detecter_periode(doc, infos.periode)
    structure = AnalyseStructure(doc)
    tableaux = ControleTableaux(doc)
    # Avec le décret, le texte de création est vérifié par la confrontation au décret (plus complète).
    fiche_tr = replace(fiche, texte_creation="") if (fiche and decret) else fiche
    transverses = ControlesTransverses(doc, structure, tableaux, periode, fiche_tr)
    confrontation = ConfrontationDecret(decret, structure, tableaux, periode) if decret else None

    # Situation d'exécution à la date de la période
    sources = charger_situations(situations)
    situation = situation_pour(sources, infos.epn, fiche, unique=reference_unique) if sources else None
    if situation is None and fiche and fiche.fichier_situation and Path(fiche.fichier_situation).exists():
        situation = situation_pour([charger_source(fiche.fichier_situation)], infos.epn, fiche, unique=True)
    rapprochement = Rapprochement(situation, tableaux, periode, doc.ocr) if situation and situation.lignes else None
    if situation:
        doc.avertissements.extend(situation.avertissements)
    elif sources:
        doc.avertissements.append("Aucune situation d'exécution ne correspond à cet EPN parmi les fichiers fournis.")
    if liste_decrets and not decret:
        doc.avertissements.append("Aucun des décrets fournis ne correspond à cet EPN (dénomination/sigle).")

    if doc.ocr:
        for c in tableaux.constats + transverses.constats + (confrontation.constats if confrontation else []):
            if c.nature in ("fiabilite", "coherence") and "[OCR]" not in c.message:
                c.message += NOTE_OCR
    res = ResultatAnalyse(doc, infos, periode, date_limite(periode, parametres), structure, tableaux, transverses,
                          parametres=parametres, decret=decret, confrontation=confrontation, situation=situation,
                          rapprochement=rapprochement)
    annexes = structure["annexes"]
    res.signature = controle_signature(doc, annexes.debut if annexes.trouvee else None)
    res.difficultes = extraire_difficultes_suggestions(doc, structure)
    for code in ("difficultes", "suggestions"):  # nommées dans le titre de la partie, mais sans élément formulé
        det = structure.detections.get(code)
        if det is not None and det.via_parent and not res.difficultes.get(code):
            det.mode, det.debut, det.paragraphes, det.via_parent, det.texte, det.nb_mots = None, None, [], "", "", 0
    _evaluer_canevas(res)
    _evaluer_forme(res)
    _evaluer_fond(res)
    if res.validation_directe:
        _valider(res)
    _rediger(res)
    if not periode.detectee:
        doc.avertissements.append("La période couverte n'a pas pu être détectée : précisez-la (option --periode).")
    return res


# ------------------------------------------------------------------ canevas en vigueur
def _evaluer_canevas(res: ResultatAnalyse) -> None:
    s = res.structure
    marqueurs = [PAR_CODE[c].libelle for c in MARQUEURS_CANEVAS_2023 if c in PAR_CODE and s[c].trouvee]
    texte = res.doc.texte(avec_tableaux=True)
    budget_programme = bool(re.search(r"\b\d{11}\b", texte)) or bool(re.search(r"activit[ée]s?", texte, re.I))
    points = len(marqueurs) + (1 if budget_programme else 0)
    detail = (f"Rubriques propres au canevas 2023 trouvées : {', '.join(marqueurs) or 'aucune'} ; "
              f"présentation par activités (budget-programmes) : {'oui' if budget_programme else 'non'}.")
    if points >= 3:
        res.canevas_en_vigueur = ("Oui", detail)
    elif points >= 1:
        res.canevas_en_vigueur = ("Partiellement", detail)
    else:
        res.canevas_en_vigueur = ("Non – ancien canevas probable", detail)


# ------------------------------------------------------------------ partie II : forme
def _evaluer_forme(res: ResultatAnalyse) -> None:
    s, annuel = res.structure, res.periode.annuel
    lignes: list[LigneForme] = []
    for rub in RUBRIQUES:
        det = s[rub.code]
        if rub.code == "annexes":
            statut = CONFORME if det.trouvee else NON_APPLICABLE
            precision = "Annexes jointes au rapport." if det.trouvee else "Pas d'annexes."
            lignes.append(LigneForme(rub.code, rub.libelle, None, statut, precision, True))
            continue
        if rub.ignoree:
            statut = NON_APPLICABLE
            precision = ("Rubrique non exigée par le canevas paramétré"
                         + (" (présente dans le rapport)." if det.trouvee else "."))
            lignes.append(LigneForme(rub.code, rub.libelle, rub.ligne_forme, statut, precision, rub.hors_grille))
            continue
        if rub.annuel_seulement and not annuel and not det.trouvee:
            statut, precision = NON_APPLICABLE, "Rubrique exigée uniquement dans le rapport annuel."
        elif det.mode == "titre" and det.nb_mots == 0 and not rub.cas_echeant:
            statut = A_VERIFIER if (rub.annuel_seulement and not annuel) else NON_CONFORME
            precision = f"Titre présent (« {det.titre.strip()[:80]} ») mais rubrique non renseignée."
        elif det.mode == "titre":
            statut = CONFORME
            precision = f"Titre trouvé : « {det.titre.strip()[:90]} »."
            if det.nb_mots < rub.mots_min:
                precision += f" Rubrique peu développée ({det.nb_mots} mots)."
            if rub.annuel_seulement and not annuel:
                precision += " (Rubrique facultative hors rapport annuel.)"
        elif det.mode == "texte" and det.via_parent:
            statut = CONFORME
            precision = f"Traitée sous le titre de la partie « {det.via_parent[:90]} »."
        elif det.mode == "texte":
            statut = CONFORME if not rub.titre_requis else A_VERIFIER
            precision = ("Élément traité dans le texte" + ("" if not rub.titre_requis else " sans titre dédié")
                         + f" : « {det.extrait[:120]} »")
        elif rub.cas_echeant:
            statut, precision = A_VERIFIER, "Non mentionné : à renseigner le cas échéant (vérifier si l'EPN est concerné)."
        else:
            statut, precision = NON_CONFORME, "Rubrique absente du rapport."
        manquantes = [e.libelle for e in enfants(rub.code) if not e.ignoree
                      and not s[e.code].trouvee and not e.cas_echeant and not (e.annuel_seulement and not annuel)]
        vides = [e.libelle for e in enfants(rub.code) if not e.ignoree
                 and s[e.code].mode == "titre" and s[e.code].nb_mots == 0 and not e.cas_echeant]
        if vides and statut == CONFORME:
            precision += " Sous-parties non renseignées : " + "; ".join(vides) + "."
            statut = A_VERIFIER
        if manquantes and statut != NON_APPLICABLE:
            precision += " Sous-parties manquantes : " + "; ".join(manquantes) + "."
            if statut == CONFORME and rub.code != "introduction":
                statut = A_VERIFIER
        lignes.append(LigneForme(rub.code, rub.libelle, rub.ligne_forme, statut, precision, rub.hors_grille))

    # Tableaux obligatoires
    for tab in TABLEAUX:
        if tab.ignoree:
            lignes.append(LigneForme(tab.code, f"Tableau {tab.numero} : {tab.libelle}", tab.ligne_forme, NON_APPLICABLE,
                                     "Tableau non exigé par le canevas paramétré."
                                     + (" (Présent dans le rapport.)" if tab.code in res.tableaux.par_code else "")))
            continue
        if tab.code in res.tableaux.par_code:
            t = res.tableaux.par_code[tab.code]
            legende = f" (« {t.bloc.legende[:70]} »)" if t.bloc.legende else " (sans titre/numéro)"
            source = _source_presente(res, t.bloc.index)
            statut = CONFORME if t.bloc.legende and source else A_VERIFIER
            precision = "Tableau présent" + legende + ("" if source else " ; source non indiquée") + "."
            if any(not l.valeurs for l in t.lignes) and all(not l.valeurs for l in t.lignes):
                statut, precision = NON_CONFORME, "Tableau présent mais non renseigné."
        elif tab.code in ("T7", "T8") and _sans_differes(res, tab.code):
            statut, precision = A_VERIFIER, "Tableau absent ; le rapport indique l'absence de " + (
                "différés." if tab.code == "T7" else "rejets.")
        else:
            statut, precision = NON_CONFORME, "Tableau absent du rapport."
        lignes.append(LigneForme(tab.code, f"Tableau {tab.numero} : {tab.libelle}", tab.ligne_forme, statut, precision))

    nb_non_identifies = sum(1 for t in res.tableaux.tableaux if not t.code)
    tabs = [l for l in lignes if l.code.startswith("T") and l.code[1:].isdigit() and l.statut != NON_APPLICABLE]
    manquants = [l.libelle.split(" :")[0] for l in tabs if l.statut == NON_CONFORME]
    plan = plan_modele()
    lignes.append(LigneForme("tableaux", "Présentation des tableaux et annexes", plan.forme.get("tableaux"),
                             NON_CONFORME if manquants else (A_VERIFIER if any(l.statut == A_VERIFIER for l in tabs) else CONFORME),
                             (f"Tableaux manquants ou vides : {', '.join(manquants)}. " if manquants else
                              f"Les {len(tabs)} tableaux exigés par le canevas sont présents. ")
                             + f"{len(res.tableaux.tableaux)} tableau(x) au total dans le rapport"
                             + (f", dont {nb_non_identifies} hors canevas." if nb_non_identifies else ".")))

    statut, precision = res.structure.controle_sommaire()
    lignes.append(LigneForme("sommaire", "Cohérence entre le sommaire et le contenu", plan.forme.get("sommaire"),
                             statut, precision))
    sig_statut, sig_precision, _ = res.signature
    lignes.append(LigneForme("signature", "Le rapport est signé et daté", plan.forme.get("signature"),
                             sig_statut, sig_precision))

    obligatoires = [l for l in lignes if l.code in PAR_CODE and not PAR_CODE[l.code].cas_echeant
                    and (not PAR_CODE[l.code].hors_grille or PAR_CODE[l.code].perso) and not PAR_CODE[l.code].ignoree]
    absentes = [l.libelle for l in obligatoires if l.statut == NON_CONFORME]
    a_verifier = [l.libelle for l in obligatoires if l.statut == A_VERIFIER]
    lignes.insert(0, LigneForme(
        "global_forme", "Présence de toutes les parties et sous-parties obligatoires du rapport",
        plan.forme.get("global_forme"),
        NON_CONFORME if absentes else (A_VERIFIER if a_verifier else CONFORME),
        (f"{len(absentes)} rubrique(s) obligatoire(s) absente(s) : {'; '.join(absentes)}." if absentes else
         "Toutes les rubriques obligatoires sont présentes.")
        + (f" À vérifier : {'; '.join(a_verifier)}." if a_verifier else "")))
    res.forme = lignes


def _source_presente(res: ResultatAnalyse, index: int) -> bool:
    for b in res.doc.blocs[index + 1:index + 3]:
        if b.type == "p" and re.match(r"^\s*source", b.norm):
            return True
        if b.type == "tableau":
            break
    return False


def _sans_differes(res: ResultatAnalyse, code: str) -> bool:
    texte = res.structure.texte_section("differes_rejets")
    mot = "differe" if code == "T7" else "rejet"
    from .texte import normaliser
    return bool(re.search(rf"(aucun|pas d.|neant|ni)\s*(\w+\s){{0,3}}{mot}", normaliser(texte)))


# ------------------------------------------------------------------ partie III : fond
def _evaluer_fond(res: ResultatAnalyse) -> None:
    s, t, tr, annuel = res.structure, res.tableaux, res.transverses, res.periode.annuel
    lignes: list[LigneFond] = []

    def constats_de(codes_tab=(), rubriques=(), nature=None):
        noms = {t.par_code[c].nom for c in codes_tab if c in t.par_code}
        return [c for c in res.constats if (c.tableau in noms or c.rubrique in rubriques)
                and (nature is None or c.nature == nature)]

    def statut_tableaux(codes, nature, rub_code=None):
        presents = [c for c in codes if c in t.par_code]
        if not presents:
            return None, []
        # constats des tableaux du canevas + des autres tableaux du rapport rattachés à la rubrique
        cs = constats_de(presents, rubriques=(rub_code,) if rub_code else (), nature=nature)
        cs = [c for c in cs if c.nature == nature and not c.controle.startswith("Concordance")]
        return (len(cs) == 0), cs

    regles_tableaux = {
        "pres_generale": (("T1", "T2"),),
        "pres_ressources": (("T3",),),
        "pres_emplois": (("T4",),),
        "exec_recettes": (("T5",),),
        "exec_depenses": (("T6",),),
        "differes_rejets": (("T7", "T8"),),
    }

    for rub in RUBRIQUES:
        if rub.ligne_fond is None:
            continue
        det = s[rub.code]
        extrait = f" Extrait : « {det.extrait[:160]} »" if det.trouvee and det.texte else ""
        if rub.ignoree:
            lignes.append(LigneFond(rub.code, rub.libelle, rub.ligne_fond, SANS_OBJET, SANS_OBJET,
                                    "Rubrique non exigée par le canevas paramétré."))
            continue
        if rub.annuel_seulement and not annuel and not det.trouvee:
            lignes.append(LigneFond(rub.code, rub.libelle, rub.ligne_fond, SANS_OBJET, SANS_OBJET,
                                    "Rubrique propre au rapport annuel."))
            continue
        if det.mode == "titre" and det.nb_mots == 0:
            v = A_APPRECIER if rub.cas_echeant or (rub.annuel_seulement and not annuel) else NON_RENSEIGNE
            lignes.append(LigneFond(rub.code, rub.libelle, rub.ligne_fond, v, v,
                                    "Titre présent mais aucun contenu : fond non appréciable."))
            continue
        if not det.trouvee:
            com = ("Non mentionné (le cas échéant)." if rub.cas_echeant else "Rubrique absente : fond non appréciable.")
            v = A_APPRECIER if rub.cas_echeant else NON_RENSEIGNE
            lignes.append(LigneFond(rub.code, rub.libelle, rub.ligne_fond, v, v, com))
            continue

        fiab, coh, com = A_APPRECIER, A_APPRECIER, f"Rubrique renseignée ({det.nb_mots} mots).{extrait}"
        if rub.code in regles_tableaux:
            codes = regles_tableaux[rub.code][0]
            ok_f, cs_f = statut_tableaux(codes, "fiabilite", rub.code)
            cs_c = constats_de(codes, rubriques=(rub.code,), nature="coherence")
            if ok_f is None:
                fiab, com = A_APPRECIER, "Tableau(x) " + "/".join(c[1] for c in codes) + " absent(s) : calculs non vérifiables."
            else:
                fiab = FIABLE if ok_f else NON_FIABLE
                com = ("Calculs des tableaux vérifiés sans anomalie." if ok_f else
                       f"{len(cs_f)} anomalie(s) de calcul : " + " | ".join(_court(c) for c in cs_f[:3])
                       + (" | …" if len(cs_f) > 3 else ""))
            if ok_f is not None or cs_c:
                coh = COHERENT if not cs_c else INCOHERENT
                if cs_c:
                    com += " Cohérence : " + " | ".join(_court(c) for c in cs_c[:3])
                else:
                    com += " Concordance avec les autres tableaux et le texte vérifiée."
            if det.nb_mots < rub.mots_min:
                com += f" Commentaire du CB très succinct ({det.nb_mots} mots)."
        elif rub.code == "resultat_budgetaire":
            r = tr.resultat
            if r:
                cs = [c for c in tr.constats if c.rubrique == "resultat_budgetaire"]
                maj = [c for c in cs if c.gravite == "Majeure"]
                fiab = FIABLE if r.get("montant_retrouve") else A_APPRECIER
                coh = INCOHERENT if maj else (COHERENT if r.get("sens_cite") or r.get("montant_retrouve") else A_APPRECIER)
                com = (f"Résultat recalculé (recouvrements − ordonnancements) : {r['resultat']:,.0f} ({r['sens']}).".replace(",", " ")
                       + (" " + " | ".join(_court(c) for c in cs) if cs else ""))
            else:
                com = "Tableaux d'exécution (T5/T6) absents ou incomplets : résultat non recalculable." + extrait
        elif rub.code == "ratios":
            calcules = [r for r in tr.ratios if r.calcule]
            cites = [r for r in tr.ratios if r.cite is not None]
            incoh = [r for r in tr.ratios if r.coherent is False]
            if cites and calcules:
                coh = INCOHERENT if incoh else COHERENT
                fiab = NON_FIABLE if incoh else FIABLE
            com = (f"Ratios cités : {', '.join(r.code for r in cites) or 'aucun'} ; "
                   f"ratios recalculables : {', '.join(r.code for r in calcules) or 'aucun'}."
                   + (" Écarts : " + ", ".join(r.code for r in incoh) + "." if incoh else "")
                   + " Voir l'onglet « Ratios ».")
        elif rub.code == "texte_creation":
            ok = tr.texte_creation_verifie()
            if ok is not None:
                fiab = FIABLE if ok else NON_FIABLE
                com = ("Texte de création conforme au référentiel des EPN." if ok else
                       "Texte de création non conforme au référentiel des EPN.") + extrait
        elif det.nb_mots < rub.mots_min:
            com = f"Rubrique présente mais très peu développée ({det.nb_mots} mots).{extrait}"
        if rub.code not in regles_tableaux and rub.code not in ("resultat_budgetaire", "ratios"):
            propres = [c for c in res.constats if c.rubrique == rub.code and c.gravite != "Information"
                       and not c.controle.startswith("Texte de création")]
            if any(c.nature == "coherence" for c in propres):
                coh = INCOHERENT
            if any(c.nature == "fiabilite" for c in propres):
                fiab = NON_FIABLE
        fiab, coh, com = _references(res, rub.code, fiab, coh, com)
        if res.doc.ocr and (fiab in (NON_FIABLE,) or coh in (INCOHERENT,)):
            com += " (Document scanné lu par OCR : confirmer les chiffres sur l'original. Détail : onglet « Contrôles automatiques ».)"
        lignes.append(LigneFond(rub.code, rub.libelle, rub.ligne_fond, fiab, coh, com))

    # Lignes de regroupement (Introduction, Présentation du budget, …) : synthèse des sous-rubriques
    par_code = {l.code: l for l in lignes}
    for l in lignes:
        filles = [par_code[e.code] for e in enfants(l.code) if e.code in par_code]
        if not filles:
            continue
        for attr, ko, ok in (("fiabilite", NON_FIABLE, FIABLE), ("coherence", INCOHERENT, COHERENT)):
            valeurs = [getattr(f, attr) for f in filles] + [getattr(l, attr)]
            if ko in valeurs:
                setattr(l, attr, ko)
            elif all(v in (ok, SANS_OBJET) for v in valeurs[:-1]) and any(v == ok for v in valeurs[:-1]):
                setattr(l, attr, ok)
    tous = [l for l in lignes]
    nb_ko = sum(1 for l in tous if NON_FIABLE in (l.fiabilite,) or INCOHERENT in (l.coherence,))
    nb_abs = sum(1 for l in tous if l.fiabilite == NON_RENSEIGNE)
    lignes.insert(0, LigneFond(
        "global_fond", "Présence de toutes les parties et sous-parties obligatoires du rapport",
        plan_modele().fond.get("global_fond"),
        NON_FIABLE if any(l.fiabilite == NON_FIABLE for l in tous) else A_APPRECIER,
        INCOHERENT if any(l.coherence == INCOHERENT for l in tous) else A_APPRECIER,
        f"{nb_ko} rubrique(s) présentant des anomalies de fiabilité ou de cohérence ; {nb_abs} rubrique(s) non renseignée(s)."))
    res.fond = lignes


def _rediger(res: ResultatAnalyse) -> None:
    """Commentaires rédigés en phrases simples, affichés dans le fichier d'analyse."""
    from .commentaires import commentaire_fond, commentaire_forme
    for l in res.forme:
        l.redige = commentaire_forme(l, res)
    from .thematiques import analyser_rubriques, commentaire_fond as synthese
    try:
        rubs = analyser_rubriques(res)
    except Exception:  # la synthèse ne doit jamais empêcher l'analyse
        rubs = None
    for l in res.fond:
        l.redige = commentaire_fond(l, res)
        t = synthese(l.code, res, rubs) if rubs is not None and l.fiabilite != SANS_OBJET else None
        if t:
            l.redige = _fusionner(t, l.redige)
    res.thematiques = rubs


def _fusionner(synthese: str, commentaire: str) -> str:
    """Synthèse de ce que dit le rapport, suivie des constats de contrôle (sans les citations ni les mentions
    d'absence déjà couvertes par la synthèse)."""
    restes = [ph for ph in re.split(r"(?<=[.»])\s+(?=[A-ZÀ-Ý])", commentaire or "")
              if ph.strip() and not re.search(r"Le CB y indique|Rubrique absente|Sous-rubriques? absentes?|aucune session du "
                                              r"Conseil de gestion|Aucune session du Conseil de gestion|le contenu ne peut",
                                              ph)]
    return " ".join([synthese] + restes)


def _valider(res: ResultatAnalyse) -> None:
    """Validation directe : les statuts provisoires (« À vérifier », « À apprécier ») sont tranchés."""
    s = res.structure
    for l in res.forme:
        if l.statut != A_VERIFIER:
            continue
        rub = PAR_CODE.get(l.code)
        if rub and rub.cas_echeant and not s[rub.code].trouvee:
            l.statut = NON_APPLICABLE
            l.precision = "Non mentionné ; l'établissement n'est pas réputé concerné."
        elif rub and rub.niveau == 1 and s[rub.code].trouvee and s[rub.code].nb_mots > 0:
            l.statut = CONFORME  # partie présente ; les sous-rubriques manquantes sont notées sur leurs propres lignes
        elif rub and rub.annuel_seulement and not res.periode.annuel:
            l.statut = NON_APPLICABLE
        else:
            l.statut = NON_CONFORME
    for l in res.fond:
        if A_APPRECIER not in (l.fiabilite, l.coherence):
            continue
        rub = PAR_CODE.get(l.code)
        det = s.detections.get(l.code)
        renseignee = bool(det and det.trouvee and det.nb_mots > 0)
        if rub and not renseignee and (rub.cas_echeant or (rub.annuel_seulement and not res.periode.annuel)):
            l.fiabilite = l.coherence = SANS_OBJET
            l.commentaire = "Rubrique sans objet pour cet établissement ou pour cette période."
            continue
        if l.code == "global_fond" or renseignee:
            if l.fiabilite == A_APPRECIER:
                l.fiabilite = FIABLE
            if l.coherence == A_APPRECIER:
                l.coherence = COHERENT
            if renseignee and "anomalie" not in l.commentaire.lower() and not l.commentaire.startswith("Décret – "):
                l.commentaire = "Aucune anomalie relevée. " + l.commentaire
        else:
            l.fiabilite = NON_RENSEIGNE if l.fiabilite == A_APPRECIER else l.fiabilite
            l.coherence = NON_RENSEIGNE if l.coherence == A_APPRECIER else l.coherence
    if res.confrontation:  # points du décret laissés « À vérifier » : simples constats
        from .decret import A_VERIFIER as D_A_VERIFIER, INFO
        for p in res.confrontation.points:
            if p.statut == D_A_VERIFIER:
                p.statut = INFO
    # La ligne de synthèse reflète les lignes de détail
    glob = next((l for l in res.fond if l.code == "global_fond"), None)
    if glob:
        autres = [l for l in res.fond if l is not glob]
        glob.fiabilite = NON_FIABLE if any(l.fiabilite == NON_FIABLE for l in autres) else FIABLE
        glob.coherence = INCOHERENT if any(l.coherence == INCOHERENT for l in autres) else COHERENT
    for l in res.forme:  # ligne de synthèse de la forme
        if l.code == "global_forme":
            if l.statut == A_VERIFIER:
                l.statut = CONFORME
            l.precision = re.sub(r"\s*À vérifier : .*$", "", l.precision)


def _references(res: ResultatAnalyse, code: str, fiab: str, coh: str, com: str) -> tuple[str, str, str]:
    """Complète l'appréciation du fond avec le décret de création et la situation d'exécution."""
    conf = res.confrontation
    if conf:
        st = conf.statut(code)
        if st is not None:
            if code == "texte_creation":
                fiab = NON_FIABLE if st == D_ECART else (fiab if fiab == NON_FIABLE else FIABLE)
                coh = INCOHERENT if st == D_ECART else COHERENT
            else:
                coh = INCOHERENT if st == D_ECART else (coh if coh == INCOHERENT else COHERENT)
        if conf.commentaire(code):
            com = f"Décret – {conf.commentaire(code)} " + com
    rap = res.rapprochement
    if rap:
        ecarts = [c for c in rap.constats if c.rubrique == code and c.nature == "fiabilite" and c.gravite != "Information"]
        lignes = {"exec_recettes": ("T5",), "exec_depenses": ("T6",), "pres_ressources": ("T3",),
                  "pres_emplois": ("T4",), "resultat_budgetaire": ("",)}.get(code)
        if ecarts:
            fiab = NON_FIABLE
            com += " Situation d'exécution – écart(s) : " + " | ".join(_court(c, 200) for c in ecarts[:3])
        elif lignes is not None:
            noms = {res.tableaux.par_code[c].nom for c in lignes if c in res.tableaux.par_code} | ({"Rapport"} if "" in lignes else set())
            ok = [l for l in rap.lignes if l.tableau in noms and l.statut == "Concordant"]
            if ok:
                fiab = FIABLE if fiab in (FIABLE, A_APPRECIER) else fiab
                com += f" Montants concordants avec la situation d'exécution ({len(ok)} agrégat(s) rapproché(s))."
    return fiab, coh, com.strip()


def parse_infos(epn=None, controleur=None, charge=None, reception=None, periode=None) -> InfosRapport:
    return InfosRapport(epn or "", controleur or "", charge or "", lire_date(reception), periode)
