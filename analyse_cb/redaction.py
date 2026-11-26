"""Rédaction, dans un style administratif, des appréciations générales du fichier d'analyse.

Les textes sont produits sous forme définitive (validation directe) ; en mode brouillon, ils restent à relire.
"""
from __future__ import annotations

import re

from .canevas import PAR_CODE, RUBRIQUES, TABLEAU_PAR_CODE
from .canevas import reference as reference_canevas
from .lecture import RE_LEGENDE

CONFORME, NON_CONFORME, A_VERIFIER, NON_APPLICABLE = "Conforme", "Non conforme", "À vérifier", "Non applicable"

NOMBRES = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze",
           "treize", "quatorze", "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf", "vingt"]

# Intitulé des grandes parties précédé de l'article qui convient dans une phrase
PARTIES = {
    "introduction": "une introduction",
    "presentation_budget": "la présentation du budget",
    "analyse_execution": "l'analyse de l'exécution du budget",
    "performance": "l'analyse de la performance",
    "gestion_financiere": "l'analyse de la gestion financière",
    "dispositifs_controle": "l'évaluation des dispositifs de contrôle",
    "patrimoine": "la situation du patrimoine",
    "gouvernance": "la situation de la gouvernance",
    "risques": "l'analyse de la gestion des risques",
    "difficultes_suggestions": "les difficultés et suggestions",
    "conclusion": "une conclusion",
}
AU_TITRE = {
    "introduction": "de l'introduction",
    "presentation_budget": "de la présentation du budget",
    "analyse_execution": "de l'analyse de l'exécution du budget",
    "performance": "de l'analyse de la performance",
    "gestion_financiere": "de l'analyse de la gestion financière",
    "dispositifs_controle": "de l'évaluation des dispositifs de contrôle",
    "patrimoine": "de la situation du patrimoine",
    "gouvernance": "de la gouvernance",
    "difficultes_suggestions": "des difficultés et suggestions",
    "conclusion": "de la conclusion",
}
# Intitulé des rubriques avec l'article qui convient
RUBRIQUES_PHRASE = {
    "texte_creation": "le texte de création", "missions": "le rappel des missions",
    "antennes": "le nombre d'antennes et leur lieu d'installation", "financement": "le mode de financement de l'EPN",
    "organisation": "l'organisation et l'effectif de l'EPN", "plan_strategique": "la présentation du plan stratégique",
    "paa": "la présentation du programme annuel d'activités",
    "justification": "la justification de la rédaction du rapport au regard de l'exigence légale",
    "annonce_plan": "l'annonce du plan", "pres_generale": "la présentation générale du budget",
    "pres_ressources": "la présentation des ressources", "pres_emplois": "la présentation des emplois",
    "exec_recettes": "la situation d'exécution du budget en recettes",
    "exec_depenses": "la situation d'exécution du budget en dépenses",
    "differes_rejets": "l'analyse des différés et des rejets", "resultat_budgetaire": "l'analyse du résultat budgétaire",
    "ratios": "l'analyse des ratios de gestion", "programme_activites": "la présentation du programme d'activités",
    "evaluation_activites": "l'évaluation de la réalisation des activités", "solde_tresorerie": "le solde de trésorerie",
    "creances": "les créances", "dettes": "les dettes", "provisions": "les provisions",
    "snt": "la situation nette de trésorerie", "controle_interne": "le contrôle interne budgétaire",
    "controle_gestion": "le contrôle de gestion", "patrimoine_existant": "l'état du patrimoine existant",
    "acquisitions": "le point des nouvelles acquisitions",
    "compta_matieres": "le point de la mise en œuvre de la comptabilité des matières",
    "coges": "le fonctionnement du Conseil de gestion", "comite_tresorerie": "le fonctionnement du comité de trésorerie",
    "difficultes": "les difficultés", "suggestions": "les suggestions",
    "obs_generales": "les observations générales sur la gestion",
    "obs_delais": "les observations sur les délais de production des rapports de l'Ordonnateur et de l'Agent Comptable",
}

MENTIONS = {"Très satisfaisant": "très satisfaisante", "Satisfaisant": "satisfaisante", "Passable": "passable",
            "Insuffisant": "insuffisante"}


def nombre(n: int, feminin: bool = False) -> str:
    """« six (06) », à la manière des écrits administratifs."""
    if 0 <= n < len(NOMBRES):
        mot = "une" if (n == 1 and feminin) else NOMBRES[n]
        return f"{mot} ({n:02d})"
    return str(n)


def enumerer(elements: list[str], conjonction: str = "et") -> str:
    elements = [e for e in elements if e]
    if not elements:
        return ""
    if len(elements) == 1:
        return elements[0]
    return ", ".join(elements[:-1]) + f" {conjonction} " + elements[-1]


def _min(texte: str) -> str:
    """Première lettre en minuscule (sauf sigle)."""
    if len(texte) > 1 and texte[1].isupper():
        return texte
    return texte[:1].lower() + texte[1:]


def _guillemets(libelle: str) -> str:
    return f"« {libelle} »"


