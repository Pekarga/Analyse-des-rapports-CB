"""Analyse de l'exécution par nature économique (code à 6 chiffres de la nomenclature budgétaire).

Source : la situation d'exécution (SIGOBE) lorsqu'elle est fournie, les lignes d'une même nature étant cumulées sur
l'ensemble des activités ; à défaut, les lignes codées des tableaux du rapport (tableau 5 pour les recettes, tableau 6
ou 4 pour les dépenses). Pour chaque nature : crédits initiaux et actuels, engagements, ordonnancements, prises en
charge, taux et statut ; pour l'ensemble : points d'attention (dépassements, natures non engagées, crédits supprimés
par la régulation, reste à payer, concentration, imputations à vérifier) et lecture rédigée.
"""
from __future__ import annotations

import re

from .texte import normaliser

CATEGORIES = (("personnel", "Personnel"), ("biens_services", "Biens et services"), ("transferts", "Transferts"),
              ("investissement", "Investissements"), ("", "Non classées"))
GROUPES_RECETTES = (("budget_general", "Ressources du budget général (État)"), ("propres", "Ressources propres"),
                    ("autres", "Autres ressources"), ("", "Non classées"))
_MOTIFS_DEPENSES = (("personnel", r"personnel|salaires"), ("biens_services", r"biens et services|fonctionnement"),
                    ("transferts", r"transferts?"), ("investissement", r"investissement|equipement"))
_MOTIFS_RECETTES = (("budget_general", r"budget general|etat|subvention"), ("propres", r"propres"),
                    ("autres", r"autres ressources|exterieur|dons|emprunts?"))
RE_NATURE = re.compile(r"^\d{6}$")
TOLERANCE = 1.0  # FCFA


def _sans_code(code: str, libelle: str) -> str:
    texte = re.sub(r"^\s*" + r"\s*".join(code) + r"\s*[-–:.]?\s*", "", libelle or "").strip()
    return texte[:1].upper() + texte[1:] if texte else code


def _source_situation(sit) -> str:
    d = sit.date_arrete
    systeme = "SIGOBE" if getattr(sit, "systeme", "") == "SIGOBE" else "situation d'exécution"
    return f"{systeme} au {d:%d/%m/%Y}" if d else systeme


def _depuis_situation(sit, sens: str) -> list[dict]:
    natures: dict[str, dict] = {}
    for l in sit.lignes_de(sens):
        if not RE_NATURE.match(l.code or ""):
            continue
        n = natures.setdefault(l.code, {"code": l.code, "libelle": _sans_code(l.code, l.libelle), "categorie": l.groupe,
                                        "activites": [], "valeurs": {}})
        if l.activite and l.activite not in n["activites"]:
            n["activites"].append(l.activite)
        for role, v in l.valeurs.items():
            n["valeurs"][role] = n["valeurs"].get(role, 0.0) + v
    out = []
    for n in natures.values():
        v = n.pop("valeurs")
        if sens == "depenses":
            n.update(initial=v.get("initial"), actuel=v.get("actuel"), engage=v.get("engage"),
                     realise=v.get("ordonnance", v.get("liquide")), paye=v.get("paye"))
        else:
            n.update(initial=v.get("initial"), actuel=v.get("actuel"), realise=v.get("recouvre"), paye=v.get("paye"))
        n["activites"] = len(n["activites"])
        out.append(n)
    return sorted(out, key=lambda n: n["code"])


def _depuis_tableaux(tableaux, codes: tuple[str, ...], sens: str) -> list[dict]:
    """Lignes codées (6 chiffres) des tableaux du rapport, rattachées au groupe qui les précède."""
    from .situation import _code
    motifs = _MOTIFS_DEPENSES if sens == "depenses" else _MOTIFS_RECETTES
    for code_tab in codes:
        tab = tableaux.par_code.get(code_tab)
        if not tab:
            continue
        out, groupe = {}, ""
        for l in tab.lignes:
            n = normaliser(l.libelle)
            code = _code(l.libelle)
            if not RE_NATURE.match(code or ""):
                g = next((c for c, m in motifs if re.search(m, n)), None)
                if g and l.type in ("groupe", "ligne"):
                    groupe = g
                continue
            if l.type != "ligne" or code in out:
                continue
            v = l.valeurs
            out[code] = {"code": code, "libelle": _sans_code(code, l.libelle), "categorie": groupe, "activites": 0,
                         "initial": v.get("initial"), "actuel": v.get("actuel", v.get("final")),
                         "engage": v.get("engage"), "realise": v.get("realise"), "paye": v.get("paye")}
        if out:
            return sorted(out.values(), key=lambda n: n["code"])
    return []


