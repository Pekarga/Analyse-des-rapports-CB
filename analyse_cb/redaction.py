"""Rédaction, dans un style administratif, des appréciations générales du fichier d'analyse.

Les textes produits sont des projets : ils restent à relire et à valider par le Chargé d'Études.
"""
from __future__ import annotations

import re

from .canevas import PAR_CODE, RUBRIQUES, TABLEAU_PAR_CODE
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
    if re.match(r"^(l['’]|le |la |les )", nom, re.I):
        return nom
    voyelle = re.match(r"^[aeiouyéèêàâîôûh]", nom, re.I)
    feminin = re.match(r"^(ecole|école|agence|autorite|autorité|caisse|chambre|maison|bibliotheque|bibliothèque|"
                       r"universite|université|academie|académie|haute)", nom, re.I)
    if voyelle:
        return f"l'{nom}"
    return f"la {nom}" if feminin else f"le {nom}"


# ------------------------------------------------------------------ forme
def appreciation_forme(res) -> str:
    lignes = {l.code: l for l in res.forme}
    paragraphes = []

    # 1. Préambule
    mention = MENTIONS.get(res.mention(res.score_forme), res.mention(res.score_forme).lower())
    preambule = (f"Le rapport du Contrôleur Budgétaire placé auprès de {_epn(res)}, afférent "
                 f"{periode_phrase(res)}, a été examiné au regard du canevas de rédaction institué par la note "
                 f"n°0580/MBPE/DGBF/DCB du 26 juillet 2023. Il ressort de cet examen un taux de conformité de la forme "
                 f"de {res.score_forme:.0f} %, ce qui conduit à une appréciation {mention} de la qualité formelle du document.")
    canevas, detail = res.canevas_en_vigueur
    nouvelles = [PARTIES.get(c, "la " + _min(PAR_CODE[c].libelle)) for c in ("performance", "risques", "snt")
                 if c in lignes and lignes[c].statut == NON_CONFORME]
    par_activites = "présentation par activités (budget-programmes) : oui" in detail
    if canevas == "Oui":
        preambule += " Le canevas en vigueur a été utilisé."
    elif canevas.startswith("Partiellement"):
        preambule += (" Le canevas en vigueur n'a été que partiellement observé"
                      + (" : si la présentation par activités, propre au budget-programmes, est adoptée, " if par_activites else " : ")
                      + (("les rubriques nouvelles introduites en 2023 (" + enumerer(nouvelles) + ") ne sont pas traitées."
                          if len(nouvelles) > 1 else f"la rubrique nouvelle introduite en 2023 ({nouvelles[0]}) n'est pas traitée.")
                         if nouvelles else "plusieurs rubriques du canevas de 2023 ne sont pas traitées."))
    else:
        preambule += (" Le rapport ne suit pas le canevas en vigueur ; sa présentation semble se référer à une version "
                      "antérieure de ce document.")
    paragraphes.append(preambule)

    # 2. Structuration
    presentes = [PARTIES[c] for c in PARTIES if c in lignes and lignes[c].statut in (CONFORME, A_VERIFIER)]
    absentes = [PARTIES[c] for c in PARTIES if c in lignes and lignes[c].statut == NON_CONFORME]
    struct = ""
    if presentes:
        struct = f"Sur le plan de la structuration, le rapport comporte {enumerer(presentes)}."
    if absentes:
        struct += (" En revanche, " if struct else "Sur le plan de la structuration, ")
        struct += f"{enumerer(absentes)} {'ne figurent pas' if len(absentes) > 1 else 'ne figure pas'} dans le document."
    manquantes: dict[str, list[str]] = {}
    vides, peu = [], []
    for rub in RUBRIQUES:
        l = lignes.get(rub.code)
        if not l or rub.niveau == 1 or rub.cas_echeant:
            continue
        parent = rub.parent if rub.niveau == 2 else PAR_CODE[rub.parent].parent or rub.parent
        if l.statut == NON_CONFORME and "mais rubrique non renseignée" in l.precision:
            vides.append(_guillemets(rub.libelle))
        elif l.statut == NON_CONFORME and lignes.get(parent) and lignes[parent].statut != NON_CONFORME:
            manquantes.setdefault(rub.parent, []).append(rub.code)
        if "peu développée" in l.precision:
            peu.append(_guillemets(rub.libelle))
    sans_distinction = set(manquantes.get("difficultes_suggestions", [])) >= {"difficultes", "suggestions"}
    if sans_distinction:
        manquantes["difficultes_suggestions"] = [c for c in manquantes["difficultes_suggestions"]
                                                 if c not in ("difficultes", "suggestions")]
        if not manquantes["difficultes_suggestions"]:
            del manquantes["difficultes_suggestions"]
    if manquantes:
        blocs = [f"au titre {AU_TITRE.get(p, 'de ' + _min(PAR_CODE[p].libelle))}, "
                 + enumerer([RUBRIQUES_PHRASE.get(c, _min(PAR_CODE[c].libelle)) for c in r])
                 for p, r in manquantes.items()]
        struct += (" Par ailleurs, au sein des parties traitées, plusieurs rubriques obligatoires font défaut, à savoir : "
                   + " ; ".join(blocs) + ".")
    if sans_distinction:
        struct += (" La partie consacrée aux difficultés et suggestions ne distingue pas les difficultés rencontrées "
                   "des suggestions formulées, contrairement aux prescriptions du canevas.")
    if vides:
        struct += (f" Les rubriques {enumerer(vides)}, bien qu'annoncées par un intitulé, ne sont pas renseignées."
                   if len(vides) > 1 else f" La rubrique {vides[0]}, bien qu'annoncée par un intitulé, n'est pas renseignée.")
    if peu:
        struct += (f" Les développements consacrés aux rubriques {enumerer(peu)} demeurent succincts."
                   if len(peu) > 1 else f" Les développements consacrés à la rubrique {peu[0]} demeurent succincts.")
    # Lisibilité : plan annoncé, sommaire
    sommaire = lignes.get("sommaire")
    if sommaire:
        if sommaire.statut == CONFORME:
            struct += " Le plan annoncé concorde avec les intitulés du corps du rapport, ce qui en facilite la lecture."
        elif "Aucune table des matières" in sommaire.precision:
            struct += " Le rapport ne comporte ni table des matières ni plan annoncé, ce qui nuit à sa lisibilité."
        else:
            nets = [re.sub(r"^\s*[IVXLC\d]+(?:\.\d+)*\s*[-–.)]\s*", "", e).strip() for e in res.structure.sommaire_absents]
            nets = [e.capitalize() if e.isupper() else e for e in nets]  # intitulés en capitales
            ecarts = [f"« {e[:1].upper()}{e[1:]} »" for e in nets if e][:5]
            struct += (" Le plan annoncé n'est pas fidèlement suivi : "
                       + (f"les intitulés {enumerer(ecarts)} n'y trouvent pas de développement correspondant."
                          if len(ecarts) > 1 else f"l'intitulé {ecarts[0]} n'y trouve pas de développement correspondant."
                          if ecarts else "certains intitulés n'y trouvent pas de développement correspondant."))
    paragraphes.append(struct.strip())

    # 3. Tableaux
    codes = sorted(TABLEAU_PAR_CODE)
    presents = [c for c in codes if c in lignes and lignes[c].statut in (CONFORME, A_VERIFIER)]
    tab_absents = [c for c in codes if c in lignes and lignes[c].statut == NON_CONFORME]
    tabl = (f"S'agissant de la présentation des données chiffrées, {nombre(len(presents))} des huit (08) tableaux "
            f"prescrits par le canevas {'sont produits' if len(presents) > 1 else 'est produit'}")
    if tab_absents:
        libs = [f"n°{TABLEAU_PAR_CODE[c].numero} ({_min(TABLEAU_PAR_CODE[c].libelle)})" for c in tab_absents]
        tabl += f" ; {'les tableaux' if len(libs) > 1 else 'le tableau'} {enumerer(libs)} {'font' if len(libs) > 1 else 'fait'} défaut."
    else:
        tabl += "."
    numerotation, sans_titre, sans_source = [], [], []
    for c in presents:
        t = res.tableaux.par_code.get(c)
        if not t:
            continue
        lib = _guillemets(TABLEAU_PAR_CODE[c].libelle)
        m = RE_LEGENDE.match(t.bloc.legende or "")
        if not t.bloc.legende:
            sans_titre.append(lib)
        elif m and int(m.group(2)) != TABLEAU_PAR_CODE[c].numero:
            numerotation.append((abs(int(m.group(2)) - TABLEAU_PAR_CODE[c].numero),
                                 f"le tableau {lib} porte le numéro {m.group(2)} au lieu du numéro {TABLEAU_PAR_CODE[c].numero}"))
        if "source non indiquée" in lignes[c].precision:
            sans_source.append(f"n°{TABLEAU_PAR_CODE[c].numero}")
    if numerotation:
        numerotation.sort(key=lambda x: -x[0])  # écarts de numérotation les plus marqués en premier
        tabl += (" La numérotation des tableaux ne respecte pas celle du canevas ; à titre d'illustration, "
                 + enumerer([x[1] for x in numerotation[:2]]) + ".")
    if sans_titre:
        tabl += (f" Les tableaux {enumerer(sans_titre)} sont dépourvus de titre et de numéro." if len(sans_titre) > 1
                 else f" Le tableau {sans_titre[0]} est dépourvu de titre et de numéro.")
    if sans_source:
        tabl += (f" La source des données n'est pas indiquée pour {'les tableaux' if len(sans_source) > 1 else 'le tableau'} "
                 f"{enumerer(sans_source)}.")
    supplementaires = sum(1 for t in res.tableaux.tableaux if not t.code or not t.principal)
    if supplementaires:
        tabl += (f" En outre, {nombre(supplementaires)} tableau{'x' if supplementaires > 1 else ''} complémentaire"
                 f"{'s' if supplementaires > 1 else ''}, non prévu{'s' if supplementaires > 1 else ''} par le canevas, "
                 f"{'ont' if supplementaires > 1 else 'a'} été inséré{'s' if supplementaires > 1 else ''}, ce qui alourdit "
                 "la présentation sans se substituer aux tableaux prescrits.")
    paragraphes.append(tabl)

    # 4. Forme matérielle
    sig = lignes.get("signature")
    if sig:
        if sig.statut == CONFORME:
            paragraphes.append("Le rapport est dûment daté et signé.")
        elif sig.statut == A_VERIFIER:
            paragraphes.append("La date, la signature et le cachet du Contrôleur Budgétaire sont à vérifier sur l'original.")
        elif "pas daté" in sig.precision:
            paragraphes.append("Le rapport, qui porte le nom du Contrôleur Budgétaire, n'est toutefois ni daté ni "
                               "revêtu de sa signature en fin de document, ce qui en altère la valeur formelle.")
        else:
            paragraphes.append("Le rapport n'est ni daté ni signé, ce qui en altère la valeur formelle.")

    # 5. Conclusion et recommandations
    recos = []
    if absentes or manquantes or vides:
        recos.append("se conformer strictement au canevas en vigueur en traitant l'ensemble des rubriques prescrites")
    if tab_absents or numerotation or sans_titre:
        recos.append("produire l'intégralité des tableaux du canevas en respectant leur numérotation et leurs intitulés")
    if sans_source:
        recos.append("indiquer systématiquement la source des données présentées")
    if sommaire and sommaire.statut != CONFORME:
        recos.append("veiller à la concordance entre le plan annoncé et le contenu du rapport")
    if peu:
        recos.append("approfondir les rubriques insuffisamment développées")
    if sig and sig.statut == NON_CONFORME:
        recos.append("dater et signer le rapport")
    if res.score_forme >= 90 and not recos:
        conclusion = ("Dans l'ensemble, le rapport est bien structuré et conforme au canevas ; sa présentation n'appelle "
                      "pas d'observation particulière.")
    elif res.score_forme >= 75:
        conclusion = ("Dans l'ensemble, la présentation du rapport est satisfaisante. Il conviendrait néanmoins "
                      + enumerer(_de(recos)) + ".") if recos else "Dans l'ensemble, la présentation du rapport est satisfaisante."
    else:
        conclusion = ("Au regard de ce qui précède, la forme du rapport appelle des améliorations substantielles. "
                      + (f"Il est recommandé au Contrôleur Budgétaire {enumerer(_de(recos))}." if recos else ""))
    paragraphes.append(conclusion.strip())
    return "\n".join(p for p in paragraphes if p)


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


