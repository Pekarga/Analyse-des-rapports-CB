"""Indicateurs du tableau de bord, calculés à partir de l'historique des analyses.

Le taux d'exécution d'un EPN (ordonnancements / crédits actuels) est apprécié au regard du taux attendu à la fin
de la période (25 % au 1er trimestre, 50 % au 30 juin, 75 % au 3e trimestre, 100 % en fin d'exercice) :
- « Dépassement » si l'exécution dépasse les crédits ;
- « Sous-exécution » si le taux est inférieur au taux attendu de plus de `seuil_sous_execution` points ;
- « À surveiller » si l'écart dépasse `seuil_vigilance` points ;
- « OK » sinon.
"""
from __future__ import annotations

from . import ratios
from .historique import NATURES, libelle_periode, lister, periodes

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
            "id": r["id"], "epn": r["epn"], "court": _nom_court(r), "tutelle": r["tutelle"],
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


def tableau_de_bord(periode_cle: str | None, parametres: dict) -> dict:
    liste = periodes()
    if not liste:
        return {"vide": True, "periodes": []}
    if not periode_cle or periode_cle not in {p["cle"] for p in liste}:
        periode_cle = liste[0]["cle"]
    p = next(x for x in liste if x["cle"] == periode_cle)
    records = lister(periode_cle)
    lignes = lignes_epn(records, parametres)
    tot = _totaux(lignes)

    prec = _precedente(periode_cle, liste)
    tot_prec = _totaux(lignes_epn(lister(prec["cle"]), parametres)) if prec else None
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
        t = _totaux(lignes_epn(lister(q["cle"]), parametres)) if q["cle"] != periode_cle else tot
        evolution.append({"cle": q["cle"], "libelle": q["court"], "credits": t["credits"], "taux": t["taux"]})

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
    }

    alertes = alertes_periode(lignes, records, p["rang"], parametres, tot)
    obj = objectif(p["rang"], parametres)
    synthese = _synthese(lignes, records, tot, obj)

    valeurs = [tot["credits"], tot["execution"]] + [l["credits"] for l in lignes]
    return {
        "vide": False, "periodes": liste, "periode": p, "unite": unite(valeurs), "kpi": tot,
        "comparaison": comparaison, "evolution": evolution, "lignes": lignes,
        "ratios": _ratios_periode(records, lister(prec["cle"]) if prec else []),
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


def _ratios_periode(records: list[dict], precedents: list[dict]) -> dict:
    """Ratios de gestion de la période (tous EPN) et variation, en points, par rapport à la période précédente."""
    agreges = ratios.agreger(records)
    avant = {x["code"]: x["valeur"] for x in ratios.agreger(precedents)} if precedents else {}
    for x in agreges:
        prec = avant.get(x["code"])
        x["variation"] = x["valeur"] - prec if x["valeur"] is not None and prec is not None else None
    bases = sorted({(r["donnees"].get("ratios") or {}).get("base") for r in records} - {None})
    sources = sorted({(r["donnees"].get("ratios") or {}).get("source") for r in records} - {None})
    return {"agreges": agreges, "citations": ratios.citations(records), "bases": bases, "sources": sources,
            "disponibles": sum(1 for r in records if ratios.liste(r)), "rapports": len(records)}


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


def analyse_ratios(periode_cle: str | None) -> dict:
    """Page « Analyse des ratios » : ratios de la période, détail et lecture par EPN, évolution par EPN."""
    liste = periodes()
    if not liste:
        return {"vide": True, "periodes": []}
    if not periode_cle or periode_cle not in {p["cle"] for p in liste}:
        periode_cle = liste[0]["cle"]
    p = next(x for x in liste if x["cle"] == periode_cle)
    records = lister(periode_cle)
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
        for r in lister(q["cle"]):
            valeurs = {x["code"]: x.get("valeur") for x in ratios.liste(r)}
            evolution.setdefault(r["epn"], []).append({"periode": q["court"], **valeurs})
    return {"vide": False, "periodes": liste, "periode": p, "lignes": lignes,
            "ratios": _ratios_periode(records, lister(prec["cle"]) if prec else []),
            "precedente": prec["court"] if prec else "", "evolution": evolution,
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


def comparaison(periode_cle: str | None, parametres: dict) -> dict:
    liste = periodes()
    if not liste:
        return {"vide": True}
    if not periode_cle or periode_cle not in {p["cle"] for p in liste}:
        periode_cle = liste[0]["cle"]
    lignes = lignes_epn(lister(periode_cle), parametres)
    # Évolution du taux d'exécution de chaque EPN sur toutes les périodes analysées
    historiques: dict[str, list] = {}
    for q in sorted(liste, key=lambda x: (x["annee"], x["rang"])):
        for l in lignes_epn(lister(q["cle"]), parametres):
            historiques.setdefault(l["epn"], []).append({"periode": q["court"], "taux": l["taux"]})
    valeurs = [l["credits"] for l in lignes] + [l["recettes_prevues"] for l in lignes]
    return {"vide": False, "periodes": liste, "periode": next(p for p in liste if p["cle"] == periode_cle),
            "unite": unite(valeurs), "lignes": lignes, "historiques": historiques}


def toutes_alertes(periode_cle: str | None, parametres: dict) -> dict:
    liste = periodes()
    if not liste:
        return {"vide": True, "alertes": [], "periodes": []}
    if not periode_cle or periode_cle not in {p["cle"] for p in liste}:
        periode_cle = liste[0]["cle"]
    p = next(x for x in liste if x["cle"] == periode_cle)
    records = lister(periode_cle)
    lignes = lignes_epn(records, parametres)
    al = alertes_periode(lignes, records, p["rang"], parametres, _totaux(lignes))
    return {"vide": False, "periodes": liste, "periode": p, "alertes": al,
            "unite": unite([l["credits"] for l in lignes])}


def libelle(periode_cle: str) -> str:
    return libelle_periode(periode_cle)