def periode_phrase(res) -> str:
    p = res.periode
    if p.type == "trimestriel" and p.trimestre:
        return f"au {p.trimestre}{'er' if p.trimestre == 1 else 'e'} trimestre {p.annee}"
    if p.type == "etape":
        if p.trimestre == 2:
            return f"au 2e trimestre {p.annee} (rapport d'étape au 30 juin)"
        return f"au premier semestre {p.annee} (rapport d'étape au 30 juin)"
    return f"à l'exercice {p.annee}"


def _epn(res) -> str:
    nom = re.sub(r"^Ecole\b", "École", res.infos.epn or "l'établissement")
    if re.match(r"^(l['']|le |la |les )", nom, re.I):
        return nom
    voyelle = re.match(r"^[aeiouyéèêàâîôûh]", nom, re.I)
    feminin = re.match(r"^(ecole|école|agence|autorite|autorité|caisse|chambre|maison|bibliotheque|bibliothèque|"
                       r"universite|université|academie|académie|haute)", nom, re.I)
    if voyelle:
        return f"l'{nom}"
    return f"la {nom}" if feminin else f"le {nom}"


def _de(actions: list[str]) -> list[str]:
    """« se conformer », « indiquer » → « de se conformer », « d'indiquer »."""
    return [("d'" + a) if re.match(r"^[aeiouyéèêh]", a, re.I) else ("de " + a) for a in actions]


# ------------------------------------------------------------------ outils communs
def _fcfa(v) -> str:
    from .texte import format_montant
    return f"{format_montant(v)} FCFA"


def _tableau_court(nom: str) -> str:
    """« Tableau 6 (Exécution du budget en dépenses) » → « tableau n°6 (exécution du budget en dépenses) »."""
    m = re.match(r"^Tableau (\d+) \((.+)\)$", nom or "")
    if m:
        return f"tableau n°{m.group(1)} ({_min(m.group(2))})"
    return nom or "rapport"


def _phrase(texte: str) -> str:
    texte = texte.strip()
    return texte if texte.endswith(".") else texte + "."


def _mention(res, score, masculin: bool = False) -> str:
    m = res.mention(score)
    return m.lower() if masculin else MENTIONS.get(m, m.lower())


THEMES = {"Missions": "les missions", "Organes de l'EPN": "les organes", "Tutelle technique": "la tutelle technique",
          "Mode de financement": "le mode de financement", "Référence du texte de création": "la référence du texte de création",
          "Siège": "le siège", "Antennes / implantations": "les implantations",
          "Sessions du Conseil de gestion": "les sessions du Conseil de gestion",
          "Ressources budgétées": "les ressources budgétées"}


def _ecart_decret(p) -> str:
    """Formulation administrative d'un écart relevé par rapport au décret."""
    if p.theme.startswith("Référence du texte"):
        m = re.search(r"le n°([\w\-/]+), alors que le décret de création est le n°([\w\-/]+)", p.constat)
        if m:
            return f"le texte de création y est cité sous le n°{m.group(1)} au lieu du n°{m.group(2)}"
        return "le texte de création n'y est pas correctement référencé"
    return {"Missions": "les missions de l'établissement n'y sont que partiellement rappelées",
            "Mode de financement": "le mode de financement de l'établissement n'est pas présenté dans l'introduction",
            "Organes de l'EPN": "certains organes prévus par le décret n'y sont pas évoqués",
            "Sessions du Conseil de gestion": "la périodicité des sessions du Conseil de gestion n'est pas respectée",
            "Ressources budgétées": "des ressources non prévues par le décret sont inscrites au budget",
            }.get(p.theme, _min(p.constat.rstrip(".")))


def _ecart_num(c) -> float:
    from .texte import lire_nombre
    a, b = lire_nombre(c.attendu), lire_nombre(c.constate)
    return abs(a - b) if a is not None and b is not None else 0.0



DANS = {
    "introduction": "Dans l'introduction", "presentation_budget": "Dans la présentation du budget",
    "analyse_execution": "Dans l'analyse de l'exécution du budget", "performance": "Dans l'analyse de la performance",
    "gestion_financiere": "Dans l'analyse de la gestion financière",
    "dispositifs_controle": "Dans l'évaluation des dispositifs de contrôle", "patrimoine": "Dans la situation du patrimoine",
    "gouvernance": "Dans la partie consacrée à la gouvernance", "conclusion": "Dans la conclusion",
}
TABLEAUX_COURTS = {"T1": "comparaison avec le budget de l'année précédente", "T2": "budgets des trois derniers exercices",
                   "T3": "présentation des ressources", "T4": "présentation des emplois",
                   "T5": "exécution des recettes", "T6": "exécution des dépenses",
                   "T7": "motifs des différés", "T8": "motifs des rejets"}


# Intitulés abrégés, utilisés lorsque la partie concernée vient d'être nommée
COURT = {"differes_rejets": "les différés et rejets", "resultat_budgetaire": "le résultat budgétaire",
         "ratios": "les ratios de gestion", "justification": "la justification légale du rapport",
         "compta_matieres": "la comptabilité des matières", "controle_interne": "le contrôle interne budgétaire",
         "controle_gestion": "le contrôle de gestion", "programme_activites": "le programme d'activités",
         "evaluation_activites": "l'évaluation des activités réalisées"}