def extraire(res) -> dict:
    """Natures économiques d'un rapport analysé (enregistrées dans l'historique avec l'analyse)."""
    out = {"source_depenses": "", "source_recettes": "", "depenses": [], "recettes": []}
    sit = res.situation if (res.rapprochement and res.situation and res.situation.lignes) else None
    rapport = {"depenses": _depuis_tableaux(res.tableaux, ("T6", "T4"), "depenses"),
               "recettes": _depuis_tableaux(res.tableaux, ("T5", "T3"), "recettes")}
    for sens in ("depenses", "recettes"):
        lignes = _depuis_situation(sit, sens) if sit else []
        if lignes:
            out[f"source_{sens}"] = _source_situation(sit)
            du_rapport = {n["code"]: n for n in rapport[sens]}
            for n in lignes:  # montant du rapport pour la même nature (concordance)
                r = du_rapport.get(n["code"])
                n["rapport_realise"] = r.get("realise") if r else None
        elif rapport[sens]:
            lignes = rapport[sens]
            out[f"source_{sens}"] = "tableaux du rapport"
        out[sens] = lignes
    return out


# ------------------------------------------------------------------ analyse
def _taux(num, den) -> float | None:
    return num / den * 100 if num is not None and den else None


def statut_nature(n: dict, rang: int, parametres: dict) -> tuple[str, str]:
    from .tableau import statut_execution
    actuel, engage, realise, initial = (n.get(k) or 0.0 for k in ("actuel", "engage", "realise", "initial"))
    if actuel <= TOLERANCE and engage <= TOLERANCE and realise <= TOLERANCE:
        return ("Crédits supprimés", "gris") if initial > TOLERANCE else ("Non doté", "gris")
    if engage > actuel + TOLERANCE or realise > actuel + TOLERANCE:
        return "Dépassement", "rouge"
    if engage <= TOLERANCE and realise <= TOLERANCE:
        return "Non engagé", "orange"
    return statut_execution(_taux(realise, actuel), rang, parametres)


def _m(v: float | None) -> str:
    """Montant en millions de FCFA, pour les textes."""
    if v is None:
        return "—"
    return f"{v / 1e6:,.1f}".replace(",", " ").replace(".", ",") + " M FCFA"


def _p(v: float | None) -> str:
    return "—" if v is None else f"{v:.0f} %"


def _nb(n: int, mot: str, pluriel: str | None = None) -> str:
    return f"{n} {mot if n <= 1 else (pluriel or mot + 's')}"


