"""Ratios de gestion du canevas (RRP, RDP, RDF, RDI, RDA) pour le tableau de bord et la page « Analyse des ratios ».

Les ratios sont calculés sur la même source que les montants du tableau de bord : la situation d'exécution (SIGOBE)
lorsqu'elle est fournie, sinon les tableaux du rapport. Conformément au canevas, les ratios de dépenses rapportent
chaque catégorie aux dépenses engagées (à défaut, ordonnancées) et le ratio de ressources propres rapporte les
ressources propres recouvrées au total des ressources recouvrées. Les valeurs citées par le Contrôleur Budgétaire et
leur concordance avec les tableaux du rapport proviennent des contrôles de l'analyse (onglet « Ratios »).
"""
from __future__ import annotations

# code, libellé court, libellé, formule
RATIOS = (
    ("RRP", "Ressources propres", "Ratio de Ressources Propres",
     "Ressources propres recouvrées / total des ressources recouvrées"),
    ("RDP", "Personnel", "Ratio des Dépenses du Personnel", "Dépenses de personnel / total des dépenses"),
    ("RDF", "Fonctionnement", "Ratio des Dépenses de Fonctionnement",
     "Dépenses de fonctionnement (personnel, biens et services, transferts) / total des dépenses"),
    ("RDI", "Investissement", "Ratio des Dépenses d'Investissement", "Dépenses d'investissement / total des dépenses"),
    ("RDA", "Abonnements", "Ratio des Dépenses d'Abonnement", "Dépenses d'abonnement / dépenses de fonctionnement"),
)
BASES = {"engage": "dépenses engagées", "realise": "dépenses ordonnancées"}
CATEGORIES = (("personnel", "Personnel"), ("biens_services", "Biens et services"), ("transferts", "Transferts"),
              ("investissement", "Investissements"))


def valeur(num: float | None, den: float | None) -> float | None:
    """Ratio en % ; un ratio hors de [0 ; 100 %] traduit des totaux incohérents et n'est pas retenu."""
    if num is None or not den:
        return None
    v = num / den * 100
    return v if 0 <= v <= 100.5 else None


def composantes(a: dict, base: str | None = None) -> tuple[dict[str, tuple[float | None, float | None]], str]:
    """Numérateur et dénominateur de chaque ratio à partir des agrégats (situation ou tableaux du rapport)."""
    if base is None or not a.get(f"depenses_{base}"):
        base = "engage" if a.get("depenses_engage") else "realise"
    fonct = [a.get(f"{g}_{base}") for g in ("personnel", "biens_services", "transferts")]
    fonct = sum(v for v in fonct if v is not None) if any(v is not None for v in fonct) else None
    total = a.get(f"depenses_{base}")
    return {
        "RRP": (a.get("ressources_propres_realise"), a.get("recettes_realise")),
        "RDP": (a.get(f"personnel_{base}"), total),
        "RDF": (fonct, total),
        "RDI": (a.get(f"investissement_{base}"), total),
        "RDA": (None, fonct),  # les abonnements ne sont pas isolés dans les tableaux ni dans la situation
    }, base


def completer_situation(situation, a: dict) -> dict:
    """Situation d'exécution dont toutes les lignes sont classées : une catégorie absente vaut zéro (par exemple,
    pas de ressources propres quand toutes les recettes sont des transferts du budget général)."""
    a = dict(a)
    recettes = situation.lignes_de("recettes")
    if recettes and all(l.groupe for l in recettes) and a.get("recettes_realise") is not None:
        a.setdefault("ressources_propres_realise", 0.0)
        a.setdefault("ressources_propres_final", 0.0)
    depenses = situation.lignes_de("depenses")
    if depenses and all(l.groupe for l in depenses):
        for g, _ in CATEGORIES:
            for role in ("actuel", "engage", "realise"):
                if a.get(f"depenses_{role}") is not None:
                    a.setdefault(f"{g}_{role}", 0.0)
    return a


def ratios_rapport(res, source: str) -> dict:
    """Ratios d'un rapport analysé, enregistrés dans l'historique (voir historique.enregistrer)."""
    sigobe = bool(res.rapprochement and res.situation and res.situation.lignes)
    reference = res.situation.agregats() if sigobe else res.tableaux.agregats()
    if sigobe:
        reference = completer_situation(res.situation, reference)
    comp, base = composantes(reference)
    comp_rapport, _ = composantes(res.tableaux.agregats(), base)
    controles = {r.code: r for r in getattr(res.transverses, "ratios", [])}
    liste = []
    for code, court, libelle, formule in RATIOS:
        num, den = comp[code]
        r = controles.get(code)
        liste.append({
            "code": code, "court": court, "libelle": libelle, "formule": formule,
            "num": num, "den": den, "valeur": valeur(num, den),
            "rapport": valeur(*comp_rapport[code]) if sigobe else None,  # recalculé sur les tableaux du rapport
            "cite": r.cite if r else None, "coherent": r.coherent if r else None,
            "phrase": (r.phrase or "")[:220] if r else "",
        })
    total = reference.get(f"depenses_{base}")
    structure = {g: reference.get(f"{g}_{base}") for g, _ in CATEGORIES}
    return {"source": source, "base": BASES[base], "liste": liste, "structure": structure, "total": total}


