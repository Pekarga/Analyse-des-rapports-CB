"""Synthèse, d'après le texte du rapport, des points que le Chargé d'Études doit faire ressortir :

- gouvernance : sessions du Conseil de gestion (COGES / COS / conseil d'administration) et du comité de trésorerie
  (CT), mise en place des organes, décisions ;
- situation du patrimoine : patrimoine existant (biens énumérés), nouvelles acquisitions, mise en œuvre de la
  comptabilité des matières ;
- dispositif de contrôle : contrôle interne budgétaire et contrôle de gestion, tels que le rapport les présente ;
- difficultés et suggestions, par catégorie (exécution du budget, contrôle de l'exécution, gestion de l'établissement).

Ces éléments complètent les commentaires du fond (partie III) et l'appréciation générale (points de satisfaction et
insuffisances).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .texte import normaliser

MOIS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}
NOMBRES = {"un": 1, "une": 1, "un seul": 1, "une seule": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6,
           "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12}
RE_NOMBRE = r"(\d{1,2}|un seul|une seule|un|une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze)"
TENUE = r"(tenu|tenue|tenus|tenues|tenir|reuni|reunie|reunis|siege|organise|eu lieu|convoque)"
# Catégories des difficultés et suggestions (canevas : exécution, contrôle de l'exécution, gestion de l'établissement)
CATEGORIES = (("execution", "à l'exécution du budget"), ("controle", "au contrôle de l'exécution du budget"),
              ("gestion", "à la gestion de l'établissement"))
NATURES_BIENS = {"vehicule": "véhicules", "engin": "engins", "ordinateur": "ordinateurs", "moto": "motos",
                 "immeuble": "immeubles", "batiment": "bâtiments", "bien": "biens"}


# ------------------------------------------------------------------ outils de texte
def phrases(texte: str) -> list[str]:
    """Phrases du texte (les retours à la ligne terminent aussi une phrase)."""
    out = []
    for ligne in (l.strip() for l in str(texte or "").split("\n")):
        for ph in re.split(r"(?<=[.!?;])\s+(?=[A-ZÀ-Ý«0-9])", ligne):
            ph = re.sub(r"\s+", " ", ph).strip(" -•")
            if len(ph.split()) >= 4:
                out.append(ph.replace("’", "'"))
    return out


def _choisir(liste: list[str], motif: str, n: int = 2, exclure: tuple[str, ...] = (), bonus: str | None = None,
             malus: str | None = None) -> list[str]:
    """Les n phrases les plus pertinentes (nombre de mots-clés), dans leur ordre d'apparition."""
    notes = []
    for i, ph in enumerate(liste):
        if ph in exclure:
            continue
        p = normaliser(ph)
        score = len(re.findall(motif, p))
        if score and bonus and re.search(bonus, p):
            score += 2
        if score and malus and re.search(malus, p) and not (bonus and re.search(bonus, p)):
            score -= 2
        if score > 0:
            notes.append((score, i, ph))
    meilleures = sorted(notes, key=lambda x: (-x[0], x[1]))[:n]
    return [ph for _, _, ph in sorted(meilleures, key=lambda x: x[1])]


def citer(liste: list[str], longueur: int = 240) -> str:
    morceaux = []
    for ph in liste:
        ph = ph.rstrip(" .;")
        morceaux.append(f"« {ph if len(ph) <= longueur else ph[:longueur].rsplit(' ', 1)[0] + '…'} »")
    return " ".join(morceaux)


