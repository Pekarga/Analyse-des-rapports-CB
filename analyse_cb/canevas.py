"""Référentiel des rubriques du canevas de rédaction du rapport du Contrôleur Budgétaire.

Source : canevas institué par la note n°0580/MBPE/DGBF/DCB du 26 juillet 2023
(Direction du Contrôle Budgétaire), en application du décret n°2021-677 du 03 novembre 2021.

Chaque rubrique indique :
- les expressions qui permettent de la reconnaître dans un titre (`titres`) ;
- les expressions qui permettent de la reconnaître dans le corps du texte (`contenu`),
  lorsqu'une rubrique n'a pas forcément de titre dédié (ex. « Texte de création ») ;
- la ligne correspondante du fichier d'analyse Excel (partie II « forme » et III « fond »).
"""
from __future__ import annotations

from dataclasses import dataclass


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
    hors_grille: bool = False  # rubrique du canevas 2023 absente de la grille Excel actuelle

    @property
    def ligne_fond(self) -> int | None:
        if self.ligne_forme is None or self.ligne_forme > 62:
            return None
        return self.ligne_forme + 61


R = Rubrique
RUBRIQUES: list[Rubrique] = [
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
    ligne_forme: int
    rubrique: str


TABLEAUX: list[TableauCanevas] = [
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
TABLEAU_PAR_CODE = {t.code: t for t in TABLEAUX}

# Rubriques propres au canevas 2023 (budget-programmes) : leur présence indique que le CB
# utilise bien la dernière version du canevas.
MARQUEURS_CANEVAS_2023 = ("performance", "risques", "snt")
