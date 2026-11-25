"""Indicateurs du tableau de bord, calculés à partir de l'historique des analyses.

Le taux d'exécution d'un EPN (ordonnancements / crédits actuels) est apprécié au regard du taux attendu à la fin
de la période (25 % au 1er trimestre, 50 % au 30 juin, 75 % au 3e trimestre, 100 % en fin d'exercice) :
- « Dépassement » si l'exécution dépasse les crédits ;
- « Sous-exécution » si le taux est inférieur au taux attendu de plus de `seuil_sous_execution` points ;
- « À surveiller » si l'écart dépasse `seuil_vigilance` points ;
- « OK » sinon.
"""
from __future__ import annotations

from datetime import date

from . import natures, ratios
from .controles import DEFAUT_DELAIS, jour_mois
from .historique import NATURES, epn_du, epns, libelle_periode, lister, periodes
from .texte import montant_fcfa

TAUX_ATTENDU = {1: 25.0, 2: 50.0, 3: 75.0, 4: 100.0, 5: 100.0}


def _seuils(parametres: dict) -> tuple[float, float]:
    e = (parametres or {}).get("execution", {})
    return float(e.get("seuil_vigilance", 10)), float(e.get("seuil_sous_execution", 20))


def statut_execution(taux: float | None, rang: int, parametres: dict) -> tuple[str, str]:
    if taux is None:
        return "Non renseigné", "gris"
    vigilance, sous = _seuils(parametres)
    attendu = TAUX_ATTENDU.get(rang, 100.0)
    if taux > 100.05:
        return "Dépassement", "rouge"
    if taux < attendu - sous:
        return "Sous-exécution", "orange"
    if taux < attendu - vigilance:
        return "À surveiller", "jaune"
    return "OK", "vert"


def objectif(rang: int, parametres: dict) -> float:
    vigilance, _ = _seuils(parametres)
    return max(0.0, TAUX_ATTENDU.get(rang, 100.0) - vigilance)


def _nom_court(r: dict) -> str:
    return r.get("sigle") or (r["epn"] if len(r["epn"]) <= 28 else r["epn"][:26] + "…")


def lignes_epn(records: list[dict], parametres: dict) -> list[dict]:
    out = []
    for r in records:
        m = r["donnees"].get("montants", {})
        credits, execution = m.get("credits"), m.get("execution")
        taux = execution / credits * 100 if credits and execution is not None else None
        statut, couleur = statut_execution(taux, r["rang"], parametres)
        out.append({
            "id": r["id"], "epn": r["epn"], "epn_cle": epn_du(r), "court": _nom_court(r), "tutelle": r["tutelle"],
            "credits": credits, "execution": execution, "engagements": m.get("engagements"),
            "recettes_prevues": m.get("recettes_prevues"), "recettes_realisees": m.get("recettes_realisees"),
            "taux": taux, "ecart": (execution - credits) if credits is not None and execution is not None else None,
            "statut": statut, "couleur": couleur, "source": m.get("source", ""), "natures": m.get("natures", {}),
            "forme": r["score_forme"], "fond": r["score_fond"], "anomalies_majeures": r["anomalies_majeures"],
            "retour": bool(r["retour"]), "ecart_jours": r["ecart_jours"], "controleur": r["controleur"],
            "date_reception": r["date_reception"],
        })
    return out


def _totaux(lignes: list[dict]) -> dict:
    """Totaux de la période ; « ecarts » cumule les écarts en valeur absolue (sous-exécutions et dépassements),
    « ecart_net » est la somme algébrique (exécution − crédits)."""
    avec = [l for l in lignes if l["credits"] is not None and l["execution"] is not None]
    credits = sum(l["credits"] for l in avec)
    execution = sum(l["execution"] for l in avec)
    return {"credits": credits if avec else None, "execution": execution if avec else None,
            "taux": execution / credits * 100 if avec and credits else None,
            "ecarts": sum(abs(l["ecart"]) for l in avec) if avec else None,
            "ecart_net": execution - credits if avec else None, "epn": len(lignes), "epn_chiffres": len(avec)}


def lignes_ministeres(lignes: list[dict], rang: int, parametres: dict) -> list[dict]:
    """Agrégation des EPN par ministère de tutelle (vue « Détail par ministère »)."""
    groupes: dict[str, list[dict]] = {}
    for l in lignes:
        groupes.setdefault(l["tutelle"], []).append(l)
    out = []
    for tutelle, membres in groupes.items():
        t = _totaux(membres)
        statut, couleur = statut_execution(t["taux"], rang, parametres)
        out.append({"libelle": tutelle, "epn": len(membres), "credits": t["credits"], "execution": t["execution"],
                    "taux": t["taux"], "ecart": t["ecart_net"], "statut": statut, "couleur": couleur})
    return sorted(out, key=lambda m: -(m["credits"] or 0))