def _dates(texte: str) -> list[date]:
    out = []
    n = normaliser(texte)
    for m in re.finditer(r"\b(\d{1,2})(?:er)?\s+(" + "|".join(MOIS) + r")\s+(\d{4})\b", n):
        try:
            out.append(date(int(m.group(3)), MOIS[m.group(2)], int(m.group(1))))
        except ValueError:
            pass
    for m in re.finditer(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b", n):
        try:
            out.append(date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
        except ValueError:
            pass
    return sorted(set(out))


def _sessions(texte: str) -> int | None:
    """Nombre de sessions tenues selon le texte (0 : aucune ; None : non précisé)."""
    n = normaliser(texte)
    if re.search(r"\baucun(e)?\s+(session|reunion|seance|conseil|comite|rencontre)", n) or \
            re.search(r"\bn.a (pas|jamais) (encore )?(ete )?" + TENUE, n) or \
            re.search(r"\bne s.est (pas|jamais|point) (encore )?(tenu|reuni)", n):
        return 0
    for ph in phrases(texte):
        p = normaliser(ph)
        if not re.search(TENUE, p):
            continue
        m = re.search(RE_NOMBRE + r"\s*(?:\(\s*\d+\s*\)\s*)?(?:sessions?|reunions?|seances?|fois|reprises|comites?|conseils?)", p)
        if m:
            v = m.group(1)
            return int(v) if v.isdigit() else NOMBRES.get(v)
    dates = [d for ph in phrases(texte) if re.search(TENUE, normaliser(ph)) for d in _dates(ph)]
    return len(set(dates)) or None


# ------------------------------------------------------------------ synthèses
@dataclass
class Organe:
    libelle: str
    traite: bool = False
    sessions: int | None = None
    dates: list[date] = field(default_factory=list)
    hors_periode: list[date] = field(default_factory=list)
    periodicite: str = ""  # « chaque mois », « chaque trimestre »…
    mise_en_place: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    extraits: list[str] = field(default_factory=list)

    def resume(self) -> str:
        if not self.traite:
            return f"{self.libelle} : non traité dans le rapport."
        if self.sessions is None and self.periodicite:
            s = f"réunions tenues {self.periodicite} (nombre de sessions non précisé)"
        elif self.sessions is None:
            s = "nombre de sessions non précisé"
        elif self.sessions == 0:
            s = "aucune session tenue sur la période"
        else:
            s = f"{_en_lettres(self.sessions, True)} session{'s' if self.sessions > 1 else ''} tenue{'s' if self.sessions > 1 else ''}"
            if self.dates:
                s += " (" + ", ".join(f"le {d:%d/%m/%Y}" for d in self.dates[:4]) + ")"
        if self.hors_periode:
            s += " ; date" + ("s" if len(self.hors_periode) > 1 else "") + " hors de la période : " + \
                 ", ".join(f"{d:%d/%m/%Y}" for d in self.hors_periode) + " (à vérifier)"
        return f"{self.libelle} : {s}."


@dataclass
class Rubriques:
    """Ce que le rapport dit des rubriques suivies (texte, éléments extraits)."""
    coges: Organe
    ct: Organe
    existant: list[str] = field(default_factory=list)
    biens: list[tuple[int, str]] = field(default_factory=list)
    biens_libelle: str = ""
    acquisitions: list[str] = field(default_factory=list)
    acquisitions_detaillees: bool = False
    matieres: list[str] = field(default_factory=list)
    matieres_traitee: bool = False
    controle_interne: list[str] = field(default_factory=list)
    controle_gestion: list[str] = field(default_factory=list)
    difficultes: dict[str, list[str]] = field(default_factory=dict)
    suggestions: dict[str, list[str]] = field(default_factory=dict)


def _en_lettres(n: int, feminin: bool = False) -> str:
    from .redaction import nombre
    return nombre(n, feminin)


def _texte(res, *codes: str) -> str:
    """Texte des rubriques, sans leurs titres (« V.1 Contrôle interne budgétaire »)."""
    s, vus, out = res.structure, set(), []
    titres = {normaliser(d.titre) for d in s.detections.values() if d.titre}
    for c in codes:
        t = s.texte_section(c) if c in s.detections else ""
        for ligne in t.split("\n"):
            l = ligne.strip()
            if normaliser(l) in titres or (len(l) < 90 and not l.endswith((".", ";", ":"))
                                           and re.match(r"^([IVXivx]+|\d+)([.\-]\d+)*\s*[.\-)]?\s*\S", l)):
                continue
            if ligne.strip() and ligne not in vus:
                vus.add(ligne)
                out.append(ligne)
    return "\n".join(out)


def _biens(res) -> tuple[list[tuple[int, str]], str]:
    """Biens énumérés dans la situation du patrimoine (« 1 TOYOTA HILUX », « - 2 véhicules … »)."""
    s = res.structure
    d = s.detections.get("patrimoine")
    if not d or d.mode != "titre":
        return [], ""
    biens, libelle, precedent = [], "", ""
    for b in res.doc.blocs[d.debut + 1:d.fin]:
        if b.type != "p":
            continue
        m = re.match(r"^\s*[-–•]?\s*(\d{1,3})\s+([A-Za-zÀ-ÿ].{1,60})$", b.texte.strip())
        if m:
            if not biens:
                libelle = precedent
            nom = m.group(2).strip(" ;.,")
            biens.append((int(m.group(1)), nom.title() if nom.isupper() else nom))
        elif biens:
            break
        precedent = b.texte
    nature = re.search(r"(vehicule|engin|ordinateur|moto|immeuble|batiment|bien)s?", normaliser(libelle))
    return biens, NATURES_BIENS[nature.group(1)] if nature else "biens"


def analyser_rubriques(res) -> Rubriques:
    from .controles import _debut_periode
    s = res.structure
    debut, fin = _debut_periode(res.periode), res.periode.fin

    def organe(libelle, code, motif):
        texte = _texte(res, code) or "\n".join(p for p in phrases(_texte(res, "gouvernance")) if re.search(motif, normaliser(p)))
        o = Organe(libelle, traite=bool(texte.strip()))
        if not o.traite:
            return o
        ph = phrases(texte)
        o.sessions = _sessions(texte)
        n = normaliser(texte)
        o.periodicite = ("chaque mois" if re.search(r"mensuel|chaque mois|tous les mois", n) else
                         "chaque trimestre" if re.search(r"trimestriel(le)?ment|chaque trimestre", n) else
                         "chaque semaine" if re.search(r"hebdomadaire|chaque semaine", n) else "")
        if o.sessions != 0:  # dates des sessions tenues
            o.dates = sorted({d for p in ph if re.search(TENUE, normaliser(p)) for d in _dates(p)})
            o.hors_periode = [d for d in o.dates if d < debut or d > fin]
        o.mise_en_place = _choisir(ph, r"pas encore|non encore|attendu|en attente|mise en place|installation|designation|"
                                       r"nomination|arrete|n.est pas (encore )?(cree|installe|constitue|fonctionnel)", 2)
        o.decisions = _choisir(ph, r"adopt|approuv|examin|valid|deliber|resolution|recommand", 2)
        o.extraits = _choisir(ph, TENUE + r"|session|reunion|aucun|arrete|designation|mensuel|chaque mois", 2)
        return o

    r = Rubriques(organe("Conseil de gestion (COGES / COS)", "coges",
                         r"coges|\bcos\b|conseil de gestion|conseil d.administration|conseil d.orientation|surveillance"),
                  organe("Comité de trésorerie", "comite_tresorerie", r"comite de tresorerie|\bct\b"))

    # Patrimoine
    ph_pat = phrases(_texte(res, "patrimoine", "patrimoine_existant", "acquisitions", "compta_matieres"))
    r.biens, r.biens_libelle = _biens(res)
    r.existant = _choisir(ph_pat, r"existant|situation existante|dispose|se compose|comprend|parc|vehicules?|immeubles?|"
                                  r"batiments?|locaux|terrains?|mobilier|materiel|equipements?", 2,
                          malus=r"cette annee|au cours (du trimestre|de la periode)")
    r.matieres = _choisir(ph_pat, r"comptab\w* (des |de )?matieres|comptable (des |de )?matieres|gestionnaire (du |de |des )?"
                                  r"(patrimoine|stocks?|matieres)|inventaire|fiches? de stock|sommier|codification|etiquet", 2)
    r.acquisitions = _choisir(ph_pat, r"acqui|achat|achet|dotation|nouve(au|aux|lle|lles)|commande|livr|receptionn", 2,
                              exclure=tuple(r.matieres),
                              bonus=r"cette annee|au cours (du trimestre|de la periode|de l.exercice|de la gestion (en cours|actuelle))|"
                                    r"\b20\d\d\b",
                              malus=r"gestion precedente|annee precedente|exercices? (precedent|anterieur)")
    r.acquisitions_detaillees = any(re.search(r"\d[\d\s.]*\s*(f\s?cfa|francs)|\b\d+\s+(ordinateurs?|vehicules?|tables?|chaises?|"
                                              r"bureaux?|climatiseurs?|motos?|imprimantes?)", normaliser(p))
                                    for p in r.acquisitions)
    r.matieres_traitee = bool(s.detections.get("compta_matieres") and s["compta_matieres"].trouvee)

    # Dispositif de contrôle
    ph_ctl = phrases(_texte(res, "dispositifs_controle", "controle_interne", "controle_gestion"))
    r.controle_gestion = _choisir(ph_ctl, r"controle de gestion|controleur de gestion|tableaux? de bord|indicateurs?|"
                                          r"suivi.evaluation|performance|objectifs", 2)
    r.controle_interne = _choisir(ph_ctl, r"controle interne|manuel|procedures?|textes?|audit|organigramme|separation|"
                                          r"cartographie|risques?|dispositif|organes?|commission|discipline|regularite", 3,
                                  exclure=tuple(r.controle_gestion))

    # Difficultés et suggestions par catégorie
    for cle in ("difficultes", "suggestions"):
        par = {c: [] for c, _ in CATEGORIES}
        for e in res.difficultes.get(cle, []):
            par.setdefault(e.categorie, []).append(e.texte)
        setattr(r, cle, par)
    return r


# ------------------------------------------------------------------ commentaires du fond (partie III)
def commentaire_fond(code: str, res, r: Rubriques | None = None) -> str | None:
    """Synthèse de ce que le rapport dit de la rubrique (None : rubrique non concernée)."""
    r = r or analyser_rubriques(res)
    if code == "coges":
        o = r.coges
        t = o.resume()
        if o.mise_en_place:
            t += " Mise en place du conseil : " + citer(o.mise_en_place[:1]) + "."
        if o.decisions:
            t += " Décisions : " + citer(o.decisions[:1]) + "."
        if o.sessions == 0:
            t += " Le rapport n'analyse pas les conséquences de l'absence de session sur la gouvernance de l'établissement."
        return t
    if code == "comite_tresorerie":
        o = r.ct
        t = o.resume()
        if o.traite and o.extraits:
            t += " Le CB indique : " + citer(o.extraits[:1]) + "."
        if o.mise_en_place and o.sessions in (None, 0):
            t += " " + citer(o.mise_en_place[:1]) + "."
        return t
    if code == "gouvernance":
        return f"{r.coges.resume()} {r.ct.resume()}"
    if code == "patrimoine_existant":
        if r.biens:
            total = sum(q for q, _ in r.biens)
            t = (f"Patrimoine existant : {_en_lettres(total)} {r.biens_libelle} énumérés ("
                 + ", ".join(f"{q} {n}" for q, n in r.biens[:8]) + ("…" if len(r.biens) > 8 else "") + ").")
        else:
            t = "Patrimoine existant : " + (citer(r.existant[:1]) + "." if r.existant else "non décrit.")
        if r.existant and r.biens:
            t += " Le CB indique : " + citer(r.existant[:1]) + "."
        return t
    if code == "acquisitions":
        if not r.acquisitions:
            return "Nouvelles acquisitions : aucune information dans le rapport."
        return ("Nouvelles acquisitions : " + citer(r.acquisitions) + "."
                + ("" if r.acquisitions_detaillees else " Les biens acquis (nature, quantités, montants) ne sont pas détaillés."))
    if code == "compta_matieres":
        if r.matieres_traitee:
            return "Comptabilité des matières : " + (citer(r.matieres) + "." if r.matieres else "point abordé.")
        return ("Le point de la mise en œuvre de la comptabilité des matières n'est pas traité."
                + (" Le CB signale seulement : " + citer(r.matieres[:1]) + "." if r.matieres else ""))
    if code == "patrimoine":
        morceaux = [commentaire_fond(c, res, r) for c in ("patrimoine_existant", "acquisitions")]
        if not r.matieres_traitee:
            morceaux.append("La comptabilité des matières n'est pas traitée.")
        return " ".join(morceaux)
    if code == "controle_interne":
        return ("Contrôle interne budgétaire : " + citer(r.controle_interne) + "." if r.controle_interne
                else "Le contrôle interne budgétaire n'est pas évalué dans le rapport.")
    if code == "controle_gestion":
        return ("Contrôle de gestion : " + citer(r.controle_gestion) + "." if r.controle_gestion
                else "Le contrôle de gestion n'est pas traité dans le rapport.")
    if code == "dispositifs_controle":
        return " ".join(commentaire_fond(c, res, r) for c in ("controle_interne", "controle_gestion"))
    if code in ("difficultes", "suggestions", "difficultes_suggestions"):
        cles = ("difficultes", "suggestions") if code == "difficultes_suggestions" else (code,)
        morceaux = []
        for cle in cles:
            par = getattr(r, cle)
            nom = "Difficultés" if cle == "difficultes" else "Suggestions"
            details = []
            for c, lib in CATEGORIES:
                items = par.get(c, [])
                details.append(f"liées {lib} : " + (f"{len(items)} ({_court(items[0])}{' ; …' if len(items) > 1 else ''})"
                                                     if items else "aucune"))
            morceaux.append(f"{nom} " + " ; ".join(details) + ".")
        return " ".join(morceaux)
    return None


def _court(t: str, n: int = 110) -> str:
    t = re.sub(r"\s+", " ", t).strip().rstrip(" ;:.,")
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


# ------------------------------------------------------------------ appréciation générale
def points_appreciation(res, r: Rubriques | None = None) -> tuple[list[str], list[str], list[str]]:
    """Points de satisfaction, insuffisances et recommandations tirés de la gouvernance, du patrimoine, du dispositif
    de contrôle et des difficultés et suggestions."""
    r = r or analyser_rubriques(res)
    sat, ins, recos = [], [], []
    # Gouvernance
    for o, sujet, complement in ((r.coges, "le Conseil de gestion (COGES / COS)", "du Conseil de gestion (COGES / COS)"),
                                 (r.ct, "le comité de trésorerie", "du comité de trésorerie")):
        if not o.traite:
            ins.append(f"la situation {complement} n'est pas présentée")
            continue
        if o.sessions and o.dates and len(o.hors_periode) == len(o.dates):
            ins.append(f"la session {complement} présentée comme tenue au cours de la période est datée du "
                       + ", ".join(f"{d:%d/%m/%Y}" for d in o.hors_periode) + ", hors de la période")
        elif o.sessions:
            sat.append(f"{sujet} s'est réuni ({_en_lettres(o.sessions, True)} session{'s' if o.sessions > 1 else ''} "
                       f"signalée{'s' if o.sessions > 1 else ''} au cours de la période)")
        elif o.sessions is None and o.periodicite:
            sat.append(f"{sujet} se réunit {o.periodicite}")
        elif o.sessions == 0:
            cause = ""
            mp = normaliser(" ".join(o.mise_en_place))
            if re.search(r"arrete", mp) and re.search(r"pas encore|attendu|en attente", mp):
                cause = ", sa mise en place attendant l'arrêté de désignation de ses membres"
            ins.append(f"aucune session {complement} ne s'est tenue au cours de la période{cause}"
                       + (" ; le rapport n'en tire pas les conséquences pour la gouvernance de l'établissement"
                          if o is r.coges else ""))
        else:
            ins.append(f"le nombre de sessions {complement} n'est pas précisé")
    # Patrimoine
    if r.biens or r.existant:
        sat.append("le patrimoine existant est présenté" + (f" ({_en_lettres(sum(q for q, _ in r.biens))} {r.biens_libelle})"
                                                            if r.biens else ""))
    else:
        ins.append("le patrimoine existant n'est pas décrit")
    if r.acquisitions and r.acquisitions_detaillees:
        sat.append("les nouvelles acquisitions sont détaillées")
    elif r.acquisitions:
        ins.append("les nouvelles acquisitions sont évoquées sans détail (nature, quantités, montants)")
    if not r.matieres_traitee:
        ins.append("la mise en œuvre de la comptabilité des matières n'est pas traitée")
        recos.append("faire le point de la mise en œuvre de la comptabilité des matières")
    # Dispositif de contrôle
    if r.controle_interne:
        sat.append("le dispositif de contrôle interne budgétaire est évalué")
    else:
        ins.append("le dispositif de contrôle interne budgétaire n'est pas évalué")
    if not r.controle_gestion:
        ins.append("le contrôle de gestion n'est pas traité")
    if not r.controle_interne or not r.controle_gestion:
        recos.append("évaluer le dispositif de contrôle (contrôle interne budgétaire et contrôle de gestion)")
    # Difficultés et suggestions
    avec = [lib for c, lib in CATEGORIES if r.difficultes.get(c)]
    sans = [lib for c, lib in CATEGORIES if not r.difficultes.get(c)]
    if avec:
        sat.append("les difficultés liées " + _enumerer(avec) + " sont exposées")
    if sans and avec:
        ins.append("aucune difficulté liée " + _enumerer(sans, "ni") + " n'est formulée")
    elif not avec:
        ins.append("aucune difficulté n'est formulée")
    if not any(r.suggestions.values()):
        ins.append("aucune suggestion n'est formulée")
        recos.append("formuler des suggestions en réponse aux difficultés relevées")
    return sat, ins, recos


def _enumerer(items: list[str], conj: str = "et") -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + f" {conj} " + items[-1]
