"""Référentiel des rubriques du canevas de rédaction du rapport du Contrôleur Budgétaire.

Source : canevas institué par la note n°0580/MBPE/DGBF/DCB du 26 juillet 2023
(Direction du Contrôle Budgétaire), en application du décret n°2021-677 du 03 novembre 2021.

Chaque rubrique indique :
- les expressions qui permettent de la reconnaître dans un titre (`titres`) ;
- les expressions qui permettent de la reconnaître dans le corps du texte (`contenu`),
  lorsqu'une rubrique n'a pas forcément de titre dédié (ex. « Texte de création ») ;
- la ligne correspondante du fichier d'analyse Excel (partie II « forme » et III « fond ») du modèle de la DCB.

Ce canevas par défaut peut être adapté dans les Paramètres de l'application (fichier canevas.json du profil de
l'utilisateur) : libellés, intitulés reconnus, exigence (obligatoire, le cas échéant, rapport annuel seulement, non
exigée), volume minimal, rubriques ajoutées. `actualiser()` reconstruit alors, en place, RUBRIQUES, PAR_CODE, TABLEAUX
et TABLEAU_PAR_CODE, et rattache chaque rubrique à sa ligne du modèle de fichier d'analyse en vigueur.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace

from .ressources import dossier_utilisateur
from .texte import normaliser


@dataclass(frozen=True)
class Rubrique:
    code: str
    libelle: str
    niveau: int  # 1 = partie, 2 = sous-partie, 3 = élément
    parent: str | None = None
    titres: tuple[str, ...] = ()
    contenu: tuple[str, ...] = ()
    titre_requis: bool = True  # le canevas prévoit un titre dédié
    cas_echeant: bool = False  # « le cas échéant » / « s'il existe »
    annuel_seulement: bool = False
    ligne_forme: int | None = None  # ligne du fichier Excel, partie II
    mots_min: int = 15  # en dessous : rubrique jugée trop peu développée
    hors_grille: bool = False  # rubrique absente de la grille du modèle de fichier d'analyse
    ligne_fond: int | None = -1  # ligne de la partie III ; -1 : déduite de ligne_forme (grille de la DCB)
    ignoree: bool = False  # « non exigée » dans les Paramètres : rubrique non contrôlée
    perso: bool = False  # rubrique ajoutée dans les Paramètres
    intitules: tuple[str, ...] = ()  # intitulés ajoutés dans les Paramètres (texte simple)
    apres: str | None = None  # partie ajoutée : placée après cette partie (sinon avant la conclusion)

    def __post_init__(self):
        if self.ligne_fond == -1:
            object.__setattr__(self, "ligne_fond", self.ligne_forme + 61
                               if self.ligne_forme is not None and self.ligne_forme <= 62 else None)


R = Rubrique
DEFAUT_RUBRIQUES: list[Rubrique] = [
    # ------------------------------------------------------------------ INTRODUCTION
    R("introduction", "Introduction", 1, titres=(r"^\W*introduction\b",), ligne_forme=23, mots_min=60),
    R("texte_creation", "Texte de création", 3, "introduction",
      titres=(r"texte (de|portant) creation", r"cadre (juridique|institutionnel)", r"statut juridique",
              r"historique"),
      contenu=(r"\b(decret|loi|ordonnance|arrete)\b[^.\n]{0,40}\b(19|20)\d\d\s*-\s*\d+",
               r"\b(cree|creee|institue|instituee|erige|erigee)\b[^.\n]{0,40}\b(par|suivant|selon)\b[^.\n]{0,20}\b(decret|loi|ordonnance)"),
      titre_requis=False, ligne_forme=24, mots_min=5),
    R("missions", "Rappel des missions", 3, "introduction",
      titres=(r"\bmissions?\b",),
      contenu=(r"\b(a|ont|avait) pour missions?\b", r"\bmissions? (de l|du|principales?|assi.nees?|confiees?|devolues?)\b", r"\bles missions\b",
               r"\best charge(e)? de\b"),
      titre_requis=False, ligne_forme=25, mots_min=8),
    R("antennes", "Nombre d'antennes et lieu d'installation", 3, "introduction",
      titres=(r"\bantennes?\b", r"lieux? d.installation", r"implantations?"),
      contenu=(r"\bantennes?\b", r"\b(sites|localites)\b", r"\bdirections? regionales?\b", r"\bdelegations? regionales?\b",
               r"\bimplantee?s?\b", r"\bagences? regionales?\b", r"\bsiege (social )?(est )?(situe|sis|base)"),
      titre_requis=False, cas_echeant=True, ligne_forme=26, mots_min=5),
    R("financement", "Mode de financement de l'EPN", 3, "introduction",
      titres=(r"mode de financement", r"\bfinancement\b",),
      contenu=(r"\bfinance(e|s)? (par|au moyen|grace)", r"\bsubventions? (de l.etat|du budget)",
               r"\bressources (propres|de l.epn) (proviennent|sont constituees)", r"\bressources? (de l.etablissement|de l.epn) (proviennent|sont|se composent)"),
      titre_requis=False, ligne_forme=27, mots_min=8),
    R("organisation", "Organisation et effectif de l'EPN", 3, "introduction",
      titres=(r"\borganisation\b", r"\borganigramme\b", r"\beffectifs?\b", r"^(les )?organes\b"),
      contenu=(r"\beffectif\b", r"\borganigramme\b", r"\b\d+\s+(agents|salaries|employes|fonctionnaires)\b",
               r"\b(est|sont) (organise|structure)e?s?\b"),
      titre_requis=False, ligne_forme=28, mots_min=8),
    R("plan_strategique", "Présentation du plan stratégique de l'EPN", 3, "introduction",
      titres=(r"plan strategique",), contenu=(r"plan strategique",),
      titre_requis=False, cas_echeant=True, ligne_forme=29, mots_min=5),
    R("paa", "Présentation du Programme Annuel d'Activités", 3, "introduction",
      titres=(r"programme annuel d.activites", r"\bpaa\b", r"plan de travail annuel", r"\bptba?\b"),
      contenu=(r"programme annuel d.activites", r"\bpaa\b", r"plan de travail annuel", r"\bptba?\b",
               r"programme d.activites"),
      titre_requis=False, cas_echeant=True, ligne_forme=30, mots_min=5),
    R("justification", "Justification de la rédaction du rapport (exigence légale)", 3, "introduction",
      contenu=(r"article 6[46]", r"decret n.?\s*2021\s*-\s*677", r"\bloi n.?\s*2020\s*-\s*627",
               r"(exigence|obligation|disposition)s? (legale|reglementaire)", r"conformement aux dispositions"),
      titre_requis=False, hors_grille=True, mots_min=0),
    R("annonce_plan", "Annonce du plan", 3, "introduction",
      contenu=(r"(s.articule|articule|structure|organise|subdivise|divise)\w*\s+(autour|en|comme suit|selon)",
               r"(le present|ce) rapport (comprend|presente|aborde|traite|comporte)",
               r"(abordera|presentera|traitera) (successivement|tour a tour|d.abord)"),
      titre_requis=False, hors_grille=True, mots_min=0),

    # ------------------------------------------------------------------ I. PRESENTATION DU BUDGET
    R("presentation_budget", "Présentation du budget", 1, titres=(r"presentation (generale )?du budget",),
      ligne_forme=31, mots_min=40),
    R("pres_generale", "Présentation générale", 2, "presentation_budget",
      titres=(r"presentation .en.rale", r"^presentation du budget( de l.epn| global)?$"),
      ligne_forme=32),
    R("pres_ressources", "Présentation des Ressources", 2, "presentation_budget",
      titres=(r"presentation des ressources", r"^\W*(i\.?\s*2\W*)?(les )?ressources\b",
              r"presentation .{0,30}(nature|sources?) de (recettes|ressources|financement)"), ligne_forme=33),
    R("pres_emplois", "Présentation des Emplois", 2, "presentation_budget",
      titres=(r"presentation des (emplois|depenses|charges)", r"^\W*(i\.?\s*3\W*)?(les )?emplois\b",
              r"presentation .{0,30}nature de depenses?"),
      ligne_forme=34),

    # ------------------------------------------------------------------ II. ANALYSE DE L'EXECUTION
    R("analyse_execution", "Analyse de l'exécution du budget", 1,
      titres=(r"analyse de l.execution (du budget|budgetaire)", r"execution du budget$"), ligne_forme=35,
      mots_min=40),
    R("exec_recettes", "Situation d'exécution du budget en recettes", 2, "analyse_execution",
      titres=(r"execution (du bud\w* )?(en |des )recettes", r"execution des ressources",
              r"situation .{0,40}recettes", r"mobilisation des (recettes|ressources)"), ligne_forme=36),
    R("exec_depenses", "Situation d'exécution du budget en dépenses", 2, "analyse_execution",
      titres=(r"execution (du bud\w* )?(en |des )depenses", r"execution des (emplois|charges)",
              r"situation .{0,40}depenses"), ligne_forme=37),
    R("differes_rejets", "Analyse des différés et rejets", 2, "analyse_execution",
      titres=(r"differes", r"\brejets?\b"), ligne_forme=38),
    R("resultat_budgetaire", "Analyse du résultat budgétaire", 2, "analyse_execution",
      titres=(r"resultat budgetaire",), ligne_forme=39),
    R("ratios", "Analyse des ratios de gestion", 2, "analyse_execution",
      titres=(r"\bratios?\b",), ligne_forme=40),

    # ------------------------------------------------------------------ III. PERFORMANCE (canevas 2023)
    R("performance", "Analyse de la performance", 1,
      titres=(r"analyse de la performance", r"\bperformance\b"), hors_grille=True, mots_min=30),
    R("programme_activites", "Programme d'activités", 2, "performance",
      titres=(r"programme d.activites?", r"plan d.action"), hors_grille=True),
    R("evaluation_activites", "Évaluation de la réalisation des activités", 2, "performance",
      titres=(r"evaluation de la realisation", r"realisation des activites", r"niveau de realisation"),
      hors_grille=True),

    # ------------------------------------------------------------------ IV. GESTION FINANCIERE
    R("gestion_financiere", "Analyse de la gestion financière", 1, titres=(r"gestion financiere",),
      annuel_seulement=True, ligne_forme=42, mots_min=30),
    R("solde_tresorerie", "Solde de trésorerie", 2, "gestion_financiere",
      titres=(r"soldes? de tresorerie", r"disponibilites"), annuel_seulement=True, ligne_forme=43, mots_min=8),
    R("creances", "Créances", 2, "gestion_financiere", titres=(r"\bcreances\b", r"restes? a recouvrer"),
      annuel_seulement=True, ligne_forme=44, mots_min=8),
    R("dettes", "Dettes", 2, "gestion_financiere", titres=(r"\bdettes\b", r"restes? a payer"),
      annuel_seulement=True, ligne_forme=45, mots_min=8),
    R("provisions", "Provisions", 2, "gestion_financiere", titres=(r"\bprovisions?\b",),
      annuel_seulement=True, ligne_forme=46, mots_min=8),
    R("snt", "Situation Nette de Trésorerie (SNT)", 2, "gestion_financiere",
      titres=(r"situation nette de tresorerie", r"\bsnt\b"), annuel_seulement=True, hors_grille=True,
      mots_min=8),

    # ------------------------------------------------------------------ V. DISPOSITIFS DE CONTROLE
    R("dispositifs_controle", "Évaluation des dispositifs de contrôle", 1,
      titres=(r"dispositifs? de controle", r"evaluation des (dispositifs|controles)"), ligne_forme=47,
      mots_min=30),
    R("controle_interne", "Contrôle interne budgétaire", 2, "dispositifs_controle",
      titres=(r"controle interne",), ligne_forme=48),
    R("controle_gestion", "Contrôle de gestion", 2, "dispositifs_controle",
      titres=(r"controle de .estion", r"suivi.evaluation"), ligne_forme=49),

    # ------------------------------------------------------------------ VI. PATRIMOINE
    R("patrimoine", "Situation du patrimoine", 1, titres=(r"\bpatrimoine\b",), ligne_forme=50, mots_min=30),
    R("patrimoine_existant", "État du patrimoine existant", 3, "patrimoine",
      titres=(r"etat du patrimoine", r"patrimoine existant"),
      contenu=(r"\b(immeubles?|batiments?|vehicules?|mobiliers?|materiels?)\b",
               r"patrimoine .{0,60}(se presente|comprend|se compose|est compose|voir annexe)"), titre_requis=False,
      ligne_forme=51, mots_min=5),
    R("acquisitions", "Point des nouvelles acquisitions", 3, "patrimoine",
      titres=(r"acquisitions?",), contenu=(r"\b(acquisitions?|acquis|achat de|achete)",), titre_requis=False,
      ligne_forme=52, mots_min=5),
    R("compta_matieres", "Point de la mise en œuvre de la comptabilité des matières", 3, "patrimoine",
      titres=(r"comptabilite (des |de )?matieres",), contenu=(r"comptabilite (des |de )?matieres",
                                                              r"comptable (des |de )?matieres"),
      titre_requis=False, ligne_forme=53, mots_min=5),

    # ------------------------------------------------------------------ VII. GOUVERNANCE
    R("gouvernance", "Situation de la gouvernance de l'EPN", 1, titres=(r"gouvernance",), ligne_forme=54,
      mots_min=30),
    R("coges", "COGES / Organes de supervision (Conseil de gestion)", 2, "gouvernance",
      titres=(r"\bcoges\b", r"conseil de gestion", r"or\w{1,3}anes? de (supervision|\w{0,2}ouvernance)",
              r"conseil d.administration"),
      contenu=(r"\bcoges\b", r"conseil de gestion", r"conseil d.administration"), ligne_forme=55),
    R("comite_tresorerie", "Comité de trésorerie", 2, "gouvernance", titres=(r"comite de tresorerie",),
      contenu=(r"comite de tresorerie",), ligne_forme=56),

    # ------------------------------------------------------------------ VIII / IX (canevas 2023)
    R("risques", "Analyse de la gestion des risques", 1, titres=(r"gestion des risques", r"\brisques\b"),
      hors_grille=True, mots_min=20),
    R("autres_points", "Autres points", 1, titres=(r"autres points",), hors_grille=True, cas_echeant=True,
      mots_min=0),

    # ------------------------------------------------------------------ X. DIFFICULTES ET SUGGESTIONS
    R("difficultes_suggestions", "Difficultés et suggestions", 1,
      titres=(r"difficultes et (suggestions|recommandations|propositions)", r"difficultes", r"contraintes"),
      ligne_forme=57, mots_min=20),
    R("difficultes", "Difficultés", 2, "difficultes_suggestions",
      titres=(r"difficultes", r"contraintes"), ligne_forme=58, mots_min=8),
    R("suggestions", "Suggestions", 2, "difficultes_suggestions",
      titres=(r"suggestions", r"recommandations", r"propositions"), ligne_forme=59, mots_min=8),
    R("autres_suggestions", "Autres suggestions", 2, "difficultes_suggestions",
      titres=(r"autres suggestions",), hors_grille=True, cas_echeant=True, mots_min=0),

    # ------------------------------------------------------------------ CONCLUSION
    R("conclusion", "Conclusion", 1, titres=(r"^\W*conclusion",), ligne_forme=60, mots_min=40),
    # Les annexes marquent la fin du corps du rapport (elles ne doivent pas être lues comme la conclusion).
    R("annexes", "Annexes", 1, titres=(r"^\W*an+exes?\b",), hors_grille=True, cas_echeant=True, mots_min=0),
    R("obs_generales", "Observations générales sur la gestion", 3, "conclusion",
      contenu=(r"regularite", r"concordance", r"observations?", r"(globalement|dans l.ensemble)",
               r"taux (d.execution|de realisation|de recouvrement)"),
      titre_requis=False, ligne_forme=61, mots_min=0),
    R("obs_delais", "Observations sur les délais de production des rapports de l'Ordonnateur et de l'Agent Comptable",
      3, "conclusion",
      contenu=(r"(rapport de gestion|compte financier)", r"\b(ordonnateur|agent comptable)\b[^.]{0,120}"
               r"\b(delai|transmis|produit|depose|recu)", r"\b(delai|transmis|produit|depose|recu)[^.]{0,120}"
               r"\b(ordonnateur|agent comptable|compte financier)"),
      titre_requis=False, annuel_seulement=True, ligne_forme=62, mots_min=0),
]

RUBRIQUES: list[Rubrique] = list(DEFAUT_RUBRIQUES)  # canevas en vigueur (voir actualiser)
PAR_CODE: dict[str, Rubrique] = {r.code: r for r in RUBRIQUES}


def enfants(code: str) -> list[Rubrique]:
    return [r for r in RUBRIQUES if r.parent == code]


# Tableaux obligatoires du canevas (numérotation du canevas 2023) et ligne de la grille Excel.
# NB : la grille Excel inverse les libellés des tableaux 1 et 2 par rapport au canevas ; on
# rattache chaque tableau à la ligne de la grille qui porte le même contenu.
@dataclass(frozen=True)
class TableauCanevas:
    code: str
    numero: int
    libelle: str
    ligne_forme: int | None
    rubrique: str
    ignoree: bool = False  # « non exigé » dans les Paramètres


DEFAUT_TABLEAUX: list[TableauCanevas] = [
    TableauCanevas("T1", 1, "Budget de l'année considérée comparé à celui de l'année précédente", 66,
                   "pres_generale"),
    TableauCanevas("T2", 2, "Budgets des trois derniers exercices", 65, "pres_generale"),
    TableauCanevas("T3", 3, "Présentation des ressources par nature économique", 67, "pres_ressources"),
    TableauCanevas("T4", 4, "Présentation des emplois par nature de dépenses et par activité", 68,
                   "pres_emplois"),
    TableauCanevas("T5", 5, "Exécution du budget en recettes", 69, "exec_recettes"),
    TableauCanevas("T6", 6, "Exécution du budget en dépenses", 70, "exec_depenses"),
    TableauCanevas("T7", 7, "Principaux motifs des différés", 71, "differes_rejets"),
    TableauCanevas("T8", 8, "Principaux motifs des rejets", 72, "differes_rejets"),
]
TABLEAUX: list[TableauCanevas] = list(DEFAUT_TABLEAUX)
TABLEAU_PAR_CODE = {t.code: t for t in TABLEAUX}

# Rubriques propres au canevas 2023 (budget-programmes) : leur présence indique que le CB
# utilise bien la dernière version du canevas.
MARQUEURS_CANEVAS_2023 = ("performance", "risques", "snt")


# ------------------------------------------------------------------ canevas paramétrable
REFERENCE_DEFAUT = "note n°0580/MBPE/DGBF/DCB du 26 juillet 2023"
EXIGENCES = (("obligatoire", "Obligatoire"), ("cas_echeant", "Le cas échéant"), ("annuel", "Rapport annuel seulement"),
             ("non_exigee", "Non exigée"))
EXIGENCES_TABLEAUX = (("obligatoire", "Obligatoire"), ("non_exigee", "Non exigé"))
FICHIER_CANEVAS = "canevas.json"
_ETAT: dict = {"cle": None, "reference": REFERENCE_DEFAUT, "plan": None}


def exigence(r: Rubrique) -> str:
    if r.ignoree:
        return "non_exigee"
    if r.annuel_seulement:
        return "annuel"
    return "cas_echeant" if r.cas_echeant else "obligatoire"


def motif_intitule(texte: str) -> str:
    """Intitulé saisi en texte simple → motif cherché dans les titres normalisés du rapport."""
    n = normaliser(texte)
    n = re.sub(r"^[^a-z0-9]+", "", n)
    n = re.sub(r"^((\d+(\.\d+)*|[ivx]+)\s*[.\-)]\s*)", "", n).strip()
    return re.escape(n).replace("\\ ", "\\s+").replace("'", ".") if n else ""


def chemin_config():
    return dossier_utilisateur() / FICHIER_CANEVAS


def lire_config() -> dict:
    try:
        cfg = json.loads(chemin_config().read_text(encoding="utf-8"))
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}


def _modifier(r: Rubrique, m: dict) -> Rubrique:
    ch: dict = {}
    libelle = str(m.get("libelle") or "").strip()
    intitules = tuple(str(i).strip() for i in (m.get("intitules") or []) if str(i).strip())
    titres = r.titres + tuple(x for x in (motif_intitule(i) for i in intitules) if x)
    if libelle and libelle != r.libelle:
        ch["libelle"] = libelle
        titres += tuple(x for x in (motif_intitule(libelle),) if x)
    if titres != r.titres:
        ch["titres"] = titres
    if intitules:
        ch["intitules"] = intitules
    if isinstance(m.get("mots_min"), int):
        ch["mots_min"] = m["mots_min"]
    if isinstance(m.get("titre_requis"), bool):
        ch["titre_requis"] = m["titre_requis"]
    ex = m.get("exigence")
    if ex in dict(EXIGENCES) and ex != exigence(r):
        ch.update(cas_echeant=ex == "cas_echeant", annuel_seulement=ex == "annuel", ignoree=ex == "non_exigee")
    return replace(r, **ch) if ch else r


def construire(cfg: dict) -> tuple[list[Rubrique], list[TableauCanevas]]:
    """Canevas par défaut modifié par la configuration (sans les lignes du modèle)."""
    mods = cfg.get("rubriques") or {}
    rubs = [_modifier(r, mods.get(r.code) or {}) for r in DEFAUT_RUBRIQUES]
    for a in cfg.get("ajouts") or []:
        libelle = str(a.get("libelle") or "").strip()
        code = str(a.get("code") or "")
        if not libelle or not code.startswith("perso_") or any(r.code == code for r in rubs):
            continue
        parent = a.get("parent") or None
        if parent and not any(r.code == parent and r.niveau == 1 for r in rubs):
            parent = None
        intitules = tuple(str(i).strip() for i in (a.get("intitules") or []) if str(i).strip())
        titres = tuple(x for x in (motif_intitule(t) for t in (libelle,) + intitules) if x)
        ex = a.get("exigence") if a.get("exigence") in dict(EXIGENCES) else "obligatoire"
        r = Rubrique(code, libelle, 2 if parent else 1, parent, titres=titres, titre_requis=True,
                     cas_echeant=ex == "cas_echeant", annuel_seulement=ex == "annuel", ignoree=ex == "non_exigee",
                     ligne_forme=None, ligne_fond=None, hors_grille=True, perso=True, intitules=intitules,
                     mots_min=int(a.get("mots_min") if isinstance(a.get("mots_min"), int) else 10))
        apres = a.get("apres") if not parent and any(x.code == a.get("apres") and x.niveau == 1 for x in rubs) else None
        if apres:
            r = replace(r, apres=apres)
        if parent or apres:  # après la dernière sous-rubrique de la partie
            ref = parent or apres
            pos = max(i for i, x in enumerate(rubs) if x.code == ref or x.parent == ref) + 1
        else:  # nouvelle partie : avant la conclusion
            pos = next((i for i, x in enumerate(rubs) if x.code == "conclusion"), len(rubs))
        rubs.insert(pos, r)
    tmods = cfg.get("tableaux") or {}
    tabs = []
    for t in DEFAUT_TABLEAUX:
        m = tmods.get(t.code) or {}
        libelle = str(m.get("libelle") or "").strip()
        tabs.append(replace(t, libelle=libelle or t.libelle, ignoree=m.get("exigence") == "non_exigee"))
    return rubs, tabs


_ALIAS: dict = {}


def alias_dcb() -> dict[str, set[str]]:
    """Libellés de la grille de la DCB pour chaque rubrique (pour retrouver ses lignes dans un modèle)."""
    if not _ALIAS:
        from . import modele
        try:
            libelles = modele._lire_libelles(modele.MODELE_DCB)
        except Exception:
            libelles = {}
        for r in DEFAUT_RUBRIQUES:
            if r.ligne_forme in libelles:
                _ALIAS[r.code] = {modele.libelle_norme(libelles[r.ligne_forme])}
    return _ALIAS


def _date_fichier(p) -> float | None:
    try:
        return p.stat().st_mtime
    except OSError:
        return None


def actualiser(force: bool = False) -> None:
    """Canevas en vigueur = canevas par défaut + Paramètres, rattaché aux lignes du modèle de fichier d'analyse."""
    from . import modele
    chemin = modele.modele_courant()
    cle = (_date_fichier(chemin_config()), str(chemin), _date_fichier(chemin),
           _date_fichier(dossier_utilisateur() / modele.NOM_META))
    if not force and cle == _ETAT["cle"]:
        return
    cfg = lire_config()
    rubs, tabs = construire(cfg)
    try:
        plan = modele.calculer_plan(chemin, rubs, tabs, alias_dcb(), modele.lignes_forcees())
        if not plan.valide:
            raise ValueError(plan.manquantes)
    except Exception:  # modèle importé illisible : modèle de la DCB
        plan = modele.calculer_plan(modele.MODELE_DCB, rubs, tabs, alias_dcb())
    rubs = [replace(r, ligne_forme=plan.forme.get(r.code), ligne_fond=plan.fond.get(r.code),
                    hors_grille=r.code not in plan.forme) for r in rubs]
    tabs = [replace(t, ligne_forme=plan.forme.get(t.code)) for t in tabs]
    RUBRIQUES[:] = rubs
    PAR_CODE.clear()
    PAR_CODE.update({r.code: r for r in rubs})
    TABLEAUX[:] = tabs
    TABLEAU_PAR_CODE.clear()
    TABLEAU_PAR_CODE.update({t.code: t for t in tabs})
    _ETAT.update(cle=cle, reference=str(cfg.get("reference") or "").strip() or REFERENCE_DEFAUT, plan=plan)