def _ex_calcul(c) -> str:
    colonne = re.search(r"\(colonne ([^)]+)\)", c.message)
    ligne = f"la ligne « {c.ligne} »" if c.ligne and not c.ligne.startswith(("Total", "total")) else (
        "le total général" if c.ligne.lower().startswith("total") else "une ligne")
    return (f"au {_tableau_court(c.tableau)}, {ligne}" + (f" ({colonne.group(1)})" if colonne else "")
            + f" affiche {c.constate}{' FCFA' if re.search(r'\d{3}$', c.constate or '') else ''} alors que "
            f"{'la somme des lignes' if c.controle.startswith(('Total', 'Sous-total')) else 'le montant recalculé'} s'établit à {c.attendu}{' FCFA' if re.search(r'\d{3}$', c.attendu or '') else ''}")


# ------------------------------------------------------------------ fond
def appreciation_fond(res) -> str:
    cs = res.constats
    majeures = [c for c in cs if c.gravite == "Majeure"]
    paragraphes = []
    if res.score_fond is not None:
        p = (f"Sur le fond, l'examen du rapport fait ressortir un niveau de fiabilité et de cohérence jugé "
             f"{_mention(res, res.score_fond, masculin=True)} ({res.score_fond:.0f} % des points vérifiables). ")
    else:
        p = "Sur le fond, aucun point n'a pu être vérifié de manière automatique. "
    p += (f"Les contrôles effectués ont mis en évidence {nombre(len(cs), True)} anomalies, parmi lesquelles "
          f"{nombre(len(majeures), True)} de caractère majeur ; leur détail figure à l'onglet « Contrôles automatiques »." if cs else
          "Les contrôles effectués n'ont révélé aucune anomalie.")
    paragraphes.append(p)

    # Fiabilité
    calc = [c for c in res.tableaux.constats if c.nature == "fiabilite"
            and not c.controle.startswith(("Signe", "Base de calcul", "Codes d'activité"))]
    presentation = [c for c in res.tableaux.constats if c.controle.startswith(("Signe", "Base de calcul"))]
    if calc:
        types = []
        for motif, libelle in ((r"^(Total|Sous-total)", "les totaux et sous-totaux"), (r"^Taux", "les taux"),
                               (r"Disponible|Écart =", "les disponibles"), (r"^Variation", "les variations"),
                               (r"^Montant actuel", "les montants après modification")):
            if any(re.search(motif, c.controle) for c in calc):
                types.append(libelle)
        principaux = [c for c in calc if c.gravite == "Majeure" and not c.tableau.startswith("«")] or calc
        # l'erreur la plus significative, de préférence sur les montants d'exécution
        exemple = max(principaux, key=lambda c: (bool(re.search(r"colonne (réalisation|prises en charge|recouvrement)", c.message)),
                                                 _ecart_num(c)))
        p = (f"Au titre de la fiabilité, les tableaux comportent {nombre(len(calc), True)} erreurs de calcul portant "
             f"notamment sur {enumerer(types) or 'les montants présentés'} ; à titre d'exemple, {_ex_calcul(exemple)}.")
        if presentation:
            p += (" Des anomalies de présentation sont également relevées, telles que des baisses présentées sans signe "
                  "négatif ou des taux calculés sur une base différente de celle prescrite par le canevas.")
        paragraphes.append(p)
    elif res.tableaux.par_code:
        paragraphes.append("Au titre de la fiabilité, les calculs des tableaux ont été vérifiés sans anomalie.")

    # Cohérence
    controles = {c.controle: c for c in cs}
    coh = []
    eq = next((c for c in cs if c.controle.startswith("Équilibre budgétaire")), None)
    if eq:
        coh.append(f"les ressources ({eq.constate} FCFA) et les emplois ({eq.attendu} FCFA) présentés ne sont pas équilibrés")
    if any(c.startswith("Même répartition par nature") for c in controles):
        coh.append("la répartition des crédits par nature de dépense diffère entre la présentation des emplois et "
                   "l'exécution des dépenses")
    if any(c.startswith("Budget N") for c in controles):
        coh.append("les montants du budget diffèrent d'un tableau à l'autre")
    if any("cité" in c and c.startswith("Cohérence du taux") for c in controles):
        coh.append("certains taux cités dans le texte ne correspondent pas à ceux des tableaux")
    if "Sens du résultat budgétaire" in controles:
        coh.append("le sens du résultat budgétaire indiqué dans le texte est erroné")
    if {"Exercice cité conforme à la période", "Trimestre cité conforme à la période"} & controles.keys():
        coh.append("le texte comporte des références à une autre période, vraisemblablement reprises d'un rapport antérieur")
    if "Événements datés dans la période" in controles:
        coh.append("des événements présentés comme survenus au cours de la période sont datés en dehors de celle-ci")
    if "Codes d'activité uniques" in controles:
        coh.append("des codes d'activité sont erronés ou attribués à plusieurs activités")
    if coh:
        paragraphes.append(f"Au titre de la cohérence, il apparaît que {enumerer(coh)}.")

    # Décret
    if res.confrontation:
        from .decret import CONFORME as D_OK, ECART as D_ECART
        ok = [THEMES.get(p.theme, _min(p.theme)) for p in res.confrontation.points if p.statut == D_OK]
        ec = [p for p in res.confrontation.points if p.statut == D_ECART]
        p = f"La confrontation du rapport avec le {res.decret.reference.replace('Décret', 'décret')} portant création de l'établissement "
        p += (f"en atteste la conformité en ce qui concerne {enumerer(ok)}" if ok else "ne permet de valider aucun élément")
        p += (" ; elle révèle en revanche que " + enumerer([_ecart_decret(x) for x in ec]) + "." if ec else ".")
        paragraphes.append(p)

    # Situation d'exécution
    rap = res.rapprochement
    if rap:
        d = res.situation.date_arrete
        concordants = [l for l in rap.lignes if l.statut == "Concordant"]
        decales = [l for l in rap.lignes if l.statut == "Écart (décalage de date)"]
        p = (f"Le rapprochement avec la situation d'exécution issue du système d'information budgétaire"
             + (f", arrêtée au {d:%d/%m/%Y}," if d else "") + f" confirme {nombre(len(concordants))} des "
             f"{nombre(len([l for l in rap.lignes if l.statut != 'Non comparable']))} agrégats comparés"
             + (f", {nombre(len(decales))} autres présentant des écarts susceptibles de résulter du décalage de date"
                if decales else ""))
        impossibles = [l for l in rap.detail + rap.lignes if "impossible" in l.note]
        budget = next((l for l in rap.lignes if l.libelle == "Budget actuel de dépenses" and l.statut == "Écart"), None)
        constats_sit = []
        if impossibles:
            ex = next((l for l in impossibles if l.code), impossibles[0])
            constats_sit.append("certains montants d'exécution du rapport excèdent ceux de la situation de référence, "
                                "pourtant postérieure, ce qui atteste leur inexactitude "
                                f"(à titre d'exemple, {(('activité ' + ex.code) if ex.code else _min(ex.libelle))} : "
                                f"{_fcfa(ex.rapport)} contre {_fcfa(ex.situation)})")
        if budget:
            constats_sit.append(f"le budget actuel des dépenses est présenté pour {_fcfa(budget.rapport)} au lieu de "
                                f"{_fcfa(budget.situation)}, les mesures de régulation n'ayant pas été répercutées")
        autres = [l for l in rap.detail if l.statut == "Écart" and "impossible" not in l.note]
        if autres and not budget:
            constats_sit.append(f"{nombre(len(autres))} montants par ligne ne concordent pas avec la situation de référence")
        p += (" ; il fait toutefois apparaître que " + enumerer(constats_sit) + "." if constats_sit else ".")
        if rap.date_conforme is False and d:
            p += (f" Cette situation n'étant pas arrêtée à la date de fin de période ({res.periode.fin:%d/%m/%Y}), les "
                  "écarts de faible ampleur demeurent à confirmer.")
        paragraphes.append(p)

    # Rubriques non appréciables
    absentes = [_guillemets(l.libelle.strip(" -")) for l in res.fond if l.ligne and l.fiabilite == "Non renseigné"]
    if absentes:
        paragraphes.append(f"Enfin, {nombre(len(absentes), True)} rubriques étant absentes ou non renseignées, "
                           "leur fond n'a pu être apprécié ; les rubriques présentes appellent par ailleurs une "
                           "appréciation qualitative du Chargé d'Études.")
    return "\n".join(paragraphes)


