"""Rédaction des commentaires de la grille et des constats en phrases simples, et mise en paragraphes.

Les champs techniques (statuts, précisions) restent utilisés par les contrôles ; ce module produit le texte
affiché dans le fichier d'analyse.
"""
from __future__ import annotations

import re

from .canevas import PAR_CODE, TABLEAU_PAR_CODE, enfants
from .lecture import RE_LEGENDE
from .redaction import COURT, RUBRIQUES_PHRASE, enumerer, nombre
from .structure import _sans_numero
from .texte import lire_nombre

CONFORME, NON_CONFORME, A_VERIFIER, NON_APPLICABLE = "Conforme", "Non conforme", "À vérifier", "Non applicable"
FIABLE, NON_FIABLE, COHERENT, INCOHERENT = "Fiable", "Non fiable", "Cohérent", "Incohérent"
NON_RENSEIGNE, SANS_OBJET = "Non renseigné", "Sans objet"

# Tableaux du canevas rattachés aux lignes du fond
TABLEAUX_DE = {"pres_generale": ("T1", "T2"), "pres_ressources": ("T3",), "pres_emplois": ("T4",),
               "exec_recettes": ("T5",), "exec_depenses": ("T6",), "differes_rejets": ("T7", "T8")}


# ------------------------------------------------------------------ outils
def pluriel(n: int, singulier: str, pluriel_: str) -> str:
    return singulier if n == 1 else pluriel_


def compte(n: int, singulier: str, pluriel_: str, feminin: bool = False) -> str:
    """« une erreur », « deux (02) erreurs », « 33 erreurs »."""
    if n == 1:
        return f"{'une' if feminin else 'un'} {singulier}"
    return f"{nombre(n, feminin)} {pluriel_}"


def _minuscule(t: str) -> str:
    """Première lettre en minuscule, en préservant les sigles (EPN, COGES)."""
    return t if len(t) > 1 and t[1].isupper() else t[:1].lower() + t[1:]


def majuscule(t: str) -> str:
    return t[:1].upper() + t[1:] if t else t


def phrase(t: str) -> str:
    t = re.sub(r"\s+", " ", t or "").strip()
    return t if not t or t[-1] in ".!?…»" else t + "."


def aerer(texte: str, car_par_ligne: int = 175, lignes: int = 3) -> str:
    """Découpe le texte en paragraphes d'environ `lignes` lignes (au plus), aux limites de phrases,
    et sépare les paragraphes par une ligne vide."""
    limite = car_par_ligne * lignes
    blocs = []
    for paragraphe in (p.strip() for p in texte.split("\n") if p.strip()):
        if len(paragraphe) <= limite:
            blocs.append(paragraphe)
            continue
        phrases = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý«(0-9])", paragraphe)
        courant = ""
        for ph in phrases:
            if courant and len(courant) + 1 + len(ph) > limite:
                blocs.append(courant)
                courant = ph
            else:
                courant = f"{courant} {ph}".strip()
        if courant:
            blocs.append(courant)
    return "\n\n".join(blocs)


def _titre(det) -> str:
    """Titre tel qu'il figure dans le rapport (sans sa numérotation)."""
    return _sans_numero(det.titre or "").strip(" :-–").replace("’", "'")


def _court(libelle: str, n: int = 60) -> str:
    libelle = re.sub(r"\s+", " ", libelle or "").strip()
    return libelle if len(libelle) <= n else libelle[: n - 1].rsplit(" ", 1)[0] + "…"


def _ou(tableau: str) -> str:
    """« Tableau 6 (Exécution…) » → « au tableau n°6 » ; tableau hors canevas → « au tableau « … » »."""
    m = re.match(r"^Tableau (\d+) \(", tableau or "")
    if m:
        return f"au tableau n°{m.group(1)}"
    m = re.match(r"^« (.+?) » \[", tableau or "")
    if m:
        return f"au tableau « {_court(m.group(1), 55)} »"
    return "dans le rapport"


def _fcfa(v: str) -> str:
    return f"{v} FCFA" if re.search(r"\d{3}$", v or "") and "%" not in v else v


