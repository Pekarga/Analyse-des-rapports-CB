"""Génère des rapports de CB FICTIFS au format du canevas 2023, pour tester l'outil.

- rapport_exemple_conforme.docx : rapport complet, calculs justes ;
- rapport_exemple_anomalies.docx : rubriques manquantes, erreurs de calcul, incohérences, non daté ;
- decret_creation_ANEX.pdf : décret FICTIF de création et d'organisation de l'EPN ;
- situation_execution_30062099.xlsx : situation d'exécution FICTIVE consolidée (plusieurs EPN) au 30/06/2099,
  concordante avec le rapport conforme ;
- situation_execution_ecarts_30062099.xlsx : même situation, avec des écarts volontaires.

Usage : python exemples/generer_exemple.py [dossier_sortie]
"""
from __future__ import annotations

import sys
from pathlib import Path

import docx
from docx.shared import Pt

RESSOURCES = [
    ("Ressources du budget général", None),
    ("731300 Transferts reçus du budget général- Achats de biens et services", (400_000_000, 0)),
    ("731100 Transferts reçus du budget général- Dépenses de personnel", (600_000_000, 50_000_000)),
    ("Sous total", "st"),
    ("Ressources propres", None),
    ("702900 Autres prestations - services vendus", (150_000_000, -10_000_000)),
    ("721470 Location d'immeubles", (50_000_000, 0)),
    ("Sous total", "st"),
    ("Total général", "tg"),
]
TAUX_RECOUVREMENT = {"731300": 0.80, "731100": 0.95, "702900": 0.60, "721470": 0.90}

EMPLOIS = [
    ("1 Personnel", None),
    ("90047390002 Prendre en charge les salaires et accessoires du Personnel Contractuel", (250_000_000, 0)),
    ("90047390140 Prendre en charge les salaires et accessoires du personnel permanent", (350_000_000, 50_000_000)),
    ("Sous total", "st"),
    ("2 Biens et services", None),
    ("90047300011 Assurer le contrôle des opérations budgétaires / CB", (20_000_000, 0)),
    ("90047300012 Assurer le fonctionnement courant des services", (380_000_000, -10_000_000)),
    ("Sous total", "st"),
    ("3 Transferts", None),
    ("90047300013 Apporter un appui aux organismes partenaires", (100_000_000, 0)),
    ("Sous total", "st"),
    ("4 Investissements", None),
    ("90047300020 Acquérir du matériel informatique", (100_000_000, 0)),
    ("Sous total", "st"),
    ("Total général", "tg"),
]
TAUX_EXECUTION = {"90047390002": 0.96, "90047390140": 0.92, "90047300011": 0.70, "90047300012": 0.75,
                  "90047300013": 0.50, "90047300020": 0.30}