# ------------------------------------------------------------------ appréciation générale (partie V)
def appreciation_generale(res) -> str:
    from .decret import CONFORME as D_OK, ECART as D_ECART
    lignes = {l.code: l for l in res.forme}
    fond = (f" et le fond une appréciation {_mention(res, res.score_fond)} ({res.score_fond:.0f} % des points vérifiables)"
            if res.score_fond is not None else "")
    p1 = (f"Au terme de son examen, le rapport du Contrôleur Budgétaire placé auprès de {_epn(res)}, afférent "
          f"{periode_phrase(res)}, appelle quant à la forme une appréciation {_mention(res, res.score_forme)} "
          f"({res.score_forme:.0f} % de conformité au canevas){fond}.")
    e = res.ecart_jours
    p1 += (" La date de réception par la DCB n'étant pas renseignée, le respect du délai de transmission reste à apprécier."
           if e is None else " Le rapport a été transmis dans les délais." if e <= 0
           else f" Le rapport a été transmis avec un retard de {nombre(e)} jour{'s' if e > 1 else ''}.")

    # Points positifs
    forts = []
    if res.score_forme >= 90:
        forts.append("le canevas de rédaction est globalement respecté")
    if res.confrontation:
        ok = [THEMES.get(p.theme, _min(p.theme)) for p in res.confrontation.points if p.statut == D_OK]
        if ok:
            forts.append(f"la présentation de l'établissement est conforme au décret de création en ce qui concerne {enumerer(ok)}")
    if res.rapprochement:
        def sens(l):
            return "recettes" if re.search(r"recette|ressource|recouvr", l.libelle, re.I) else "dépenses"
        statut = {}
        for l in res.rapprochement.lignes + res.rapprochement.detail:
            if l.statut in ("Concordant", "Écart") and not l.libelle.startswith("Résultat"):
                cle = sens(l) if not l.code else ("recettes" if len(l.code) == 6 and l.code.startswith("7") else "dépenses")
                statut.setdefault(cle, set()).add(l.statut)
        complets = [k for k in ("recettes", "dépenses") if statut.get(k) == {"Concordant"}]
        partiels = [k for k in ("recettes", "dépenses") if statut.get(k, set()) >= {"Concordant", "Écart"}]
        blocs = ([f"l'ensemble des données de {' et de '.join(complets)}"] if complets else []) + \
                ([f"une partie des données de {' et de '.join(partiels)}"] if partiels else [])
        if blocs:
            forts.append(f"{enumerer(blocs)} concordent avec la situation d'exécution de référence")
    if res.tableaux.par_code and not [c for c in res.tableaux.constats if c.nature == "fiabilite"]:
        forts.append("les tableaux chiffrés sont arithmétiquement justes")
    if lignes.get("signature") and lignes["signature"].statut == CONFORME:
        forts.append("le rapport est dûment daté et signé")
    p2 = (f"Au titre des points positifs, il convient de relever que {enumerer(forts)}." if forts
          else "L'examen ne fait ressortir aucun point positif particulier.")

    # Insuffisances
    faibles = []
    nb_rub = sum(1 for l in res.forme if l.statut == NON_CONFORME and l.code in PAR_CODE and not PAR_CODE[l.code].cas_echeant)
    nb_tab = sum(1 for c in TABLEAU_PAR_CODE if c in lignes and lignes[c].statut == NON_CONFORME)
    if nb_rub or nb_tab:
        faibles.append("le canevas n'est pas intégralement respecté, "
                       + enumerer(([f"{nombre(nb_rub, True)} rubriques obligatoires"] if nb_rub else [])
                                  + ([f"{nombre(nb_tab)} tableau{'x' if nb_tab > 1 else ''} prescrit{'s' if nb_tab > 1 else ''}"] if nb_tab else []))
                       + (" faisant défaut" if (nb_rub + nb_tab) > 1 else " faisant défaut"))
    calc = [c for c in res.tableaux.constats if c.nature == "fiabilite" and c.gravite == "Majeure"]
    if calc:
        faibles.append(f"les tableaux comportent {nombre(len(calc), True)} erreurs de calcul majeures")
    coh = [c for c in res.constats if c.nature == "coherence" and c.gravite != "Information"]
    if coh:
        faibles.append(f"{nombre(len(coh), True)} incohérences affectent les données présentées, entre tableaux ou entre "
                       "le texte et les tableaux")
    if res.confrontation:
        ec = [p for p in res.confrontation.points if p.statut == D_ECART]
        ref = next((p for p in ec if p.theme.startswith("Référence du texte")), None)
        if ref:
            faibles.append(f"le texte de création est mal référencé, le décret applicable étant le "
                           f"{res.decret.reference.replace('Décret ', '')}")
        if [p for p in ec if p is not ref]:
            faibles.append("le cadre institutionnel de l'EPN n'est pas fidèlement rappelé ("
                           + enumerer([p.theme.lower() for p in ec if p is not ref]) + ")")
        if any(p.rubrique == "coges" and "aucune session" in p.constat for p in res.confrontation.points):
            faibles.append("l'absence de toute session du Conseil de gestion n'est pas analysée au regard de ses "
                           "conséquences sur la gouvernance de l'établissement")
    rap = res.rapprochement
    budget = None
    if rap:
        if any("impossible" in l.note for l in rap.detail + rap.lignes):
            faibles.append("certains montants d'exécution sont démentis par la situation d'exécution de référence")
        budget = next((l for l in rap.lignes if l.libelle == "Budget actuel de dépenses" and l.statut == "Écart"), None)
        if budget:
            faibles.append("les mesures de régulation budgétaire ne sont pas répercutées dans la présentation des dépenses")
    if lignes.get("signature") and lignes["signature"].statut == NON_CONFORME:
        faibles.append("le rapport n'est ni daté ni signé")
    p3 = ("Le rapport présente toutefois des insuffisances notables : " + "; ".join(faibles).replace(";", " ;") + "."
          if faibles else "Aucune insuffisance majeure n'a été relevée.")

    # Recommandations
    recos = []
    if nb_rub or nb_tab:
        recos.append("se conformer strictement au canevas en vigueur")
    if calc or coh:
        recos.append("fiabiliser les données chiffrées en vérifiant les calculs et la concordance des tableaux et des commentaires")
    if res.confrontation and any(p.statut == D_ECART for p in res.confrontation.points):
        recos.append(f"rappeler fidèlement le cadre institutionnel de l'établissement, en visant le {res.decret.reference.replace('Décret', 'décret')}")
    if rap and (any("impossible" in l.note for l in rap.detail + rap.lignes) or budget):
        recos.append("établir les tableaux d'exécution à partir de la situation du système d'information budgétaire "
                     "arrêtée à la fin de la période" + (", sur la base du budget actuel" if budget else ""))
    if {"Exercice cité conforme à la période", "Trimestre cité conforme à la période"} & {c.controle for c in res.constats}:
        recos.append("actualiser les mentions de période reprises de rapports antérieurs")
    if lignes.get("signature") and lignes["signature"].statut == NON_CONFORME:
        recos.append("dater et signer le rapport")
    if e is not None and e > 0:
        recos.append("respecter les délais de transmission des rapports à la DCB")
    p4 = (f"En conséquence, il est recommandé au Contrôleur Budgétaire {enumerer(_de(recos))}." if recos else "")
    if rap and rap.date_conforme is False and res.situation.date_arrete:
        p4 += (f" Il conviendrait par ailleurs que la DCB obtienne la situation d'exécution arrêtée au "
               f"{res.periode.fin:%d/%m/%Y} afin de confirmer les écarts relevés.")
    return "\n".join(p for p in (p1, p2, p3, p4.strip()) if p)