def _ligne(c) -> str:
    l = (c.ligne or "").strip()
    if not l:
        return ""
    if re.match(r"^total", l, re.I):
        return "le total général"
    if re.match(r"^(sous[- ]?total|s/t)", l, re.I):
        return "le sous-total"
    return f"la ligne « {_court(l, 55)} »"


# ------------------------------------------------------------------ constats
def phrase_constat(c, systeme: str = "SIGOBE") -> str:
    """Formulation simple d'un constat automatique."""
    ctl, ou, lig = c.controle, _ou(c.tableau), _ligne(c)
    col = re.search(r"\(colonne ([^)]+)\)", c.message)
    col = f" ({col.group(1)})" if col else ""
    lig_ou = f"{majuscule(ou)}, {lig}{col}" if lig else majuscule(ou)
    if ctl.startswith(("Total", "Sous-total")):
        return phrase(f"{lig_ou} affiche {_fcfa(c.constate)}, alors que la somme des lignes donne {_fcfa(c.attendu)}")
    if ctl.startswith("Taux"):
        return phrase(f"{lig_ou} : taux affiché {c.constate}, taux exact {c.attendu}")
    if ctl.startswith("Variation"):
        return phrase(f"{lig_ou} : variation affichée {_fcfa(c.constate)}, au lieu de {_fcfa(c.attendu)}")
    if ctl.startswith(("Disponible", "Écart =")):
        return phrase(f"{lig_ou} : disponible affiché {_fcfa(c.constate)}, au lieu de {_fcfa(c.attendu)}")
    if ctl.startswith("Montant actuel"):
        return phrase(f"{lig_ou} : montant après modification affiché {_fcfa(c.constate)}, au lieu de {_fcfa(c.attendu)}")
    if ctl.startswith("Signe"):
        n = re.match(r"(\d+) lignes", c.ligne or "")
        un, quoi, presente = {"Signe de la variation": ("une", "baisse", "présentée"),
                              "Signe du taux": ("un", "taux de baisse", "présenté"),
                              "Signe des modifications": ("une", "réduction de crédits", "présentée")}.get(ctl, ("une", "baisse", "présentée"))
        if n:
            return phrase(f"{majuscule(ou)}, {nombre(int(n.group(1)), True)} lignes présentent {un} {quoi} sans signe négatif")
        return phrase(f"{lig_ou} : {quoi} {presente} sans signe négatif ({c.constate} au lieu de {c.attendu})")
    if ctl.startswith("Base de calcul"):
        return phrase(f"{majuscule(ou)}, des taux sont calculés sur une autre base que celle du canevas "
                      f"(par exemple {c.constate} au lieu de {c.attendu})")
    if ctl.startswith("Codes d'activité"):
        return phrase(f"{majuscule(ou)}, un même code est attribué à plusieurs activités ({c.constate})")
    if ctl.startswith("Équilibre"):
        return phrase(f"Les ressources ({_fcfa(c.constate)}) et les emplois ({_fcfa(c.attendu)}) ne sont pas équilibrés")
    if ctl.startswith("Même répartition"):
        return phrase(f"{c.ligne} : {_fcfa(c.attendu)} au tableau n°4, contre {_fcfa(c.constate)} au tableau n°6")
    if ctl.startswith(("Budget N", "Prévisions", "Budget actuel des dépenses (T6)", "Budget initial des dépenses")):
        return phrase(f"Montants discordants entre tableaux : {c.constate} contre {c.attendu} ({_court(ctl, 70).lower()})")
    if ctl.startswith("Cohérence du taux"):
        return phrase(f"Le texte cite un taux de {c.constate}, que les tableaux ne permettent pas de retrouver"
                      + (f" (taux recalculé : {c.attendu})" if c.attendu else ""))
    if ctl.startswith("Cohérence du R"):
        return phrase(f"Le ratio {ctl.split()[-1]} cité ({c.constate}) ne correspond pas au calcul ({c.attendu})")
    if ctl == "Sens du résultat budgétaire":
        return phrase(f"Le texte qualifie le résultat budgétaire de {c.constate}, alors qu'il est {c.attendu}")
    if ctl == "Montant du résultat budgétaire":
        return phrase(f"Le montant du résultat budgétaire ({_fcfa(c.attendu)}) n'est pas retrouvé dans le texte")
    if ctl == "Calcul exact dans le texte":
        return phrase(f"Un calcul du texte est inexact : {c.constate} au lieu de {c.attendu}")
    if ctl == "Exercice cité conforme à la période":
        return phrase(f"Le texte mentionne l'exercice {c.constate} au lieu de {c.attendu}")
    if ctl == "Trimestre cité conforme à la période":
        cite = re.sub(r"(\d)\s*(eme|ème|e)\b", r"\1e", c.constate)
        return phrase(f"Le texte renvoie au {cite} au lieu du {c.attendu}, sans doute par reprise d'un rapport antérieur")
    if ctl == "Événements datés dans la période":
        return phrase(f"Un événement présenté comme tenu au cours de la période est daté du {c.constate}")
    if ctl == "Date de la situation d'exécution":
        return phrase(f"La situation d'exécution est arrêtée au {c.constate}, et non à la fin de la période ({c.attendu})")
    if ctl == "Concordance avec la situation d'exécution":
        libelle = c.message.split(" : ", 1)[0]
        impossible = "impossible" in c.message
        return phrase(f"{libelle} : {_fcfa(c.constate)} dans le rapport, contre {_fcfa(c.attendu)} au {systeme}"
                      + (" ; ce montant est impossible, la situation étant arrêtée plus tard" if impossible else ""))
    if ctl == "Concordance des lignes avec la situation d'exécution":
        n = re.match(r"(\d+) montant", c.message)
        ex = c.message.split(" : ", 1)[-1].split(" ; ")[0]
        k = int(n.group(1)) if n else 0
        return phrase(f"{majuscule(ou)}, {compte(k, 'montant diffère', 'montants diffèrent')} du {systeme}"
                      + (", dont certains sont impossibles compte tenu de la date de la situation" if "impossible" in c.message else "")
                      + f" (par exemple {ex.rstrip('.…')})")
    if ctl.startswith("Texte de création"):
        m = re.search(r"le n°([\w\-/]+), alors que le décret de création est le n°([\w\-/]+)", c.message)
        if m:
            return phrase(f"Le texte de création est cité sous le n°{m.group(1)} au lieu du n°{m.group(2)}")
    if ctl.startswith("Mode de financement conforme"):
        return "Le mode de financement prévu par le décret de création n'est pas présenté dans l'introduction."
    if ctl.startswith("Missions conformes"):
        return phrase("Les missions fixées par le décret ne sont que partiellement rappelées")
    if ctl.startswith("Organisation conforme"):
        return phrase("Certains organes prévus par le décret ne sont pas évoqués")
    if ctl.startswith("Périodicité des sessions"):
        return phrase("La périodicité des sessions du Conseil de gestion fixée par le décret n'est pas respectée")
    if ctl.startswith("Ressources budgétées"):
        return phrase("Des ressources non prévues par le décret sont inscrites au budget")
    if ctl.startswith("Tableau vide") or ctl.startswith("Tableau non renseigné"):
        return phrase(f"{majuscule(ou)} est présent mais n'est pas renseigné")
    # À défaut : message d'origine, débarrassé des mentions techniques
    m = re.sub(r"\s*\[(OCR|format du tableau \d)\]", "", c.message)
    m = m.replace(" (même écart sur plusieurs colonnes)", "")
    return phrase(m)