def f(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


def t(v: float) -> str:
    return f"{v:.2f} %".replace(".", ",")


def _tableau(d, legende, entetes, lignes):
    d.add_paragraph(legende).runs[0].italic = True
    tab = d.add_table(rows=1, cols=len(entetes))
    tab.style = "Table Grid"
    for j, e in enumerate(entetes):
        tab.rows[0].cells[j].text = e
    for l in lignes:
        cells = tab.add_row().cells
        for j, v in enumerate(l):
            cells[j].text = v
    d.add_paragraph("Source : Ordonnateur / Agent Comptable")


def _presentation(lignes_def):
    """Renvoie les lignes (libellé, initial, modif, actuel) avec sous-totaux et total."""
    out, st, tg = [], [0, 0], [0, 0]
    for lib, v in lignes_def:
        if v is None:
            out.append((lib, "", "", ""))
        elif v == "st":
            out.append((lib, f(st[0]), f(st[1]), f(st[0] + st[1])))
            st = [0, 0]
        elif v == "tg":
            out.append((lib, f(tg[0]), f(tg[1]), f(tg[0] + tg[1])))
        else:
            st = [st[0] + v[0], st[1] + v[1]]
            tg = [tg[0] + v[0], tg[1] + v[1]]
            out.append((lib, f(v[0]), f(v[1]), f(v[0] + v[1])))
    return out, tg


def _execution(lignes_def, taux, recettes=True, erreur=None):
    out, st, tg = [], [0, 0, 0], [0, 0, 0]

    def fmt(lib, ini, fin, real):
        if recettes:
            return (lib, f(ini), f(fin), f(real), t(real / fin * 100 if fin else 0), f(fin - real))
        return (lib, f(ini), f(fin), f(real), t(real / fin * 100 if fin else 0))

    for lib, v in lignes_def:
        if v is None:
            out.append((lib,) + ("",) * (5 if recettes else 4))
        elif v == "st":
            out.append(fmt(lib, *st))
            st = [0, 0, 0]
        elif v == "tg":
            out.append(fmt(lib, *tg))
        else:
            code = lib.split()[0]
            fin = v[0] + v[1]
            real = round(fin * taux[code])
            st = [st[0] + v[0], st[1] + fin, st[2] + real]
            tg = [tg[0] + v[0], tg[1] + fin, tg[2] + real]
            ligne = list(fmt(lib, v[0], fin, real))
            if erreur and code == erreur:
                ligne[4] = t(real / fin * 100 + 7)  # taux volontairement faux
            out.append(tuple(ligne))
    return out, tg


def generer(sortie: Path, anomalies: bool) -> Path:
    d = docx.Document()
    d.styles["Normal"].font.size = Pt(11)
    d.add_paragraph("MINISTERE DU BUDGET ET DU PORTEFEUILLE DE L'ETAT")
    d.add_paragraph("DIRECTION DU CONTRÔLE BUDGETAIRE")
    d.add_heading("RAPPORT DU CONTROLEUR BUDGETAIRE", 0)
    d.add_paragraph("Agence Nationale d'Exemple (ANEX)")
    d.add_paragraph("Rapport d'étape – 1er semestre 2099")

    d.add_paragraph("TABLE DES MATIERES")
    sommaire = ["INTRODUCTION", "I. PRESENTATION DU BUDGET", "II. ANALYSE DE L'EXECUTION DU BUDGET",
                "III. ANALYSE DE LA PERFORMANCE", "V. EVALUATION DES DISPOSITIFS DE CONTROLE",
                "VI. SITUATION DU PATRIMOINE", "VII. SITUATION DE LA GOUVERNANCE DE L'EPN",
                "VIII. ANALYSE DE LA GESTION DES RISQUES", "X. DIFFICULTES ET SUGGESTIONS", "CONCLUSION"]
    if anomalies:
        sommaire.insert(3, "II.3 ANALYSE DES MARCHES PUBLICS")
    for i, s in enumerate(sommaire, start=3):
        d.add_paragraph(f"{s}{'.' * 20}{i}")

    d.add_heading("INTRODUCTION", 1)
    d.add_paragraph("L'Agence Nationale d'Exemple (ANEX) a été créée par le décret n°2099-001 du 01 janvier 2099 "
                    "portant création, attributions, organisation et fonctionnement de l'ANEX. "
                    + ("Elle a pour missions de promouvoir les activités d'exemple et d'en assurer le suivi." if anomalies else
                       "Elle a pour missions de promouvoir les activités d'exemple sur l'ensemble du territoire national, "
                       "d'assurer le suivi et l'évaluation des activités d'exemple, et de conseiller le Gouvernement "
                       "en matière d'exemple. Elle est placée sous la tutelle technique du Ministre chargé de l'Exemple."))
    if not anomalies:
        d.add_paragraph("L'ANEX dispose de trois antennes régionales installées à Bouaké, Korhogo et San Pedro.")
    d.add_paragraph("L'ANEX est financée par les subventions de l'Etat et par ses ressources propres issues "
                    "des prestations de services.")
    d.add_paragraph("L'ANEX est organisée en quatre directions. Son effectif est de 120 agents au 30 juin 2099."
                    + ("" if anomalies else " Ses organes sont le Conseil de gestion et la Direction générale, "
                       "assistés d'un Agent comptable."))
    d.add_paragraph("Le présent rapport est produit conformément aux dispositions de l'article 66 du décret "
                    "n°2021-677 du 03 novembre 2021 portant régime financier et comptable des EPN. "
                    "Il s'articule autour des points suivants : la présentation du budget, l'analyse de son exécution, "
                    "la performance, les dispositifs de contrôle, le patrimoine, la gouvernance, les risques, "
                    "les difficultés et suggestions.")

    d.add_heading("I. PRESENTATION DU BUDGET", 1)
    pres_r, tg_r = _presentation(RESSOURCES)
    pres_e, tg_e = _presentation(EMPLOIS)
    budget_n, budget_n1, budget_n2 = tg_r[0] + tg_r[1], 1_100_000_000, 1_000_000_000
    d.add_heading("I.1- Présentation générale", 2)
    d.add_paragraph(f"Le budget de l'exercice 2099 s'établit à {f(budget_n)} FCFA contre {f(budget_n1)} FCFA en 2098, "
                    f"soit une hausse de {t((budget_n - budget_n1) / budget_n1 * 100)}.")
    _tableau(d, "Tableau 1 : Budget de l'année considérée comparé à celui de l'année précédente",
             ["", "année N-1 (a)", "année N (b)", "Montant (C=b-a)", "Taux Variations d=(c/a) x 100"],
             [("Budget", f(budget_n1), f(budget_n), f(budget_n - budget_n1),
               t((budget_n - budget_n1) / budget_n1 * 100))])
    _tableau(d, "Tableau 2 : Budgets des trois derniers exercices", ["", "année N-2", "année N-1", "année N"],
             [("Budget", f(budget_n2), f(budget_n1 if not anomalies else 1_150_000_000), f(budget_n))])
    d.add_heading("I.2- Présentation des Ressources", 2)
    d.add_paragraph("Les ressources sont constituées majoritairement des transferts de l'Etat.")
    if anomalies:  # erreur de sous-total volontaire
        pres_r[3] = ("Sous total", f(1_000_000_000), f(50_000_000), f(1_100_000_000))
    _tableau(d, "Tableau 3 : Présentation des ressources par nature économique",
             ["Ressources", "Montant initial", "Modifications", "Montant actuel"], pres_r)
    d.add_heading("I.3- Présentation des Emplois", 2)
    d.add_paragraph("Les emplois sont présentés par nature de dépense et par activité.")
    _tableau(d, "Tableau 4 : Présentation des emplois par nature de dépenses et par activité",
             ["Natures de dépense/ Activités", "Montant initial", "Modifications", "Montant actuel"], pres_e)

    d.add_heading("II. ANALYSE DE L'EXECUTION DU BUDGET", 1)
    d.add_paragraph("L'analyse de l'exécution du budget consiste à présenter et commenter le niveau de mobilisation "
                    "des recettes et d'exécution des dépenses.")
    d.add_heading("II.1- Situation d'exécution du budget", 2)
    d.add_heading("II.1.1- Situation d'exécution du budget en recettes", 3)
    exe_r, tgr = _execution(RESSOURCES, TAUX_RECOUVREMENT, True, erreur="702900" if anomalies else None)
    taux_r = tgr[2] / tgr[1] * 100
    d.add_paragraph(f"Au 30 juin 2099, les recouvrements s'élèvent à {f(tgr[2])} FCFA pour une prévision finale de "
                    f"{f(tgr[1])} FCFA, soit un taux de réalisation de {t(taux_r if not anomalies else taux_r + 5)}.")
    _tableau(d, "Tableau 5 : Exécution du budget en recettes",
             ["Ressources", "Prévision initiale", "Prévision finale", "Recouvrement", "Taux de Réalisation", "Ecart"], exe_r)
    d.add_heading("II.1.2- Situation d'exécution du budget en dépenses", 3)
    exe_d, tgd = _execution(EMPLOIS, TAUX_EXECUTION, False)
    d.add_paragraph(f"Les ordonnancements s'élèvent à {f(tgd[2])} FCFA, soit un taux d'exécution de "
                    f"{t(tgd[2] / tgd[1] * 100)}.")
    _tableau(d, "Tableau 6 : Exécution du budget en dépenses",
             ["Natures de dépense/ Activités", "Budget initial", "Budget actuel", "Ordonnancement", "Taux d'Exécution"], exe_d)
    d.add_heading("II.1.3- Analyse des différés et des rejets", 3)
    d.add_paragraph("Au cours de la période, 40 dossiers ont été reçus ; 5 ont été différés et 2 rejetés.")
    _tableau(d, "Tableau 7 : principaux motifs des différés", ["Motif des différés", "Nombre", "Montant équivalent", "Taux"],
             [("Pièces justificatives incomplètes", "3", "6 000 000", "60,00 %"),
              ("Imputation budgétaire erronée", "2", "4 000 000", "40,00 %")])
    if not anomalies:
        _tableau(d, "Tableau 8 : principaux motifs des rejets", ["Motif des rejets", "Nombre", "Montant équivalent", "Taux"],
                 [("Absence de crédits disponibles", "2", "3 000 000", "100,00 %")])
    resultat = tgr[2] - tgd[2]
    d.add_heading("II.2-Analyse du résultat budgétaire", 2)
    sens = "excédentaire" if resultat > 0 else "déficitaire"
    if anomalies:
        sens = "déficitaire" if resultat > 0 else "excédentaire"
    d.add_paragraph(f"Le résultat budgétaire au 30 juin 2099 est {sens} de {f(abs(resultat))} FCFA.")
    if not anomalies:
        rp = sum(round((v[0] + v[1]) * TAUX_RECOUVREMENT[l.split()[0]]) for l, v in RESSOURCES[5:7])
        d.add_heading("II.2.1-Analyse des ratios de gestion", 3)
        pers = sum(round((v[0] + v[1]) * TAUX_EXECUTION[l.split()[0]]) for l, v in EMPLOIS[1:3])
        d.add_paragraph(f"Le ratio de ressources propres (RRP) est de {t(rp / tgr[2] * 100)}. "
                        f"Le ratio des dépenses de personnel (RDP) est de {t(pers / tgd[2] * 100)}.")

    d.add_heading("III. Analyse de la performance", 1)
    d.add_heading("III.1 Programme d'activités", 2)
    d.add_paragraph("Le programme d'activités 2099 comporte 12 activités assorties d'indicateurs et de cibles.")
    d.add_heading("III.2 Évaluation de la réalisation des activités", 2)
    d.add_paragraph("A mi-parcours, 7 activités sur 12 sont réalisées, en cohérence avec le niveau d'exécution budgétaire.")

    d.add_heading("V. EVALUATION DES DISPOSITIFS DE CONTROLE", 1)
    d.add_heading("V.1 Contrôle interne budgétaire", 2)
    d.add_paragraph("Un manuel de procédures existe mais n'est pas actualisé depuis 2090 ; le dispositif reste perfectible.")
    if not anomalies:
        d.add_heading("V.2 Contrôle de gestion", 2)
        d.add_paragraph("Un service de suivi-évaluation des activités existe et produit des rapports trimestriels.")

    d.add_heading("VI. SITUATION DU PATRIMOINE", 1)
    d.add_paragraph("Le patrimoine de l'ANEX comprend un immeuble de bureaux, 10 véhicules et du mobilier de bureau.")
    d.add_paragraph("Les nouvelles acquisitions du semestre portent sur 15 ordinateurs.")
    d.add_paragraph("La comptabilité des matières est tenue par un comptable des matières nommé en 2098.")

    d.add_heading("VII. SITUATION DE LA GOUVERNANCE DE L'EPN", 1)
    d.add_heading("VII.1.1 COGES / Organes de supervision", 2)
    d.add_paragraph("Le Conseil de gestion ne s'est pas réuni au cours du semestre." if anomalies else
                    "Le Conseil de gestion s'est réuni deux fois au cours du semestre, conformément à la périodicité.")
    d.add_heading("VII.1.2 Comité de trésorerie", 2)
    d.add_paragraph("Le comité de trésorerie s'est réuni mensuellement et a examiné les stratégies de mobilisation.")

    if not anomalies:
        d.add_heading("VIII. ANALYSE DE LA GESTION DES RISQUES", 1)
        d.add_paragraph("Les principaux risques identifiés sont budgétaires (retard des transferts) et opérationnels.")

    d.add_heading("X. DIFFICULTES ET SUGGESTIONS", 1)
    d.add_heading("X-1- Difficultés", 2)
    d.add_paragraph("- Retard dans la mise à disposition des transferts de l'Etat ;", style="List Bullet")
    d.add_paragraph("- Transmission tardive des dossiers au visa du Contrôleur Budgétaire ;", style="List Bullet")
    d.add_paragraph("- Insuffisance de personnel qualifié au sein de la direction financière.", style="List Bullet")
    d.add_heading("X-2- Suggestions", 2)
    d.add_paragraph("- Mettre en place un plan de trésorerie pour anticiper les retards de transferts ;", style="List Bullet")
    d.add_paragraph("- Respecter les délais de transmission des dossiers au contrôle budgétaire.", style="List Bullet")

    d.add_heading("CONCLUSION", 1)
    d.add_paragraph(f"Au 30 juin 2099, le taux de réalisation des recettes est de {t(taux_r)} et le taux d'exécution "
                    f"des dépenses de {t(tgd[2] / tgd[1] * 100)}. Dans l'ensemble, les opérations budgétaires ont été "
                    "exécutées dans le respect de la réglementation et les situations sont concordantes.")
    if not anomalies:
        d.add_paragraph("Fait à Abidjan, le 20 juillet 2099")
    d.add_paragraph("Le Contrôleur Budgétaire")
    d.add_paragraph("KOUASSI Exemple")

    nom = "rapport_exemple_anomalies.docx" if anomalies else "rapport_exemple_conforme.docx"
    sortie.mkdir(parents=True, exist_ok=True)
    chemin = sortie / nom
    d.save(chemin)
    return chemin


DECRET = [
    "REPUBLIQUE D'EXEMPLE",
    "DECRET N° 2099-001 DU 01 JANVIER 2099 portant création, attributions, organisation et fonctionnement de "
    "l'Agence Nationale d'Exemple, en abrégé ANEX",
    "CHAPITRE 1 : DISPOSITIONS GENERALES",
    "Article 1 : Il est créé un Etablissement Public National à caractère administratif dénommé « Agence Nationale "
    "d'Exemple », en abrégé « ANEX ».",
    "Article 2 : L'ANEX est placée sous la tutelle technique du Ministre chargé de l'Exemple et sous la tutelle "
    "économique et financière du Ministre chargé du Budget.",
    "Article 3 : Le siège de l'ANEX est fixé à Abidjan. Des antennes régionales peuvent être créées par décision du "
    "Conseil de gestion.",
    "CHAPITRE 2 : MISSIONS",
    "Article 4 : L'ANEX a pour missions :",
    "- de promouvoir les activités d'exemple sur l'ensemble du territoire national ;",
    "- d'assurer le suivi et l'évaluation des activités d'exemple ;",
    "- de conseiller le Gouvernement en matière d'exemple.",
    "CHAPITRE 3 : ORGANISATION ET FONCTIONNEMENT",
    "Article 5 : Les organes de l'ANEX sont :",
    "- le Conseil de gestion ;",
    "- la Direction générale.",
    "Article 6 : Le Conseil de gestion se réunit en session ordinaire deux fois par an, sur convocation de son Président.",
    "Article 7 : La Direction générale est dirigée par un Directeur Général nommé par décret pris en Conseil des Ministres.",
    "CHAPITRE 4 : DISPOSITIONS FINANCIERES",
    "Article 8 : Les ressources de l'ANEX sont constituées par :",
    "- les subventions de l'Etat ;",
    "- les produits des prestations de services ;",
    "- les dons et legs.",
    "Article 9 : Un Agent comptable et un Contrôleur budgétaire sont nommés auprès de l'ANEX conformément au décret "
    "n°2021-677 du 03 novembre 2021.",
]


def generer_decret(sortie: Path) -> Path:
    """Décret FICTIF au format PDF (texte)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    sortie.mkdir(parents=True, exist_ok=True)
    chemin = sortie / "decret_creation_ANEX.pdf"
    styles = getSampleStyleSheet()
    elements = []
    for ligne in DECRET:
        elements += [Paragraph(ligne.replace("&", "&amp;"), styles["Normal"]), Spacer(1, 6)]
    SimpleDocTemplate(str(chemin), pagesize=A4).build(elements)
    return chemin


def generer_situation(sortie: Path, ecarts: bool = False) -> Path:
    """Situation d'exécution FICTIVE consolidée (colonne EPN) au 30/06/2099, au format Excel."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws_r = wb.active
    ws_r.title = "Recettes"
    ws_r.append(["Situation d'exécution du budget des EPN au 30/06/2099 – recettes"])
    ws_r.append([])
    ws_r.append(["EPN", "Code", "Libellé", "Prévision initiale", "Prévision finale", "Recouvrements"])
    for lib, v in RESSOURCES:
        if not isinstance(v, tuple):
            continue
        code = lib.split()[0]
        fin = v[0] + v[1]
        real = round(fin * TAUX_RECOUVREMENT[code])
        if ecarts and code == "702900":
            real += 4_000_000
        ws_r.append(["ANEX", code, lib.split(" ", 1)[1], v[0], fin, real])
    ws_r.append(["OFEX", "731300", "Transferts reçus du budget général", 90_000_000, 90_000_000, 45_000_000])
    ws_d = wb.create_sheet("Dépenses")
    ws_d.append(["Situation d'exécution du budget des EPN au 30/06/2099 – dépenses"])
    ws_d.append([])
    ws_d.append(["EPN", "Code activité", "Libellé", "Nature", "Crédits initiaux", "Budget actuel", "Engagements",
                 "Liquidations", "Ordonnancements"])
    nature = ""
    for lib, v in EMPLOIS:
        if v is None:
            nature = lib.split(" ", 1)[1]
            continue
        if not isinstance(v, tuple):
            continue
        code = lib.split()[0]
        act = v[0] + v[1]
        ordo = round(act * TAUX_EXECUTION[code])
        if ecarts and code == "90047300020":
            ordo += 5_000_000
        eng = min(act, round(ordo * 1.05))
        ws_d.append(["ANEX", code, lib.split(" ", 1)[1], nature, v[0], act, eng, ordo, ordo])
    ws_d.append(["OFEX", "90047300099", "Fonctionnement courant", "Biens et services", 90_000_000, 90_000_000,
                 40_000_000, 35_000_000, 35_000_000])
    sortie.mkdir(parents=True, exist_ok=True)
    chemin = sortie / ("situation_execution_ecarts_30062099.xlsx" if ecarts else "situation_execution_30062099.xlsx")
    wb.save(chemin)
    return chemin


if __name__ == "__main__":
    dossier = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
    for anomalies in (False, True):
        print(generer(dossier, anomalies))
    print(generer_decret(dossier))
    print(generer_situation(dossier, False))
    print(generer_situation(dossier, True))
