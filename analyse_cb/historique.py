"""Historique des analyses (base SQLite locale), qui alimente le tableau de bord de l'application.

Chaque analyse est enregistrée avec :
- l'identification (EPN, ministère de tutelle, période, CB, Chargé d'Études) ;
- les indicateurs de qualité du rapport (forme, fond, anomalies, délai, suite à donner) ;
- les montants d'exécution retenus (situation d'exécution si elle est fournie, sinon tableaux du rapport) ;
- les alertes, les principaux constats et l'appréciation générale rédigée.

Une nouvelle analyse du même EPN pour la même période remplace la précédente.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

from .texte import normaliser

LIBELLES_PERIODES = {
    "T1": ("1er trimestre", "janv. – mars"), "T2": ("2e trimestre", "avr. – juin, rapport d'étape"),
    "T3": ("3e trimestre", "juil. – sept."), "T4": ("4e trimestre", "oct. – déc."),
    "A": ("Exercice", "rapport annuel"),
}
RANGS = {"T1": 1, "T2": 2, "T3": 3, "T4": 4, "A": 5}
NATURES = (("personnel", "Personnel"), ("biens_services", "Biens et services"), ("transferts", "Transferts"),
           ("investissement", "Investissements"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cle TEXT UNIQUE,
    date_analyse TEXT,
    rapport TEXT,
    fichier_analyse TEXT,
    epn TEXT,
    sigle TEXT,
    tutelle TEXT,
    periode_cle TEXT,
    annee INTEGER,
    rang INTEGER,
    controleur TEXT,
    charge TEXT,
    date_reception TEXT,
    date_limite TEXT,
    ecart_jours INTEGER,
    score_forme REAL,
    score_fond REAL,
    anomalies_majeures INTEGER,
    anomalies INTEGER,
    retour INTEGER,
    donnees TEXT
);
CREATE INDEX IF NOT EXISTS idx_periode ON analyses (periode_cle);
"""


def chemin_base() -> Path:
    from .ressources import dossier_utilisateur
    return dossier_utilisateur() / "historique.db"