# ------------------------------------------------------------------ forme
def commentaire_forme(l, res) -> str:
    s = res.structure
    if l.code in TABLEAU_PAR_CODE:
        return _forme_tableau(l, res)
    if l.code == "tableaux":
        exiges = [c for c in sorted(TABLEAU_PAR_CODE) if not TABLEAU_PAR_CODE[c].ignoree]
        manquants = [f"n°{TABLEAU_PAR_CODE[c].numero}" for c in exiges if c not in res.tableaux.par_code]
        total = len(res.tableaux.tableaux)
        hors = sum(1 for t in res.tableaux.tableaux if not t.code or not t.principal)
        debut = (f"{pluriel(len(manquants), 'Le tableau', 'Les tableaux')} {enumerer(manquants)} "
                 f"{pluriel(len(manquants), 'manque', 'manquent')}. ") if manquants else (
            "Les huit tableaux du canevas sont présents. " if len(exiges) == 8 else
            f"Les {nombre(len(exiges))} tableaux exigés par le canevas sont présents. ")
        return debut + f"Le rapport compte {compte(total, 'tableau', 'tableaux')}" + (
            f", dont {nombre(hors)} hors canevas." if hors else ".")
    if l.code == "sommaire":
        if l.statut == CONFORME:
            return "Le plan annoncé correspond aux titres du rapport."
        if "Aucune table des matières" in l.precision:
            return "Le rapport n'a ni sommaire ni plan annoncé."
        nets = [re.sub(r"^\s*[IVXLC\d]+(?:\.\d+)*\s*[-–.)]\s*", "", e).strip() for e in s.sommaire_absents]
        nets = [f"« {majuscule(e.capitalize() if e.isupper() else e)} »" for e in nets if e]
        sujet = compte(len(nets), "intitulé du plan annoncé n'a", "intitulés du plan annoncé n'ont")
        return f"{majuscule(sujet)} pas de développement dans le rapport : {enumerer(nets[:5])}."
    if l.code == "signature":
        if l.statut == CONFORME:
            return "Le rapport est daté et signé."
        if l.statut == A_VERIFIER:
            return "Date, signature et cachet à contrôler sur l'original (document scanné)."
        if "pas daté" in l.precision:
            return "Le rapport porte le nom du Contrôleur Budgétaire, mais il n'est ni daté ni signé."
        return "Le rapport n'est ni daté ni signé."
    if l.code == "global_forme":
        manquantes = [RUBRIQUES_PHRASE.get(x.code, x.libelle.lower()) for x in res.forme
                      if x.code in PAR_CODE and x.statut == NON_CONFORME
                      and (not PAR_CODE[x.code].hors_grille or PAR_CODE[x.code].perso)
                      and not PAR_CODE[x.code].cas_echeant and x.precision.startswith("Rubrique absente")]
        vides = [x.libelle for x in res.forme if x.code in PAR_CODE and "mais rubrique non renseignée" in x.precision]
        if not manquantes and not vides:
            return "Toutes les rubriques obligatoires de la grille sont présentes."
        t = (f"{majuscule(compte(len(manquantes), 'rubrique obligatoire manque', 'rubriques obligatoires manquent', True))} : "
             f"{enumerer(manquantes)}." if manquantes else "")
        if vides:
            t += f" {pluriel(len(vides), 'Une rubrique est titrée', 'Des rubriques sont titrées')} mais vide{pluriel(len(vides), '', 's')} : {enumerer(vides)}."
        return t.strip()
    rub = PAR_CODE.get(l.code)
    if not rub:
        return l.precision
    det = s[l.code]
    if l.code == "annexes":
        return "Des annexes sont jointes au rapport." if det.trouvee else "Pas d'annexes."
    if l.statut == NON_APPLICABLE:
        if rub.annuel_seulement and not res.periode.annuel:
            return "Exigée seulement dans le rapport annuel."
        return "Non mentionnée ; l'établissement n'est pas concerné."
    if "mais rubrique non renseignée" in l.precision:
        return f"Le titre « {_titre(det)} » figure, mais la rubrique n'est pas renseignée."
    if l.precision.startswith("Rubrique absente"):
        t = "Absente du rapport."
    elif det.mode == "titre":
        t = f"Présente sous le titre « {_titre(det)} »."
    elif det.mode == "texte":
        t = "Traitée dans le texte, sans titre propre."
    else:
        t = phrase(l.precision)
    manquants = [COURT.get(e.code) or RUBRIQUES_PHRASE.get(e.code, e.libelle.lower()) for e in enfants(l.code)
                 if not s[e.code].trouvee and not e.cas_echeant and not (e.annuel_seulement and not res.periode.annuel)]
    if manquants and det.trouvee:
        t += " Il y manque " + enumerer(manquants) + "."
    if "peu développée" in l.precision:
        t += " Développement très succinct."
    return t