def analyser(depenses: list[dict], recettes: list[dict], rang: int, parametres: dict) -> dict:
    """Statuts, totaux par catégorie, points d'attention et lecture rédigée."""
    lignes = []
    for n in depenses:
        statut, couleur = statut_nature(n, rang, parametres)
        actuel = n.get("actuel")
        lignes.append({**n, "statut": statut, "couleur": couleur,
                       "taux_engagement": _taux(n.get("engage"), actuel), "taux": _taux(n.get("realise"), actuel),
                       "disponible": (actuel - (n.get("engage") or 0)) if actuel is not None else None,
                       "reste_a_payer": ((n.get("realise") or 0) - n["paye"]) if n.get("paye") is not None else None,
                       "variation": (actuel - n["initial"]) if actuel is not None and n.get("initial") is not None else None})
    total = {k: sum(l.get(k) or 0 for l in lignes) for k in ("initial", "actuel", "engage", "realise", "paye")}
    total.update(taux_engagement=_taux(total["engage"], total["actuel"]), taux=_taux(total["realise"], total["actuel"]))
    categories = []
    for code, libelle in CATEGORIES:
        membres = [l for l in lignes if (l.get("categorie") or "") == code]
        if not membres:
            continue
        c = {k: sum(l.get(k) or 0 for l in membres) for k in ("initial", "actuel", "engage", "realise", "paye")}
        c.update(code=code, libelle=libelle, natures=sorted(membres, key=lambda l: -(l.get("actuel") or 0)),
                 taux_engagement=_taux(c["engage"], c["actuel"]), taux=_taux(c["realise"], c["actuel"]))
        categories.append(c)

    points = []
    dep = [l for l in lignes if l["statut"] == "Dépassement"]
    if dep:
        points.append({"niveau": "critique", "titre": f"{_nb(len(dep), 'nature')} en dépassement de crédits",
                       "detail": "; ".join(f"{l['code']} {l['libelle']} ({_m(max(l.get('engage') or 0, l.get('realise') or 0) - (l.get('actuel') or 0))} de plus que les crédits)" for l in dep[:4])})
    non_eng = sorted((l for l in lignes if l["statut"] == "Non engagé"), key=lambda l: -(l.get("actuel") or 0))
    if non_eng:
        montant = sum(l.get("actuel") or 0 for l in non_eng)
        cats = sorted({dict(CATEGORIES).get(l.get("categorie") or "", "Non classées").lower() for l in non_eng})
        points.append({"niveau": "attention", "titre": f"{_nb(len(non_eng), 'nature dotée', 'natures dotées')} sans aucun engagement",
                       "detail": f"{_m(montant)} de crédits non engagés ({', '.join(cats)}), dont "
                                 + ", ".join(f"{l['libelle']} ({_m(l.get('actuel'))})" for l in non_eng[:3]) + "."})
    reduites = [l for l in lignes if l.get("variation") is not None and l["variation"] < -TOLERANCE]
    if reduites:
        baisse = -sum(l["variation"] for l in reduites)
        supprimees = [l for l in reduites if (l.get("actuel") or 0) <= TOLERANCE]
        points.append({"niveau": "info", "titre": "Crédits réduits par la régulation",
                       "detail": f"{_m(baisse)} retirés sur {_nb(len(reduites), 'nature')}"
                                 + (f", dont {_nb(len(supprimees), 'nature')} entièrement supprimée{'s' if len(supprimees) > 1 else ''}" if supprimees else "")
                                 + "."})
    hausses = [l for l in lignes if l.get("variation") is not None and l["variation"] > TOLERANCE]
    if hausses:
        points.append({"niveau": "info", "titre": "Crédits augmentés en cours d'exercice",
                       "detail": f"{_m(sum(l['variation'] for l in hausses))} ajoutés sur {_nb(len(hausses), 'nature')}, dont "
                                 + ", ".join(f"{l['libelle']} (+{_m(l['variation'])})" for l in sorted(hausses, key=lambda l: -l['variation'])[:2]) + "."})
    rap = sorted((l for l in lignes if (l.get("reste_a_payer") or 0) > TOLERANCE), key=lambda l: -l["reste_a_payer"])
    if rap:
        points.append({"niveau": "attention", "titre": "Ordonnancements non encore payés",
                       "detail": f"Reste à payer de {_m(sum(l['reste_a_payer'] for l in rap))}, dont "
                                 + ", ".join(f"{l['libelle']} ({_m(l['reste_a_payer'])})" for l in rap[:2]) + "."})
    invest = [l for l in lignes if l["code"].startswith("2") and (l.get("categorie") or "") not in ("investissement", "")]
    if invest:
        points.append({"niveau": "attention", "titre": "Imputation à vérifier",
                       "detail": f"{_nb(len(invest), 'nature')} d'investissement (comptes de classe 2 : "
                                 + ", ".join(l["libelle"].lower() for l in invest[:4])
                                 + ") inscrite" + ("s" if len(invest) > 1 else "") + " en "
                                 + ", ".join(sorted({dict(CATEGORIES)[l['categorie']].lower() for l in invest})) + "."})
    executees = sorted((l for l in lignes if (l.get("realise") or 0) > 0), key=lambda l: -l["realise"])
    if total["realise"] and len(executees) >= 4:
        top = executees[:3]
        part = sum(l["realise"] for l in top) / total["realise"] * 100
        if part >= 50:
            points.append({"niveau": "info", "titre": "Exécution concentrée",
                           "detail": f"Trois natures représentent {_p(part)} des ordonnancements : "
                                     + ", ".join(f"{l['libelle']} ({_m(l['realise'])})" for l in top) + "."})

    rec = []
    for n in recettes:
        taux = _taux(n.get("realise"), n.get("actuel"))
        statut, couleur = ("Non doté", "gris") if not n.get("actuel") else \
            ("Non recouvré", "orange") if not n.get("realise") else ("Recouvré", "vert") if (taux or 0) >= 99.5 else ("En cours", "bleu")
        rec.append({**n, "taux": taux, "statut": statut, "couleur": couleur})
    total_rec = {k: sum(r.get(k) or 0 for r in rec) for k in ("initial", "actuel", "realise")}
    total_rec["taux"] = _taux(total_rec["realise"], total_rec["actuel"])
    groupes_rec = []
    for code, libelle in GROUPES_RECETTES:
        membres = [r for r in rec if (r.get("categorie") or "") == code]
        if membres:
            g = {k: sum(r.get(k) or 0 for r in membres) for k in ("initial", "actuel", "realise")}
            g.update(code=code, libelle=libelle, natures=membres, taux=_taux(g["realise"], g["actuel"]))
            groupes_rec.append(g)
    non_rec = [r for r in rec if r["statut"] == "Non recouvré"]
    if non_rec:
        points.append({"niveau": "attention", "titre": f"{_nb(len(non_rec), 'recette prévue', 'recettes prévues')} sans recouvrement",
                       "detail": ", ".join(f"{r['libelle']} ({_m(r.get('actuel'))})" for r in non_rec[:3]) + "."})
    ordre = {"critique": 0, "attention": 1, "info": 2}
    points.sort(key=lambda p: ordre[p["niveau"]])
    return {"categories": categories, "total": total, "recettes": groupes_rec, "total_recettes": total_rec,
            "points": points, "lecture": _lecture(lignes, total, executees, non_eng, reduites, rec, total_rec),
            "natures": len([l for l in lignes if (l.get("actuel") or 0) > TOLERANCE]),
            "top": [{"code": l["code"], "libelle": l["libelle"], "actuel": l.get("actuel"), "engage": l.get("engage"),
                     "realise": l.get("realise")} for l in sorted(lignes, key=lambda l: -(l.get("actuel") or 0))[:10]
                    if (l.get("actuel") or 0) > TOLERANCE]}


