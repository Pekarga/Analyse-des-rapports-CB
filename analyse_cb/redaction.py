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
    return "\n\n".join(p for p in paragraphes if p)


def _de(actions: list[str]) -> list[str]:
    """« se conformer », « indiquer » → « de se conformer », « d'indiquer »."""
    return [("d'" + a) if re.match(r"^[aeiouyéèêh]", a, re.I) else ("de " + a) for a in actions]