def _forme_tableau(l, res) -> str:
    code = l.code
    t = res.tableaux.par_code.get(code)
    if not t:
        if l.statut == A_VERIFIER or "indique l'absence" in l.precision:
            quoi = "différés" if code == "T7" else "rejets"
            return f"Absent ; le rapport indique qu'il n'y a pas eu de {quoi}."
        return "Absent du rapport."
    if "non renseigné" in l.precision:
        return "Présent, mais non renseigné."
    morceaux = []
    m = RE_LEGENDE.match(t.bloc.legende or "")
    if not t.bloc.legende:
        morceaux.append("sans titre ni numéro")
    elif m and int(m.group(2)) != TABLEAU_PAR_CODE[code].numero:
        morceaux.append(f"numéroté {m.group(2)} au lieu de {TABLEAU_PAR_CODE[code].numero}")
    texte = "Présent" + (", " + enumerer(morceaux) if morceaux else "")
    if "source non indiquée" in l.precision:
        texte += " ; la source n'est pas indiquée"
    return texte + "."


# ------------------------------------------------------------------ fond
def _extrait(det, n: int = 170) -> str:
    texte = re.sub(r"\s+", " ", det.texte or "").strip().replace("’", "'")
    if not texte:
        return ""
    phrases = re.split(r"(?<=[.!?])\s+", texte)
    ex = phrases[0]
    if len(ex) < 60 and len(phrases) > 1:
        ex = f"{ex} {phrases[1]}"
    return _court(ex, n)


