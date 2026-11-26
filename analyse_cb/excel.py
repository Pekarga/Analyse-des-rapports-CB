"""Remplissage du fichier d'analyse Excel (modèle de la DCB) et production des onglets de détail."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .analyse import (A_APPRECIER, A_VERIFIER, COHERENT, CONFORME, FIABLE, INCOHERENT, NON_APPLICABLE,
                      NON_CONFORME, NON_FIABLE, NON_RENSEIGNE, SANS_OBJET, RACINE, ResultatAnalyse)
from .controles import CATEGORIES
from .commentaires import aerer, phrase_constat
from .texte import format_taux

MODELE_DEFAUT = RACINE / "modeles" / "Fichier_analyse_des_rapports_des_CB.xlsx"

VERT, ROUGE, ORANGE, GRIS, BLEU = "C6EFCE", "FFC7CE", "FFEB9C", "EDEDED", "DDEBF7"
ENVELOPPE = Alignment(wrap_text=True, vertical="top")
CENTRE = Alignment(wrap_text=True, vertical="center", horizontal="center")
FIN = Side(style="thin", color="999999")
BORDURE = Border(left=FIN, right=FIN, top=FIN, bottom=FIN)
ENTETE = PatternFill("solid", fgColor="1F4E78")
POLICE_AUTO = Font(name="Calibri", size=9, italic=True, color="1F4E78")
MENTION_AUTO = "[Pré-rempli automatiquement – à valider par le Chargé d'Études]"  # mode brouillon uniquement


def _mention(res) -> str:
    return "" if res.validation_directe else MENTION_AUTO


def _prefixe(res) -> str:
    return "" if res.validation_directe else MENTION_AUTO + "\n"


def _mettre_en_forme_statuts(ws, plage: str) -> None:
    premiere = plage.split(":")[0]
    for valeurs, couleur in (((CONFORME, FIABLE, COHERENT), VERT),
                             ((NON_CONFORME, NON_FIABLE, INCOHERENT, NON_RENSEIGNE), ROUGE),
                             ((A_VERIFIER, A_APPRECIER), ORANGE),
                             ((NON_APPLICABLE, SANS_OBJET), GRIS)):
        cond = "OR(" + ",".join(f'{premiere}="{v}"' for v in valeurs) + ")"
        ws.conditional_formatting.add(plage, FormulaRule(formula=[cond], fill=PatternFill("solid", bgColor=couleur)))


def _ecrire_long(ws, ligne: int, texte: str, derniere_ligne: int | None = None, hauteur: float | None = None):
    """Écrit un texte long dans A:E (fusionné) avec retour à la ligne."""
    derniere_ligne = derniere_ligne or ligne
    plage = f"A{ligne}:E{derniere_ligne}"
    for rng in list(ws.merged_cells.ranges):
        if rng.min_row >= ligne and rng.max_row <= derniere_ligne:
            ws.unmerge_cells(str(rng))
    ws.merge_cells(plage)
    c = ws[f"A{ligne}"]
    c.value = texte
    c.alignment = ENVELOPPE
    c.font = Font(name="Calibri", size=10)
    if hauteur and derniere_ligne == ligne:
        ws.row_dimensions[ligne].height = hauteur


def _ajuster_texte(ws, ligne: int, texte: str, colonnes: str = "ABCDE", derniere: int | None = None) -> None:
    """Hauteur de ligne (et au besoin taille de police) pour qu'un texte rédigé tienne entièrement dans la cellule
    fusionnée : Excel limite la hauteur d'une ligne à 409 points."""
    import math
    largeur = sum(ws.column_dimensions[c].width or 9 for c in colonnes)
    nb_lignes = (derniere or ligne) - ligne + 1
    for taille in (10, 9.5, 9, 8.5, 8):
        car_par_ligne = largeur * 1.2 * 11 / taille
        nb = sum(max(1, math.ceil(len(p) / car_par_ligne)) for p in texte.split("\n"))
        hauteur = nb * taille * 1.35 + 6
        if hauteur <= 409 * nb_lignes:
            break
    for r in range(ligne, ligne + nb_lignes):
        ws.row_dimensions[r].height = min(409, max(15, hauteur / nb_lignes))
    ws[f"A{ligne}"].font = Font(name="Calibri", size=taille)
    ws[f"A{ligne}"].alignment = Alignment(wrap_text=True, vertical="top", horizontal="justify")