def _variation(actuel, precedent, points: bool = False):
    if actuel is None or precedent is None:
        return None
    if points:
        return actuel - precedent
    return (actuel - precedent) / abs(precedent) * 100 if precedent else None


def unite(valeurs: list[float | None]) -> dict:
    m = max((abs(v) for v in valeurs if v is not None), default=0)
    if m >= 1e9:
        return {"diviseur": 1e9, "libelle": "Mds FCFA"}
    return {"diviseur": 1e6, "libelle": "M FCFA"}


def _precedente(cle: str, liste: list[dict]) -> dict | None:
    """Période précédente disponible dans l'historique (ordre chronologique)."""
    ordre = sorted(liste, key=lambda p: (p["annee"], p["rang"]))
    for i, p in enumerate(ordre):
        if p["cle"] == cle:
            return ordre[i - 1] if i > 0 else None
    return None


def alertes_periode(lignes: list[dict], records: list[dict], rang: int, parametres: dict, totaux: dict) -> list[dict]:
    """Alertes de la période : exécution budgétaire puis qualité des rapports."""
    out = []
    for l in lignes:
        if l["statut"] == "Dépassement":
            out.append({"niveau": "critique", "type": "execution", "titre": "Dépassement de crédits", "epn": l["epn"],
                        "id": l["id"], "valeur": l["ecart"], "detail": f"Exécution supérieure aux crédits de {l['court']}."})
        elif l["statut"] == "Sous-exécution":
            out.append({"niveau": "attention", "type": "execution", "titre": "Sous-exécution significative",
                        "epn": l["epn"], "id": l["id"], "valeur": l["ecart"],
                        "detail": f"Taux d'exécution de {l['taux']:.1f} % pour {l['court']}.".replace(".", ",", 1)})
        elif l["statut"] == "À surveiller":
            out.append({"niveau": "info", "type": "execution", "titre": "Exécution à surveiller", "epn": l["epn"],
                        "id": l["id"], "valeur": l["ecart"],
                        "detail": f"Taux d'exécution de {l['taux']:.1f} % pour {l['court']}.".replace(".", ",", 1)})
    for r in records:
        for a in r["donnees"].get("alertes", []):
            out.append({**a, "type": "rapport", "epn": r["epn"], "id": r["id"]})
    ordre = {"critique": 0, "attention": 1, "info": 2}
    return sorted(out, key=lambda a: ordre.get(a["niveau"], 3))


def _epn_valide(epn: str | None) -> str | None:
    """Identifiant d'EPN connu de l'historique, sinon None (« Ensemble des EPN »)."""
    return epn if epn and epn in {e["cle"] for e in epns()} else None