def constats_ligne(code: str, res) -> list:
    noms = {res.tableaux.par_code[c].nom for c in TABLEAUX_DE.get(code, ()) if c in res.tableaux.par_code}
    # Les écarts au décret sont rédigés à part (_points_decret)
    decret = ("Texte de création", "Date du texte", "Mode de financement conforme", "Missions conformes",
              "Organisation conforme", "Périodicité des sessions", "Ressources budgétées")
    return [c for c in res.constats if c.gravite != "Information"
            and (c.rubrique == code or (noms and c.tableau in noms))
            and not c.controle.startswith(decret)]


def _points_decret(code: str, res) -> list[str]:
    conf = res.confrontation
    if not conf:
        return []
    out = []
    for p in conf.points:
        if p.rubrique != code:
            continue
        if p.theme.startswith("Référence du texte"):
            m = re.search(r"le n°([\w\-/]+), alors que le décret de création est le n°([\w\-/]+)", p.constat)
            if m:
                out.append(f"Le texte de création est cité sous le n°{m.group(1)} au lieu du n°{m.group(2)} "
                           f"({res.decret.reference.replace('Décret', 'décret')}).")
            elif p.statut == "Conforme":
                out.append(f"Le texte de création cité est conforme au {res.decret.reference.replace('Décret', 'décret')}.")
            else:
                out.append(phrase(p.constat))
        elif p.theme == "Missions":
            m = re.match(r"(\d+) mission\(s\) sur (\d+)", p.constat)
            if m and m.group(1) == m.group(2):
                out.append(f"Les {nombre(int(m.group(2)), True)} missions fixées par le décret sont rappelées.")
            elif m:
                out.append(f"Seules {nombre(int(m.group(1)), True)} des {nombre(int(m.group(2)), True)} missions du décret sont rappelées.")
        elif p.theme == "Organes de l'EPN":
            out.append("Tous les organes prévus par le décret sont évoqués." if p.statut == "Conforme"
                       else phrase(p.constat.replace("Organes prévus par le décret non évoqués", "Organes du décret non évoqués")))
        elif p.theme == "Mode de financement":
            out.append("Le mode de financement prévu par le décret n'est pas présenté." if p.statut == "Écart"
                       else "Les sources de financement citées sont conformes au décret.")
        elif p.theme == "Sessions du Conseil de gestion":
            m = re.match(r"(\d+) session\(s\) rapportée\(s\)(?: pour| \(≥) (\d+) attendue", p.constat)
            att = re.search(r"attendu sur la période : (\d+)", p.constat)
            if "aucune session" in p.constat or (m and m.group(1) == "0"):
                out.append("Aucune session du Conseil de gestion ne s'est tenue sur la période"
                           + (f", alors que le décret en prévoit au moins {nombre(int(m.group(2)), True)}" if m else "")
                           + " ; le rapport n'en analyse pas les conséquences.")
            elif m and p.statut == "Écart":
                out.append(f"Le Conseil de gestion n'a tenu que {compte(int(m.group(1)), 'session', 'sessions', True)} "
                           f"sur la période, pour {nombre(int(m.group(2)), True)} au moins selon le décret.")
            elif m:
                out.append("Le nombre de sessions du Conseil de gestion respecte la périodicité fixée par le décret.")
            elif att:
                out.append("Le rapport ne précise pas le nombre de sessions du Conseil de gestion.")
        elif p.theme == "Tutelle technique" and p.statut == "Conforme":
            out.append("La tutelle technique est mentionnée.")
        elif p.theme == "Ressources budgétées" and p.statut == "Écart":
            out.append("Des ressources non prévues par le décret sont inscrites au budget.")
    return out