def reference() -> str:
    """Référence du canevas en vigueur (« note n°0580/MBPE/DGBF/DCB du 26 juillet 2023 » par défaut)."""
    actualiser()
    return _ETAT["reference"]


def plan():
    """Lignes du modèle de fichier d'analyse en vigueur (modele.Plan)."""
    actualiser()
    return _ETAT["plan"]


# ------------------------------------------------------------------ Paramètres : lecture et enregistrement
def description() -> dict:
    """Canevas en vigueur et modèle de fichier d'analyse, pour la page Paramètres."""
    from . import modele
    actualiser()
    p = _ETAT["plan"]
    forcees = modele.lignes_forcees()
    defauts = {r.code: r for r in DEFAUT_RUBRIQUES}
    tdefauts = {t.code: t for t in DEFAUT_TABLEAUX}
    rubriques = [{
        "code": r.code, "libelle": r.libelle, "libelle_defaut": defauts[r.code].libelle if r.code in defauts else None,
        "niveau": r.niveau, "parent": r.parent, "exigence": exigence(r),
        "exigence_defaut": exigence(defauts[r.code]) if r.code in defauts else None,
        "titre_requis": r.titre_requis, "mots_min": r.mots_min, "intitules": list(r.intitules), "perso": r.perso,
        "apres": r.apres,
        "ligne": r.ligne_forme, "ligne_fond": r.ligne_fond,
        "ligne_choisie": forcees.get(r.code)} for r in _ordre_affichage()]
    tableaux = [{"code": t.code, "numero": t.numero, "libelle": t.libelle, "libelle_defaut": tdefauts[t.code].libelle,
                 "exigence": "non_exigee" if t.ignoree else "obligatoire", "ligne": t.ligne_forme,
                 "ligne_choisie": forcees.get(t.code)} for t in TABLEAUX]
    fixes = {p.ancres.get(n) for n in ("forme_global", "sommaire", "tableaux", "signature")}
    zone = p.lignes_zone("forme_global", "appreciation_forme")
    from .canevas_document import document
    from .word import CHAMPS
    return {
        "reference": _ETAT["reference"], "reference_defaut": REFERENCE_DEFAUT, "modifie": bool(lire_config()),
        "document": document(),
        "exigences": [{"code": c, "libelle": l} for c, l in EXIGENCES],
        "exigences_tableaux": [{"code": c, "libelle": l} for c, l in EXIGENCES_TABLEAUX],
        "rubriques": rubriques, "tableaux": tableaux,
        "parties": [{"code": r.code, "libelle": r.libelle} for r in RUBRIQUES if r.niveau == 1],
        "modele_word": {**modele.info_word(), "champs_disponibles": [{"code": c, "libelle": l} for c, l in CHAMPS]},
        "modele": {**modele.info(),
                   "lignes": [{"ligne": r, "libelle": re.sub(r"\s+", " ", t).strip()[:90]} for r, t in zone if r not in fixes],
                   "ancres": [{"nom": n, "designation": modele.DESIGNATION[n], "ligne": p.ancres.get(n)}
                              for n, _, _, _, _ in modele.ANCRES],
                   "manquantes": p.manquantes,
                   "sans_ligne": [r.libelle for r in RUBRIQUES if r.code not in p.forme and not r.ignoree
                                  and r.code not in ("justification", "annonce_plan", "annexes")]
                   + [f"Tableau {t.numero}" for t in TABLEAUX if t.code not in p.forme and not t.ignoree]},
    }