def periode_pour(res) -> str:
    """« pour le 3e trimestre 2026 », « pour le premier semestre 2026 (rapport d'étape) », « pour l'exercice 2026 »."""
    p = res.periode
    if p.type == "trimestriel" and p.trimestre:
        return f"pour le {p.trimestre}{'er' if p.trimestre == 1 else 'e'} trimestre {p.annee}"
    if p.type == "etape":
        return (f"pour le 2e trimestre {p.annee} (rapport d'étape au 30 juin)" if p.trimestre == 2
                else f"pour le premier semestre {p.annee} (rapport d'étape)")
    return f"pour l'exercice {p.annee}"


def _de_article(x: str) -> str:
    """« le résultat » → « du résultat », « les ratios » → « des ratios », « la » → « de la », « l' » → « de l' »."""
    for avant, apres in (("le ", "du "), ("les ", "des "), ("la ", "de la "), ("l'", "de l'")):
        if x.startswith(avant):
            return apres + x[len(avant):]
    return "de " + x


def _pluriel(objets: list[str]) -> bool:
    return len(objets) > 1 or (bool(objets) and objets[0].startswith("les "))


def _a(actions: list[str]) -> list[str]:
    return ["à " + a for a in actions]


def _accord(n: int, singulier: str, pluriel: str) -> str:
    return singulier if n == 1 else pluriel


def _recommander(recos: list[str]) -> str:
    """Recommandations en deux phrases au plus, pour éviter une énumération d'un seul bloc."""
    if not recos:
        return ""
    if len(recos) <= 2:
        return f"Le Contrôleur Budgétaire est invité {enumerer(_a(recos))}."
    return (f"Le Contrôleur Budgétaire est invité {enumerer(_a(recos[:2]))}. "
            f"Il lui revient également {enumerer(_de(recos[2:]))}.")


def _systeme(res) -> str:
    return "SIGOBE" if getattr(res.situation, "systeme", "") == "SIGOBE" else "système d'information budgétaire"


def _plus_tard(res) -> str:
    d, fin = res.situation.date_arrete, res.periode.fin
    jours = (d - fin).days if d else 0
    if 25 <= jours <= 35:
        return "un mois plus tard"
    return f"au {d:%d/%m/%Y}" if d else ""