def tableau_de_bord(periode_cle: str | None, parametres: dict, epn: str | None = None) -> dict:
    """Tableau de bord d'une période, pour l'ensemble des EPN ou pour un seul EPN (`epn`)."""
    epn = _epn_valide(epn)
    liste = periodes(epn=epn)
    if not liste:
        return {"vide": True, "periodes": [], "epns": epns()}
    if not periode_cle or periode_cle not in {p["cle"] for p in liste}:
        periode_cle = liste[0]["cle"]
    p = next(x for x in liste if x["cle"] == periode_cle)
    records = lister(periode_cle, epn=epn)
    lignes = lignes_epn(records, parametres)
    tot = _totaux(lignes)

    prec = _precedente(periode_cle, liste)
    tot_prec = _totaux(lignes_epn(lister(prec["cle"], epn=epn), parametres)) if prec else None
    comparaison = {
        "libelle": f"vs {prec['court']}" if prec else "",
        "credits": _variation(tot["credits"], tot_prec and tot_prec["credits"]),
        "execution": _variation(tot["execution"], tot_prec and tot_prec["execution"]),
        "taux": _variation(tot["taux"], tot_prec and tot_prec["taux"], points=True),
        "ecarts": _variation(tot["ecarts"], tot_prec and tot_prec["ecarts"]),
    }

    # Évolution sur l'exercice
    evolution = []
    for q in sorted((x for x in liste if x["annee"] == p["annee"]), key=lambda x: x["rang"]):
        t = _totaux(lignes_epn(lister(q["cle"], epn=epn), parametres)) if q["cle"] != periode_cle else tot
        evolution.append({"cle": q["cle"], "libelle": q["court"], "credits": t["credits"], "taux": t["taux"],
                          "execution": t["execution"]})

    # Graphique prévu / réalisé : par EPN et par nature de dépense
    natures: dict[str, dict] = {}
    for l in lignes:
        for cle, libelle in NATURES:
            n = l["natures"].get(cle)
            if n and (n.get("prevu") or n.get("realise")):
                agg = natures.setdefault(cle, {"libelle": libelle, "prevu": 0.0, "realise": 0.0})
                agg["prevu"] += n.get("prevu") or 0
                agg["realise"] += n.get("realise") or 0
    graphiques = {
        "epn": [{"libelle": l["court"], "prevu": l["credits"], "realise": l["execution"]} for l in lignes
                if l["credits"] is not None],
        "nature": [natures[c] for c, _ in NATURES if c in natures],
        "trimestre": [{"libelle": e["libelle"], "prevu": e["credits"], "realise": e["execution"]} for e in evolution
                      if e["credits"] is not None],
    }
    # Un seul EPN : exécution par catégorie de dépense (à la place du détail par EPN)
    categories = []
    if epn and lignes:
        for cle, lib in NATURES:
            n = (lignes[0]["natures"] or {}).get(cle)
            if not n or not (n.get("prevu") or n.get("realise")):
                continue
            taux = n["realise"] / n["prevu"] * 100 if n.get("prevu") and n.get("realise") is not None else None
            statut, couleur = statut_execution(taux, p["rang"], parametres) if taux is not None else ("Non renseigné", "gris")
            categories.append({"libelle": lib, "credits": n.get("prevu"), "execution": n.get("realise"), "taux": taux,
                               "ecart": (n["realise"] - n["prevu"]) if n.get("prevu") is not None and n.get("realise") is not None else None,
                               "statut": statut, "couleur": couleur})

    alertes = alertes_periode(lignes, records, p["rang"], parametres, tot)
    obj = objectif(p["rang"], parametres)
    synthese = _synthese(lignes, records, tot, obj)

    valeurs = [tot["credits"], tot["execution"]] + [l["credits"] for l in lignes]
    fiche = next((e for e in epns() if e["cle"] == epn), None) if epn else None
    return {
        "vide": False, "periodes": liste, "periode": p, "unite": unite(valeurs), "kpi": tot, "epns": epns(),
        "epn": {"cle": epn, "epn": fiche["epn"], "court": fiche["court"], "tutelle": fiche["tutelle"],
                "id": records[0]["id"] if records else None} if fiche else None,
        "categories": categories,
        "comparaison": comparaison, "evolution": evolution, "lignes": lignes,
        "ratios": _ratios_periode(records, lister(prec["cle"], epn=epn) if prec else [],
                                  f"Ratios de l'EPN {fiche['court']}" if fiche else ""),
        "difficultes": difficultes_periode(records),
        "ministeres": lignes_ministeres(lignes, p["rang"], parametres),
        "graphiques": graphiques, "alertes": alertes, "synthese": synthese, "objectif": obj,
        "attendu": TAUX_ATTENDU.get(p["rang"], 100.0),
        "badge": sum(1 for a in alertes if a["niveau"] in ("critique", "attention")),
        "rapports": {
            "total": len(records), "retours": sum(1 for r in records if r["retour"]),
            "hors_delai": sum(1 for r in records if (r["ecart_jours"] or 0) > 0),
            "forme_moyenne": sum(r["score_forme"] for r in records) / len(records) if records else None,
        },
    }


def _ratios_periode(records: list[dict], precedents: list[dict], portee: str = "") -> dict:
    """Ratios de gestion de la période (tous EPN, ou l'EPN suivi) et variation, en points, par rapport à la période
    précédente."""
    agreges = ratios.agreger(records)
    avant = {x["code"]: x["valeur"] for x in ratios.agreger(precedents)} if precedents else {}
    for x in agreges:
        prec = avant.get(x["code"])
        x["variation"] = x["valeur"] - prec if x["valeur"] is not None and prec is not None else None
    bases = sorted({(r["donnees"].get("ratios") or {}).get("base") for r in records} - {None})
    sources = sorted({(r["donnees"].get("ratios") or {}).get("source") for r in records} - {None})
    return {"agreges": agreges, "citations": ratios.citations(records), "bases": bases, "sources": sources,
            "disponibles": sum(1 for r in records if ratios.liste(r)), "rapports": len(records), "portee": portee}