def _ordre_affichage() -> list[Rubrique]:
    """Chaque partie suivie de ses sous-rubriques (la conclusion avant les annexes, par exemple)."""
    out = []
    for r in RUBRIQUES:
        if r.parent is None:
            out.append(r)
            out += [x for x in RUBRIQUES if x.parent == r.code]
    return out + [r for r in RUBRIQUES if r not in out]


def _entier(v, mini: int = 0, maxi: int = 5000) -> int | None:
    try:
        n = int(float(str(v).replace(",", ".")))
    except (TypeError, ValueError):
        return None
    return max(mini, min(maxi, n))


def _intitules(v) -> list[str]:
    if isinstance(v, str):
        v = re.split(r"[;\n]", v)
    return [str(i).strip()[:150] for i in (v or []) if str(i).strip()][:20]


def enregistrer(data: dict) -> dict:
    """Enregistre le canevas saisi dans les Paramètres (écarts par rapport au canevas par défaut, rubriques ajoutées,
    lignes du modèle choisies)."""
    from . import modele
    defauts = {r.code: r for r in DEFAUT_RUBRIQUES}
    exigences = dict(EXIGENCES)
    cfg: dict = {"rubriques": {}, "ajouts": [], "tableaux": {}}
    reference_saisie = str(data.get("reference") or "").strip()[:200]
    if reference_saisie and reference_saisie != REFERENCE_DEFAUT:
        cfg["reference"] = reference_saisie
    lignes: dict[str, int] = {}
    parties_perso: set[str] = set()
    numeros = [int(c[6:]) for c in (str(i.get("code") or "") for i in data.get("rubriques") or [])
               if c.startswith("perso_") and c[6:].isdigit()]
    suivant = max(numeros, default=0) + 1
    renommes: dict[str, str] = {}  # code provisoire de l'interface → code définitif
    for item in data.get("rubriques") or []:
        code = str(item.get("code") or "")
        libelle = str(item.get("libelle") or "").strip()[:200]
        ex = item.get("exigence") if item.get("exigence") in exigences else None
        intitules = _intitules(item.get("intitules"))
        mots = _entier(item.get("mots_min")) if item.get("mots_min") not in (None, "") else None
        if code in defauts:
            d, m = defauts[code], {}
            if libelle and libelle != d.libelle:
                m["libelle"] = libelle
            if ex and ex != exigence(d):
                m["exigence"] = ex
            if intitules:
                m["intitules"] = intitules
            if mots is not None and mots != d.mots_min:
                m["mots_min"] = mots
            if isinstance(item.get("titre_requis"), bool) and item["titre_requis"] != d.titre_requis:
                m["titre_requis"] = item["titre_requis"]
            if m:
                cfg["rubriques"][code] = m
        else:
            if not libelle:
                raise ValueError("Chaque rubrique ajoutée doit avoir un libellé.")
            if not code.startswith("perso_"):
                renommes[code] = f"perso_{suivant}"
                code = renommes[code]
                suivant += 1
            parent = item.get("parent") or None
            parent = renommes.get(parent, parent)
            if parent and not ((parent in defauts and defauts[parent].niveau == 1) or parent in parties_perso):
                raise ValueError(f"Partie de rattachement inconnue pour la rubrique « {libelle} ».")
            apres = renommes.get(item.get("apres"), item.get("apres")) if not parent else None
            if apres and not ((apres in defauts and defauts[apres].niveau == 1) or apres in parties_perso):
                apres = None
            if not parent:
                parties_perso.add(code)
            cfg["ajouts"].append({"code": code, "libelle": libelle, "parent": parent, "apres": apres,
                                  "exigence": ex or "obligatoire", "intitules": intitules,
                                  "mots_min": 10 if mots is None else mots})
        if "ligne" in item and item["ligne"] not in (None, "", "auto"):
            lignes[code] = _entier(item["ligne"], 0, 100000) or 0
    for item in data.get("tableaux") or []:
        code = str(item.get("code") or "")
        t = next((x for x in DEFAUT_TABLEAUX if x.code == code), None)
        if not t:
            continue
        m = {}
        libelle = str(item.get("libelle") or "").strip()[:200]
        if libelle and libelle != t.libelle:
            m["libelle"] = libelle
        if item.get("exigence") == "non_exigee":
            m["exigence"] = "non_exigee"
        if m:
            cfg["tableaux"][code] = m
        if "ligne" in item and item["ligne"] not in (None, "", "auto"):
            lignes[code] = _entier(item["ligne"], 0, 100000) or 0
    cfg = {k: v for k, v in cfg.items() if v}
    if cfg:
        chemin_config().write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    elif chemin_config().exists():
        chemin_config().unlink()
    meta = modele.lire_meta()
    if lignes or meta.get("lignes"):
        meta["lignes"] = lignes
        modele.ecrire_meta(meta)
    actualiser(force=True)
    return description()


def reinitialiser() -> dict:
    """Canevas de la note n°0580 (les lignes choisies pour le modèle sont aussi oubliées)."""
    from . import modele
    if chemin_config().exists():
        chemin_config().unlink()
    meta = modele.lire_meta()
    if meta.get("lignes"):
        meta["lignes"] = {}
        modele.ecrire_meta(meta)
    actualiser(force=True)
    return description()


def importer_modele(source, nom: str) -> dict:
    from . import modele
    rubs, tabs = construire(lire_config())
    modele.importer(source, nom, rubs, tabs, alias_dcb())
    actualiser(force=True)
    return description()


def reinitialiser_modele() -> dict:
    from . import modele
    modele.reinitialiser()
    actualiser(force=True)
    return description()