def commentaire_fond(l, res) -> str:
    code = l.code
    s = res.structure
    if code == "global_fond":
        ko = [x for x in res.fond if x.code != code and x.ligne and (x.fiabilite == NON_FIABLE or x.coherence == INCOHERENT)]
        abs_ = [x for x in res.fond if x.code != code and x.ligne and x.fiabilite == NON_RENSEIGNE]
        t = (f"{majuscule(compte(len(ko), 'rubrique présente', 'rubriques présentent', True))} des anomalies de fiabilité "
             "ou de cohérence." if ko else "Aucune rubrique ne présente d'anomalie de fiabilité ou de cohérence.")
        if abs_:
            t += f" {majuscule(compte(len(abs_), 'rubrique est absente ou vide', 'rubriques sont absentes ou vides', True))}."
        return t
    rub = PAR_CODE.get(code)
    if l.fiabilite == SANS_OBJET:
        return "Rubrique propre au rapport annuel." if rub and rub.annuel_seulement and not res.periode.annuel \
            else "Sans objet pour cet établissement."
    det = s.detections.get(code)
    if l.fiabilite == NON_RENSEIGNE:
        if det and det.mode == "titre" and det.nb_mots == 0:
            return "Le titre figure, mais la rubrique est vide : son contenu ne peut être apprécié."
        return "Rubrique absente : son contenu ne peut être apprécié."
    morceaux = _points_decret(code, res)
    filles = [e for e in enfants(code) if e.code in {x.code for x in res.fond}]
    if filles:  # ligne de regroupement : synthèse des sous-rubriques
        par = {x.code: x for x in res.fond}
        ko = [_minuscule(e.libelle) for e in filles if par[e.code].fiabilite == NON_FIABLE or par[e.code].coherence == INCOHERENT]
        absentes = [_minuscule(e.libelle) for e in filles if par[e.code].fiabilite == NON_RENSEIGNE]
        if ko:
            morceaux.append(f"Anomalies relevées dans {pluriel(len(ko), 'la sous-rubrique', 'les sous-rubriques')} : "
                            f"{enumerer([_court(k, 80) for k in ko])} (détail ci-dessous).")
        if absentes:
            morceaux.append(f"{pluriel(len(absentes), 'Sous-rubrique absente', 'Sous-rubriques absentes')} : "
                            f"{enumerer([_court(a, 80) for a in absentes])}.")
    cs = constats_ligne(code, res)
    systeme = "SIGOBE" if getattr(res.situation, "systeme", "") == "SIGOBE" else "système d'information budgétaire"
    calc = [c for c in cs if c.nature == "fiabilite" and not c.controle.startswith("Concordance")]
    coh = [c for c in cs if c.nature == "coherence"]
    sit = [c for c in cs if c.controle.startswith("Concordance")]
    if calc:
        majeurs = [c for c in calc if c.gravite == "Majeure"] or calc
        exemple = max(majeurs, key=lambda c: _ecart(c))
        morceaux.append(f"{majuscule(compte(len(calc), 'erreur de calcul', 'erreurs de calcul', True))}. "
                        f"Par exemple, {phrase_constat(exemple, systeme)[0].lower()}{phrase_constat(exemple, systeme)[1:]}")
    for c in coh[:2]:
        morceaux.append(phrase_constat(c, systeme))
    if len(coh) > 2:
        morceaux.append(f"Et {compte(len(coh) - 2, 'autre incohérence', 'autres incohérences', True)}.")
    for c in sit[:2]:
        morceaux.append("Rapprochement avec le " + systeme + " : " + phrase_constat(c, systeme)[0].lower()
                        + phrase_constat(c, systeme)[1:])
    if not cs and not any("au lieu" in m or "n'est pas" in m or "Anomalies" in m for m in morceaux):
        morceaux.append("Aucune anomalie relevée.")
        if res.rapprochement and code in ("exec_recettes", "exec_depenses", "pres_ressources", "pres_emplois",
                                          "resultat_budgetaire"):
            morceaux.append(f"Les montants concordent avec le {systeme}.")
    if det and det.trouvee and not filles and (l.fiabilite in (FIABLE,) and l.coherence in (COHERENT,)):
        ex = _extrait(det)
        if ex:
            morceaux.append(f"Le CB y indique : « {ex} »")
    if det and det.trouvee and rub and det.nb_mots < rub.mots_min:
        morceaux.append("Développement très succinct.")
    return " ".join(phrase(m) for m in morceaux if m)