# ------------------------------------------------------------------ forme
def appreciation_forme(res) -> str:
    lignes = {l.code: l for l in res.forme}
    s = res.structure

    # Préambule
    p1 = (f"Le rapport du Contrôleur Budgétaire auprès de {_epn(res)} {periode_pour(res)} "
          f"a été examiné au regard du canevas fixé par la {reference_canevas()}. "
          f"Le taux de conformité de la forme est de {res.score_forme:.0f} % ; l'appréciation est {_mention(res, res.score_forme)}.")
    canevas, detail = res.canevas_en_vigueur
    nouvelles_codes = [c for c in ("performance", "risques") if c in lignes and lignes[c].statut == NON_CONFORME
                       and not s[c].trouvee]
    nouvelles = [PARTIES[c] for c in nouvelles_codes]
    par_activites = "présentation par activités (budget-programmes) : oui" in detail
    if canevas == "Oui":
        p1 += " Le canevas en vigueur est utilisé."
    elif nouvelles:
        objet = (f"les deux rubriques introduites en 2023 : {enumerer(nouvelles)}" if len(nouvelles) == 2
                 else f"la rubrique introduite en 2023 : {nouvelles[0]}")
        p1 += (f" Le CB a retenu la présentation par activités du budget-programmes, mais n'a pas traité {objet}."
               if par_activites else f" Le CB n'a pas traité {objet}.")
    elif not canevas.startswith("Partiellement"):
        p1 += " Le rapport ne suit pas le canevas en vigueur et semble se référer à une version antérieure."

    # Structuration
    presentes = [PARTIES[c] for c in PARTIES if c in lignes and lignes[c].statut in (CONFORME, A_VERIFIER)]
    absentes = [PARTIES[c] for c in PARTIES if c in lignes and lignes[c].statut == NON_CONFORME
                and not s[c].trouvee and c not in nouvelles_codes]
    p2 = f"Le rapport comprend {enumerer(presentes)}." if presentes else ""
    if absentes:
        p2 += f" {enumerer(absentes)[:1].upper()}{enumerer(absentes)[1:]} {_accord(len(absentes), 'manque', 'manquent')}."
    manquantes: dict[str, list[str]] = {}
    vides, peu = [], []
    for rub in RUBRIQUES:
        l = lignes.get(rub.code)
        if not l or rub.niveau == 1 or rub.cas_echeant:
            continue
        parent = rub.parent if rub.niveau == 2 else PAR_CODE[rub.parent].parent or rub.parent
        if l.statut == NON_CONFORME and "mais rubrique non renseignée" in l.precision:
            vides.append(_guillemets(rub.libelle))
        elif (l.statut == NON_CONFORME and l.precision.startswith("Rubrique absente") and lignes.get(parent)
              and lignes[parent].statut != NON_CONFORME):
            manquantes.setdefault(rub.parent, []).append(rub.code)
        if "peu développée" in l.precision:
            peu.append(_guillemets(rub.libelle))
    ds = manquantes.get("difficultes_suggestions", [])
    sans_distinction = {"difficultes", "suggestions"} <= set(ds)
    if sans_distinction:
        manquantes["difficultes_suggestions"] = [c for c in ds if c not in ("difficultes", "suggestions")]
    phrases = []
    for i, (parent, codes) in enumerate((p, c) for p, c in manquantes.items() if c):
        objets = [COURT.get(c) or RUBRIQUES_PHRASE.get(c, _min(PAR_CODE[c].libelle)) for c in codes]
        debut = DANS.get(parent, "Dans la partie « " + PAR_CODE[parent].libelle + " »")
        n = 2 if _pluriel(objets) else 1
        if i % 3 == 0:
            phrases.append(f"{debut}, {enumerer(objets)} {_accord(n, 'fait', 'font')} défaut.")
        elif i % 3 == 1:
            phrases.append(f"{debut}, rien n'est dit {enumerer([_de_article(o) for o in objets])}.")
        else:
            phrases.append(f"{enumerer(objets)[:1].upper()}{enumerer(objets)[1:]} "
                           f"{_accord(n, "n'apparaît", "n'apparaissent")} pas davantage {debut[0].lower()}{debut[1:]}.")
    if phrases:
        p2 += " Plusieurs rubriques obligatoires manquent toutefois. " + " ".join(phrases)
    if sans_distinction:
        p2 += " Les difficultés et les suggestions sont présentées ensemble, sans la distinction prévue par le canevas."
    if vides:
        p2 += (f" {_accord(len(vides), 'La rubrique', 'Les rubriques')} {enumerer(vides)} "
               f"{_accord(len(vides), 'porte un intitulé mais reste vide', 'portent un intitulé mais restent vides')}.")
    if peu:
        p2 += f" {_accord(len(peu), 'La rubrique', 'Les rubriques')} {enumerer(peu)} {_accord(len(peu), 'est traitée', 'sont traitées')} trop brièvement."
    sommaire = lignes.get("sommaire")
    if sommaire and sommaire.statut != CONFORME:
        if "Aucune table des matières" in sommaire.precision:
            p2 += " Le rapport n'a ni sommaire ni plan annoncé."
        else:
            nets = [re.sub(r"^\s*[IVXLC\d]+(?:\.\d+)*\s*[-–.)]\s*", "", e).strip() for e in s.sommaire_absents]
            nets = [e.capitalize() if e.isupper() else e for e in nets if e]
            ecarts = [f"« {e[:1].upper()}{e[1:]} »" for e in nets][:5]
            if ecarts:
                p2 += (f" Enfin, le plan annoncé n'est pas suivi : {enumerer(ecarts)} "
                       f"{_accord(len(ecarts), 'y figure', 'y figurent')} sans développement correspondant.")
    elif sommaire:
        p2 += " Le plan annoncé correspond au contenu du rapport."

    # Tableaux
    codes = sorted(c for c in TABLEAU_PAR_CODE if not TABLEAU_PAR_CODE[c].ignoree)
    presents = [c for c in codes if c in res.tableaux.par_code]
    tab_absents = [c for c in codes if c not in res.tableaux.par_code]
    p3 = (f"{nombre(len(presents)).capitalize()} des {nombre(len(codes))} tableaux prescrits "
          f"{_accord(len(presents), 'est produit', 'sont produits')}")
    if tab_absents:
        libs = [f"n°{TABLEAU_PAR_CODE[c].numero} ({TABLEAUX_COURTS[c]})" for c in tab_absents]
        p3 += f" ; {_accord(len(libs), 'le tableau', 'les tableaux')} {enumerer(libs)} {_accord(len(libs), 'manque', 'manquent')}."
    else:
        p3 += "."
    numerotation, sans_titre, sans_source = [], [], []
    for c in presents:
        t = res.tableaux.par_code[c]
        m = RE_LEGENDE.match(t.bloc.legende or "")
        if not t.bloc.legende:
            sans_titre.append(c)
        elif m and int(m.group(2)) != TABLEAU_PAR_CODE[c].numero:
            numerotation.append((abs(int(m.group(2)) - TABLEAU_PAR_CODE[c].numero),
                                 f"la {TABLEAUX_COURTS[c]} porte le n°{m.group(2)} au lieu du n°{TABLEAU_PAR_CODE[c].numero}"
                                 .replace("la motifs", "les motifs").replace("la budgets", "les budgets")
                                 .replace("la comparaison", "la comparaison")))
        if c in lignes and "source non indiquée" in lignes[c].precision:
            sans_source.append(f"n°{TABLEAU_PAR_CODE[c].numero}")
    if numerotation:
        numerotation.sort(key=lambda x: -x[0])
        ex = [x[1] for x in numerotation[:2]]
        p3 += f" La numérotation ne suit pas le canevas : {ex[0]}" + (f", {ex[1].replace(' porte le', ' le')}." if len(ex) > 1 else ".")
    if sans_titre:
        noms = [TABLEAUX_COURTS[c] for c in sans_titre]
        p3 += (f" Le tableau d'{noms[0]} n'a ni titre ni numéro" if len(noms) == 1 and noms[0].startswith("exécution")
               else f" {_accord(len(noms), 'Le tableau', 'Les tableaux')} {enumerer(noms)} {_accord(len(noms), "n'a", "n'ont")} ni titre ni numéro")
        p3 += (f", et la source n'est pas indiquée pour {_accord(len(sans_source), 'le tableau', 'les tableaux')} "
               f"{enumerer(sans_source)}." if sans_source else ".")
    elif sans_source:
        p3 += f" La source n'est pas indiquée pour {_accord(len(sans_source), 'le tableau', 'les tableaux')} {enumerer(sans_source)}."
    supplementaires = sum(1 for t in res.tableaux.tableaux if not t.code or not t.principal)
    if supplementaires:
        p3 += (f" {nombre(supplementaires).capitalize()} {_accord(supplementaires, 'tableau non prévu', 'tableaux non prévus')} "
               f"par le canevas {_accord(supplementaires, 'a', 'ont')} en outre été {_accord(supplementaires, 'ajouté', 'ajoutés')}.")

    # Date et signature
    sig = lignes.get("signature")
    p4 = ""
    if sig:
        if sig.statut == CONFORME:
            p4 = "Le rapport est daté et signé."
        elif sig.statut == A_VERIFIER:
            p4 = "La date, la signature et le cachet sont à contrôler sur l'original."
        elif "pas daté" in sig.precision:
            p4 = "Le rapport porte le nom du Contrôleur Budgétaire, mais il n'est ni daté ni signé."
        else:
            p4 = "Le rapport n'est ni daté ni signé."

    # Conclusion
    recos = []
    if absentes or any(manquantes.values()) or vides or nouvelles:
        recos.append("traiter toutes les rubriques du canevas")
    if tab_absents or numerotation or sans_titre or sans_source:
        recos.append("produire les huit tableaux avec leur numérotation et leurs intitulés"
                     + (", en citant leurs sources" if sans_source else ""))
    if sommaire and sommaire.statut != CONFORME:
        recos.append("mettre le plan annoncé en accord avec le contenu")
    if peu:
        recos.append("développer les rubriques traitées trop brièvement")
    if sig and sig.statut == NON_CONFORME:
        recos.append("dater et signer son rapport")
    if res.score_forme >= 90 and not recos:
        p5 = "La présentation du rapport n'appelle pas d'observation particulière."
    elif res.score_forme >= 75:
        p5 = "La présentation du rapport est dans l'ensemble satisfaisante." + (
            " " + _recommander(recos).replace("est invité", "est toutefois invité", 1) if recos else "")
    else:
        p5 = "La forme du rapport doit donc être sensiblement améliorée. " + _recommander(recos)
    return "\n".join(p.strip() for p in (p1, p2, p3, p4, p5) if p.strip())