def analyse_natures(periode_cle: str | None, choix: str | None, parametres: dict) -> dict:
    """Page « Nature économique » : un EPN ou l'ensemble des EPN de la période (natures cumulées par code)."""
    choix = _epn_valide(choix)
    liste = periodes(epn=choix)
    if not liste:
        return {"vide": True, "periodes": []}
    if not periode_cle or periode_cle not in {p["cle"] for p in liste}:
        periode_cle = liste[0]["cle"]
    p = next(x for x in liste if x["cle"] == periode_cle)
    records = lister(periode_cle)
    avec = [r for r in records if (r["donnees"].get("natures") or {}).get("depenses")
            or (r["donnees"].get("natures") or {}).get("recettes")]
    choisis = [r for r in avec if epn_du(r) == choix] if choix else avec
    concernes = [r for r in records if epn_du(r) == choix] if choix else records
    non_disponible = bool(choix) and not choisis  # l'EPN suivi n'a pas encore d'analyse par nature pour la période
    if not choix:
        choix = epn_du(choisis[0]) if len(choisis) == 1 else "tous"
    donnees = [r["donnees"]["natures"] for r in choisis]
    depenses = natures.fusionner([d.get("depenses") or [] for d in donnees]) if len(donnees) > 1 else \
        (donnees[0].get("depenses") or [] if donnees else [])
    recettes = natures.fusionner([d.get("recettes") or [] for d in donnees]) if len(donnees) > 1 else \
        (donnees[0].get("recettes") or [] if donnees else [])
    sources = sorted({s for d in donnees for s in (d.get("source_depenses"), d.get("source_recettes")) if s})
    valeurs = [depenses and max((n.get("actuel") or 0) for n in depenses) or 0,
               recettes and max((n.get("actuel") or 0) for n in recettes) or 0]
    return {"vide": False, "periodes": liste, "periode": p, "epns": epns(), "choix": choix,
            "disponibles": [epn_du(r) for r in avec], "non_disponible": non_disponible,
            "a_reanalyser": len(concernes) - len(choisis), "sources": sources, "unite": unite(valeurs),
            **natures.analyser(depenses, recettes, p["rang"], parametres)}


CATEGORIES_DS = (("execution", "Exécution du budget"), ("controle", "Contrôle de l'exécution du budget"),
                 ("gestion", "Gestion de l'établissement"))


def difficultes_periode(records: list[dict]) -> dict:
    """Difficultés et suggestions formulées par les CB dans les rapports de la période, par catégorie."""
    out = {"difficultes": [], "suggestions": [], "categories": [{"code": c, "libelle": l} for c, l in CATEGORIES_DS],
           "rapports": 0, "sans_difficultes": [], "sans_suggestions": [], "a_reanalyser": 0}
    for r in records:
        ds = r["donnees"].get("difficultes")
        if ds is None:
            out["a_reanalyser"] += 1
            continue
        out["rapports"] += 1
        for cle in ("difficultes", "suggestions"):
            elements = ds.get(cle) or []
            if not elements:
                out[f"sans_{cle}"].append(_nom_court(r))
            for e in elements:
                out[cle].append({**e, "id": r["id"], "epn": r["epn"], "court": _nom_court(r)})
    ordre = {c: i for i, (c, _) in enumerate(CATEGORIES_DS)}
    for cle in ("difficultes", "suggestions"):
        out[cle].sort(key=lambda e: (ordre.get(e["categorie"], 9), e["court"]))
    return out


def analyse_ratios(periode_cle: str | None, epn: str | None = None) -> dict:
    """Page « Analyse des ratios » : ratios de la période, détail et lecture par EPN, évolution par EPN."""
    epn = _epn_valide(epn)
    liste = periodes(epn=epn)
    if not liste:
        return {"vide": True, "periodes": []}
    if not periode_cle or periode_cle not in {p["cle"] for p in liste}:
        periode_cle = liste[0]["cle"]
    p = next(x for x in liste if x["cle"] == periode_cle)
    records = lister(periode_cle, epn=epn)
    prec = _precedente(periode_cle, liste)
    lignes = []
    for r in records:
        info = r["donnees"].get("ratios") or {}
        lst = info.get("liste") or []
        total = info.get("total")
        structure = []
        for cle, libelle in ratios.CATEGORIES:
            v = (info.get("structure") or {}).get(cle)
            if v is not None and total:
                structure.append({"cle": cle, "libelle": libelle, "part": v / total * 100})
        if structure and total:
            reste = 100 - sum(x["part"] for x in structure)
            if reste > 0.5:
                structure.append({"cle": "autres", "libelle": "Non classées", "part": reste})
        lignes.append({"id": r["id"], "epn": r["epn"], "court": _nom_court(r), "tutelle": r["tutelle"],
                       "source": info.get("source", ""), "base": info.get("base", ""), "ratios": lst,
                       "structure": structure,
                       "lecture": ratios.lecture(lst, info.get("base") or "dépenses engagées") if lst else ""})
    # Évolution de chaque ratio par EPN sur les périodes analysées
    evolution: dict[str, list] = {}
    for q in sorted(liste, key=lambda x: (x["annee"], x["rang"])):
        for r in lister(q["cle"], epn=epn):
            valeurs = {x["code"]: x.get("valeur") for x in ratios.liste(r)}
            evolution.setdefault(r["epn"], []).append({"periode": q["court"], **valeurs})
    return {"vide": False, "periodes": liste, "periode": p, "lignes": lignes,
            "ratios": _ratios_periode(records, lister(prec["cle"], epn=epn) if prec else []),
            "precedente": prec["court"] if prec else "", "evolution": evolution, "epns": epns(), "epn": epn,
            "definitions": [{"code": c, "court": co, "libelle": li, "formule": f} for c, co, li, f in ratios.RATIOS]}