def connexion(chemin: str | Path | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(str(chemin or chemin_base()))
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


# ------------------------------------------------------------------ période
def cle_periode(periode) -> tuple[str, int, int]:
    """(« 2026-T3 », 2026, rang) ; le rapport d'étape au 30 juin correspond au 2e trimestre."""
    if periode.type == "annuel":
        code = "A"
    elif periode.type == "etape":
        code = "T2"
    else:
        code = f"T{periode.trimestre or 4}"
    return f"{periode.annee}-{code}", periode.annee, RANGS[code]


def libelle_periode(cle: str, court: bool = False) -> str:
    annee, code = cle.split("-", 1)
    nom, mois = LIBELLES_PERIODES.get(code, (code, ""))
    if code == "A":
        return f"Exercice {annee}" if court else f"Exercice {annee} ({mois})"
    if court:
        return f"{code} {annee}"
    return f"{nom} {annee} ({mois})"


# ------------------------------------------------------------------ extraction des indicateurs d'une analyse
def _tutelle(res) -> str:
    t = ""
    if res.decret and res.decret.tutelle_technique:
        t = res.decret.tutelle_technique
    elif res.situation and getattr(res.situation, "section", ""):
        t = res.situation.section
    else:
        from .controles import charger_referentiel
        from .analyse import REFERENTIEL_DEFAUT
        nom = normaliser(res.infos.epn)
        for fiche in charger_referentiel(REFERENTIEL_DEFAUT):
            if fiche.tutelle and ((fiche.sigle and normaliser(fiche.sigle) in nom)
                                  or (fiche.denomination and normaliser(fiche.denomination) in nom)):
                t = fiche.tutelle
                break
    t = re.sub(r"^\s*(le |la )?ministre\b", "Ministère", t.strip(), flags=re.I)
    t = re.sub(r"^\s*Ministère chargé (de |des |du )", lambda m: "Ministère " + m.group(1), t)
    return t[:1].upper() + t[1:] if t else "Tutelle non renseignée"


def _sigle(res) -> str:
    if res.decret and res.decret.sigle:
        return res.decret.sigle
    m = re.search(r"\(([A-Z0-9\-]{2,12})\)", res.infos.epn or "")
    return m.group(1) if m else ""


def montants(res) -> dict:
    """Montants d'exécution retenus : situation d'exécution si elle est exploitable, sinon tableaux du rapport."""
    if res.rapprochement and res.situation and res.situation.lignes:
        a = res.situation.agregats()
        d = res.situation.date_arrete
        systeme = "SIGOBE" if getattr(res.situation, "systeme", "") == "SIGOBE" else "situation d'exécution"
        source = f"{systeme} au {d:%d/%m/%Y}" if d else systeme
    else:
        a = res.tableaux.agregats()
        source = "tableaux du rapport"
    m = {
        "credits": a.get("depenses_actuel", a.get("depenses_initial")),
        "credits_initiaux": a.get("depenses_initial"),
        "engagements": a.get("depenses_engage"),
        "execution": a.get("depenses_realise"),
        "recettes_prevues": a.get("recettes_final", a.get("recettes_initial")),
        "recettes_realisees": a.get("recettes_realise"),
        "source": source,
        "natures": {},
    }
    for cle, libelle in NATURES:
        prevu, realise = a.get(f"{cle}_actuel"), a.get(f"{cle}_realise")
        if prevu is not None or realise is not None:
            m["natures"][cle] = {"libelle": libelle, "prevu": prevu, "realise": realise}
    return m


def alertes(res) -> list[dict]:
    """Alertes relatives au rapport (les alertes d'exécution budgétaire sont calculées par le tableau de bord)."""
    from .excel import suite_a_donner
    out = []

    def ajouter(niveau, titre, detail):
        out.append({"niveau": niveau, "titre": titre, "detail": detail})

    if "retourné" in suite_a_donner(res):
        ajouter("critique", "Rapport à retourner au CB",
                f"{res.nb_anomalies_majeures} anomalies majeures ; forme {res.score_forme:.0f} %"
                + (f", fond {res.score_fond:.0f} %" if res.score_fond is not None else "") + ".")
    if res.ecart_jours is not None and res.ecart_jours > 0:
        ajouter("attention", "Rapport transmis hors délai", f"Reçu avec {res.ecart_jours} jour(s) de retard.")
    if res.confrontation:
        for p in res.confrontation.points:
            if p.theme.startswith("Référence du texte") and p.statut == "Écart":
                m = re.search(r"le n°([\w\-/]+), alors que le décret de création est le n°([\w\-/]+)", p.constat)
                ajouter("critique", "Texte de création mal cité",
                        f"Cité sous le n°{m.group(1)} au lieu du n°{m.group(2)}." if m else p.constat)
            if p.rubrique == "coges" and "aucune session" in p.constat:
                ajouter("attention", "Conseil de gestion non réuni", "Aucune session du Conseil de gestion sur la période.")
    if res.rapprochement:
        if any("impossible" in l.note for l in res.rapprochement.detail + res.rapprochement.lignes):
            ajouter("critique", "Montants contredits par la situation d'exécution",
                    "Des montants d'exécution du rapport dépassent ceux de la situation de référence, pourtant postérieure.")
        budget = next((l for l in res.rapprochement.lignes if l.libelle == "Budget actuel de dépenses" and l.statut == "Écart"), None)
        if budget:
            from .texte import format_montant
            ajouter("attention", "Régulation non répercutée",
                    f"Budget actuel présenté pour {format_montant(budget.rapport)} FCFA au lieu de {format_montant(budget.situation)} FCFA.")
    signature = next((l for l in res.forme if l.code == "signature"), None)
    if signature and signature.statut == "Non conforme":
        ajouter("info", "Rapport ni daté ni signé", "La date et la signature du CB manquent.")
    if {"Exercice cité conforme à la période", "Trimestre cité conforme à la période"} & {c.controle for c in res.constats}:
        ajouter("info", "Mentions d'une autre période", "Passages vraisemblablement repris d'un rapport antérieur.")
    return out


def constats_principaux(res, n: int = 12) -> list[dict]:
    from .commentaires import phrase_constat
    systeme = "SIGOBE" if getattr(res.situation, "systeme", "") == "SIGOBE" else "système d'information budgétaire"
    ordre = {"Majeure": 0, "Mineure": 1, "Information": 2}
    cs = sorted(res.constats, key=lambda c: ordre.get(c.gravite, 3))
    return [{"gravite": c.gravite, "texte": phrase_constat(c, systeme)} for c in cs[:n]]


def enregistrer(res, fichier_analyse: str | Path, con: sqlite3.Connection | None = None) -> int:
    """Enregistre (ou remplace) l'analyse d'un rapport ; renvoie son identifiant."""
    from .commentaires import aerer
    from .excel import suite_a_donner
    from .redaction import appreciation_generale
    fermer = con is None
    con = con or connexion()
    pcle, annee, rang = cle_periode(res.periode)
    sigle = _sigle(res)
    cle_epn = normaliser(sigle or res.infos.epn)
    donnees = {
        "periode_libelle": res.periode.libelle,
        "montants": montants(res),
        "alertes": alertes(res),
        "constats": constats_principaux(res),
        "appreciation": aerer(appreciation_generale(res), 140),
        "suite": suite_a_donner(res),
        "decret": res.appreciation_decret if res.confrontation else "",
        "situation": res.appreciation_situation if res.rapprochement else "",
        "delai": res.appreciation_delai,
        "mention_forme": res.mention(res.score_forme),
        "mention_fond": res.mention(res.score_fond),
        "avertissements": list(res.doc.avertissements),
        "ocr": bool(res.doc.ocr),
    }
    valeurs = dict(
        cle=f"{cle_epn}|{pcle}", date_analyse=datetime.now().isoformat(timespec="seconds"), rapport=res.doc.chemin.name,
        fichier_analyse=str(fichier_analyse), epn=res.infos.epn, sigle=sigle, tutelle=_tutelle(res), periode_cle=pcle,
        annee=annee, rang=rang, controleur=res.infos.controleur, charge=res.infos.charge_etudes,
        date_reception=res.infos.date_reception.isoformat() if res.infos.date_reception else None,
        date_limite=res.date_limite.isoformat(), ecart_jours=res.ecart_jours, score_forme=res.score_forme,
        score_fond=res.score_fond, anomalies_majeures=res.nb_anomalies_majeures, anomalies=len(res.constats),
        retour=int("retourné" in suite_a_donner(res)), donnees=json.dumps(donnees, ensure_ascii=False),
    )
    colonnes = ", ".join(valeurs)
    marques = ", ".join("?" for _ in valeurs)
    maj = ", ".join(f"{k}=excluded.{k}" for k in valeurs if k != "cle")
    con.execute(f"INSERT INTO analyses ({colonnes}) VALUES ({marques}) ON CONFLICT(cle) DO UPDATE SET {maj}",
                list(valeurs.values()))
    con.commit()
    ident = con.execute("SELECT id FROM analyses WHERE cle = ?", (valeurs["cle"],)).fetchone()["id"]
    if fermer:
        con.close()
    return ident


def _ligne(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["donnees"] = json.loads(d.get("donnees") or "{}")
    return d


def lister(periode_cle: str | None = None, con: sqlite3.Connection | None = None) -> list[dict]:
    fermer = con is None
    con = con or connexion()
    if periode_cle:
        rows = con.execute("SELECT * FROM analyses WHERE periode_cle = ? ORDER BY epn", (periode_cle,)).fetchall()
    else:
        rows = con.execute("SELECT * FROM analyses ORDER BY annee DESC, rang DESC, epn").fetchall()
    out = [_ligne(r) for r in rows]
    if fermer:
        con.close()
    return out


def obtenir(ident: int, con: sqlite3.Connection | None = None) -> dict | None:
    fermer = con is None
    con = con or connexion()
    row = con.execute("SELECT * FROM analyses WHERE id = ?", (ident,)).fetchone()
    if fermer:
        con.close()
    return _ligne(row) if row else None


def supprimer(ident: int, con: sqlite3.Connection | None = None) -> None:
    fermer = con is None
    con = con or connexion()
    con.execute("DELETE FROM analyses WHERE id = ?", (ident,))
    con.commit()
    if fermer:
        con.close()


def periodes(con: sqlite3.Connection | None = None) -> list[dict]:
    fermer = con is None
    con = con or connexion()
    rows = con.execute("SELECT periode_cle, annee, rang, COUNT(*) AS n FROM analyses "
                       "GROUP BY periode_cle ORDER BY annee DESC, rang DESC").fetchall()
    if fermer:
        con.close()
    return [{"cle": r["periode_cle"], "libelle": libelle_periode(r["periode_cle"]),
             "court": libelle_periode(r["periode_cle"], True), "annee": r["annee"], "rang": r["rang"],
             "rapports": r["n"]} for r in rows]


def aujourd_hui() -> str:
    return date.today().isoformat()