def _hauteur(texte: str, largeur_car: int = 60, mini: float = 18) -> float:
    lignes = sum(max(1, -(-len(p) // largeur_car)) for p in str(texte).split("\n"))
    return max(mini, min(400, 13 * lignes + 4))


def _texte_cellule(ws, cellule: str) -> str:
    from .texte import normaliser
    return normaliser(str(ws[cellule].value or ""))


def remplir_modele(res: ResultatAnalyse, sortie: str | Path, modele: str | Path | None = None) -> Path:
    """Remplit le modèle de fichier d'analyse (modèle en vigueur, ou `modele`). Les lignes à remplir sont celles que
    modele.calculer_plan retrouve d'après les libellés de la colonne A."""
    from . import canevas, modele as modeles
    if modele:
        modele = Path(modele)
        plan = modeles.calculer_plan(modele, canevas.RUBRIQUES, canevas.TABLEAUX, canevas.alias_dcb(),
                                     modeles.lignes_forcees() if modele == modeles.modele_courant() else None)
        if not plan.valide:
            raise ValueError("Modèle de fichier d'analyse inutilisable : lignes introuvables – " + " ; ".join(plan.manquantes))
    else:
        plan = canevas.plan()
        modele = plan.chemin
    a = plan.ancres
    wb = load_workbook(modele)
    ws = wb.worksheets[0]
    ws.title = ws.title or "Analyse"

    # ---------------------------------------------------------------- en-tête
    gras = InlineFont(b=True, rFont="Calibri", sz=11)
    normal = InlineFont(rFont="Calibri", sz=11, color="1F4E78")
    for ancre, valeur in (
        ("epn", res.infos.epn),
        ("controleur", res.infos.controleur or "(non identifié)"),
        ("periode", res.periode.libelle),
        ("reception", res.infos.date_reception.strftime("%d/%m/%Y") if res.infos.date_reception else "(à renseigner)"),
        ("charge", res.infos.charge_etudes or "(à renseigner)"),
    ):
        if ancre not in a:
            continue
        cellule = ws[f"A{a[ancre]}"]
        libelle = str(cellule.value or "")
        libelle = libelle if libelle.endswith(" ") else libelle.rstrip() + " "
        cellule.value = CellRichText([TextBlock(gras, libelle), TextBlock(normal, str(valeur))])
    if "canevas" in a:
        c = ws[f"E{a['canevas']}"]
        c.value = f"→ {res.canevas_en_vigueur[0]}"
        c.font = Font(bold=True, color="1F4E78")
        c.alignment = ENVELOPPE
        if a["canevas"] + 1 not in plan.libelles:
            ws[f"A{a['canevas'] + 1}"].value = res.canevas_en_vigueur[1]
            ws[f"A{a['canevas'] + 1}"].font = POLICE_AUTO
    ligne_mention = plan.premiere_vide(1, a.get("epn") or 4)
    if ligne_mention < (a.get("epn") or 4):
        entete = _mention(res)
        ws[f"A{ligne_mention}"].value = ((entete + " – " if entete else "") + f"Rapport analysé : {res.doc.chemin.name}"
                                         + (" (document scanné)" if res.doc.ocr else "")
                                         + f" – analyse du {date.today():%d/%m/%Y}")
        ws[f"A{ligne_mention}"].font = POLICE_AUTO

    # ---------------------------------------------------------------- libellés du modèle de la DCB corrigés
    # (le modèle de la DCB intitule « forme » l'encadré du fond, nomme « Contrôle de gestion / Contrôle de
    # trésorerie » les lignes du COGES et du comité de trésorerie, et inverse les numéros des tableaux 1 et 2) ;
    # un libellé déjà modifié dans un modèle importé est laissé tel quel.
    for ligne, attendu, libelle in (
            (plan.forme.get("coges"), "controle de gestion", " - COGES / Organes de supervision (Conseil de gestion)"),
            (plan.forme.get("comite_tresorerie"), "controle de tresorerie", " - Comité de trésorerie"),
            (plan.fond.get("coges"), "controle de gestion", " - COGES / Organes de supervision (Conseil de gestion)"),
            (plan.fond.get("comite_tresorerie"), "controle de tresorerie", " - Comité de trésorerie"),
            (plan.forme.get("T2"), "tableau 1 : budget des trois derniers exercices",
             " - Tableau 2 : Budgets des trois derniers exercices"),
            (plan.forme.get("T1"), "tableau 2 : variation du budget global",
             " - Tableau 1 : Budget de l'année comparé à celui de l'année précédente"),
            (a.get("appreciation_fond"), "appreciation generale de la forme", "Appréciation générale du fond du rapport : ")):
        if ligne and _texte_cellule(ws, f"A{ligne}").strip(" -").startswith(attendu):
            ws[f"A{ligne}"].value = libelle

    # ---------------------------------------------------------------- I. délai
    if "delai" in a:
        d = a["delai"] + 1
        ws[f"A{d}"].value = res.periode.fin
        ws[f"B{d}"].value = res.date_limite
        ws[f"C{d}"].value = res.infos.date_reception
        for col in "ABC":
            ws[f"{col}{d}"].number_format = "DD/MM/YYYY"
            ws[f"{col}{d}"].alignment = CENTRE
        ws[f"D{d}"].value = f'=IF(AND(ISNUMBER(B{d}),ISNUMBER(C{d})),C{d}-B{d},"")'
        ws[f"D{d}"].number_format = "0"
        ws[f"D{d}"].alignment = CENTRE
        ws[f"E{d}"].value = (f'=IF(D{d}="","Date de réception non renseignée",IF(D{d}<=0,"Transmis dans les délais",'
                             f'"Hors délai de "&D{d}&IF(D{d}>1," jours"," jour")))')
        ws[f"E{d}"].alignment = ENVELOPPE
        if not res.validation_directe and d + 2 not in plan.libelles:
            ws[f"A{d + 2}"].value = ("Date limite calculée selon les paramètres de l'application ; l'écart et "
                                     "l'appréciation se recalculent si vous modifiez les dates.")
            ws[f"A{d + 2}"].font = POLICE_AUTO

    # ---------------------------------------------------------------- II. forme
    lignes_forme = []
    for l in res.forme:
        ligne = plan.forme.get(l.code)
        if not ligne:
            continue
        lignes_forme.append(ligne)
        ws[f"C{ligne}"].value = l.statut
        ws[f"C{ligne}"].alignment = CENTRE
        texte_e = aerer(l.redige or l.precision, 62)
        ws[f"E{ligne}"].value = texte_e
        ws[f"E{ligne}"].alignment = ENVELOPPE
        ws[f"E{ligne}"].font = Font(name="Calibri", size=9)
        ws.row_dimensions[ligne].height = max(ws.row_dimensions[ligne].height or 15, _hauteur(texte_e, 70, 22))
    ws.column_dimensions["E"].width = 55
    if lignes_forme:
        plage = f"C{min(lignes_forme)}:C{max(lignes_forme)}"
        dv_forme = DataValidation(type="list", formula1=f'"{CONFORME},{NON_CONFORME},{A_VERIFIER},{NON_APPLICABLE}"',
                                  allow_blank=True)
        ws.add_data_validation(dv_forme)
        dv_forme.add(plage)
        _mettre_en_forme_statuts(ws, plage)

    from .redaction import appreciation_forme
    synthese_forme = _prefixe(res) + aerer(appreciation_forme(res))
    ligne_af = plan.premiere_vide(a["appreciation_forme"])
    _ecrire_long(ws, ligne_af, synthese_forme.strip())
    _ajuster_texte(ws, ligne_af, synthese_forme.strip())

    # ---------------------------------------------------------------- III. fond
    lignes_fond = []
    for l in res.fond:
        ligne = plan.fond.get(l.code)
        if not ligne:
            continue
        lignes_fond.append(ligne)
        for col, val in (("C", l.fiabilite), ("D", l.coherence)):
            ws[f"{col}{ligne}"].value = val
            ws[f"{col}{ligne}"].alignment = CENTRE
        texte_e = aerer(l.redige or l.commentaire, 62)
        ws[f"E{ligne}"].value = texte_e
        ws[f"E{ligne}"].alignment = ENVELOPPE
        ws[f"E{ligne}"].font = Font(name="Calibri", size=9)
        ws.row_dimensions[ligne].height = max(ws.row_dimensions[ligne].height or 15, _hauteur(texte_e, 70, 22))
    if lignes_fond:
        haut, bas = min(lignes_fond), max(lignes_fond)
        dv_fond_f = DataValidation(type="list", formula1=f'"{FIABLE},{NON_FIABLE},{A_APPRECIER},{NON_RENSEIGNE},{SANS_OBJET}"',
                                   allow_blank=True)
        dv_fond_c = DataValidation(type="list", formula1=f'"{COHERENT},{INCOHERENT},{A_APPRECIER},{NON_RENSEIGNE},{SANS_OBJET}"',
                                   allow_blank=True)
        ws.add_data_validation(dv_fond_f)
        ws.add_data_validation(dv_fond_c)
        dv_fond_f.add(f"C{haut}:C{bas}")
        dv_fond_c.add(f"D{haut}:D{bas}")
        _mettre_en_forme_statuts(ws, f"C{haut}:D{bas}")
    from .redaction import appreciation_fond
    synthese_fond = _prefixe(res) + aerer(appreciation_fond(res))
    ligne_ad = plan.premiere_vide(a["appreciation_fond"])
    _ecrire_long(ws, ligne_ad, synthese_fond)
    _ajuster_texte(ws, ligne_ad, synthese_fond)

    # ---------------------------------------------------------------- IV. difficultés et suggestions
    lignes_diff = {cat: a[f"diff_{cat}"] for cat in ("execution", "controle", "gestion") if f"diff_{cat}" in a}
    lignes_sugg = {cat: a[f"sugg_{cat}"] for cat in ("execution", "controle", "gestion") if f"sugg_{cat}" in a}
    for cle, depart, col_appr in (("difficultes", lignes_diff, "D"), ("suggestions", lignes_sugg, "C")):
        elements = res.difficultes.get(cle, [])
        for cat, ligne in depart.items():
            items = [e for e in elements if e.categorie == cat]
            if not items:
                ws[f"E{ligne}"].value = "Aucun élément formulé dans cette catégorie."
                ws[f"E{ligne}"].font = Font(name="Calibri", size=9, italic=True)
                continue
            texte = "\n".join(f"• {e.texte}" for e in items)
            ws[f"E{ligne}"].value = texte
            ws[f"E{ligne}"].alignment = ENVELOPPE
            ws[f"E{ligne}"].font = Font(name="Calibri", size=9)
            ws.row_dimensions[ligne].height = _hauteur(texte, 50, 22)
            if cle == "difficultes":
                pages = sorted({e.page for e in items if e.page})
                ws[f"C{ligne}"].value = items[0].rubrique + (f" (p. {', '.join(map(str, pages))})" if pages else "")
                ws[f"C{ligne}"].alignment = ENVELOPPE
            ws[f"{col_appr}{ligne}"].value = "Retenue" if res.validation_directe else A_APPRECIER
            ws[f"{col_appr}{ligne}"].alignment = CENTRE
    nd, ns = len(res.difficultes.get("difficultes", [])), len(res.difficultes.get("suggestions", []))
    if "appreciation_difficultes" in a:
        _ecrire_long(ws, plan.premiere_vide(a["appreciation_difficultes"]), f"{nd} difficulté(s) extraite(s) du rapport. "
                     + ("Vérifier le classement par catégorie et apprécier leur pertinence." if nd else
                        "Aucune difficulté n'a été extraite : vérifier la partie « Difficultés et suggestions »."),
                     hauteur=30)
    if "appreciation_suggestions" in a:
        _ecrire_long(ws, plan.premiere_vide(a["appreciation_suggestions"]), f"{ns} suggestion(s) extraite(s) du rapport. "
                     + ("Apprécier leur caractère opérationnel et leur lien avec les difficultés." if ns else
                        "Aucune suggestion n'a été extraite."), hauteur=30)

    # ---------------------------------------------------------------- V. appréciation générale
    from .redaction import appreciation_generale
    projet = _prefixe(res) + aerer(appreciation_generale(res))
    debut_v = plan.premiere_vide(a["appreciation_generale"])
    fin_v = max(debut_v, a["suite"] - 2)
    _ecrire_long(ws, debut_v, projet, fin_v)
    _ajuster_texte(ws, debut_v, projet, derniere=fin_v)
    suite = aerer(suite_a_donner(res))
    _ecrire_long(ws, a["suite"] + 1, suite, a["suite"] + 3)
    ws.print_area = f"A1:E{a['suite'] + 4}"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0

    ajouter_onglets_detail(wb, res)
    sortie = Path(sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    wb.save(sortie)
    return sortie


def suite_a_donner(res: ResultatAnalyse) -> str:
    seuil = res.parametres.get("appreciation", {}).get("retour_cb_si_score_forme_inferieur_a", 75)
    if res.score_forme < seuil or res.nb_anomalies_majeures >= res.parametres.get("appreciation", {}).get(
            "retour_cb_si_anomalies_majeures", 3):
        return (f"Compte tenu de ces insuffisances, sur la forme ({res.score_forme:.0f} % de conformité) comme sur le fond "
                f"({res.nb_anomalies_majeures} anomalies majeures), le rapport est retourné au Contrôleur Budgétaire "
                "pour correction et complément.")
    return ("Le rapport est exploitable. Il est intégré à la synthèse des rapports des Contrôleurs Budgétaires, "
            "les observations ci-dessus devant être prises en compte dans le prochain rapport.")


# ------------------------------------------------------------------ onglets de détail
COULEURS_STATUT = {"rouge": ROUGE, "orange": ORANGE, "jaune": "FFF2CC", "vert": VERT, "gris": GRIS, "bleu": BLEU}


def _onglet_natures(wb, res) -> None:
    """Analyse par nature économique (situation d'exécution, sinon tableaux du rapport)."""
    from . import natures
    from .analyse import charger_parametres
    from .historique import cle_periode
    n = natures.extraire(res)
    if not n["depenses"] and not n["recettes"]:
        return
    a = natures.analyser(n["depenses"], n["recettes"], cle_periode(res.periode)[2], charger_parametres())
    ws = wb.create_sheet("Nature économique")
    ws["A1"] = "Analyse de l'exécution par nature économique"
    ws["A1"].font = Font(bold=True, size=13, color="1F4E78")
    ws["A2"] = "Sources : " + " ; ".join(sorted({s for s in (n["source_depenses"], n["source_recettes"]) if s})) + "."
    ws["A2"].font = POLICE_AUTO
    ws["A3"] = a["lecture"]
    ws["A3"].alignment = ENVELOPPE
    ws.merge_cells("A3:K3")
    ws.row_dimensions[3].height = 75
    i = 5
    ws.cell(i, 1, "Points d'attention").font = Font(bold=True)
    for p in a["points"]:
        i += 1
        ws.cell(i, 1, {"critique": "Critique", "attention": "À examiner", "info": "Information"}[p["niveau"]])
        ws.cell(i, 2, p["titre"]).font = Font(bold=True)
        ws.cell(i, 3, p["detail"]).alignment = ENVELOPPE
        ws.merge_cells(start_row=i, start_column=3, end_row=i, end_column=11)
        ws.row_dimensions[i].height = 30
    i += 2
    if a["categories"]:
        _ecrire_natures(ws, i, a["categories"], True)
        i += 2 + sum(1 + len(c["natures"]) for c in a["categories"]) + 1
    if a["recettes"]:
        _ecrire_natures(ws, i + 1, a["recettes"], False)


def _ecrire_natures(ws, i: int, groupes: list[dict], depenses: bool) -> None:
    titres = (["Nature", "Libellé", "Crédits initiaux", "Crédits actuels", "Engagements", "Ordonnancements",
               "Prises en charge", "Taux d'exécution (%)", "Statut", "Activités"] if depenses else
              ["Nature", "Libellé", "Prévisions initiales", "Prévisions actuelles", "Recouvrements", "", "",
               "Taux de recouvrement (%)", "Statut", ""])
    ws.cell(i, 1, "Dépenses par nature économique" if depenses else "Recettes par nature économique").font = Font(bold=True)
    _entetes(ws, i + 1, titres, [10, 55, 16, 16, 16, 16, 16, 12, 18, 10])
    j = i + 1
    for g in groupes:
        j += 1
        _ligne(ws, j, ["", g["libelle"], g.get("initial"), g.get("actuel"), g.get("engage") if depenses else g.get("realise"),
                       g.get("realise") if depenses else None, g.get("paye") if depenses else None,
                       round(g["taux"], 1) if g.get("taux") is not None else None, "", ""], BLEU)
        for c in range(1, 11):
            ws.cell(j, c).font = Font(bold=True)
        for nat in g["natures"]:
            j += 1
            _ligne(ws, j, [nat["code"], nat["libelle"], nat.get("initial"), nat.get("actuel"),
                           nat.get("engage") if depenses else nat.get("realise"),
                           nat.get("realise") if depenses else None, nat.get("paye") if depenses else None,
                           round(nat["taux"], 1) if nat.get("taux") is not None else None, nat["statut"],
                           nat.get("activites") or "" if depenses else ""])
            ws.cell(j, 9).fill = PatternFill("solid", fgColor=COULEURS_STATUT.get(nat["couleur"], GRIS))
        for c in range(3, 8):
            for r in range(i + 2, j + 1):
                ws.cell(r, c).number_format = "# ##0"


def _entetes(ws, ligne: int, titres: list[str], largeurs: list[int]):
    for j, (t, w) in enumerate(zip(titres, largeurs), start=1):
        c = ws.cell(ligne, j, t)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = ENTETE
        c.alignment = CENTRE
        c.border = BORDURE
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = ws.cell(ligne + 1, 1)


def _ligne(ws, ligne: int, valeurs: list, couleur: str | None = None):
    for j, v in enumerate(valeurs, start=1):
        c = ws.cell(ligne, j, v)
        c.alignment = ENVELOPPE
        c.border = BORDURE
        if couleur:
            c.fill = PatternFill("solid", fgColor=couleur)


def _couleur(statut: str) -> str | None:
    return {CONFORME: VERT, FIABLE: VERT, COHERENT: VERT, NON_CONFORME: ROUGE, NON_FIABLE: ROUGE,
            INCOHERENT: ROUGE, NON_RENSEIGNE: ROUGE, A_VERIFIER: ORANGE, A_APPRECIER: ORANGE,
            "Majeure": ROUGE, "Mineure": ORANGE}.get(statut)


def ajouter_onglets_detail(wb: Workbook, res: ResultatAnalyse) -> None:
    # Synthèse
    ws = wb.create_sheet("Synthèse")
    ws["A1"] = "Synthèse de l'analyse automatique"
    ws["A1"].font = Font(bold=True, size=14, color="1F4E78")
    infos = [
        ("Fichier analysé", res.doc.chemin.name + (" — document scanné, lu par OCR" if res.doc.ocr else "")), ("EPN", res.infos.epn), ("Contrôleur Budgétaire", res.infos.controleur),
        ("Période", res.periode.libelle), ("Date limite de transmission", res.date_limite.strftime("%d/%m/%Y")),
        ("Date de réception", res.infos.date_reception.strftime("%d/%m/%Y") if res.infos.date_reception else "—"),
        ("Délai", res.appreciation_delai), ("Canevas en vigueur", res.canevas_en_vigueur[0]),
        ("Taux de conformité de la forme", f"{res.score_forme:.0f} % – {res.mention(res.score_forme)}"),
        ("Fiabilité / cohérence (points vérifiables)",
         f"{res.score_fond:.0f} % – {res.mention(res.score_fond)}" if res.score_fond is not None else "—"),
        ("Tableaux du canevas identifiés", ", ".join(sorted(res.tableaux.par_code)) or "aucun"),
        ("Constats automatiques", f"{len(res.constats)} dont {res.nb_anomalies_majeures} majeur(s)"),
        ("Signature / date", res.signature[1]),
        ("Décret de création et d'organisation",
         (f"{res.decret.reference} ({res.decret.chemin.name}) – " if res.decret else "") + res.appreciation_decret),
        ("Situation d'exécution",
         (f"{res.situation.noms_fichiers} – " if res.situation else "") + res.appreciation_situation),
        ("Suite à donner", suite_a_donner(res)),
    ]
    for i, (k, v) in enumerate(infos, start=3):
        ws.cell(i, 1, k).font = Font(bold=True)
        ws.cell(i, 2, v).alignment = ENVELOPPE
    ligne = len(infos) + 4
    if res.doc.avertissements:
        ws.cell(ligne, 1, "Avertissements").font = Font(bold=True, color="C00000")
        for a in res.doc.avertissements:
            ws.cell(ligne, 2, a).alignment = ENVELOPPE
            ligne += 1
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 100

    # Structure complète (y compris rubriques du canevas 2023 absentes de la grille)
    ws = wb.create_sheet("Contrôle structure")
    _entetes(ws, 1, ["Rubrique du canevas", "Niveau", "Dans la grille", "Statut", "Détection", "Nb mots", "Précision"],
             [50, 8, 12, 15, 12, 10, 90])
    from .canevas import PAR_CODE
    for i, l in enumerate(res.forme, start=2):
        rub = PAR_CODE.get(l.code)
        det = res.structure.detections.get(l.code)
        _ligne(ws, i, [l.libelle, rub.niveau if rub else "", "Non" if l.hors_grille else "Oui", l.statut,
                       {"titre": "Titre", "texte": "Texte", None: "—"}[det.mode] if det else "",
                       det.nb_mots if det else "", l.redige or l.precision])
        ws.cell(i, 4).fill = PatternFill("solid", fgColor=_couleur(l.statut) or "FFFFFF")

    # Contrôles automatiques
    ws = wb.create_sheet("Contrôles automatiques")
    _entetes(ws, 1, ["Gravité", "Nature", "Rubrique", "Constat", "Valeur du rapport", "Valeur attendue",
                     "Contrôle effectué", "Détail technique"], [11, 11, 28, 90, 18, 18, 32, 70])
    from .canevas import PAR_CODE as PC
    systeme = "SIGOBE" if getattr(res.situation, "systeme", "") == "SIGOBE" else "système d'information budgétaire"
    ordre = {"Majeure": 0, "Mineure": 1, "Information": 2}
    constats = sorted(res.constats, key=lambda c: (ordre.get(c.gravite, 3), c.nature))
    for i, c in enumerate(constats, start=2):
        _ligne(ws, i, [c.gravite, {"fiabilite": "Fiabilité", "coherence": "Cohérence"}.get(c.nature, c.nature),
                       PC[c.rubrique].libelle if c.rubrique in PC else c.rubrique, phrase_constat(c, systeme),
                       c.constate, c.attendu, c.controle, c.message])
        ws.cell(i, 1).fill = PatternFill("solid", fgColor=_couleur(c.gravite) or "FFFFFF")
    if not constats:
        ws.cell(2, 1, "Aucune anomalie détectée par les contrôles automatiques.")

    # Ratios
    ws = wb.create_sheet("Ratios")
    _entetes(ws, 1, ["Ratio", "Libellé", "Formule (canevas)", "Valeur recalculée", "Valeur citée par le CB",
                     "Cohérence", "Phrase du rapport"], [8, 35, 45, 35, 15, 12, 80])
    for i, r in enumerate(res.transverses.ratios, start=2):
        coh = {True: COHERENT, False: INCOHERENT, None: A_APPRECIER}[r.coherent]
        if coh == A_APPRECIER and res.validation_directe:
            coh = "Non cité" if r.cite is None else "Non vérifiable"
        _ligne(ws, i, [r.code, r.libelle, r.formule,
                       "\n".join(f"{format_taux(v)} (base {b})" for b, v in r.calcule.items()) or "non calculable",
                       format_taux(r.cite) if r.cite is not None else "non cité", coh, r.phrase])
        ws.cell(i, 6).fill = PatternFill("solid", fgColor=_couleur(coh) or "FFFFFF")
    a = res.transverses.agregats
    i = len(res.transverses.ratios) + 3
    ws.cell(i, 1, "Agrégats extraits des tableaux").font = Font(bold=True)
    for k, v in a.items():
        i += 1
        ws.cell(i, 2, k.replace("_", " "))
        ws.cell(i, 3, v).number_format = "# ##0"
    if res.transverses.resultat:
        r = res.transverses.resultat
        i += 2
        ws.cell(i, 1, "Résultat budgétaire recalculé").font = Font(bold=True)
        ws.cell(i, 3, r["resultat"]).number_format = "# ##0"
        ws.cell(i, 4, r["sens"])

    # Difficultés et suggestions
    ws = wb.create_sheet("Difficultés-Suggestions")
    _entetes(ws, 1, ["Type", "Catégorie (proposée)", "Texte extrait du rapport", "Page", "Appréciation du CE"],
             [12, 45, 100, 8, 25])
    i = 2
    libelles = {c: l for c, l, _ in CATEGORIES}
    for cle, nom in (("difficultes", "Difficulté"), ("suggestions", "Suggestion")):
        for e in res.difficultes.get(cle, []):
            _ligne(ws, i, [nom, libelles[e.categorie], e.texte, e.page or "", ""])
            i += 1

    if res.decret:
        _onglet_decret(wb, res)
    if res.situation:
        _onglet_situation(wb, res)
    _onglet_natures(wb, res)

    # Tableaux extraits (pour vérification visuelle)
    ws = wb.create_sheet("Tableaux extraits")
    i = 1
    for t in res.tableaux.tableaux:
        ws.cell(i, 1, f"{t.nom}" + (f" – {t.bloc.legende}" if t.bloc.legende else "")).font = Font(bold=True, color="1F4E78")
        i += 1
        for row in t.bloc.lignes:
            for j, v in enumerate(row, start=1):
                ws.cell(i, j, v).border = BORDURE
            i += 1
        i += 1
    for j in range(1, 9):
        ws.column_dimensions[get_column_letter(j)].width = 22 if j > 1 else 50


_COULEURS_REF = {"Conforme": VERT, "Concordant": VERT, "Écart": ROUGE, "À vérifier": ORANGE, "Information": GRIS,
                 "Écart (décalage de date)": ORANGE,
                 "Non comparable": GRIS}


def _bloc_infos(ws, ligne: int, infos: list[tuple[str, str]]) -> int:
    for k, v in infos:
        ws.cell(ligne, 1, k).font = Font(bold=True)
        c = ws.cell(ligne, 2, v)
        c.alignment = ENVELOPPE
        ws.merge_cells(start_row=ligne, start_column=2, end_row=ligne, end_column=5)
        ws.row_dimensions[ligne].height = _hauteur(v, 110, 15)
        ligne += 1
    return ligne + 1


def _onglet_decret(wb: Workbook, res: ResultatAnalyse) -> None:
    d, conf = res.decret, res.confrontation
    ws = wb.create_sheet("Décret de création")
    ws["A1"] = "Confrontation du rapport au décret de création et d'organisation de l'EPN"
    ws["A1"].font = Font(bold=True, size=14, color="1F4E78")
    ws["A2"] = (_mention(res) + " – " if _mention(res) else "") + ("Décret scanné, lu par reconnaissance de caractères." if d.ocr else "")
    ws["A2"].font = POLICE_AUTO
    i = _bloc_infos(ws, 4, [
        ("Fichier", d.chemin.name), ("Texte de création", d.reference or "(non lu)"),
        ("Dénomination", d.denomination or "(non lue)"), ("Sigle", d.sigle or "—"), ("Catégorie", d.categorie or "—"),
        ("Tutelle technique", d.tutelle_technique or "—"), ("Tutelle économique et financière", d.tutelle_financiere or "—"),
        ("Siège", d.siege or "—"), ("Antennes / implantations", d.antennes or "—"),
        ("Missions", "\n".join(f"• {m}" for m in d.missions) or "(non lues)"),
        ("Organes", " ; ".join(d.organes) or "—"),
        ("Sessions du Conseil de gestion", (f"{d.sessions_conseil_par_an} par an au minimum – {d.phrase_sessions}"
                                            if d.sessions_conseil_par_an else "Périodicité non lue")),
        ("Ressources", "\n".join(f"• {r}" for r in d.ressources) or "(non lues)"),
    ])
    ws.cell(i, 1, "Points de contrôle").font = Font(bold=True, size=12, color="1F4E78")
    _entetes(ws, i + 1, ["Thème", "Rubrique du canevas", "Disposition du décret", "Constat dans le rapport", "Statut",
                         "Appréciation du CE"], [34, 30, 60, 70, 14, 25])
    from .canevas import PAR_CODE
    for k, p in enumerate(conf.points if conf else [], start=i + 2):
        _ligne(ws, k, [p.theme, PAR_CODE[p.rubrique].libelle if p.rubrique in PAR_CODE else p.rubrique,
                       p.disposition, p.constat, p.statut, ""])
        ws.cell(k, 5).fill = PatternFill("solid", fgColor=_COULEURS_REF.get(p.statut, "FFFFFF"))


def _onglet_situation(wb: Workbook, res: ResultatAnalyse) -> None:
    sit, rap = res.situation, res.rapprochement
    ws = wb.create_sheet("Situation d'exécution")
    ws["A1"] = "Rapprochement du rapport avec la situation d'exécution du budget"
    ws["A1"].font = Font(bold=True, size=14, color="1F4E78")
    ws["A2"] = _mention(res)
    ws["A2"].font = POLICE_AUTO
    date_ok = ("—" if not rap or rap.date_conforme is None else
               "conforme à la fin de la période" if rap.date_conforme else
               f"différente de la fin de la période ({res.periode.fin:%d/%m/%Y})")
    i = _bloc_infos(ws, 4, [
        ("Fichier(s)", sit.noms_fichiers + (f" (lignes de l'EPN « {sit.filtre_epn} »)" if sit.filtre_epn else "")),
        ("Date d'arrêté", (f"{sit.date_arrete:%d/%m/%Y} – {date_ok}" if sit.date_arrete else "non trouvée – à vérifier")),
        ("Lignes lues", f"{len(sit.lignes_de('recettes'))} ligne(s) de recettes, {len(sit.lignes_de('depenses'))} ligne(s) de dépenses"),
        ("Synthèse", res.appreciation_situation),
    ] + [("Avertissement", a) for a in sit.avertissements])
    if not rap:
        return
    ws.cell(i, 1, "Rapprochement des agrégats").font = Font(bold=True, size=12, color="1F4E78")
    _entetes(ws, i + 1, ["Agrégat", "Tableau du rapport", "Montant du rapport", "Montant de la situation", "Écart (rapport − situation)",
                         "Statut", "Explication"], [55, 45, 20, 22, 22, 15, 60])
    k = i + 2
    for l in rap.lignes:
        _ligne(ws, k, [l.libelle, l.tableau, l.rapport, l.situation, l.ecart, l.statut, l.note])
        for col in (3, 4, 5):
            ws.cell(k, col).number_format = "# ##0"
            if l.taux and ws.cell(k, col).value is not None:
                ws.cell(k, col).value = ws.cell(k, col).value / 100
                ws.cell(k, col).number_format = "0.00%"
        ws.cell(k, 6).fill = PatternFill("solid", fgColor=_COULEURS_REF.get(l.statut, "FFFFFF"))
        k += 1
    k += 1
    ws.cell(k, 1, "Rapprochement ligne à ligne (par code)").font = Font(bold=True, size=12, color="1F4E78")
    _entetes(ws, k + 1, ["Ligne (code – libellé – montant)", "Tableau du rapport", "Montant du rapport", "Montant de la situation",
                         "Écart (rapport − situation)", "Statut", "Explication"], [55, 45, 20, 22, 22, 15, 60])
    k += 2
    detail = sorted(rap.detail, key=lambda l: (l.statut != "Écart", l.statut != "Écart (décalage de date)"))
    for l in detail:
        _ligne(ws, k, [l.libelle, l.tableau, l.rapport, l.situation, l.ecart, l.statut, l.note])
        for col in (3, 4, 5):
            ws.cell(k, col).number_format = "# ##0"
        ws.cell(k, 6).fill = PatternFill("solid", fgColor=_COULEURS_REF.get(l.statut, "FFFFFF"))
        k += 1
    if not detail:
        ws.cell(k, 1, "Aucun code commun entre les tableaux 5/6 du rapport et la situation (rapprochement global uniquement).")
        k += 1
    for titre, liste in (("Lignes de la situation absentes du rapport", rap.codes_absents_rapport),
                         ("Lignes du rapport absentes de la situation", rap.codes_absents_situation)):
        if liste:
            k += 1
            ws.cell(k, 1, titre).font = Font(bold=True, color="C00000")
            for x in liste:
                k += 1
                ws.cell(k, 1, x)
    # Données de la situation retenues (pour contrôle)
    k += 2
    ws.cell(k, 1, "Données de la situation d'exécution retenues pour l'EPN").font = Font(bold=True, size=12, color="1F4E78")
    from .situation import LIBELLES_GROUPES
    _entetes(ws, k + 1, ["Libellé", "Sens / groupe", "Code", "Initial", "Actuel / final", "Engagements",
                         "Ordonnancements", "Recouvrements"], [55, 45, 20, 22, 22, 15, 18, 18])
    k += 2
    for l in sit.lignes:
        v = l.valeurs
        _ligne(ws, k, [l.libelle, f"{'Recettes' if l.sens == 'recettes' else 'Dépenses'} – {LIBELLES_GROUPES.get(l.groupe, l.groupe)}",
                       l.code, v.get("initial"), v.get("actuel"), v.get("engage"), v.get("ordonnance", v.get("liquide")),
                       v.get("recouvre")])
        for col in range(4, 9):
            ws.cell(k, col).number_format = "# ##0"
        k += 1


# ------------------------------------------------------------------ tableau de bord multi-rapports
def tableau_de_bord(resultats: list[tuple[ResultatAnalyse, Path]], sortie: str | Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Tableau de bord"
    titres = ["EPN", "Contrôleur Budgétaire", "Période", "Date limite", "Date de réception", "Écart (jours)",
              "Délai", "Canevas en vigueur", "Conformité forme (%)", "Appréciation forme", "Fiabilité/cohérence (%)",
              "Rubriques absentes", "Tableaux manquants", "Anomalies majeures", "Anomalies mineures",
              "Signé et daté", "Conformité au décret de création", "Concordance avec la situation d'exécution",
              "Suite à donner", "Fichier d'analyse"]
    _entetes(ws, 1, titres, [35, 25, 28, 12, 12, 10, 22, 18, 12, 18, 12, 50, 22, 10, 10, 14, 40, 60, 60, 40])
    for i, (r, fichier) in enumerate(resultats, start=2):
        tabs_manquants = [l.libelle.split(" :")[0] for l in r.forme
                          if l.code.startswith("T") and l.code[1:].isdigit() and l.statut == NON_CONFORME]
        _ligne(ws, i, [r.infos.epn, r.infos.controleur, r.periode.libelle, r.date_limite, r.infos.date_reception,
                       r.ecart_jours, r.appreciation_delai, r.canevas_en_vigueur[0], r.score_forme,
                       r.mention(r.score_forme), r.score_fond, "; ".join(r.rubriques_absentes),
                       ", ".join(tabs_manquants), r.nb_anomalies_majeures,
                       sum(1 for c in r.constats if c.gravite == "Mineure"), r.signature[0],
                       r.appreciation_decret, r.appreciation_situation, suite_a_donner(r), fichier.name])
        ws.cell(i, 4).number_format = ws.cell(i, 5).number_format = "DD/MM/YYYY"
        ws.cell(i, 20).hyperlink = fichier.name
        if r.confrontation:
            ws.cell(i, 17).fill = PatternFill("solid", fgColor=VERT if r.decret_conforme else ORANGE)
        if r.rapprochement:
            ws.cell(i, 18).fill = PatternFill("solid", fgColor=ROUGE if r.rapprochement.nb_ecarts else VERT)
        ws.cell(i, 9).fill = PatternFill("solid", fgColor=VERT if r.score_forme >= 75 else ORANGE if r.score_forme >= 50 else ROUGE)
        if r.ecart_jours is not None and r.ecart_jours > 0:
            ws.cell(i, 7).fill = PatternFill("solid", fgColor=ROUGE)
    ws.auto_filter.ref = f"A1:{get_column_letter(len(titres))}{len(resultats) + 1}"
    sortie = Path(sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    wb.save(sortie)
    return sortie


# ------------------------------------------------------------------ export du tableau de bord de l'application
def exporter_tableau_de_bord(donnees: dict, sortie: str | Path) -> Path:
    """Classeur Excel reprenant le tableau de bord d'une période : indicateurs, détail par EPN, alertes."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Tableau de bord"
    p, k = donnees["periode"], donnees["kpi"]
    ws["A1"] = f"Tableau de bord – {donnees['epn']['epn'] + ' – ' if donnees.get('epn') else ''}{p['libelle']}"
    ws["A1"].font = Font(bold=True, size=14, color="1F4E78")
    ws["A2"] = f"Montants en FCFA ; {donnees['rapports']['total']} rapport(s) analysé(s)."
    ws["A2"].font = POLICE_AUTO
    indicateurs = [("Crédits budgétaires", k["credits"]), ("Exécution budgétaire", k["execution"]),
                   ("Taux d'exécution (%)", k["taux"]),
                   ("Écarts à analyser (cumul des écarts entre crédits et exécution)", k["ecarts"]),
                   ("Taux d'exécution attendu à la fin de la période (%)", donnees.get("attendu")),
                   ("Taux à partir duquel l'exécution est jugée normale (%)", donnees["objectif"]),
                   ("Rapports à retourner au CB", donnees["rapports"]["retours"]),
                   ("Rapports transmis hors délai", donnees["rapports"]["hors_delai"])]
    for i, (lib, val) in enumerate(indicateurs, start=4):
        ws.cell(i, 1, lib).font = Font(bold=True)
        c = ws.cell(i, 2, round(val, 2) if isinstance(val, float) else val)
        c.number_format = "0.00" if "%" in lib else "# ##0"
    i = len(indicateurs) + 6
    titres = ["EPN", "Ministère de tutelle", "Crédits", "Exécution", "Taux (%)", "Écart", "Statut", "Source des montants",
              "Forme (%)", "Fond (%)", "Anomalies majeures", "Suite"]
    _entetes(ws, i, titres, [40, 34, 18, 18, 10, 18, 16, 28, 10, 10, 12, 26])
    for j, l in enumerate(donnees["lignes"], start=i + 1):
        _ligne(ws, j, [l["epn"], l["tutelle"], l["credits"], l["execution"],
                       round(l["taux"], 2) if l["taux"] is not None else None, l["ecart"], l["statut"], l["source"],
                       l["forme"], round(l["fond"], 1) if l["fond"] is not None else None, l["anomalies_majeures"],
                       "Retour au CB" if l["retour"] else "Exploitable"])
        for col in (3, 4, 6):
            ws.cell(j, col).number_format = "# ##0"
        ws.cell(j, 7).fill = PatternFill("solid", fgColor={"rouge": ROUGE, "orange": ORANGE, "jaune": "FFF2CC",
                                                            "vert": VERT}.get(l["couleur"], GRIS))
    ws3 = wb.create_sheet("Ratios")
    from .ratios import RATIOS
    if "ratios_detail" not in donnees:
        from .tableau import analyse_ratios
        donnees = {**donnees, "ratios_detail": analyse_ratios(donnees["periode"]["cle"],
                                                              (donnees.get("epn") or {}).get("cle"))["lignes"]}
    _entetes(ws3, 1, ["EPN", "Source", "Base des dépenses"] + [f"{c} – {court} (%)" for c, court, *_ in RATIOS]
             + ["Ratios cités par le CB"], [40, 26, 22] + [16] * len(RATIOS) + [60])
    j = 1
    for l in donnees["lignes"]:
        rec = next((r for r in donnees.get("ratios_detail", []) if r["id"] == l["id"]), None)
        if not rec or not rec["ratios"]:
            continue
        j += 1
        valeurs = {x["code"]: x for x in rec["ratios"]}
        cites = [f"{x['code']} cité {x['cite']:.1f} % ({'concordant' if x['coherent'] else 'discordant' if x['coherent'] is False else 'non vérifiable'})".replace(".", ",", 1)
                 for x in rec["ratios"] if x.get("cite") is not None]
        _ligne(ws3, j, [l["epn"], rec["source"], rec["base"]]
               + [round(valeurs[c]["valeur"], 2) if c in valeurs and valeurs[c]["valeur"] is not None else None
                  for c, *_ in RATIOS] + ["; ".join(cites) or "Aucun ratio cité"])
    if j > 1:
        j += 2
        ws3.cell(j, 1, "Ensemble des EPN (pondéré par les montants)").font = Font(bold=True)
        for k, x in enumerate(donnees["ratios"]["agreges"], start=4):
            if x["valeur"] is not None:
                ws3.cell(j, k, round(x["valeur"], 2))
    else:
        ws3.cell(2, 1, "Ratios non disponibles pour cette période (analyses à relancer avec la version 3.1).")
    ws5 = wb.create_sheet("Natures économiques")
    _entetes(ws5, 1, ["EPN", "Sens", "Nature", "Libellé", "Catégorie", "Crédits / prévisions actuels", "Engagements",
                      "Ordonnancements / recouvrements", "Taux (%)", "Statut"], [34, 10, 10, 50, 22, 18, 16, 18, 10, 18])
    from .natures import CATEGORIES, GROUPES_RECETTES, analyser as analyser_natures
    from .historique import lister as lister_analyses
    from .analyse import charger_parametres
    j = 1
    for rec in lister_analyses(donnees["periode"]["cle"], epn=(donnees.get("epn") or {}).get("cle")):
        nat = rec["donnees"].get("natures") or {}
        if not (nat.get("depenses") or nat.get("recettes")):
            continue
        a = analyser_natures(nat.get("depenses") or [], nat.get("recettes") or [], donnees["periode"]["rang"],
                             charger_parametres())
        for sens, groupes, libelles in (("Dépenses", a["categories"], dict(CATEGORIES)),
                                        ("Recettes", a["recettes"], dict(GROUPES_RECETTES))):
            for g in groupes:
                for n in g["natures"]:
                    j += 1
                    _ligne(ws5, j, [rec["epn"], sens, n["code"], n["libelle"], libelles.get(g["code"], g["libelle"]),
                                    n.get("actuel"), n.get("engage") if sens == "Dépenses" else None, n.get("realise"),
                                    round(n["taux"], 1) if n.get("taux") is not None else None, n["statut"]])
                    for c in (6, 7, 8):
                        ws5.cell(j, c).number_format = "# ##0"
                    ws5.cell(j, 10).fill = PatternFill("solid", fgColor=COULEURS_STATUT.get(n["couleur"], GRIS))
    if j == 1:
        ws5.cell(2, 1, "Analyse par nature économique non disponible pour cette période (analyses à relancer).")
    ws4 = wb.create_sheet("Difficultés-Suggestions")
    _entetes(ws4, 1, ["Type", "Catégorie", "EPN", "Texte du rapport", "Page"], [12, 32, 34, 110, 8])
    ds = donnees.get("difficultes") or {}
    libelles = {c["code"]: c["libelle"] for c in ds.get("categories", [])}
    j = 1
    for cle, nom in (("difficultes", "Difficulté"), ("suggestions", "Suggestion")):
        for e in ds.get(cle, []):
            j += 1
            _ligne(ws4, j, [nom, libelles.get(e["categorie"], e["categorie"]), e["epn"], e["texte"], e.get("page") or ""])
    if j == 1:
        ws4.cell(2, 1, "Aucune difficulté ni suggestion relevée dans les rapports de la période.")
    ws2 = wb.create_sheet("Alertes")
    _entetes(ws2, 1, ["Niveau", "Alerte", "EPN", "Détail"], [12, 40, 40, 90])
    for j, a in enumerate(donnees["alertes"], start=2):
        _ligne(ws2, j, [{"critique": "Critique", "attention": "Attention", "info": "Information"}.get(a["niveau"], a["niveau"]),
                        a["titre"], a.get("epn", ""), a.get("detail", "")])
    sortie = Path(sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    wb.save(sortie)
    return sortie