def _synthese(lignes, records, tot, obj) -> dict:
    """Points saillants (au plus quatre) et recommandation, pour le panneau « Synthèse & Alertes »."""
    points = []
    dep = sorted((l for l in lignes if l["statut"] == "Dépassement"), key=lambda l: -(l["ecart"] or 0))
    sous = sorted((l for l in lignes if l["statut"] in ("Sous-exécution",)), key=lambda l: l["ecart"] or 0)
    if dep:
        points.append({"niveau": "critique", "titre": "Dépassement de crédits", "epn": dep[0]["court"],
                       "valeur": dep[0]["ecart"], "texte": f"{dep[0]['court']}"
                       + (f" et {len(dep) - 1} autre(s)" if len(dep) > 1 else "")})
    if sous:
        points.append({"niveau": "attention", "titre": "Sous-exécution significative", "epn": sous[0]["court"],
                       "valeur": sous[0]["ecart"], "texte": f"{sous[0]['court']}"
                       + (f" et {len(sous) - 1} autre(s)" if len(sous) > 1 else "")})
    if tot["taux"] is not None:
        ok = tot["taux"] >= obj
        points.append({"niveau": "info" if ok else "attention",
                       "titre": "Taux d'exécution global " + ("satisfaisant" if ok else "insuffisant"),
                       "taux": tot["taux"], "objectif": obj})
    retours = sum(1 for r in records if r["retour"])
    hors = sum(1 for r in records if (r["ecart_jours"] or 0) > 0)
    if retours or hors:
        morceaux = []
        if retours:
            morceaux.append(f"{retours} rapport{'s' if retours > 1 else ''} à retourner au CB")
        if hors:
            morceaux.append(f"{hors} transmis hors délai")
        points.append({"niveau": "attention" if retours else "info", "titre": "Qualité des rapports",
                       "texte": " ; ".join(morceaux)})
    reco = []
    if dep or sous:
        reco.append("renforcer le suivi des EPN en sous-exécution et faire justifier les dépassements")
    if retours:
        reco.append("retourner aux CB les rapports non conformes pour correction")
    if hors:
        reco.append("rappeler les délais de transmission")
    if not reco:
        reco.append("maintenir le rythme d'exécution et la qualité des rapports")
    texte = "Il est recommandé de " + " ; de ".join(reco) + "."
    return {"points": points[:4], "recommandation": texte}


CODES_PERIODES = (("T1", 1, "1er trimestre"), ("T2", 2, "2e trimestre"), ("T3", 3, "3e trimestre"),
                  ("T4", 4, "4e trimestre"), ("A", 5, "Rapport annuel"))


def _somme(valeurs):
    v = [x for x in valeurs if x is not None]
    return sum(v) if v else None


def _taux_sur(num, den):
    return num / den * 100 if den and num is not None else None


def _recettes_par_nature(recs: list[dict]) -> dict:
    """Recouvrement par nature économique de recettes (code à 6 chiffres) et par groupe de ressources, cumulé sur les
    rapports de la colonne. Les analyses antérieures à la version 3.3 n'ont pas ce détail (`natures_a_reanalyser`)."""
    listes = [(r["donnees"].get("natures") or {}).get("recettes") or [] for r in recs]
    avec = [x for x in listes if x]
    out, groupes = {}, {}
    for n in (natures.fusionner(avec) if avec else []):
        prevu = n.get("actuel") if n.get("actuel") is not None else n.get("initial")
        realise = n.get("realise")
        out[n["code"]] = {"libelle": n["libelle"], "groupe": n.get("categorie") or "", "prevu": prevu, "realise": realise,
                          "taux": _taux_sur(realise, prevu)}
        g = groupes.setdefault(n.get("categorie") or "", {"prevu": None, "realise": None})
        for k, v in (("prevu", prevu), ("realise", realise)):
            if v is not None:
                g[k] = (g[k] or 0) + v
    for g in groupes.values():
        g["taux"] = _taux_sur(g["realise"], g["prevu"])
    sources = sorted({(r["donnees"].get("natures") or {}).get("source_recettes") for r in recs} - {None, ""})
    return {"recettes_natures": out, "recettes_groupes": groupes, "natures_a_reanalyser": len(recs) - len(avec),
            "source_natures_recettes": sources}