def _ecart(c) -> float:
    a, b = lire_nombre(c.attendu), lire_nombre(c.constate)
    return abs(a - b) if a is not None and b is not None else 0.0


# ------------------------------------------------------------------ synthèses courtes (onglet Synthèse, tableau de bord)
def synthese_decret(res) -> str:
    conf = res.confrontation
    if not conf:
        return "Décret non fourni."
    from .redaction import THEMES
    ok = [THEMES.get(p.theme, p.theme.lower()) for p in conf.points if p.statut == "Conforme"]
    ec = [THEMES.get(p.theme, p.theme.lower()) for p in conf.points if p.statut == "Écart"]
    if not ok and not ec:
        return "Rapprochement avec le décret non concluant."
    if not ec:
        return "Conforme au décret de création sur tous les points vérifiés."
    t = (f"Conforme au décret pour {enumerer(ok)}" if ok else "")
    if ec:
        t += ("" if not t else " ; ") + f"écarts sur {enumerer(ec)}"
    return majuscule(t) + "."


def synthese_situation(res) -> str:
    rap = res.rapprochement
    if not rap:
        return "Situation d'exécution non fournie." if not res.situation else "Situation d'exécution non exploitable."
    d = res.situation.date_arrete
    comparables = [l for l in rap.lignes if l.statut != "Non comparable"]
    ok = [l for l in comparables if l.statut == "Concordant"]
    dates = [l for l in comparables if l.statut == "Écart (décalage de date)"]
    ecarts = [l for l in comparables if l.statut == "Écart"]
    t = (f"Situation au {d:%d/%m/%Y} : " if d else "") + \
        f"{nombre(len(ok))} des {nombre(len(comparables))} agrégats comparés concordent"
    if dates:
        t += f", {compte(len(dates), 'écart peut s’expliquer', 'écarts peuvent s’expliquer').replace('’', chr(39))} par la date de la situation"
    if ecarts:
        t += f", {compte(len(ecarts), 'écart est relevé', 'écarts sont relevés')} (" + \
             "; ".join(_court(l.libelle, 45).lower() for l in ecarts[:3]) + ("…" if len(ecarts) > 3 else "") + ")"
    return t + "."