# ------------------------------------------------------------------ fond
def _ex_calcul(c) -> str:
    colonne = re.search(r"\(colonne ([^)]+)\)", c.message)
    m = re.match(r"^Tableau (\d+)", c.tableau or "")
    ou = f"Au tableau n°{m.group(1)}" if m else f"Au tableau {c.tableau}"
    quoi = (f"le total des {colonne.group(1)}" if colonne and c.ligne.lower().startswith("total") else
            f"la ligne « {c.ligne} »" + (f" ({colonne.group(1)})" if colonne else "") if c.ligne else "un montant")
    unite = lambda v: f"{v} FCFA" if re.search(r"\d{3}$", v or "") else v  # noqa: E731
    base = "la somme des lignes donne" if c.controle.startswith(("Total", "Sous-total")) else "le recalcul donne"
    return f"{ou}, par exemple, {quoi} est arrêté à {unite(c.constate)}, alors que {base} {unite(c.attendu)}."


def _nb_calcul(res) -> int:
    return len([c for c in res.tableaux.constats if c.nature == "fiabilite"
                and not c.controle.startswith(("Signe", "Base de calcul", "Codes d'activité"))])


def _nb_incoherences(res) -> int:
    return len([c for c in res.constats if c.nature == "coherence" and c.gravite != "Information"])