def _colonne(code: str, rang: int, annee: int, nom: str, recs: list[dict], parametres: dict) -> dict:
    col = {"code": code, "rang": rang, "libelle": f"{code} {annee}" if rang < 5 else f"Exercice {annee}",
           "nom": nom, "present": bool(recs)}
    if not recs:
        return col
    lignes = lignes_epn(recs, parametres)
    t = _totaux(lignes)
    statut, couleur = statut_execution(t["taux"], rang, parametres)
    rp, rr = _somme(l["recettes_prevues"] for l in lignes), _somme(l["recettes_realisees"] for l in lignes)
    categories = {}
    for cle, lib in NATURES:
        prevu = _somme((l["natures"].get(cle) or {}).get("prevu") for l in lignes)
        realise = _somme((l["natures"].get(cle) or {}).get("realise") for l in lignes)
        if prevu is not None or realise is not None:
            categories[cle] = {"libelle": lib, "prevu": prevu, "realise": realise,
                               "taux": realise / prevu * 100 if prevu and realise is not None else None}
    col.update({
        "ids": [r["id"] for r in recs], "nb": len(recs),
        "credits": t["credits"], "engagements": _somme(l["engagements"] for l in lignes), "execution": t["execution"],
        "taux": t["taux"], "attendu": TAUX_ATTENDU.get(rang, 100.0), "statut": statut, "couleur": couleur,
        "recettes_prevues": rp, "recettes_realisees": rr, "taux_recouvrement": rr / rp * 100 if rp and rr is not None else None,
        "categories": categories, **_recettes_par_nature(recs),
        "ratios": {x["code"]: x["valeur"] for x in ratios.agreger(recs)},
        "forme": sum(r["score_forme"] for r in recs) / len(recs),
        "fond": _somme(r["score_fond"] for r in recs) / len([r for r in recs if r["score_fond"] is not None])
        if any(r["score_fond"] is not None for r in recs) else None,
        "anomalies_majeures": sum(r["anomalies_majeures"] for r in recs),
        "ecart_jours": max((r["ecart_jours"] for r in recs if r["ecart_jours"] is not None), default=None),
        "date_reception": recs[0]["date_reception"] if len(recs) == 1 else None,
        "date_limite": recs[0]["date_limite"] if len(recs) == 1 else None,
        "retours": sum(1 for r in recs if r["retour"]),
        "sources": sorted({(r["donnees"].get("montants") or {}).get("source", "") for r in recs} - {""}),
    })
    return col


def _echeance(rang: int, annee: int, parametres: dict) -> date | None:
    """Date limite de transmission du rapport d'une période (paramètres [delais])."""
    d = {**DEFAUT_DELAIS, **(parametres.get("delais") or {})}
    try:
        if rang < 5:
            jj, mm = jour_mois(d[f"trimestre_{rang}_date_limite"])
            return date(annee + 1 if mm < 3 * rang else annee, mm, jj)
        jj, mm = jour_mois(d["rapport_annuel_date_limite"])
        return date(annee + 1, mm, jj)
    except (KeyError, ValueError):
        return None


def comparaison_epn(epn: str | None, annee: int | None, parametres: dict) -> dict:
    """Comparaison budgétaire des rapports d'un EPN (1er au 4e trimestre, et rapport annuel) pour un exercice.
    `epn` = « tous » : ensemble des EPN, trimestre par trimestre."""
    tous = lister()
    if not tous:
        return {"vide": True, "epns": []}
    liste = epns()
    if epn != "tous":
        epn = _epn_valide(epn) or epn_du(max(tous, key=lambda r: r["date_analyse"] or ""))
    records = tous if epn == "tous" else [r for r in tous if epn_du(r) == epn]
    annees = sorted({r["annee"] for r in records}, reverse=True)
    annee = annee if annee in annees else annees[0]
    colonnes = [_colonne(code, rang, annee, nom, [r for r in records if r["annee"] == annee and r["rang"] == rang],
                         parametres) for code, rang, nom in CODES_PERIODES]
    colonnes = [c for c in colonnes if c["rang"] < 5 or c["present"]]  # colonne annuelle seulement si analysée
    for c in colonnes:  # rapport absent : en retard, ou pas encore dû (date limite non atteinte)
        if not c["present"]:
            echeance = _echeance(c["rang"], annee, parametres)
            c["echeance"] = echeance.isoformat() if echeance else None
            c["a_venir"] = bool(echeance and echeance >= date.today())
    # Exécution réalisée au cours de chaque trimestre (les rapports trimestriels sont cumulatifs) : écart avec le
    # trimestre précédent, calculé sur les EPN présents aux deux trimestres.
    par_epn = {c["rang"]: {epn_du(r): r["donnees"].get("montants") or {} for r in records
                           if r["annee"] == annee and r["rang"] == c["rang"]} for c in colonnes}
    for i, c in enumerate(colonnes):
        prec = colonnes[i - 1] if i > 0 and colonnes[i - 1]["rang"] == c["rang"] - 1 else None
        if c["present"] and c["rang"] < 5:
            if c["rang"] == 1:
                c["execution_periode"], c["recettes_periode"] = c["execution"], c["recettes_realisees"]
            elif prec and prec["present"]:
                actuels, precedents = par_epn[c["rang"]], par_epn[prec["rang"]]
                communs = [k for k in actuels if k in precedents]
                c["base_periode"] = len(communs)
                for cle_m, cle_p in (("execution", "execution_periode"), ("recettes_realisees", "recettes_periode")):
                    ecarts = [actuels[k][cle_m] - precedents[k][cle_m] for k in communs
                              if actuels[k].get(cle_m) is not None and precedents[k].get(cle_m) is not None]
                    c[cle_p] = sum(ecarts) if ecarts else None
            # Recouvrement du trimestre par nature : seulement si les deux colonnes portent sur les mêmes EPN
            if c["rang"] == 1 or (prec and prec["present"] and set(par_epn[c["rang"]]) == set(par_epn[prec["rang"]])
                                  and not c["natures_a_reanalyser"] and not prec["natures_a_reanalyser"]):
                for cle_n, n in c["recettes_natures"].items():
                    avant = (prec["recettes_natures"].get(cle_n) or {}).get("realise") if c["rang"] > 1 else 0
                    if c["rang"] > 1 and avant is None and cle_n not in prec["recettes_natures"]:
                        avant = 0  # nature apparue au cours du trimestre
                    n["periode"] = n["realise"] - avant if n["realise"] is not None and avant is not None else None
    fiche = next((e for e in liste if e["cle"] == epn), None)
    valeurs = [c.get("credits") for c in colonnes] + [c.get("recettes_prevues") for c in colonnes]
    u = unite(valeurs)
    return {"vide": False, "epns": liste, "epn": epn, "fiche": fiche, "annees": annees, "annee": annee,
            "colonnes": colonnes, "unite": u, "natures_recettes": _liste_natures_recettes(colonnes),
            "lecture": _lecture_comparaison(colonnes, fiche, annee, u)}