# ------------------------------------------------------------------ agrégation et lecture
def liste(record: dict) -> list[dict]:
    return ((record.get("donnees") or {}).get("ratios") or {}).get("liste") or []


def agreger(records: list[dict]) -> list[dict]:
    """Ratios de l'ensemble des EPN de la période, pondérés par les montants (Σ numérateurs / Σ dénominateurs)."""
    out = []
    for code, court, libelle, formule in RATIOS:
        num = den = 0.0
        n = 0
        for rec in records:
            x = next((x for x in liste(rec) if x["code"] == code), None)
            if x and x.get("valeur") is not None and x.get("num") is not None and x.get("den"):
                num += x["num"]
                den += x["den"]
                n += 1
        out.append({"code": code, "court": court, "libelle": libelle, "formule": formule,
                    "valeur": valeur(num, den) if n else None, "epn": n})
    return out


def citations(records: list[dict]) -> dict:
    """Ratios cités par les CB : concordants, discordants avec les tableaux du rapport, non vérifiables ; rapports
    ne citant aucun ratio."""
    c = {"concordants": 0, "discordants": 0, "non_verifiables": 0, "rapports_sans_ratio": 0, "rapports": 0}
    for rec in records:
        lst = liste(rec)
        if not lst:
            continue
        c["rapports"] += 1
        cites = [x for x in lst if x.get("cite") is not None]
        if not cites:
            c["rapports_sans_ratio"] += 1
        for x in cites:
            cle = {True: "concordants", False: "discordants"}.get(x.get("coherent"), "non_verifiables")
            c[cle] += 1
    return c


def _pct(v: float | None) -> str:
    return "non calculable" if v is None else f"{v:.1f} %".replace(".", ",")


def lecture(lst: list[dict], base: str = "dépenses engagées") -> str:
    """Lecture rédigée des ratios d'un EPN (deux à quatre phrases)."""
    v = {x["code"]: x.get("valeur") for x in lst}
    if all(val is None for val in v.values()):
        return "Les ratios de gestion ne peuvent pas être calculés : les montants nécessaires ne sont pas disponibles."
    phrases = []
    if v.get("RRP") is not None and v["RRP"] < 0.05:
        phrases.append("Aucune ressource propre n'a été recouvrée : l'établissement dépend entièrement des autres "
                       "ressources, notamment des transferts de l'État.")
    elif v.get("RRP") is not None:
        p = f"Les ressources propres représentent {_pct(v['RRP'])} des ressources recouvrées"
        if v["RRP"] < 25:
            p += " : l'établissement dépend principalement des autres ressources, notamment des transferts de l'État"
        elif v["RRP"] >= 50:
            p += " : l'établissement finance l'essentiel de son activité par ses propres recettes"
        phrases.append(p + ".")
    depenses = [(c, v.get(c)) for c in ("RDP", "RDF", "RDI") if v.get(c) is not None]
    if depenses:
        noms = {"RDP": "de personnel", "RDF": "de fonctionnement", "RDI": "d'investissement"}
        (c0, v0), suite = depenses[0], depenses[1:]
        p = f"Les dépenses {noms[c0]} représentent {_pct(v0)} des {base}"
        autres = [f"celles {noms[c]} {_pct(val)}" for c, val in suite]
        if len(autres) == 1:
            p += " et " + autres[0]
        elif autres:
            p += ", " + ", ".join(autres[:-1]) + " et " + autres[-1]
        phrases.append(p + ".")
        if v.get("RDF") is not None and v["RDF"] >= 80:
            phrases.append("Le fonctionnement absorbe l'essentiel des dépenses"
                           + (" ; l'investissement reste marginal." if (v.get("RDI") or 0) < 10 else "."))
        elif v.get("RDI") is not None and v["RDI"] >= 30:
            phrases.append("L'effort d'investissement est significatif.")
    cites = [x for x in lst if x.get("cite") is not None]
    discordants = [x for x in cites if x.get("coherent") is False]
    if not cites:
        phrases.append("Le Contrôleur Budgétaire ne cite aucun ratio dans son rapport.")
    elif len(discordants) == 1:
        x = discordants[0]
        phrases.append(f"Le {x['code']} cité par le Contrôleur Budgétaire ({_pct(x['cite'])}) ne concorde pas avec "
                       "les tableaux du rapport.")
    elif discordants:
        phrases.append("Les ratios " + ", ".join(x["code"] for x in discordants[:-1]) + f" et {discordants[-1]['code']} "
                       "cités par le Contrôleur Budgétaire ne concordent pas avec les tableaux du rapport.")
    else:
        phrases.append("Les ratios cités par le Contrôleur Budgétaire concordent avec les tableaux du rapport.")
    return " ".join(phrases)
