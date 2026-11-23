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
from .texte import format_montant, format_taux

MODELE_DEFAUT = RACINE / "modeles" / "Fichier_analyse_des_rapports_des_CB.xlsx"

VERT, ROUGE, ORANGE, GRIS, BLEU = "C6EFCE", "FFC7CE", "FFEB9C", "EDEDED", "DDEBF7"
ENVELOPPE = Alignment(wrap_text=True, vertical="top")
CENTRE = Alignment(wrap_text=True, vertical="center", horizontal="center")
FIN = Side(style="thin", color="999999")
BORDURE = Border(left=FIN, right=FIN, top=FIN, bottom=FIN)
ENTETE = PatternFill("solid", fgColor="1F4E78")
POLICE_AUTO = Font(name="Calibri", size=9, italic=True, color="1F4E78")
MENTION_AUTO = "[Pré-rempli automatiquement – à valider par le Chargé d'Études]"


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


def _hauteur(texte: str, largeur_car: int = 60, mini: float = 18) -> float:
    lignes = sum(max(1, -(-len(p) // largeur_car)) for p in str(texte).split("\n"))
    return max(mini, min(400, 13 * lignes + 4))


def remplir_modele(res: ResultatAnalyse, sortie: str | Path, modele: str | Path | None = None) -> Path:
    modele = Path(modele) if modele else MODELE_DEFAUT
    wb = load_workbook(modele)
    ws = wb.worksheets[0]
    ws.title = ws.title or "Analyse"

    # ---------------------------------------------------------------- en-tête
    gras = InlineFont(b=True, rFont="Calibri", sz=11)
    normal = InlineFont(rFont="Calibri", sz=11, color="1F4E78")
    for ligne, libelle, valeur in (
        (4, "EPN : ", res.infos.epn),
        (5, "Contrôleur Budgétaire : ", res.infos.controleur or "(non identifié)"),
        (6, "Période couverte par le présent rapport : ", res.periode.libelle),
        (7, "Date de réception par la DCB : ",
         res.infos.date_reception.strftime("%d/%m/%Y") if res.infos.date_reception else "(à renseigner)"),
        (8, "Chargé d'Etudes : ", res.infos.charge_etudes or "(à renseigner)"),
    ):
        ws[f"A{ligne}"].value = CellRichText([TextBlock(gras, libelle), TextBlock(normal, str(valeur))])
    ws["E9"].value = f"→ {res.canevas_en_vigueur[0]}"
    ws["E9"].font = Font(bold=True, color="1F4E78")
    ws["E9"].alignment = ENVELOPPE
    ws["A10"].value = res.canevas_en_vigueur[1]
    ws["A10"].font = POLICE_AUTO
    ws["A2"].value = (MENTION_AUTO + f" – fichier analysé : {res.doc.chemin.name}"
                      + (" (scanné, lu par OCR)" if res.doc.ocr else "") + f" – le {date.today():%d/%m/%Y}")
    ws["A2"].font = POLICE_AUTO

    # ---------------------------------------------------------------- I. délai
    ws["A14"].value = res.periode.fin
    ws["B14"].value = res.date_limite
    ws["C14"].value = res.infos.date_reception
    for col in "ABC":
        ws[f"{col}14"].number_format = "DD/MM/YYYY"
        ws[f"{col}14"].alignment = CENTRE
    ws["D14"].value = '=IF(AND(ISNUMBER(B14),ISNUMBER(C14)),C14-B14,"")'
    ws["D14"].number_format = "0"
    ws["D14"].alignment = CENTRE
    ws["E14"].value = ('=IF(D14="","Date de réception non renseignée",IF(D14<=0,"Transmis dans les délais",'
                       '"Hors délai de "&D14&" jour(s)"))')
    ws["E14"].alignment = ENVELOPPE
    ws["A16"].value = ("Date limite calculée selon config/parametres.toml ; l'écart et l'appréciation se recalculent "
                       "si vous modifiez les dates.")
    ws["A16"].font = POLICE_AUTO

    # ---------------------------------------------------------------- II. forme
    for l in res.forme:
        if not l.ligne:
            continue
        ws[f"C{l.ligne}"].value = l.statut
        ws[f"C{l.ligne}"].alignment = CENTRE
        ws[f"E{l.ligne}"].value = l.precision
        ws[f"E{l.ligne}"].alignment = ENVELOPPE
        ws[f"E{l.ligne}"].font = Font(name="Calibri", size=9)
        ws.row_dimensions[l.ligne].height = max(ws.row_dimensions[l.ligne].height or 15,
                                                _hauteur(l.precision, 38, 22))
    ws.column_dimensions["E"].width = 55
    dv_forme = DataValidation(type="list", formula1=f'"{CONFORME},{NON_CONFORME},{A_VERIFIER},{NON_APPLICABLE}"',
                              allow_blank=True)
    ws.add_data_validation(dv_forme)
    dv_forme.add("C22:C74")
    _mettre_en_forme_statuts(ws, "C22:C74")

    hors_grille = [l for l in res.forme if l.hors_grille]
    synthese_forme = (f"Taux de conformité de la forme : {res.score_forme:.0f} % – appréciation : "
                      f"{res.mention(res.score_forme)}.\n")
    absentes = [l.libelle for l in res.forme if l.statut == NON_CONFORME]
    if absentes:
        synthese_forme += "Éléments non conformes : " + "; ".join(absentes) + ".\n"
    hg_abs = [l.libelle for l in hors_grille if l.statut in (NON_CONFORME,)]
    if hg_abs:
        synthese_forme += ("Rubriques du canevas 2023 absentes (hors grille) : " + "; ".join(hg_abs) + ".\n")
    _ecrire_long(ws, 78, synthese_forme.strip(), hauteur=_hauteur(synthese_forme, 95, 30))

    # ---------------------------------------------------------------- III. fond
    for l in res.fond:
        if not l.ligne:
            continue
        for col, val in (("C", l.fiabilite), ("D", l.coherence)):
            ws[f"{col}{l.ligne}"].value = val
            ws[f"{col}{l.ligne}"].alignment = CENTRE
        ws[f"E{l.ligne}"].value = l.commentaire
        ws[f"E{l.ligne}"].alignment = ENVELOPPE
        ws[f"E{l.ligne}"].font = Font(name="Calibri", size=9)
        ws.row_dimensions[l.ligne].height = max(ws.row_dimensions[l.ligne].height or 15,
                                                _hauteur(l.commentaire, 38, 22))
    dv_fond_f = DataValidation(type="list", formula1=f'"{FIABLE},{NON_FIABLE},{A_APPRECIER},{NON_RENSEIGNE},{SANS_OBJET}"',
                               allow_blank=True)
    dv_fond_c = DataValidation(type="list", formula1=f'"{COHERENT},{INCOHERENT},{A_APPRECIER},{NON_RENSEIGNE},{SANS_OBJET}"',
                               allow_blank=True)
    ws.add_data_validation(dv_fond_f)
    ws.add_data_validation(dv_fond_c)
    dv_fond_f.add("C83:C123")
    dv_fond_c.add("D83:D123")
    _mettre_en_forme_statuts(ws, "C83:D123")
    majeures = [c for c in res.constats if c.gravite == "Majeure"]
    synthese_fond = (f"Taux de fiabilité/cohérence sur les points vérifiables : "
                     + (f"{res.score_fond:.0f} % – {res.mention(res.score_fond)}" if res.score_fond is not None else "non évaluable")
                     + f". {len(res.constats)} constat(s) automatique(s) dont {len(majeures)} majeur(s) "
                     "(détail dans l'onglet « Contrôles automatiques »).")
    if majeures:
        from .analyse import _court
        synthese_fond += "\nPrincipaux constats : " + " | ".join(_court(c, 160) for c in majeures[:5])
    synthese_fond += f"\nDécret de création et d'organisation : {res.appreciation_decret}."
    synthese_fond += f"\nSituation d'exécution : {res.appreciation_situation}"
    synthese_fond += "\nLes rubriques « À apprécier » nécessitent une lecture qualitative du Chargé d'Études."
    _ecrire_long(ws, 127, synthese_fond, hauteur=_hauteur(synthese_fond, 95, 45))

    # ---------------------------------------------------------------- IV. difficultés et suggestions
    lignes_diff = {"execution": 136, "controle": 138, "gestion": 140}
    lignes_sugg = {"execution": 149, "controle": 152, "gestion": 155}
    for cle, depart, nb_lignes, col_appr in (("difficultes", lignes_diff, 2, "D"), ("suggestions", lignes_sugg, 3, "C")):
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
            ws[f"{col_appr}{ligne}"].value = A_APPRECIER
            ws[f"{col_appr}{ligne}"].alignment = CENTRE
    nd, ns = len(res.difficultes.get("difficultes", [])), len(res.difficultes.get("suggestions", []))
    _ecrire_long(ws, 145, f"{nd} difficulté(s) extraite(s) du rapport. "
                 + ("Vérifier le classement par catégorie et apprécier leur pertinence." if nd else
                    "Aucune difficulté n'a été extraite : vérifier la partie « Difficultés et suggestions »."),
                 hauteur=30)
    _ecrire_long(ws, 160, f"{ns} suggestion(s) extraite(s) du rapport. "
                 + ("Apprécier leur caractère opérationnel et leur lien avec les difficultés." if ns else
                    "Aucune suggestion n'a été extraite."), hauteur=30)

    # ---------------------------------------------------------------- V. appréciation générale
    projet = projet_appreciation(res)
    _ecrire_long(ws, 166, projet, 178)
    for r in range(166, 179):
        ws.row_dimensions[r].height = max(15, _hauteur(projet, 95) / 13)
    suite = suite_a_donner(res)
    _ecrire_long(ws, 181, suite, 183)
    ws.print_area = "A1:E184"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0

    ajouter_onglets_detail(wb, res)
    sortie = Path(sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    wb.save(sortie)
    return sortie


def projet_appreciation(res: ResultatAnalyse) -> str:
    forts, faibles, recos = [], [], []
    if res.ecart_jours is not None:
        (forts if res.ecart_jours <= 0 else faibles).append(res.appreciation_delai.lower())
        if res.ecart_jours > 0:
            recos.append("Respecter les délais de transmission des rapports à la DCB.")
    if res.score_forme >= 90:
        forts.append("respect global du canevas de rédaction")
    absentes = [l.libelle for l in res.forme if l.statut == NON_CONFORME and l.code not in ("signature", "sommaire")]
    if absentes:
        faibles.append("rubriques/tableaux manquants : " + "; ".join(absentes[:10]) + ("…" if len(absentes) > 10 else ""))
        recos.append("Se conformer strictement au canevas en vigueur (note n°0580/MBPE/DGBF/DCB) en intégrant les "
                     "rubriques et tableaux manquants.")
    calc = [c for c in res.tableaux.constats if c.nature == "fiabilite"]
    if res.tableaux.par_code and not calc:
        forts.append("tableaux chiffrés arithmétiquement justes")
    elif calc:
        faibles.append(f"{len(calc)} erreur(s) de calcul dans les tableaux")
        recos.append("Vérifier les calculs (sous-totaux, totaux, taux) avant transmission du rapport.")
    coh = [c for c in res.constats if c.nature == "coherence"]
    if coh:
        faibles.append(f"{len(coh)} incohérence(s) entre tableaux ou entre texte et tableaux")
        recos.append("Assurer la concordance des montants et des taux entre les différents tableaux et les commentaires.")
    elif res.tableaux.par_code:
        forts.append("concordance des données entre tableaux et commentaires")
    if res.signature[0] == NON_CONFORME:
        faibles.append("rapport non signé ou non daté")
        recos.append("Dater et signer le rapport.")
    peu = [l for l in res.forme if l.statut == CONFORME and "peu développée" in l.precision]
    if peu:
        faibles.append("rubriques insuffisamment développées : " + "; ".join(l.libelle for l in peu[:6]))
        recos.append("Approfondir l'analyse des rubriques insuffisamment développées.")
    if not res.difficultes.get("suggestions"):
        recos.append("Formuler des suggestions opérationnelles en réponse aux difficultés relevées.")
    if res.confrontation:
        from .decret import ECART
        ecarts = [p for p in res.confrontation.points if p.statut == ECART]
        if ecarts:
            faibles.append("écarts avec le décret de création et d'organisation (" + ", ".join(p.theme.lower() for p in ecarts) + ")")
            recos.append("Rappeler fidèlement le cadre institutionnel de l'EPN (texte de création, missions, organes, "
                         "ressources) tel que fixé par le décret de création.")
        else:
            forts.append("présentation de l'EPN conforme au décret de création")
    if res.rapprochement:
        if any(c.controle.startswith("Concordance") for c in res.rapprochement.constats):
            faibles.append("montants du rapport non concordants avec la situation d'exécution de référence")
            recos.append("Rapprocher les données du rapport de la situation d'exécution arrêtée à la fin de la période "
                         "(système d'information budgétaire) et justifier les écarts.")
        elif res.rapprochement.nb_concordants:
            forts.append("données d'exécution concordantes avec la situation d'exécution de référence")
    texte = (f"{MENTION_AUTO}\n"
             f"Appréciation globale : forme {res.mention(res.score_forme).lower()} ({res.score_forme:.0f} %), fond "
             + (f"{res.mention(res.score_fond).lower()} ({res.score_fond:.0f} % des points vérifiables)." if res.score_fond is not None
                else "à apprécier (aucun point vérifiable automatiquement).")
             + "\n\nPoints forts : " + ("; ".join(forts) if forts else "à compléter") + "."
             + "\n\nInsuffisances : " + ("; ".join(faibles) if faibles else "aucune insuffisance majeure détectée automatiquement") + "."
             + "\n\nRecommandations au Contrôleur Budgétaire :\n" + ("\n".join(f"- {r}" for r in recos) if recos else "- RAS"))
    return texte


def suite_a_donner(res: ResultatAnalyse) -> str:
    seuil = res.parametres.get("appreciation", {}).get("retour_cb_si_score_forme_inferieur_a", 75)
    if res.score_forme < seuil or res.nb_anomalies_majeures >= res.parametres.get("appreciation", {}).get(
            "retour_cb_si_anomalies_majeures", 3):
        return (f"Proposition : retourner le rapport au Contrôleur Budgétaire pour correction et complétude "
                f"(conformité de forme {res.score_forme:.0f} %, {res.nb_anomalies_majeures} anomalie(s) majeure(s)).")
    return "Proposition : rapport exploitable, à intégrer dans la synthèse des rapports des CB (sous réserve des points à vérifier)."


# ------------------------------------------------------------------ onglets de détail
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
    ws = wb.create_sheet("Synthèse auto")
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
         (f"{res.situation.chemin.name} – " if res.situation else "") + res.appreciation_situation),
        ("Suite à donner (proposition)", suite_a_donner(res)),
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
                       det.nb_mots if det else "", l.precision])
        ws.cell(i, 4).fill = PatternFill("solid", fgColor=_couleur(l.statut) or "FFFFFF")

    # Contrôles automatiques
    ws = wb.create_sheet("Contrôles automatiques")
    _entetes(ws, 1, ["Gravité", "Nature", "Rubrique", "Tableau", "Ligne", "Contrôle", "Attendu (recalculé)",
                     "Constaté (rapport)", "Message"], [10, 12, 22, 30, 30, 35, 18, 18, 80])
    from .canevas import PAR_CODE as PC
    constats = sorted(res.constats, key=lambda c: (c.gravite != "Majeure", c.nature))
    for i, c in enumerate(constats, start=2):
        _ligne(ws, i, [c.gravite, {"fiabilite": "Fiabilité", "coherence": "Cohérence"}.get(c.nature, c.nature),
                       PC[c.rubrique].libelle if c.rubrique in PC else c.rubrique, c.tableau, c.ligne, c.controle,
                       c.attendu, c.constate, c.message])
        ws.cell(i, 1).fill = PatternFill("solid", fgColor=_couleur(c.gravite) or "FFFFFF")
    if not constats:
        ws.cell(2, 1, "Aucune anomalie détectée par les contrôles automatiques.")

    # Ratios
    ws = wb.create_sheet("Ratios")
    _entetes(ws, 1, ["Ratio", "Libellé", "Formule (canevas)", "Valeur recalculée", "Valeur citée par le CB",
                     "Cohérence", "Phrase du rapport"], [8, 35, 45, 35, 15, 12, 80])
    for i, r in enumerate(res.transverses.ratios, start=2):
        coh = {True: COHERENT, False: INCOHERENT, None: A_APPRECIER}[r.coherent]
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
    ws["A2"] = MENTION_AUTO + (" – décret scanné, lu par OCR : à confirmer sur l'original." if d.ocr else "")
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
    ws["A2"] = MENTION_AUTO
    ws["A2"].font = POLICE_AUTO
    date_ok = ("—" if not rap or rap.date_conforme is None else
               "conforme à la fin de la période" if rap.date_conforme else
               f"différente de la fin de la période ({res.periode.fin:%d/%m/%Y})")
    i = _bloc_infos(ws, 4, [
        ("Fichier", sit.chemin.name + (f" (lignes de l'EPN « {sit.filtre_epn} »)" if sit.filtre_epn else "")),
        ("Date d'arrêté", (f"{sit.date_arrete:%d/%m/%Y} – {date_ok}" if sit.date_arrete else "non trouvée – à vérifier")),
        ("Lignes lues", f"{len(sit.lignes_de('recettes'))} ligne(s) de recettes, {len(sit.lignes_de('depenses'))} ligne(s) de dépenses"),
        ("Synthèse", res.appreciation_situation),
    ] + [("Avertissement", a) for a in sit.avertissements])
    if not rap:
        return
    ws.cell(i, 1, "Rapprochement des agrégats").font = Font(bold=True, size=12, color="1F4E78")
    _entetes(ws, i + 1, ["Agrégat", "Tableau du rapport", "Montant du rapport", "Montant de la situation", "Écart (rapport − situation)",
                         "Statut"], [55, 45, 20, 22, 22, 15])
    k = i + 2
    for l in rap.lignes:
        _ligne(ws, k, [l.libelle, l.tableau, l.rapport, l.situation, l.ecart, l.statut])
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
                         "Écart (rapport − situation)", "Statut"], [55, 45, 20, 22, 22, 15])
    k += 2
    detail = sorted(rap.detail, key=lambda l: l.statut != "Écart")
    for l in detail:
        _ligne(ws, k, [l.libelle, l.tableau, l.rapport, l.situation, l.ecart, l.statut])
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
              "Suite à donner (proposition)", "Fichier d'analyse"]
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
            ws.cell(i, 17).fill = PatternFill("solid", fgColor=VERT if r.appreciation_decret.startswith("Conforme") else ORANGE)
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