def _liste_natures_recettes(colonnes: list[dict]) -> list[dict]:
    """Groupes de ressources et natures de recettes rencontrés dans les rapports de l'exercice, dans l'ordre du
    budget (ressources du budget général, ressources propres, autres ressources, non classées), puis par code."""
    vus: dict[str, dict] = {}
    for c in colonnes:
        for code, n in (c.get("recettes_natures") or {}).items():
            vus.setdefault(code, {"code": code, "libelle": n["libelle"], "groupe": n["groupe"]})
    out = []
    for code_g, libelle_g in natures.GROUPES_RECETTES:
        membres = sorted((n for n in vus.values() if n["groupe"] == code_g), key=lambda n: n["code"])
        if membres:
            out.append({"groupe": code_g, "libelle": libelle_g, "natures": membres})
    return out


def _statut_texte(statut: str) -> str:
    return statut if statut == "OK" else statut.lower()


def _lecture_comparaison(colonnes: list[dict], fiche: dict | None, annee: int, u: dict) -> str:
    """Lecture rédigée de l'évolution d'un trimestre à l'autre."""
    def m(v):
        return montant_fcfa(v)

    def p(v):
        return "—" if v is None else f"{v:.1f} %".replace(".", ",")
    presents = [c for c in colonnes if c["present"] and c["rang"] < 5]
    absents = [c for c in colonnes if not c["present"] and c["rang"] < 5 and not c.get("a_venir")]
    a_venir = [c for c in colonnes if not c["present"] and c["rang"] < 5 and c.get("a_venir")]
    suite = ""
    if a_venir:
        suite = " ; " + ", ".join(c["code"] for c in a_venir) + " à venir" \
            + (f" (date limite : {date.fromisoformat(a_venir[0]['echeance']):%d/%m/%Y})" if a_venir[0].get("echeance") else "")
    sujet = f"l'{fiche['court']}" if fiche and fiche["court"][:1] in "AEIOUY" else (f"le {fiche['court']}" if fiche else "l'ensemble des EPN")
    if not presents:
        return f"Aucun rapport trimestriel de l'exercice {annee} n'a été analysé pour {sujet}."
    pl = len(presents) > 1
    debut = (f"Pour {sujet}, {len(presents)} rapport{'s' if pl else ''} trimestriel{'s' if pl else ''} de l'exercice {annee} "
             f"{'ont' if pl else 'a'} été analysé{'s' if pl else ''}") if fiche else \
        (f"Pour l'ensemble des EPN, {sum(c['nb'] for c in presents)} rapports de l'exercice {annee} ont été analysés, "
         f"sur {len(presents)} trimestre{'s' if pl else ''}")
    phrases = [f"{debut} ({', '.join(c['code'] for c in presents)})"
               + (f" ; {'manquent' if len(absents) > 1 else 'manque'} : {', '.join(c['code'] for c in absents)}" if absents else "")
               + suite + "."]
    a, b = presents[0], presents[-1]
    if len(presents) > 1:
        if fiche is None and len({c["nb"] for c in presents}) > 1:
            phrases.append("Le nombre de rapports analysés varie d'un trimestre à l'autre ("
                           + ", ".join(f"{c['nb']} au {c['code']}" for c in presents)
                           + ") : les montants cumulés ne portent pas sur les mêmes EPN.")
        if a.get("credits") is not None and b.get("credits") is not None and abs(b["credits"] - a["credits"]) >= 0.5:
            sens = "baisse" if b["credits"] < a["credits"] else "hausse"
            phrases.append(f"Les crédits passent de {m(a['credits'])} au {a['code']} à {m(b['credits'])} au {b['code']} "
                           f"({sens} de {m(abs(b['credits'] - a['credits']))}).")
        if a.get("taux") is not None and b.get("taux") is not None:
            phrases.append(f"Le taux d'exécution passe de {p(a['taux'])} au {a['code']} à {p(b['taux'])} au {b['code']}"
                           + (f", dont {m(b['execution_periode'])} ordonnancés au cours du {b['nom']}" if b.get("execution_periode") is not None else "")
                           + f" (statut au {b['code']} : {_statut_texte(b['statut'])}).")
        if a.get("taux_recouvrement") is not None and b.get("taux_recouvrement") is not None:
            phrases.append(f"Le taux de recouvrement des recettes passe de {p(a['taux_recouvrement'])} à {p(b['taux_recouvrement'])}.")
        phrases += _lecture_natures_recettes(presents, m, p)
        if a.get("forme") is not None and b.get("forme") is not None:
            ecart = b["forme"] - a["forme"]
            tendance = "s'améliore" if ecart >= 2 else "se dégrade" if ecart <= -2 else "reste stable"
            phrases.append(f"La conformité des rapports au canevas {tendance} ({p(a['forme'])} au {a['code']}, {p(b['forme'])} au {b['code']}).")
    else:
        if b.get("taux") is not None:
            phrases.append(f"Au {b['code']}, le taux d'exécution est de {p(b['taux'])} pour un taux attendu de {p(b['attendu'])} "
                           f"(statut : {_statut_texte(b['statut'])}).")
        phrases += _lecture_natures_recettes(presents, m, p)
        phrases.append("La comparaison s'enrichira à mesure de l'analyse des rapports des autres trimestres.")
    return " ".join(phrases)