def _lecture(lignes, total, executees, non_eng, reduites, rec, total_rec) -> str:
    if not lignes and not rec:
        return ""
    phrases = []
    if lignes and total["actuel"]:
        phrases.append(f"Les crédits de {_nb(len([l for l in lignes if (l.get('actuel') or 0) > TOLERANCE]), 'nature économique', 'natures économiques')} "
                       f"s'élèvent à {_m(total['actuel'])} ; {_p(total['taux_engagement'])} sont engagés et "
                       f"{_p(total['taux'])} ordonnancés.")
    if executees:
        top = executees[:3]
        phrases.append("Les principaux ordonnancements portent sur "
                       + ", ".join(f"{l['libelle'].lower()} ({_m(l['realise'])})" for l in top) + ".")
    if non_eng:
        phrases.append(f"Aucun engagement n'a été pris sur {_nb(len(non_eng), 'nature dotée', 'natures dotées')} "
                       f"de {_m(sum(l.get('actuel') or 0 for l in non_eng))}.")
    if reduites:
        phrases.append(f"La régulation a réduit les crédits de {_nb(len(reduites), 'nature')} "
                       f"pour {_m(-sum(l['variation'] for l in reduites))}.")
    if rec and total_rec["actuel"]:
        phrases.append(f"En recettes, {_p(total_rec['taux'])} des prévisions sont recouvrées "
                       f"({_m(total_rec['realise'])} sur {_m(total_rec['actuel'])}).")
    return " ".join(phrases)


def fusionner(listes: list[list[dict]]) -> list[dict]:
    """Natures de plusieurs EPN cumulées par code (vue « Ensemble des EPN »)."""
    out: dict[str, dict] = {}
    for lst in listes:
        for n in lst:
            c = out.setdefault(n["code"], {"code": n["code"], "libelle": n["libelle"], "categorie": n.get("categorie", ""),
                                           "activites": 0, "epn": 0})
            c["epn"] += 1
            c["activites"] += n.get("activites") or 0
            for k in ("initial", "actuel", "engage", "realise", "paye"):
                if n.get(k) is not None:
                    c[k] = (c.get(k) or 0) + n[k]
    return sorted(out.values(), key=lambda n: n["code"])