def appreciation_fond(res) -> str:
    cs = res.constats
    majeures = [c for c in cs if c.gravite == "Majeure"]
    paragraphes = []
    p = (f"Sur le fond, le niveau de fiabilité et de cohérence est {_mention(res, res.score_fond, masculin=True)} : "
         f"{res.score_fond:.0f} % des points vérifiables." if res.score_fond is not None
         else "Sur le fond, aucun point n'a pu être vérifié de manière automatique.")
    p += (f" Les contrôles ont relevé {nombre(len(cs), True)} anomalies, dont {nombre(len(majeures), True)} majeures, "
          "détaillées à l'onglet « Contrôles automatiques »." if cs else " Les contrôles n'ont relevé aucune anomalie.")
    paragraphes.append(p)

    calc = [c for c in res.tableaux.constats if c.nature == "fiabilite"
            and not c.controle.startswith(("Signe", "Base de calcul", "Codes d'activité"))]
    if calc:
        types = [libelle for motif, libelle in (
            (r"^(Total|Sous-total)", "totaux et sous-totaux"), (r"^Taux", "taux"), (r"Disponible|Écart =", "disponibles"),
            (r"^Variation", "variations"), (r"^Montant actuel", "montants après modification"))
            if any(re.search(motif, c.controle) for c in calc)]
        principaux = [c for c in calc if c.gravite == "Majeure" and not c.tableau.startswith("«")] or calc
        exemple = max(principaux, key=lambda c: (bool(re.search(r"colonne (réalisation|prises en charge|recouvrement)", c.message)),
                                                 _ecart_num(c)))
        p = (f"Les tableaux comportent {nombre(len(calc), True)} erreurs de calcul ({', '.join(types)}). {_ex_calcul(exemple)}")
        signes = any(c.controle.startswith("Signe") for c in res.tableaux.constats)
        bases = any(c.controle.startswith("Base de calcul") for c in res.tableaux.constats)
        if signes or bases:
            p += " " + " et ".join(x for x in (
                "certaines baisses sont présentées sans signe négatif" if signes else "",
                "certains taux sont calculés sur une autre base que celle du canevas" if bases else "") if x).capitalize() + "."
        paragraphes.append(p)
    elif res.tableaux.par_code:
        paragraphes.append("Les calculs des tableaux sont exacts.")

    controles = {c.controle for c in cs}
    coh1, coh2 = [], []
    eq = next((c for c in cs if c.controle.startswith("Équilibre budgétaire")), None)
    if eq:
        coh1.append(f"les ressources ({eq.constate} FCFA) et les emplois ({eq.attendu} FCFA) ne sont pas équilibrés")
    if any(c.startswith("Même répartition par nature") for c in controles):
        coh1.append("la répartition des crédits par nature diffère entre la présentation des emplois et l'exécution des dépenses")
    if any(c.startswith("Budget N") for c in controles):
        coh1.append("le montant du budget varie d'un tableau à l'autre")
    if any(c.startswith("Cohérence du taux") for c in controles):
        coh1.append("certains taux cités dans le texte ne se retrouvent pas dans les tableaux")
    if "Sens du résultat budgétaire" in controles:
        coh1.append("le sens du résultat budgétaire indiqué dans le texte est erroné")
    if {"Exercice cité conforme à la période", "Trimestre cité conforme à la période"} & controles:
        coh2.append("le texte renvoie par endroits à une autre période, sans doute par reprise d'un rapport antérieur")
    if "Événements datés dans la période" in controles:
        coh2.append("certains événements sont datés hors de la période")
    if "Codes d'activité uniques" in controles:
        coh2.append("des codes d'activité sont erronés ou en double")
    if coh1 or coh2:
        p = "Les données ne sont pas non plus cohérentes entre elles."
        if coh1:
            p += f" {enumerer(coh1)[:1].upper()}{enumerer(coh1)[1:]}."
        if coh2:
            p += f" {coh2[0][:1].upper()}{coh2[0][1:]}" + (f" ; {enumerer(coh2[1:])}" if len(coh2) > 1 else "") + "."
        paragraphes.append(p)

    if res.confrontation:
        from .decret import CONFORME as D_OK, ECART as D_ECART
        ok = [THEMES.get(p.theme, _min(p.theme)) for p in res.confrontation.points if p.statut == D_OK]
        ec = [p for p in res.confrontation.points if p.statut == D_ECART]
        ref = res.decret.reference.replace("Décret", "décret")
        p = (f"Rapproché du {ref} portant création de l'établissement, le rapport présente correctement {enumerer(ok)}."
             if ok else f"Le rapport n'a pu être rapproché utilement du {ref}.")
        textes = []
        for x in ec:
            if x.theme.startswith("Référence du texte"):
                m = re.search(r"le n°([\w\-/]+), alors que le décret de création est le n°([\w\-/]+)", x.constat)
                textes.append(f"il cite le texte de création sous le n°{m.group(1)} au lieu du n°{m.group(2)}" if m
                              else "il ne cite pas correctement le texte de création")
            elif x.theme == "Mode de financement":
                textes.append("l'introduction ne présente pas le mode de financement")
            else:
                textes.append(_ecart_decret(x))
        if textes:
            p += f" En revanche, {enumerer(textes)}."
        paragraphes.append(p)

    rap = res.rapprochement
    if rap:
        d = res.situation.date_arrete
        systeme = _systeme(res)
        concordants = [l for l in rap.lignes if l.statut == "Concordant"]
        decales = [l for l in rap.lignes if l.statut == "Écart (décalage de date)"]
        comparables = [l for l in rap.lignes if l.statut != "Non comparable"]
        p = (f"La situation d'exécution du {systeme}" + (f" au {d:%d/%m/%Y}" if d else "")
             + f" confirme {nombre(len(concordants))} des {nombre(len(comparables))} agrégats comparés"
             + (f" ; {nombre(len(decales))} écarts peuvent s'expliquer par le décalage de date." if decales else "."))
        impossibles = [l for l in rap.detail + rap.lignes if "impossible" in l.note]
        budget = next((l for l in rap.lignes if l.libelle == "Budget actuel de dépenses" and l.statut == "Écart"), None)
        if impossibles or budget:
            p += " D'autres montants sont en revanche inexacts."
        if impossibles:
            ex = next((l for l in impossibles if l.code), impossibles[0])
            objet = f"Pour l'activité {ex.code}" if ex.code else f"Pour le poste « {ex.libelle} »"
            p += (f" {objet}, le rapport déclare {_fcfa(ex.rapport)} au {res.periode.fin:%d/%m/%Y}, contre "
                  f"{_fcfa(ex.situation)} au {systeme} {_plus_tard(res)}, ce qui est impossible puisque les montants "
                  "d'exécution sont cumulés.")
        if budget:
            p += (f" Le budget actuel des dépenses figure pour {_fcfa(budget.rapport)} au lieu de {_fcfa(budget.situation)} : "
                  "la régulation n'a pas été répercutée.")
        if rap.date_conforme is False and d and d > res.periode.fin:
            p += (f" Les montants du rapport inférieurs à ceux du {systeme} n'ont pas été comptés comme des erreurs, "
                  f"la situation étant arrêtée après la fin de la période.")
        paragraphes.append(p)

    absentes = [l for l in res.fond if l.ligne and l.fiabilite == "Non renseigné"]
    if absentes:
        paragraphes.append(f"{nombre(len(absentes), True).capitalize()} {_accord(len(absentes), "rubrique absente ou vide n'a pu être appréciée", "rubriques absentes ou vides n'ont pu être appréciées")} sur le fond.")
    return "\n".join(paragraphes)