def _lecture_natures_recettes(presents: list[dict], m, p) -> list[str]:
    """Recouvrement par nature de recettes au dernier rapport (natures les plus dotées, recettes non recouvrées)."""
    avec = [c for c in presents if c.get("recettes_natures")]
    if not avec:
        return []
    b = avec[-1]
    dotees = sorted((n for n in b["recettes_natures"].values() if n["prevu"]), key=lambda n: -n["prevu"])
    if not dotees:
        return []
    def lib(n):
        return n["libelle"].capitalize() if n["libelle"].isupper() else n["libelle"]
    principales = [n for n in dotees if n["realise"]][:3]
    phrases = []
    if principales:
        phrases.append(f"Par nature de recettes, au {b['code']} : "
                       + " ; ".join(f"{lib(n)}, {p(n['taux'])} recouvrés sur {m(n['prevu'])} prévus" for n in principales) + ".")
    sans = [n for n in dotees if not n["realise"]]
    if sans:
        phrases.append(f"Aucun recouvrement au {b['code']} sur : "
                       + " ; ".join(f"{lib(n)} ({m(n['prevu'])} prévus)" for n in sans[:3])
                       + (f" et {len(sans) - 3} autre{'s' if len(sans) > 4 else ''} nature{'s' if len(sans) > 4 else ''}" if len(sans) > 3 else "")
                       + ".")
    return phrases


def toutes_alertes(periode_cle: str | None, parametres: dict, epn: str | None = None) -> dict:
    epn = _epn_valide(epn)
    liste = periodes(epn=epn)
    if not liste:
        return {"vide": True, "alertes": [], "periodes": [], "epns": epns()}
    if not periode_cle or periode_cle not in {p["cle"] for p in liste}:
        periode_cle = liste[0]["cle"]
    p = next(x for x in liste if x["cle"] == periode_cle)
    records = lister(periode_cle, epn=epn)
    lignes = lignes_epn(records, parametres)
    al = alertes_periode(lignes, records, p["rang"], parametres, _totaux(lignes))
    return {"vide": False, "periodes": liste, "periode": p, "alertes": al, "epns": epns(), "epn": epn,
            "unite": unite([l["credits"] for l in lignes])}


def libelle(periode_cle: str) -> str:
    return libelle_periode(periode_cle)
