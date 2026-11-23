"""Interface en ligne de commande.

Exemples :
    python -m analyse_cb rapport.docx --reception 05/08/2025 --charge "M. X"
    python -m analyse_cb dossier_rapports/ --registre registre.csv --sortie resultats/
    python -m analyse_cb rapport.pdf --decret decret_creation.pdf --situation situation_30062025.xlsx
    python -m analyse_cb rapports/ --decret decrets/ --situation situation_consolidee_30062025.xlsx
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analyse import analyser, charger_decrets, charger_parametres, charger_situations, parse_infos
from .controles import lire_csv
from .excel import remplir_modele, tableau_de_bord
from .texte import normaliser

EXTENSIONS = {".docx", ".pdf"}


def _registre(chemin: str | None) -> dict[str, dict]:
    """Registre de réception : fichier;epn;controleur;periode;date_reception;charge_etudes[;decret;situation]"""
    if not chemin:
        return {}
    base = Path(chemin).parent
    registre = {}
    for r in lire_csv(chemin):
        if not r.get("fichier"):
            continue
        for cle in ("decret", "situation"):  # chemins relatifs au registre
            if r.get(cle) and not Path(r[cle]).is_absolute():
                r[cle] = str(base / r[cle])
        registre[normaliser(Path(r["fichier"]).name)] = r
    return registre


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m analyse_cb",
                                description="Analyse automatique des rapports des Contrôleurs Budgétaires (canevas DCB 2023).")
    p.add_argument("entrees", nargs="+", help="Rapport(s) .docx/.pdf ou dossier(s) les contenant")
    p.add_argument("--sortie", "-o", default="resultats", help="Dossier de sortie (défaut : resultats/)")
    p.add_argument("--registre", help="CSV de réception : fichier;epn;controleur;periode;date_reception;charge_etudes")
    p.add_argument("--reception", help="Date de réception par la DCB (jj/mm/aaaa) – rapport unique")
    p.add_argument("--charge", help="Nom du Chargé d'Études")
    p.add_argument("--epn", help="Nom de l'EPN (sinon détecté)")
    p.add_argument("--controleur", help="Nom du Contrôleur Budgétaire (sinon détecté)")
    p.add_argument("--periode", help="Période, ex. « 1er semestre 2025 » ou « exercice 2024 » (sinon détectée)")
    p.add_argument("--parametres", help="Fichier de paramètres TOML (défaut : config/parametres.toml)")
    p.add_argument("--referentiel", help="Référentiel des EPN (défaut : config/referentiel_epn.csv)")
    p.add_argument("--modele", help="Modèle Excel d'analyse (défaut : modeles/Fichier_analyse_des_rapports_des_CB.xlsx)")
    p.add_argument("--decret", action="append", default=[],
                   help="Décret de création et d'organisation (.pdf/.docx/.txt) ou dossier de décrets ; répétable. "
                        "Chaque rapport est associé au décret de son EPN (dénomination ou sigle).")
    p.add_argument("--situation", action="append", default=[],
                   help="Situation d'exécution à la date de la période (.xlsx/.csv/.pdf/.docx) ou dossier ; répétable. "
                        "Un fichier consolidé avec une colonne « EPN » est filtré automatiquement.")
    a = p.parse_args(argv)

    fichiers: list[Path] = []
    for e in a.entrees:
        chemin = Path(e)
        if chemin.is_dir():
            fichiers += sorted(f for f in chemin.iterdir() if f.suffix.lower() in EXTENSIONS and not f.name.startswith("~$"))
        elif chemin.exists():
            fichiers.append(chemin)
        else:
            print(f"Introuvable : {e}", file=sys.stderr)
    if not fichiers:
        print("Aucun rapport à analyser.", file=sys.stderr)
        return 1

    from . import lecture

    def progression(page, total):
        print(f"\r   lecture OCR (document scanné) : page {page}/{total}", end="" if page < total else "\n",
              file=sys.stderr, flush=True)

    lecture.RAPPEL_PROGRESSION = progression
    parametres = charger_parametres(a.parametres)
    registre = _registre(a.registre)
    try:
        decrets = charger_decrets(a.decret)
        situations = charger_situations(a.situation)
    except Exception as exc:
        print(f"Référence illisible : {exc}", file=sys.stderr)
        return 1
    for d in decrets:
        print(f"Décret lu : {d.chemin.name} → {d.nom or '(EPN non identifié)'} – {d.reference or 'référence non lue'}")
    sortie = Path(a.sortie)
    resultats, erreurs = [], 0
    for f in fichiers:
        r = registre.get(normaliser(f.name), {})
        unique = len(fichiers) == 1
        infos = parse_infos(epn=r.get("epn") or (a.epn if unique else None),
                            controleur=r.get("controleur") or (a.controleur if unique else None),
                            charge=r.get("charge_etudes") or a.charge,
                            reception=r.get("date_reception") or (a.reception if unique else None),
                            periode=r.get("periode") or (a.periode if unique else None))
        try:
            res = analyser(f, infos, parametres, a.referentiel,
                           decrets=charger_decrets(r["decret"]) if r.get("decret") else decrets,
                           situations=charger_situations(r["situation"]) if r.get("situation") else situations,
                           reference_unique=unique or bool(r.get("decret") or r.get("situation")))
            fichier_sortie = remplir_modele(res, sortie / f"Analyse_{f.stem}.xlsx", a.modele)
        except Exception as exc:  # un rapport illisible ne doit pas bloquer le lot
            erreurs += 1
            print(f"✗ {f.name} : {exc}", file=sys.stderr)
            continue
        resultats.append((res, fichier_sortie))
        print(f"✓ {f.name} → {fichier_sortie}")
        print(f"   EPN : {res.infos.epn} | {res.periode.libelle} | {res.appreciation_delai}")
        print(f"   Forme : {res.score_forme:.0f} % ({res.mention(res.score_forme)}) | "
              f"constats : {len(res.constats)} dont {res.nb_anomalies_majeures} majeur(s)")
        if res.confrontation or decrets:
            print(f"   Décret : {res.appreciation_decret}")
        if res.situation or situations:
            print(f"   Situation d'exécution : {res.appreciation_situation}")
        for avert in res.doc.avertissements:
            print(f"   ⚠ {avert}")
    if len(resultats) > 1 or a.registre:
        tdb = tableau_de_bord(resultats, sortie / "Tableau_de_bord_rapports_CB.xlsx")
        print(f"Tableau de bord : {tdb}")
    return 1 if erreurs and not resultats else 0


if __name__ == "__main__":
    sys.exit(main())