# ------------------------------------------------------------------ appréciation générale (partie V)
def appreciation_generale(res) -> str:
    from .decret import CONFORME as D_OK, ECART as D_ECART
    lignes = {l.code: l for l in res.forme}
    sigle = re.search(r"\(([A-Z0-9\-]{2,12})\)", res.infos.epn or "")
    epn = f"l'{sigle.group(1)}" if sigle and sigle.group(1)[0] in "AEIOUY" else (f"le {sigle.group(1)}" if sigle else _epn(res))
    periode = periode_pour(res)
    p1 = (f"Le rapport du Contrôleur Budgétaire auprès de {epn} {periode} est {_mention(res, res.score_forme, True)} "
          f"sur la forme ({res.score_forme:.0f} % de conformité au canevas)"
          + (f" et {_mention(res, res.score_fond, True)} sur le fond ({res.score_fond:.0f} % des points vérifiables)."
             if res.score_fond is not None else "."))
    e = res.ecart_jours
    limite = f"{res.date_limite:%d/%m/%Y}"
    recu = f"{res.infos.date_reception:%d/%m/%Y}" if res.infos.date_reception else ""
    p1 += (f" La date de réception par la DCB n'étant pas renseignée, le respect du délai de transmission (date limite "
           f"du {limite}) ne peut être apprécié." if e is None
           else f" Reçu le {recu}, il a été transmis dans le délai, fixé au {limite}." if e <= 0
           else f" Reçu le {recu}, il a été transmis avec {nombre(e)} jour{'s' if e > 1 else ''} de retard sur la "
                f"date limite du {limite}.")

    forts = []
    if res.score_forme >= 90:
        forts.append("suit le canevas de rédaction")
    if res.confrontation:
        ok = [THEMES.get(p.theme, _min(p.theme)) for p in res.confrontation.points if p.statut == D_OK]
        if ok:
            forts.append(f"présente correctement {enumerer(ok)} de l'établissement, conformément au décret de création")
    if res.rapprochement:
        statut = {}
        for l in res.rapprochement.lignes + res.rapprochement.detail:
            if l.statut in ("Concordant", "Écart") and not l.libelle.startswith("Résultat"):
                cle = (("recettes" if len(l.code) == 6 and l.code.startswith("7") else "dépenses") if l.code else
                       "recettes" if re.search(r"recette|ressource|recouvr", l.libelle, re.I) else "dépenses")
                statut.setdefault(cle, set()).add(l.statut)
        complets = [k for k in ("recettes", "dépenses") if statut.get(k) == {"Concordant"}]
        partiels = [k for k in ("recettes", "dépenses") if statut.get(k, set()) >= {"Concordant", "Écart"}]
        if complets or partiels:
            quoi = enumerer(([f"toutes ses données de {' et de '.join(complets)}"] if complets else [])
                            + ([f"une partie de ses données de {' et de '.join(partiels)}"] if partiels else []))
            forts.append(f"{quoi} {'concordent' if complets and not partiels else 'concorde'} avec la situation d'exécution"
                         .replace("toutes ses", "dont toutes les", 0))
    if res.tableaux.par_code and not _nb_calcul(res):
        forts.append("ne comporte pas d'erreur de calcul")
    if lignes.get("signature") and lignes["signature"].statut == CONFORME:
        forts.append("est daté et signé")
    if forts:
        # « Le rapport présente… et une partie de ses données… concorde » : sujets différents, deux propositions
        verbes = [f for f in forts if not f.startswith(("toutes", "une partie"))]
        donnees = [f for f in forts if f.startswith(("toutes", "une partie"))]
        p2 = (f"Le rapport {enumerer(verbes)}" if verbes else "")
        if donnees:
            p2 += (", et " if p2 else "") + donnees[0][:1].upper() * (not p2) + (donnees[0][1:] if not p2 else donnees[0])
        p2 += "."
    else:
        p2 = "L'examen ne fait ressortir aucun point positif particulier."

    faibles = []
    nb_tab = sum(1 for c in TABLEAU_PAR_CODE if c not in res.tableaux.par_code)
    nb_rub = sum(1 for l in res.forme if l.statut == NON_CONFORME and l.code in PAR_CODE and not PAR_CODE[l.code].cas_echeant
                 and (l.precision.startswith("Rubrique absente") or "non renseignée" in l.precision))
    if nb_rub or nb_tab:
        faibles.append(" et ".join(x for x in (
            "plusieurs rubriques obligatoires" if nb_rub > 1 else "une rubrique obligatoire" if nb_rub else "",
            f"{nombre(nb_tab)} {_accord(nb_tab, 'tableau', 'tableaux')} du canevas" if nb_tab else "") if x)
            + f" {_accord(nb_rub + nb_tab, 'manque', 'manquent')}")
    n_calc, n_coh = _nb_calcul(res), _nb_incoherences(res)
    if n_calc or n_coh:
        faibles.append(", et ".join(x for x in (
            f"les tableaux comportent {nombre(n_calc, True)} erreurs de calcul" if n_calc else "",
            f"{nombre(n_coh, True)} incohérences affectent les données" if n_coh else "") if x))
    if res.confrontation:
        ec = [p for p in res.confrontation.points if p.statut == D_ECART]
        ref = next((p for p in ec if p.theme.startswith("Référence du texte")), None)
        if ref:
            faibles.append(f"le texte de création est mal cité : le décret applicable est le {res.decret.reference.replace('Décret ', '')}")
        if any(p.theme == "Mode de financement" for p in ec):
            faibles.append("le mode de financement n'est pas présenté")
        autres = [p for p in ec if p is not ref and p.theme != "Mode de financement"]
        if autres:
            faibles.append(enumerer([_ecart_decret(p) for p in autres]))
        if any(p.rubrique == "coges" and "aucune session" in p.constat for p in res.confrontation.points):
            faibles.append("le rapport constate qu'aucune session du Conseil de gestion ne s'est tenue, sans en tirer "
                           "les conséquences pour la gouvernance de l'établissement")
    rap = res.rapprochement
    budget = impossibles = None
    if rap:
        impossibles = any("impossible" in l.note for l in rap.detail + rap.lignes)
        budget = next((l for l in rap.lignes if l.libelle == "Budget actuel de dépenses" and l.statut == "Écart"), None)
        if impossibles and budget:
            faibles.append("certains montants d'exécution sont contredits par la situation d'exécution, et la régulation "
                           "budgétaire n'est pas répercutée sur les dépenses")
        elif impossibles:
            faibles.append("certains montants d'exécution sont contredits par la situation d'exécution")
        elif budget:
            faibles.append("la régulation budgétaire n'est pas répercutée sur les dépenses")
    if lignes.get("signature") and lignes["signature"].statut == NON_CONFORME:
        faibles.append("le rapport n'est ni daté ni signé")
    if faibles:
        phrases = [f[:1].upper() + f[1:] + "." for f in faibles]
        if len(phrases) > 1:
            phrases[-1] = "Enfin, " + phrases[-1][:1].lower() + phrases[-1][1:]
        p3 = "Ses insuffisances sont toutefois importantes. " + " ".join(phrases) if forts else " ".join(phrases)
    else:
        p3 = "Aucune insuffisance majeure n'a été relevée."

    recos = []
    if nb_rub or nb_tab:
        recos.append("suivre strictement le canevas en vigueur")
    if n_calc or n_coh:
        recos.append("vérifier ses calculs ainsi que la concordance entre les tableaux et le texte")
    if res.confrontation and any(p.statut == D_ECART for p in res.confrontation.points):
        recos.append(f"citer correctement le {res.decret.reference.replace('Décret', 'décret')}")
    if rap and (impossibles or budget):
        recos.append(f"établir les tableaux d'exécution à partir de la situation du {_systeme(res)} à la fin de la période"
                     + (", sur la base du budget actuel" if budget else ""))
    if {"Exercice cité conforme à la période", "Trimestre cité conforme à la période"} & {c.controle for c in res.constats}:
        recos.append("mettre à jour les mentions de période reprises d'anciens rapports")
    if lignes.get("signature") and lignes["signature"].statut == NON_CONFORME:
        recos.append("dater et signer son rapport")
    if e is not None and e > 0:
        recos.append("respecter le délai de transmission")
    p4 = _recommander(recos)
    if rap and rap.date_conforme is False and res.situation.date_arrete:
        p4 += (f" La situation d'exécution au {res.periode.fin:%d/%m/%Y} sera demandée pour confirmer les écarts relevés.")
    return "\n".join(p.strip() for p in (p1, p2, p3, p4) if p.strip())
