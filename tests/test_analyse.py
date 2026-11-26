import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import openpyxl
import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "exemples"))

from analyse_cb import InfosRapport, analyser, remplir_modele, tableau_de_bord  # noqa: E402
from analyse_cb.__main__ import main  # noqa: E402
from analyse_cb.texte import lire_nombre  # noqa: E402
from generer_exemple import generer, generer_decret, generer_situation  # noqa: E402


@pytest.fixture(scope="session")
def rapports(tmp_path_factory):
    d = tmp_path_factory.mktemp("rapports")
    return {"conforme": generer(d, False), "anomalies": generer(d, True)}


@pytest.fixture(scope="session")
def references(tmp_path_factory):
    d = tmp_path_factory.mktemp("references")
    return {"decret": generer_decret(d), "situation": generer_situation(d, False),
            "situation_ecarts": generer_situation(d, True)}


@pytest.fixture(scope="session")
def res_conforme_ref(rapports, references):
    return analyser(rapports["conforme"], InfosRapport(date_reception=date(2099, 7, 12)),
                    decrets=references["decret"], situations=references["situation"])


@pytest.fixture(scope="session")
def res_anomalies_ref(rapports, references):
    return analyser(rapports["anomalies"], InfosRapport(date_reception=date(2099, 7, 27)),
                    decrets=references["decret"], situations=references["situation_ecarts"])


@pytest.fixture(scope="session")
def res_conforme(rapports):
    return analyser(rapports["conforme"], InfosRapport(date_reception=date(2099, 7, 12), charge_etudes="CE"))


@pytest.fixture(scope="session")
def res_anomalies(rapports):
    return analyser(rapports["anomalies"], InfosRapport(date_reception=date(2099, 7, 27)))


def statut(res, code):
    return next(l for l in res.forme if l.code == code).statut


def fond(res, code):
    return next(l for l in res.fond if l.code == code)


# ------------------------------------------------------------------ lecture des nombres
@pytest.mark.parametrize("brut,attendu", [
    ("1 234 567", 1234567), ("1 234 567", 1234567), ("12,5 %", 12.5), ("(3 000)", -3000),
    ("1.234.567", 1234567), ("-50 000 000", -50000000), ("95.25", 95.25), ("", None), ("Etc.", None),
    ("1 234 567,89", 1234567.89),
])
def test_lire_nombre(brut, attendu):
    assert lire_nombre(brut) == attendu


# ------------------------------------------------------------------ rapport conforme
def test_conforme_identification(res_conforme):
    r = res_conforme
    assert r.infos.epn == "Agence Nationale d'Exemple"
    assert r.infos.controleur == "KOUASSI Exemple"
    assert r.periode.type == "etape" and r.periode.annee == 2099
    assert r.date_limite == date(2099, 7, 15)  # 2e trimestre (rapport d'étape au 30 juin) : 15 juillet
    assert r.ecart_jours == -3 and r.appreciation_delai == "Transmis dans les délais"
    assert r.canevas_en_vigueur[0] == "Oui"


def test_conforme_structure_et_tableaux(res_conforme):
    r = res_conforme
    assert set(r.tableaux.par_code) == {f"T{i}" for i in range(1, 9)}
    assert r.constats == []
    for code in ("introduction", "texte_creation", "missions", "financement", "presentation_budget", "exec_recettes",
                 "exec_depenses", "differes_rejets", "resultat_budgetaire", "ratios", "controle_interne",
                 "controle_gestion", "coges", "comite_tresorerie", "difficultes", "suggestions", "conclusion",
                 "performance", "risques"):
        assert statut(r, code) == "Conforme", code
    assert statut(r, "gestion_financiere") == "Non applicable"  # rapport d'étape
    assert statut(r, "sommaire") == "Conforme"
    assert r.score_forme >= 90


def test_conforme_fond(res_conforme):
    for code in ("pres_generale", "pres_ressources", "pres_emplois", "exec_recettes", "exec_depenses",
                 "resultat_budgetaire", "ratios"):
        l = fond(res_conforme, code)
        assert (l.fiabilite, l.coherence) == ("Fiable", "Cohérent"), code
    assert fond(res_conforme, "texte_creation").fiabilite == "Fiable"  # conforme au référentiel


def test_conforme_ratios_et_resultat(res_conforme):
    r = res_conforme.transverses
    assert r.resultat["sens"] == "excédentaire" and r.resultat["resultat"] == 87_000_000
    rrp = next(x for x in r.ratios if x.code == "RRP")
    assert rrp.coherent is True


def test_difficultes_categorisees(res_conforme):
    d = res_conforme.difficultes
    assert [e.categorie for e in d["difficultes"]] == ["execution", "controle", "gestion"]
    assert len(d["suggestions"]) == 2


# ------------------------------------------------------------------ rapport avec anomalies
def test_anomalies_rubriques_manquantes(res_anomalies):
    r = res_anomalies
    assert statut(r, "ratios") == "Non conforme"
    assert statut(r, "controle_gestion") == "Non conforme"
    assert statut(r, "risques") == "Non conforme"
    assert statut(r, "T8") == "Non conforme"
    assert statut(r, "antennes") == "Non applicable"  # validation directe : « le cas échéant » non mentionné
    assert statut(r, "global_forme") == "Non conforme"
    assert statut(r, "signature") == "Non conforme"
    assert statut(r, "sommaire") in ("À vérifier", "Non conforme")


def test_anomalies_calculs_et_coherence(res_anomalies):
    controles = {c.controle for c in res_anomalies.constats}
    assert "Sous-total = somme des lignes" in controles  # T3
    assert "Taux de réalisation = Recouvrement / Prévision finale" in controles  # T5
    assert "Budget N−1 identique dans les tableaux 1 et 2" in controles
    assert "Sens du résultat budgétaire" in controles
    assert any("taux de réalisation des recettes cité" in c.controle for c in res_anomalies.constats)
    assert fond(res_anomalies, "pres_ressources").fiabilite == "Non fiable"
    assert fond(res_anomalies, "exec_recettes").coherence == "Incohérent"
    assert fond(res_anomalies, "resultat_budgetaire").coherence == "Incohérent"
    assert res_anomalies.ecart_jours == 12 and res_anomalies.appreciation_delai == "Hors délai de 12 jours"


# ------------------------------------------------------------------ Excel
def test_remplissage_excel(res_anomalies, tmp_path):
    sortie = remplir_modele(res_anomalies, tmp_path / "analyse.xlsx")
    wb = openpyxl.load_workbook(sortie)
    ws = wb.worksheets[0]
    assert ws["A1"].value.startswith("CANEVAS D'ANALYSE")  # modèle conservé
    assert ws["B14"].value.date() == date(2099, 7, 15)  # date limite du 2e trimestre
    assert ws["D14"].value.startswith("=IF(")
    assert ws["C40"].value == "Non conforme"  # ratios
    assert ws["C101"].value == "Non renseigné"
    assert ws["C97"].value == "Non fiable"
    assert "Retard" in ws["E136"].value
    assert {"Synthèse", "Contrôle structure", "Contrôles automatiques", "Ratios",
            "Difficultés-Suggestions", "Tableaux extraits"} <= set(wb.sheetnames)
    tdb = tableau_de_bord([(res_anomalies, sortie)], tmp_path / "tdb.xlsx")
    assert openpyxl.load_workbook(tdb).active["A2"].value == "Agence Nationale d'Exemple"


def test_cli_lot(rapports, tmp_path):
    registre = tmp_path / "registre.csv"
    registre.write_text("fichier;date_reception;charge_etudes\n"
                        f"{rapports['conforme'].name};28/07/2099;CE\n", encoding="utf-8")
    code = main([str(rapports["conforme"].parent), "--registre", str(registre), "-o", str(tmp_path / "out")])
    assert code == 0
    assert (tmp_path / "out" / "Tableau_de_bord_rapports_CB.xlsx").exists()
    assert (tmp_path / "out" / "Analyse_rapport_exemple_conforme.xlsx").exists()


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice absent (conversion PDF)")
def test_pdf_meme_resultat_que_docx(rapports, res_anomalies, tmp_path):
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(tmp_path),
                    str(rapports["anomalies"])], check=True, capture_output=True, timeout=180)
    res_pdf = analyser(tmp_path / "rapport_exemple_anomalies.pdf", InfosRapport(date_reception=date(2099, 8, 12)))
    assert {l.code: l.statut for l in res_pdf.forme} == {l.code: l.statut for l in res_anomalies.forme}
    assert {c.controle for c in res_pdf.constats} == {c.controle for c in res_anomalies.constats}


# ------------------------------------------------------------------ rapport scanné (OCR)
def _scanner(pdf: Path, sortie: Path) -> Path:
    """Simule un scan : chaque page du PDF devient une image (aucune couche texte)."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf))
    images = [doc[i].render(scale=200 / 72, grayscale=True).to_pil().convert("L") for i in range(len(doc))]
    doc.close()
    images[0].save(sortie, "PDF", resolution=200, save_all=True, append_images=images[1:])
    return sortie


def _ocr_ok():
    from analyse_cb.ocr import ocr_disponible
    return ocr_disponible()[0]


@pytest.mark.skipif(not shutil.which("soffice") or not _ocr_ok(), reason="LibreOffice ou Tesseract absent")
def test_rapport_scanne_ocr(rapports, res_anomalies, tmp_path, monkeypatch):
    monkeypatch.setenv("ANALYSE_CB_CACHE", str(tmp_path / "cache"))
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(tmp_path),
                    str(rapports["anomalies"])], check=True, capture_output=True, timeout=180)
    scan = _scanner(tmp_path / "rapport_exemple_anomalies.pdf", tmp_path / "scan.pdf")
    res = analyser(scan, InfosRapport(date_reception=date(2099, 8, 12)))
    assert res.doc.ocr
    assert set(res.tableaux.par_code) >= {"T1", "T2", "T3", "T4", "T5", "T6", "T7"}
    attendus = {c.controle for c in res_anomalies.constats}
    trouves = {c.controle for c in res.constats}
    assert attendus <= trouves, attendus - trouves
    for code in ("ratios", "controle_gestion", "risques", "T8"):
        assert statut(res, code) == "Non conforme", code


# ------------------------------------------------------------------ décret de création et d'organisation
def test_lecture_decret(references):
    from analyse_cb.decret import lire_decret
    d = lire_decret(references["decret"])
    assert d.numero == "2099-001" and d.date == date(2099, 1, 1)
    assert d.denomination == "Agence Nationale d'Exemple" and d.sigle == "ANEX"
    assert d.tutelle_technique == "Ministre chargé de l'Exemple"
    assert d.tutelle_financiere == "Ministre chargé du Budget"
    assert d.siege == "Abidjan"
    assert len(d.missions) == 3
    assert {"Conseil de gestion", "Agent comptable"} <= set(d.organes)
    assert d.sessions_conseil_par_an == 2
    assert len(d.ressources) == 3 and "Dons et legs" in d.categories_ressources


def test_decret_rapport_conforme(res_conforme_ref):
    r = res_conforme_ref
    statuts = {p.theme: p.statut for p in r.confrontation.points}
    for theme in ("Référence du texte de création", "Missions", "Mode de financement", "Organes de l'EPN",
                  "Sessions du Conseil de gestion"):
        assert statuts[theme] == "Conforme", theme
    assert r.confrontation.constats == []
    assert r.appreciation_decret == "Conforme au décret de création sur tous les points vérifiés."
    assert fond(r, "missions").coherence == "Cohérent"
    assert fond(r, "texte_creation").fiabilite == "Fiable"


def test_decret_rapport_anomalies(res_anomalies_ref):
    r = res_anomalies_ref
    statuts = {p.theme: p.statut for p in r.confrontation.points}
    assert statuts["Missions"] == "Écart"
    assert statuts["Sessions du Conseil de gestion"] == "Écart"  # le Conseil ne s'est pas réuni
    assert fond(r, "missions").coherence == "Incohérent"
    assert fond(r, "coges").coherence == "Incohérent"


def test_decret_identifie_epn_sans_referentiel(rapports, references, tmp_path):
    vide = tmp_path / "ref.csv"
    vide.write_text("sigle;denomination;texte_creation;tutelle;controleur\n", encoding="utf-8")
    r = analyser(rapports["conforme"], referentiel=vide, decrets=[references["decret"]], reference_unique=False)
    assert r.decret is not None  # associé par le sigle/dénomination cités dans le rapport
    assert r.infos.epn.startswith("Agence Nationale d'Exemple")


def test_decret_texte_creation_errone(references, tmp_path):
    from analyse_cb.decret import lire_decret
    faux = tmp_path / "decret.txt"
    texte = lire_decret(references["decret"]).texte.replace("2099-001", "2099-777")
    faux.write_text(texte, encoding="utf-8")
    d = tmp_path / "r"
    r = analyser(generer(d, False), decrets=faux)
    assert any(c.controle == "Texte de création conforme au décret" for c in r.constats)
    assert fond(r, "texte_creation").fiabilite == "Non fiable"


# ------------------------------------------------------------------ situation d'exécution
def test_situation_concordante(res_conforme_ref):
    r = res_conforme_ref
    assert r.situation.filtre_epn == "ANEX" and len(r.situation.lignes) == 10  # lignes de l'OFEX écartées
    assert r.situation.date_arrete == date(2099, 6, 30)
    rap = r.rapprochement
    assert rap.date_conforme is True
    assert rap.nb_ecarts == 0 and rap.nb_concordants >= 12
    assert rap.constats == []
    assert r.constats == []  # aucune anomalie, même avec les références
    for code in ("exec_recettes", "exec_depenses", "resultat_budgetaire"):
        assert fond(r, code).fiabilite == "Fiable", code
        assert "concordants avec la situation" in fond(r, code).commentaire


def test_situation_ecarts(res_anomalies_ref):
    rap = res_anomalies_ref.rapprochement
    ecarts = {l.libelle for l in rap.lignes if l.statut == "Écart"}
    assert {"Recouvrements", "Ordonnancements", "Ordonnancements – Investissements",
            "Résultat budgétaire (recouvrements − ordonnancements)"} <= ecarts
    assert {l.code for l in rap.detail if l.statut == "Écart"} == {"702900", "90047300020"}
    assert fond(res_anomalies_ref, "exec_depenses").fiabilite == "Non fiable"
    assert "Situation d'exécution – écart" in fond(res_anomalies_ref, "exec_depenses").commentaire


def test_situation_csv_et_date_decalee(rapports, tmp_path):
    csv = tmp_path / "situation.csv"
    csv.write_text("Situation au 31/03/2099;;;;\n"
                   "Code;Libellé;Budget actuel;Engagements;Ordonnancements\n"
                   "90047390002;Salaires contractuels;250 000 000;240 000 000;240 000 000\n", encoding="utf-8")
    r = analyser(rapports["conforme"], situations=csv)
    assert r.situation.date_arrete == date(2099, 3, 31)
    assert r.rapprochement.date_conforme is False
    assert any(c.controle == "Date de la situation d'exécution" for c in r.constats)
    assert any(l.code == "90047390002" and l.statut == "Concordant" for l in r.rapprochement.detail)


def test_situation_autre_epn_non_associee(rapports, references, tmp_path):
    import openpyxl
    wb = openpyxl.load_workbook(references["situation"])
    for ws in wb.worksheets:
        for row in ws.iter_rows(min_row=4):
            if row[0].value == "ANEX":
                row[0].value = "AUTRE"
    autre = tmp_path / "autre.xlsx"
    wb.save(autre)
    r = analyser(rapports["conforme"], situations=autre)
    assert r.rapprochement is None
    assert any("aucune ligne pour cet EPN" in a for a in r.doc.avertissements)


def test_excel_references(res_anomalies_ref, tmp_path):
    sortie = remplir_modele(res_anomalies_ref, tmp_path / "analyse.xlsx")
    wb = openpyxl.load_workbook(sortie)
    assert {"Décret de création", "Situation d'exécution"} <= set(wb.sheetnames)
    assert wb.worksheets[0]["D86"].value == "Incohérent"  # missions
    assert wb.worksheets[0]["C98"].value == "Non fiable"  # exécution en dépenses
    assert "La situation d'exécution" in wb.worksheets[0]["A127"].value
    assert "- " not in wb.worksheets[0]["A166"].value  # appréciation générale rédigée, sans tirets
    valeurs = [c.value for row in wb["Situation d'exécution"].iter_rows() for c in row]
    assert "Écart" in valeurs and "Concordant" in valeurs
    tdb = openpyxl.load_workbook(tableau_de_bord([(res_anomalies_ref, sortie)], tmp_path / "tdb.xlsx")).active
    entetes = [c.value for c in tdb[1]]
    assert "écarts sur les missions" in tdb.cell(2, entetes.index("Conformité au décret de création") + 1).value


def test_cli_references(rapports, references, tmp_path):
    code = main([str(rapports["anomalies"]), "--decret", str(references["decret"]),
                 "--situation", str(references["situation_ecarts"]), "-o", str(tmp_path / "out")])
    assert code == 0
    wb = openpyxl.load_workbook(tmp_path / "out" / "Analyse_rapport_exemple_anomalies.xlsx")
    assert "Situation d'exécution" in wb.sheetnames


# ------------------------------------------------------------------ présentations rencontrées dans des rapports réels
def _rapport_libre(chemin: Path) -> Path:
    """Rapport trimestriel FICTIF qui s'écarte du canevas : plan annoncé sans pagination, tableaux numérotés
    librement, tableau d'exécution sans titre, baisses présentées sans signe, nom du CB en page de garde."""
    import docx
    d = docx.Document()
    for t in ("DIRECTION DU CONTRÔLE BUDGETAIRE", "RAPPORT DU CONTROLEUR BUDGETAIRE AUPRES DE L'OFFICE D'ESSAI (OFES)",
              "3ème TRIMESTRE 2099", "KONE Awa", "Administrateur des Services Financiers"):
        d.add_paragraph(t)
    d.add_paragraph("INTRODUCTION").runs[0].bold = True
    d.add_paragraph("L'Office d'Essai a été créé par décret n°2090-12 du 2 mai 2090. Le présent rapport présente la "
                    "situation d'exécution du budget au 3ème trimestre de l'exercice 2098. Il suit le plan ci-après :")
    d.add_heading("PLAN DU RAPPORT", 1)
    for t in ("I - Présentation du budget", "II - Analyse de l'exécution du budget", "III - Difficultés et suggestions",
              "Conclusion"):
        d.add_paragraph(t).runs[0].bold = True
    d.add_heading("PRESENTATION DU BUDGET", 1)
    d.add_paragraph("I.1- Présentation du budget").runs[0].bold = True
    d.add_paragraph("Tableau 2 : Variation du budget global par rapport à l'exercice précédent")
    tab = d.add_table(rows=0, cols=5)
    for row in (["", "Budget 2098", "Budget 2099", "Montant", "Taux Variations"],
                ["Recettes", "500 000 000", "450 000 000", "50 000 000", "10%"],
                ["Dépenses", "500 000 000", "450 000 000", "50 000 000", "10%"]):
        cells = tab.add_row().cells
        for j, v in enumerate(row):
            cells[j].text = v
    d.add_paragraph("Source : état d'exécution")
    d.add_paragraph("Le budget diminue de 50 000 000 FCFA. Aucune variation des dotations au 2ème trimestre 2099.")
    d.add_heading("ANALYSE DE L'EXECUTION DU BUDGET", 1)
    d.add_paragraph("II.2- Analyse de l'exécution du budget en dépenses").runs[0].bold = True
    tab = d.add_table(rows=0, cols=5)
    for row in (["Natures de dépense/ Activités", "Budget initial", "Budget final", "Exécutions", "Taux d'Exécutions %"],
                ["1 Personnel", "50 000 000", "50 000 000", "0", "0"],
                ["2 Biens et services", "", "", "", ""],
                ["90042200031 Assurer la gouvernance", "400 000 000", "400 000 000", "200 000 000", "50,00"],
                ["Total général", "450 000 000", "450 000 000", "200 000 000", "44,44"]):
        cells = tab.add_row().cells
        for j, v in enumerate(row):
            cells[j].text = v
    d.add_paragraph("Le taux d'exécution des dépenses est de 44,44 %, en ligne avec les prévisions de l'Office.")
    d.add_heading("DIFFICULTES ET SUGGESTIONS", 1)
    d.add_paragraph("La principale difficulté demeure le retard des transferts de l'Etat.")
    d.add_heading("CONCLUSION", 1)
    d.add_paragraph("Globalement, le taux d'exécution des dépenses est de 44,44 % au 30 septembre 2099.")
    d.save(chemin)
    return chemin


def test_rapport_hors_canevas(tmp_path):
    r = analyser(_rapport_libre(tmp_path / "libre.docx"))
    assert r.infos.controleur == "KONE Awa"  # page de garde
    assert r.periode.trimestre == 3
    # le plan annoncé n'est pas pris pour les vrais titres
    assert r.structure["presentation_budget"].titre == "PRESENTATION DU BUDGET"
    assert r.structure["pres_generale"].trouvee
    assert statut(r, "exec_depenses") == "Conforme"
    # tableau d'exécution sans titre reconnu ; ligne « 1 Personnel » chiffrée sans détail comptée dans le total
    assert "T6" in r.tableaux.par_code
    controles = {c.controle: c for c in r.constats}
    assert not any(c.controle.startswith("Total") for c in r.constats), [c.message for c in r.constats]
    # baisse présentée sans signe : anomalie mineure (et non erreur de calcul majeure)
    assert controles["Signe de la variation"].gravite == "Mineure"
    assert "Variation = N − (N−1)" not in controles
    assert "Budget N identique dans les tableaux 1 et 2" not in controles  # lignes Recettes/Dépenses non additionnées
    # copier-coller d'un rapport antérieur
    assert controles["Exercice cité conforme à la période"].constate == "2098"
    assert "Trimestre cité conforme à la période" in controles


def test_decret_scanne_mise_en_page_ocr(tmp_path):
    """Décret lu par OCR : numéros d'articles reportés en fin de ligne, sigle à points, énumérations sans tiret ;
    rapport citant un mauvais numéro de décret dans la phrase de création."""
    from analyse_cb.decret import lire_decret
    decret = tmp_path / "decret.txt"
    decret.write_text(
        "Décret n° 2090-589 du 06 octobre 2090 portant création de l'Office d'Essai\n"
        "Il est créé un Etablissement Public Administratif Article 1 :\n"
        "dénommé « Office d'Essai », en abrégé O.F.E.S, placé sous la tutelle technique du Ministre des Essais "
        "et sous la tutelle financière du Ministre du Budget et du Portefeuille de l'Etat.\n"
        "Article 3 :\nL'O.F.E.S à pour mission de conduire les essais nationaux.\n"
        "Article d4 :\nA ce titre, l'O.F.E.S est chargé :\n- de planifier les essais ;\n-_ d'en publier les résultats.\n"
        ": Les recettes et les dépenses sont prévues au budget annuel. Article 25\n"
        "Les recettes de l'O.F.E.S comprennent notamment :\nla rémunération de ses prestations ;\nle budget de l'Etat ;\n"
        "les dons et legs.\nLes dépenses concernent les dépenses ordinaires.\n", encoding="utf-8")
    d = lire_decret(decret)
    assert d.numero == "2090-589" and d.sigle == "OFES" and d.denomination == "Office d'Essai"
    assert d.tutelle_financiere == "Ministre du Budget et du Portefeuille de l'Etat"
    assert [a.numero for a in d.articles] == ["1", "3", "4", "25"]
    assert d.missions == ["conduire les essais nationaux", "de planifier les essais", "d'en publier les résultats"]
    assert d.ressources == ["la rémunération de ses prestations", "le budget de l'Etat", "les dons et legs"]
    r = analyser(_rapport_libre(tmp_path / "libre.docx"), decrets=decret)  # rapport : « décret n°2090-12 »
    point = next(p for p in r.confrontation.points if p.theme == "Référence du texte de création")
    assert point.statut == "Écart" and "2090-12" in point.constat


def test_situation_sigobe_hierarchique_date_posterieure(rapports, tmp_path):
    """Situation au format SIGOBE : EPN > catégorie > programme > activité > nature (en-têtes répétés à chaque
    page), arrêtée un mois après la fin de la période."""
    import openpyxl
    from generer_exemple import EMPLOIS, TAUX_EXECUTION
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Situation d'exécution Annexe EPN"])
    ws.append(["Date Comptable : 31/07/2099"])
    ws.append(["", "Voté", "Actuel (A)", "Deng Saisie (B)", "Eng ViseCf", "OP Emis", "OP Visecf", "OP PEC", "Disponible (A-B)"])
    lignes, categorie = [], None
    for lib, v in EMPLOIS:
        if v is None:
            categorie = lib
        elif isinstance(v, tuple):
            code = lib.split()[0]
            act = v[0] + v[1]
            op = round(act * TAUX_EXECUTION[code]) + (-5_000_000 if code == "90047300020" else 1_000_000)
            lignes.append((categorie, lib, [v[0], act, op, op, op, op, op, act - op]))
    total = [sum(x[2][k] for x in lignes) for k in range(8)]
    ws.append(["32099000 Agence Nationale d'Exemple"] + total)
    for cat in dict.fromkeys(c for c, _, _ in lignes):
        sous = [x for x in lignes if x[0] == cat]
        ws.append([cat] + [sum(x[2][k] for x in sous) for k in range(8)])
        ws.append(["2613101 Mettre en oeuvre les missions du programme"] + [sum(x[2][k] for x in sous) for k in range(8)])
        for _, lib, vals in sous:
            ws.append([lib] + vals)
            ws.append(["601100 Achats de petits matériels"] + vals)
    ws.append(["TOTAL"] + total)
    chemin = tmp_path / "Situation_annexe_EPN_31_07_2099.xlsx"
    wb.save(chemin)
    r = analyser(rapports["conforme"], situations=chemin)
    sit = r.situation
    assert sit.date_arrete == date(2099, 7, 31)
    assert len(sit.lignes) == 6 and all(l.activite for l in sit.lignes)  # seules les natures sont retenues
    assert sit.agregats()["depenses_actuel"] == 1_240_000_000  # pas de double comptage des regroupements
    rap = r.rapprochement
    assert rap.date_conforme is False
    lignes = {(l.code, l.libelle.split(" – ")[-1]): l for l in rap.detail}
    assert lignes[("90047300020", "réalisation")].statut == "Écart"  # rapport > situation postérieure : impossible
    assert "impossible" in lignes[("90047300020", "réalisation")].note
    assert lignes[("90047390002", "réalisation")].statut == "Écart (décalage de date)"
    assert lignes[("90047390002", "budget actuel")].statut == "Concordant"
    assert any(c.gravite == "Majeure" and "impossibles" in c.message for c in rap.constats)


def test_redaction_appreciation_forme(res_anomalies):
    from analyse_cb.redaction import appreciation_forme
    texte = appreciation_forme(res_anomalies)
    assert texte.startswith("Le rapport du Contrôleur Budgétaire auprès de l'Agence Nationale d'Exemple")
    assert "note n°0580/MBPE/DGBF/DCB du 26 juillet 2023" in texte
    assert "Dans l'analyse de l'exécution du budget, les ratios de gestion font défaut." in texte
    assert "pour le premier semestre 2099 (rapport d'étape)" in texte
    assert "le tableau n°8 (motifs des rejets) manque" in texte
    assert "n'a pas traité la rubrique introduite en 2023 : l'analyse de la gestion des risques" in texte
    assert "« Analyse des marches publics »" in texte
    assert "-" not in texte.replace("Contrôleur", "").split("\n")[-1][:3]  # pas de liste à tirets
    assert "  " not in texte and " ," not in texte and "’" not in texte


def test_validation_directe_et_mode_brouillon(rapports, tmp_path):
    from analyse_cb.analyse import charger_parametres
    r = analyser(rapports["anomalies"])
    assert all(l.statut != "À vérifier" for l in r.forme)
    assert all("À apprécier" not in (l.fiabilite, l.coherence) for l in r.fond)
    ws = openpyxl.load_workbook(remplir_modele(r, tmp_path / "def.xlsx")).worksheets[0]
    textes = " ".join(str(ws[c].value) for c in ("A2", "A78", "A127", "A166"))
    assert "Pré-rempli" not in textes and "valider" not in textes
    parametres = charger_parametres()
    parametres["analyse"] = {"validation_directe": False}
    b = analyser(rapports["anomalies"], parametres=parametres)
    assert statut(b, "antennes") == "À vérifier"
    ws = openpyxl.load_workbook(remplir_modele(b, tmp_path / "brouillon.xlsx")).worksheets[0]
    assert ws["A78"].value.startswith("[Pré-rempli")


def test_ressources_application_empaquetee(tmp_path, monkeypatch):
    """Dans l'application Windows, les paramètres modifiables sont copiés dans le profil de l'utilisateur."""
    from analyse_cb import ressources
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(RACINE), raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    chemin = ressources.fichier_config("parametres.toml")
    assert chemin == tmp_path / "AnalyseRapportsCB" / "parametres.toml" and chemin.exists()
    assert ressources.dossier_ressources() == RACINE


def _profil_temporaire(monkeypatch, dossier):
    """Profil d'utilisateur isolé (historique, préférences, documents déposés)."""
    monkeypatch.setenv("APPDATA", str(dossier))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(dossier))
    monkeypatch.setenv("LOCALAPPDATA", str(dossier / "local"))
    monkeypatch.setenv("ANALYSE_CB_SANS_OUVERTURE", "1")


def test_historique_et_tableau_de_bord(res_conforme_ref, res_anomalies_ref, tmp_path, monkeypatch):
    """Les analyses enregistrées alimentent le tableau de bord ; une nouvelle analyse du même EPN et de la même
    période remplace la précédente."""
    _profil_temporaire(monkeypatch, tmp_path)
    from analyse_cb import historique, tableau
    from analyse_cb.analyse import charger_parametres
    from analyse_cb.excel import exporter_tableau_de_bord
    m = historique.montants(res_conforme_ref)
    assert m["source"].startswith("situation d'exécution au") and m["credits"] and m["execution"] is not None
    ident = historique.enregistrer(res_conforme_ref, tmp_path / "a.xlsx")
    assert historique.periodes()[0]["cle"] == "2099-T2"
    d = tableau.tableau_de_bord(None, charger_parametres())
    assert not d["vide"] and d["attendu"] == 50 and d["periode"]["court"] == "T2 2099"
    assert d["kpi"]["credits"] == m["credits"] and d["kpi"]["execution"] == m["execution"]
    ligne = d["lignes"][0]
    assert ligne["statut"] in ("OK", "À surveiller", "Sous-exécution", "Dépassement") and ligne["tutelle"]
    assert d["ministeres"][0]["credits"] == m["credits"] and "repartition" not in d
    assert "ministere" not in d["graphiques"] and {"epn", "nature"} <= set(d["graphiques"])  # plus de vue « par ministère »
    # Ratios de gestion de la période (même source que les montants : la situation d'exécution)
    rr = {x["code"]: x for x in d["ratios"]["agreges"]}
    assert set(rr) == {"RRP", "RDP", "RDF", "RDI", "RDA"} and d["ratios"]["disponibles"] == 1
    assert rr["RDF"]["valeur"] is not None and 0 <= rr["RDF"]["valeur"] <= 100
    assert d["ratios"]["sources"][0].startswith("situation d'exécution")
    # Difficultés et suggestions des CB
    ds = d["difficultes"]
    assert ds["rapports"] == 1 and ds["difficultes"] and ds["suggestions"]
    assert {e["categorie"] for e in ds["difficultes"] + ds["suggestions"]} <= {"execution", "controle", "gestion"}
    assert d["synthese"]["recommandation"].startswith("Il est recommandé de")
    # Même EPN, même période : l'analyse est remplacée (pas de doublon).
    assert historique.enregistrer(res_anomalies_ref, tmp_path / "b.xlsx") == ident
    assert len(historique.lister()) == 1
    al = tableau.toutes_alertes(None, charger_parametres())["alertes"]
    assert any(a["titre"] == "Rapport à retourner au CB" and a["niveau"] == "critique" for a in al)
    wb = openpyxl.load_workbook(exporter_tableau_de_bord(tableau.tableau_de_bord(None, charger_parametres()),
                                                         tmp_path / "tdb.xlsx"))
    assert wb.sheetnames == ["Tableau de bord", "Ratios", "Natures économiques", "Difficultés-Suggestions", "Alertes"]
    assert wb["Ratios"]["A2"].value and wb["Difficultés-Suggestions"]["A2"].value in ("Difficulté", "Suggestion")
    historique.supprimer(ident)
    assert tableau.tableau_de_bord(None, charger_parametres())["vide"]


def test_ratios_de_gestion_calcul_et_lecture():
    """Ratios du canevas : base des dépenses engagées, valeurs hors bornes écartées, agrégation pondérée, lecture."""
    from analyse_cb import ratios
    a = {"ressources_propres_realise": 20.0, "recettes_realise": 200.0, "depenses_engage": 100.0,
         "personnel_engage": 30.0, "biens_services_engage": 50.0, "transferts_engage": 5.0, "investissement_engage": 15.0}
    comp, base = ratios.composantes(a)
    assert base == "engage" and ratios.valeur(*comp["RRP"]) == 10 and ratios.valeur(*comp["RDF"]) == 85
    assert ratios.valeur(*comp["RDA"]) is None and ratios.valeur(250, 100) is None  # hors de [0 ; 100 %]
    assert ratios.composantes({"depenses_realise": 10.0, "personnel_realise": 1.0})[1] == "realise"

    def rec(num, den, cite=None, coherent=None):
        return {"donnees": {"ratios": {"liste": [{"code": "RDP", "num": num, "den": den, "valeur": num / den * 100,
                                                  "cite": cite, "coherent": coherent}]}}}
    agreges = {x["code"]: x for x in ratios.agreger([rec(30, 100), rec(10, 300)])}
    assert agreges["RDP"]["valeur"] == 10 and agreges["RDP"]["epn"] == 2  # (30 + 10) / (100 + 300)
    c = ratios.citations([rec(30, 100, 31, False), rec(10, 300)])
    assert c["discordants"] == 1 and c["rapports_sans_ratio"] == 1
    texte = ratios.lecture([{"code": "RRP", "valeur": 10.0}, {"code": "RDP", "valeur": 30.0},
                            {"code": "RDF", "valeur": 85.0}, {"code": "RDI", "valeur": 15.0},
                            {"code": "RDA", "valeur": None, "cite": 12.0, "coherent": False}])
    assert "10,0 % des ressources recouvrées" in texte and "transferts de l'État" in texte
    assert "celles d'investissement 15,0 %" in texte and "Le RDA cité" in texte and "(s)" not in texte


def test_difficultes_suggestions_partie_sans_sous_titres():
    """Partie « Difficultés et suggestions » sans sous-titres : les propositions sont rangées parmi les suggestions."""
    from analyse_cb.controles import RE_DIFFICULTE, RE_SUGGESTION
    from analyse_cb.texte import normaliser
    suggestion = normaliser("Nous suggérons la tenue régulière des sessions du Conseil de gestion.")
    difficulte = normaliser("La principale difficulté demeure le problème de connexion ; il serait utile d'y remédier.")
    assert RE_SUGGESTION.search(suggestion) and not RE_DIFFICULTE.search(suggestion)
    assert RE_DIFFICULTE.search(difficulte)  # description d'une difficulté : reste une difficulté


def test_dates_limites_de_transmission(tmp_path, monkeypatch):
    """1er trimestre : 15 avril ; 2e (rapport d'étape) : 15 juillet ; 3e : 15 octobre ; 4e : 15 janvier N+1."""
    from analyse_cb import ressources
    from analyse_cb.analyse import charger_parametres
    from analyse_cb.controles import Periode, _periode_trimestre, date_limite, jour_mois
    p = charger_parametres()
    assert [date_limite(_periode_trimestre(t, 2026), p) for t in (1, 2, 3, 4)] == [
        date(2026, 4, 15), date(2026, 7, 15), date(2026, 10, 15), date(2027, 1, 15)]
    assert date_limite(Periode("etape", 2026, "Rapport d'étape au 30 juin 2026"), p) == date(2026, 7, 15)
    assert date_limite(Periode("annuel", 2026, "Rapport annuel"), p) == date(2027, 4, 30)
    # Anciennes clés (délai en jours) ignorées : les dates par trimestre s'appliquent.
    ancien = {"delais": {"rapport_trimestriel_delai_jours": 30, "rapport_etape_date_limite": "31/07"}}
    assert date_limite(_periode_trimestre(3, 2026), ancien) == date(2026, 10, 15)
    assert date_limite(_periode_trimestre(1, 2026), {"delais": {"trimestre_1_date_limite": "20/04"}}) == date(2026, 4, 20)
    with pytest.raises(ValueError, match="n'existe pas"):
        jour_mois("31/02")
    # Application installée : la copie des paramètres d'une version antérieure est remplacée (ancienne conservée).
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(RACINE), raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    copie = tmp_path / "AnalyseRapportsCB" / "parametres.toml"
    copie.parent.mkdir(parents=True)
    copie.write_text('[delais]\nrapport_trimestriel_delai_jours = 30\n', encoding="utf-8")
    assert ressources.fichier_config("parametres.toml") == copie
    assert "trimestre_3_date_limite" in copie.read_text(encoding="utf-8")
    assert (tmp_path / "AnalyseRapportsCB" / "parametres.avant-3.2.toml").exists()


def test_analyse_par_nature_economique():
    """Natures cumulées sur les activités, statuts, points d'attention et lecture (lignes de type SIGOBE)."""
    import types
    from analyse_cb import natures
    from analyse_cb.situation import LigneSituation

    def ligne(code, act, groupe, **v):
        return LigneSituation("depenses", code, f"{code} Libellé {code}", groupe, v, activite=act)
    lignes = [
        ligne("601100", "90042200031", "biens_services", initial=10.0, actuel=10.0, engage=10.0, ordonnance=10.0, paye=8.0),
        ligne("601100", "90042200032", "biens_services", initial=5.0, actuel=5.0, engage=4.0, ordonnance=4.0, paye=4.0),
        ligne("662110", "90042200029", "personnel", initial=35.0, actuel=33.0, engage=0.0, ordonnance=0.0, paye=0.0),
        ligne("611100", "90042200031", "biens_services", initial=3.0, actuel=0.0, engage=0.0, ordonnance=0.0, paye=0.0),
        ligne("245110", "90042200031", "biens_services", initial=100.0, actuel=100.0, engage=100.0, ordonnance=100.0, paye=100.0),
        ligne("601200", "90042200031", "biens_services", initial=4.0, actuel=4.0, engage=6.0, ordonnance=5.0, paye=5.0),
    ]
    sit = types.SimpleNamespace(lignes=lignes, lignes_de=lambda sens: lignes if sens == "depenses" else [],
                                date_arrete=date(2026, 10, 31), systeme="SIGOBE")
    dep = natures._depuis_situation(sit, "depenses")
    n = {x["code"]: x for x in dep}
    assert n["601100"]["actuel"] == 15 and n["601100"]["activites"] == 2 and n["601100"]["libelle"] == "Libellé 601100"
    a = natures.analyser(dep, [], 3, {})
    statuts = {x["code"]: x["statut"] for c in a["categories"] for x in c["natures"]}
    assert statuts == {"601100": "OK", "662110": "Non engagé", "611100": "Crédits supprimés", "245110": "OK",
                       "601200": "Dépassement"}
    titres = " | ".join(p["titre"] for p in a["points"])
    assert a["points"][0]["niveau"] == "critique" and "dépassement" in titres
    assert "sans aucun engagement" in titres and "Ordonnancements non encore payés" in titres
    assert "Imputation à vérifier" in titres and "régulation" in titres
    assert "Aucun engagement n'a été pris sur 1 nature dotée" in a["lecture"] and "(s)" not in a["lecture"]
    assert [c["code"] for c in a["categories"]] == ["personnel", "biens_services"]
    cumul = natures.fusionner([dep, dep])
    assert next(x for x in cumul if x["code"] == "601100")["actuel"] == 30


def test_icone_application():
    """Icône Windows en 7 tailles (16 à 256 pixels) et image de la fenêtre (256 pixels), tirées de la bannière."""
    from PIL import Image
    ico = Image.open(RACINE / "packaging" / "icone.ico")
    assert {(t, t) for t in (16, 24, 32, 48, 64, 128, 256)} <= set(ico.info["sizes"])
    png = Image.open(RACINE / "packaging" / "icone.png")
    assert png.size == (256, 256) and png.mode == "RGBA" and png.getpixel((0, 0))[3] == 0  # fond transparent
    assert (RACINE / "packaging" / "banniere.jpg").exists()


def test_tableau_de_bord_et_comparaison_par_epn(rapports, references, tmp_path, monkeypatch):
    """Analyses d'un même EPN sur trois trimestres : liste et fiche de l'EPN, tableau de bord de l'EPN, comparaison
    de ses rapports trimestre par trimestre."""
    import json
    _profil_temporaire(monkeypatch, tmp_path)
    from analyse_cb import historique, tableau
    from analyse_cb.analyse import charger_parametres
    params = charger_parametres()
    for periode in ("1er trimestre 2099", "2e trimestre 2099", "3e trimestre 2099"):
        res = analyser(rapports["conforme"], InfosRapport(periode=periode), decrets=references["decret"],
                       situations=references["situation"])
        historique.enregistrer(res, tmp_path / f"{periode}.xlsx")
    (fiche,) = historique.epns()
    cle = fiche["cle"]
    assert fiche["nb"] == 3 and [p["court"] for p in fiche["periodes"]] == ["T3 2099", "T2 2099", "T1 2099"]
    assert [p["cle"] for p in historique.periodes(epn=cle)] == ["2099-T3", "2099-T2", "2099-T1"]
    assert historique.periodes(epn="epn inconnu") == [] and len(historique.fiche_epn(cle)["analyses"]) == 3
    d = tableau.tableau_de_bord(None, params, epn=cle)
    assert d["epn"]["cle"] == cle and d["periode"]["cle"] == "2099-T3" and len(d["lignes"]) == 1
    assert [g["libelle"] for g in d["graphiques"]["trimestre"]] == ["T1 2099", "T2 2099", "T3 2099"]
    assert d["categories"] and all(c["statut"] for c in d["categories"])
    assert tableau.tableau_de_bord(None, params, epn="epn inconnu")["epn"] is None  # EPN inconnu : ensemble des EPN
    c = tableau.comparaison_epn(cle, None, params)
    assert c["annee"] == 2099 and [col["code"] for col in c["colonnes"]] == ["T1", "T2", "T3", "T4"]
    assert [col["present"] for col in c["colonnes"]] == [True, True, True, False]
    t1, t2 = c["colonnes"][0], c["colonnes"][1]
    assert t1["execution_periode"] == t1["execution"] and t2["execution_periode"] == t2["execution"] - t1["execution"]
    # Recouvrement par nature économique de recettes : groupes de ressources, natures, recouvrement du trimestre
    assert c["natures_recettes"] and all(g["natures"] for g in c["natures_recettes"])
    code = c["natures_recettes"][0]["natures"][0]["code"]
    n1, n2 = t1["recettes_natures"][code], t2["recettes_natures"][code]
    assert n1["periode"] == n1["realise"] and n2["periode"] == pytest.approx(n2["realise"] - n1["realise"])
    assert n2["taux"] == pytest.approx(n2["realise"] / n2["prevu"] * 100) and t2["natures_a_reanalyser"] == 0
    groupe = t2["recettes_groupes"][c["natures_recettes"][0]["groupe"]]
    assert groupe["realise"] == pytest.approx(sum(n["realise"] or 0 for n in t2["recettes_natures"].values()
                                                  if n["groupe"] == c["natures_recettes"][0]["groupe"]))
    assert "Par nature de recettes, au T3" in c["lecture"] and "recouvrés sur" in c["lecture"]
    assert "initial" in n2 and "initial" in groupe  # prévisions initiales, pour signaler les prévisions modifiées
    # T4 2099 : date limite (15/01/2100) non atteinte, le rapport est « à venir » et non manquant
    assert "3 rapports trimestriels" in c["lecture"] and "T4 à venir (date limite : 15/01/2100)" in c["lecture"]
    assert "manque" not in c["lecture"]
    assert c["colonnes"][3]["a_venir"] is True and c["colonnes"][3]["echeance"] == "2100-01-15"
    assert tableau.comparaison_epn("tous", 2099, params)["colonnes"][0]["present"]
    # Nature économique : l'EPN suivi, puis un rapport de l'EPN analysé sans le détail par nature
    n = tableau.analyse_natures("2099-T3", cle, params)
    assert n["choix"] == cle and not n["non_disponible"] and (n["categories"] or n["recettes"])
    con = historique.connexion()
    row = con.execute("SELECT id, donnees FROM analyses WHERE periode_cle = '2099-T1'").fetchone()
    donnees = json.loads(row["donnees"])
    donnees.pop("natures", None)
    con.execute("UPDATE analyses SET donnees = ? WHERE id = ?", (json.dumps(donnees), row["id"]))
    # Un second EPN, présent au T2 seulement : l'exécution du trimestre ne porte que sur les EPN des deux trimestres
    autre = dict(con.execute("SELECT * FROM analyses WHERE periode_cle = '2099-T2'").fetchone())
    autre.pop("id")
    autre.update(cle="autre epn|2099-T2", epn="Autre établissement", sigle="AE")
    con.execute(f"INSERT INTO analyses ({', '.join(autre)}) VALUES ({', '.join('?' * len(autre))})", list(autre.values()))
    con.commit()
    con.close()
    n = tableau.analyse_natures("2099-T1", cle, params)
    assert n["non_disponible"] and n["choix"] == cle and n["a_reanalyser"] == 1
    apres = tableau.comparaison_epn(cle, 2099, params)["colonnes"]
    assert apres[0]["natures_a_reanalyser"] == 1 and not apres[0]["recettes_natures"]
    assert "periode" not in apres[1]["recettes_natures"][code]  # T1 sans détail : pas de recouvrement du trimestre
    tous = tableau.comparaison_epn("tous", 2099, params)
    c2 = tous["colonnes"][1]
    assert c2["nb"] == 2 and c2["base_periode"] == 1
    assert c2["execution_periode"] == pytest.approx(t2["execution"] - t1["execution"])
    assert "Le nombre de rapports analysés varie d'un trimestre à l'autre (1 au T1, 2 au T2, 1 au T3)" in tous["lecture"]
    assert len(historique.epns()) == 2 and tableau.comparaison_epn(cle, 2099, params)["colonnes"][1]["nb"] == 1


def test_statut_execution_selon_periode():
    from analyse_cb.tableau import statut_execution
    p = {"execution": {"seuil_vigilance": 10, "seuil_sous_execution": 20}}
    assert statut_execution(72.9, 3, p)[0] == "OK"            # 3e trimestre : 75 % attendus
    assert statut_execution(60, 3, p)[0] == "À surveiller"
    assert statut_execution(50, 3, p)[0] == "Sous-exécution"
    assert statut_execution(101, 2, p)[0] == "Dépassement"
    assert statut_execution(None, 2, p)[0] == "Non renseigné"


def test_serveur_interface_et_api(rapports, references, tmp_path, monkeypatch):
    """Parcours complet par l'API du serveur local : dépôt des documents, analyse, tableau de bord, paramètres."""
    import json
    import time
    import urllib.error
    import urllib.request
    from urllib.parse import quote
    _profil_temporaire(monkeypatch, tmp_path)
    from analyse_cb.serveur import Serveur
    srv = Serveur().demarrer()
    base = f"http://127.0.0.1:{srv.port}"

    def appel(chemin, data=None, brut=None, entetes=None):
        h = {"X-Jeton": srv.app.jeton, **(entetes or {})}
        corps = brut if brut is not None else (json.dumps(data).encode() if data is not None else None)
        req = urllib.request.Request(base + chemin, data=corps, headers=h, method="POST" if corps is not None else "GET")
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())

    def deposer(chemin, categorie):
        return appel("/api/televerser", brut=Path(chemin).read_bytes(),
                     entetes={"X-Nom-Fichier": quote(Path(chemin).name), "X-Categorie": categorie})
    try:
        with urllib.request.urlopen(base + "/", timeout=10) as r:
            assert b'id="contenu"' in r.read()
        with urllib.request.urlopen(base + "/static/app.js", timeout=10) as r:
            assert b"function router" in r.read()
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/api/etat", timeout=10)
        assert e.value.code == 403
        assert appel("/api/tableau")["vide"] is True
        assert not srv.app.interface_chargee.is_set()
        appel("/api/etat")
        assert srv.app.interface_chargee.is_set()  # signal utilisé pour vérifier l'affichage dans la fenêtre
        assert appel("/api/journal", {"message": "essai"})["ok"]
        assert appel("/api/presence?page=p1", {}) == {"quitter": False} and srv.app.pages_ouvertes(60) == 1
        balise = urllib.request.Request(f"{base}/api/fermeture?jeton={srv.app.jeton}&page=p1", data=b"", method="POST")
        with urllib.request.urlopen(balise, timeout=10) as rep:  # signal envoyé à la fermeture (jeton dans l'adresse)
            assert rep.status == 200
        assert srv.app.pages_ouvertes(60) == 0 and srv.app.derniere_fermeture
        r = deposer(rapports["conforme"], "rapport")
        d = deposer(references["decret"], "decret")
        s = deposer(references["situation"], "situation")
        faux = tmp_path / "programme.exe"
        faux.write_bytes(b"MZ")
        with pytest.raises(urllib.error.HTTPError) as e:
            deposer(faux, "rapport")
        assert e.value.code == 400
        appel("/api/analyser", {"rapports": [{"id": r["id"], "reception": "28/07/2099", "periode": ""}],
                                "decrets": [d["id"]], "situations": [s["id"]], "charge": "Test",
                                "sortie": str(tmp_path / "sortie")})
        debut = time.time()
        while (t := appel("/api/travail"))["en_cours"]:
            assert time.time() - debut < 180, "analyse trop longue"
            time.sleep(0.3)
        assert t["rapports"][0]["etat"] == "ok", t
        res = t["resultats"][0]
        assert Path(res["fichier"]).exists() and res["epn"]
        dossier = Path(res["dossier"])  # <sortie>/<EPN>/<période>/ : analyse et copie du rapport
        assert dossier.parent.parent == tmp_path / "sortie" and dossier.name == res["periode_cle"]
        assert Path(res["fichier"]).parent == dossier and (dossier / Path(rapports["conforme"]).name).exists()
        # Fichier d'analyse au format Word (par défaut : Word et Excel), ouvrable depuis l'interface
        assert res["fichier"].endswith(".xlsx") and res["excel"] == res["fichier"]
        assert res["word"].endswith(".docx") and Path(res["word"]).parent == dossier and Path(res["word"]).exists()
        assert appel("/api/ouvrir", {"quoi": "word", "id": res["id"]})["ok"]
        assert appel(f"/api/rapport?id={res['id']}")["fichier_word_existe"]
        assert appel("/api/epns")["epns"][0]["cle"] == res["epn_cle"]
        fiche = appel("/api/epn?cle=" + quote(res["epn_cle"]))
        assert fiche["analyses"][0]["rapport_conserve"] and fiche["dossier_existe"]
        assert appel("/api/ouvrir", {"quoi": "rapport", "id": res["id"]})["ok"]
        assert appel("/api/ouvrir", {"quoi": "dossier_epn", "cle": res["epn_cle"]})["ok"]
        assert appel("/api/tableau?epn=" + quote(res["epn_cle"]))["epn"]["cle"] == res["epn_cle"]
        comp = appel("/api/comparaison?epn=" + quote(res["epn_cle"]))
        assert comp["epn"] == res["epn_cle"] and any(c["present"] for c in comp["colonnes"])
        assert res["date_limite"] == "2099-07-15" and res["ecart_jours"] == 13 and res["delai"] == "Hors délai de 13 jours"
        tb = appel("/api/tableau")
        assert not tb["vide"] and tb["lignes"][0]["id"] == res["id"]
        assert appel("/api/rapports")["rapports"][0]["date_reception"] == "2099-07-28"
        an = appel("/api/natures")
        assert an["epns"] and an["recettes"] and an["sources"][0].startswith("situation d'exécution")
        ar = appel("/api/ratios")
        assert not ar["vide"] and ar["lignes"][0]["ratios"] and ar["lignes"][0]["lecture"]
        assert tb["difficultes"]["rapports"] == 1
        detail = appel(f"/api/rapport?id={res['id']}")
        assert detail["fichier_existe"] and detail["donnees"]["appreciation"]
        p = appel("/api/parametres", {"utilisateur": {"nom": "Test", "fonction": "Chargé d'Études"},
                                      "execution": {"seuil_vigilance": "5"}})
        assert p["execution"]["seuil_vigilance"] == 5 and appel("/api/etat")["utilisateur"]["nom"] == "Test"
        # Paramètres : canevas des rapports et modèle du fichier d'analyse
        from analyse_cb import modele
        cv = appel("/api/canevas")
        assert len(cv["rubriques"]) > 40 and len(cv["tableaux"]) == 8 and not cv["modele"]["personnalise"]
        assert not cv["modele"]["manquantes"] and cv["modele"]["lignes"]
        dep = appel("/api/televerser", brut=modele.MODELE_DCB.read_bytes(),
                    entetes={"X-Nom-Fichier": quote("Modèle DCB.xlsx"), "X-Categorie": "modele"})
        cv = appel("/api/modele/importer", {"id": dep["id"]})
        assert cv["modele"]["personnalise"] and cv["modele"]["nom"] == "Modèle DCB.xlsx"
        assert not appel("/api/modele/reinitialiser", {})["modele"]["personnalise"]
        assert Path(appel("/api/modele/exporter", {"ouvrir": False})["chemin"]).exists()
        with pytest.raises(urllib.error.HTTPError) as e:
            appel("/api/parametres", {"delais": {"trimestre_2_date_limite": "31/02"}})
        assert e.value.code == 400
        p = appel("/api/parametres", {"delais": {"trimestre_3_date_limite": "5/10"}})
        assert p["delais"]["trimestre_3_date_limite"] == "05/10" and p["delais"]["trimestre_4_date_limite"] == "15/01"
        assert appel("/api/etat")["delais"]["trimestre_3_date_limite"] == "05/10"
        assert Path(appel("/api/exporter", {"periode": tb["periode"]["cle"]})["chemin"]).exists()
    finally:
        srv.arreter()


def test_duree_de_vie_application(tmp_path, monkeypatch):
    """L'application reste ouverte tant qu'une fenêtre de l'interface l'est (rechargement, fenêtre réduite, analyse
    en cours) et s'arrête quand la dernière fenêtre est fermée ou sur « Quitter l'application »."""
    import threading
    import time
    import types
    _profil_temporaire(monkeypatch, tmp_path)
    from analyse_cb import interface
    from analyse_cb.serveur import Application
    monkeypatch.setattr(interface, "DELAI_FERMETURE", 0.3)
    monkeypatch.setattr(interface, "DELAI_PRESENCE", 1.0)
    monkeypatch.setattr(interface, "DELAI_ABANDON", 2.0)

    def serveur():
        return types.SimpleNamespace(app=Application())
    sans_navigateur = types.SimpleNamespace(processus_actif=lambda: False)
    navigateur_ouvert = types.SimpleNamespace(processus_actif=lambda: True)
    # Interface jamais affichée.
    assert interface.attendre_fin(serveur(), sans_navigateur, 0.5) == "non_affichee"
    # Fenêtre ouverte puis fermée.
    s = serveur()
    s.app.presence("a")
    threading.Timer(0.4, s.app.fermeture, args=("a",)).start()
    assert interface.attendre_fin(s, sans_navigateur, 5) == "fermee"
    # Rechargement de la page (fermeture suivie d'une nouvelle fenêtre), puis « Quitter l'application ».
    s = serveur()
    s.app.presence("a")

    def recharger():
        s.app.fermeture("a")
        time.sleep(0.1)
        s.app.presence("b")
    threading.Timer(0.2, recharger).start()
    threading.Timer(0.7, s.app.quitter.set).start()
    assert interface.attendre_fin(s, sans_navigateur, 5) == "quitter"
    # Fenêtre réduite (plus de signe de vie) alors que le navigateur est ouvert : attente, puis abandon.
    s = serveur()
    s.app.presence("a")
    debut = time.time()
    assert interface.attendre_fin(s, navigateur_ouvert, 5) == "fermee" and time.time() - debut >= 2.0
    # Fenêtre fermée pendant une analyse : l'application attend la fin de l'analyse.
    s = serveur()
    s.app.presence("a")
    s.app.travail = {"en_cours": True}
    s.app.fermeture("a")
    threading.Timer(0.8, lambda: s.app.travail.update(en_cours=False)).start()
    debut = time.time()
    assert interface.attendre_fin(s, sans_navigateur, 5) == "fermee" and time.time() - debut >= 0.8


def test_affichage_mode_application(tmp_path, monkeypatch):
    """L'interface s'ouvre en mode application avec un profil propre à l'application (données locales)."""
    _profil_temporaire(monkeypatch, tmp_path)
    from analyse_cb import interface
    a = interface.Affichage("http://127.0.0.1:1/?jeton=x")
    commande = a.commande("Microsoft Edge", "msedge.exe")
    assert commande[0] == "msedge.exe" and commande[-1] == "--app=http://127.0.0.1:1/?jeton=x"
    profil = next(c for c in commande if c.startswith("--user-data-dir="))
    assert "affichage" in profil and "Microsoft_Edge" in profil
    monkeypatch.setenv("ANALYSE_CB_NAVIGATEUR", "navigateur-de-test")
    assert interface.navigateurs() == [("Navigateur imposé", "navigateur-de-test")]
    monkeypatch.setenv("ANALYSE_CB_NAVIGATEUR", str(tmp_path / "absent.exe"))
    ouverts = []
    monkeypatch.setattr(interface.webbrowser, "open", ouverts.append)
    assert a.ouvrir() == "navigateur par défaut" and ouverts == [a.url]  # navigateur introuvable : repli


def test_lanceur_application(tmp_path, monkeypatch):
    """Le lanceur vérifie le serveur et l'interface (mode « --test-serveur » utilisé après la construction)."""
    _profil_temporaire(monkeypatch, tmp_path)
    from analyse_cb import interface
    assert interface.main and interface.test_serveur() == []


def test_redaction_commentaires_grille(res_anomalies_ref, tmp_path):
    """Commentaires de la grille rédigés en phrases simples, sans mentions techniques, et aérés."""
    from analyse_cb.commentaires import aerer
    textes = [l.redige for l in res_anomalies_ref.forme + res_anomalies_ref.fond if l.ligne]
    assert all(textes)
    for t in textes:
        assert "(s)" not in t and "Titre trouvé" not in t and "Rubrique renseignée (" not in t, t
    sit = res_anomalies_ref.appreciation_situation
    assert "agrégats comparés concordent" in sit and "/" not in sit.split(":", 1)[-1]
    long = " ".join(["Phrase numéro %d assez longue pour remplir une ligne entière du texte." % i for i in range(30)])
    blocs = aerer(long, 100, 3).split("\n\n")
    assert len(blocs) > 1 and all(len(b) <= 300 for b in blocs)


def test_modele_dcb_lignes_reperees():
    """Les lignes du modèle de la DCB, retrouvées d'après leurs libellés, sont celles de la grille d'origine."""
    from analyse_cb import canevas, modele
    plan = modele.calculer_plan(modele.MODELE_DCB, canevas.DEFAUT_RUBRIQUES, canevas.DEFAUT_TABLEAUX, canevas.alias_dcb())
    assert plan.valide and not plan.manquantes
    for r in canevas.DEFAUT_RUBRIQUES:
        assert plan.forme.get(r.code) == r.ligne_forme, r.code
        assert plan.fond.get(r.code) == r.ligne_fond, r.code
    assert {t.code: plan.forme[t.code] for t in canevas.DEFAUT_TABLEAUX} == {t.code: t.ligne_forme for t in canevas.DEFAUT_TABLEAUX}
    assert (plan.ancres["delai"], plan.ancres["suite"], plan.premiere_vide(plan.ancres["appreciation_forme"]),
            plan.premiere_vide(plan.ancres["appreciation_fond"]), plan.premiere_vide(plan.ancres["appreciation_generale"])) == \
        (13, 180, 78, 127, 166)
    assert (plan.ancres["diff_execution"], plan.ancres["sugg_gestion"]) == (136, 155)


def _inserer_ligne(ws, ligne: int, libelle: str) -> None:
    """Insère une ligne dans la grille en décalant les cellules fusionnées (comme Excel)."""
    fusions = list(ws.merged_cells.ranges)
    for f in fusions:
        ws.unmerge_cells(str(f))
    ws.insert_rows(ligne)
    for f in fusions:
        if f.min_row >= ligne:
            f.shift(0, 1)
        ws.merge_cells(str(f))
    ws.cell(ligne, 1, libelle)


def test_canevas_et_modele_parametrables(rapports, references, tmp_path, monkeypatch):
    """Canevas modifié dans les Paramètres (rubrique non exigée, rubriques ajoutées, référence) et modèle de fichier
    d'analyse importé avec une ligne ajoutée pour « Analyse de la performance » dans les parties II et III."""
    _profil_temporaire(monkeypatch, tmp_path)
    from analyse_cb import canevas, modele
    try:
        # ---- modèle importé : ligne « Analyse de la performance » après les ratios (parties II et III)
        wb = openpyxl.load_workbook(modele.MODELE_DCB)
        ws = wb.worksheets[0]
        _inserer_ligne(ws, 41, "Analyse de la performance")
        _inserer_ligne(ws, 41 + 62, "Analyse de la performance")
        source = tmp_path / "Nouveau modèle.xlsx"
        wb.save(source)
        d = canevas.importer_modele(source, source.name)
        assert d["modele"]["personnalise"] and not d["modele"]["manquantes"]
        perf = next(r for r in d["rubriques"] if r.get("code") == "performance")
        assert (perf["ligne"], perf["ligne_fond"]) == (41, 103)
        gf = next(r for r in d["rubriques"] if r["code"] == "gestion_financiere")
        assert (gf["ligne"], gf["ligne_fond"]) == (43, 105)  # lignes suivantes décalées
        assert next(a for a in d["modele"]["ancres"] if a["nom"] == "suite")["ligne"] == 182
        # un classeur qui n'est pas une grille d'analyse est refusé
        autre = openpyxl.Workbook()
        autre.active["A1"] = "Sans rapport"
        autre.save(tmp_path / "autre.xlsx")
        with pytest.raises(ValueError, match="introuvables"):
            canevas.importer_modele(tmp_path / "autre.xlsx", "autre.xlsx")

        # ---- canevas : plan stratégique non exigé, rubriques ajoutées, référence du canevas
        rubs = [{"code": r["code"], "libelle": r["libelle"], "exigence": r["exigence"], "titre_requis": r["titre_requis"],
                 "mots_min": r["mots_min"], "intitules": r["intitules"], "ligne": "auto"} for r in d["rubriques"]]
        next(r for r in rubs if r["code"] == "plan_strategique")["exigence"] = "non_exigee"
        next(r for r in rubs if r["code"] == "ratios")["intitules"] = "Ratios de performance ; Indicateurs de gestion"
        rubs.append({"code": "nouveau_1", "libelle": "Situation d'exécution du budget", "parent": "analyse_execution",
                     "exigence": "obligatoire", "intitules": []})
        rubs.append({"code": "nouveau_2", "libelle": "Analyse de la soutenabilité financière", "parent": None,
                     "exigence": "obligatoire", "intitules": "Soutenabilité"})
        d = canevas.enregistrer({"reference": "note n°0999/MBPE/DGBF/DCB du 1er janvier 2026", "rubriques": rubs,
                                 "tableaux": [{"code": "T8", "exigence": "non_exigee", "libelle": "Motifs des rejets"}]})
        ajoutees = [r for r in d["rubriques"] if r["perso"]]
        assert [(r["code"], r["parent"], r["niveau"]) for r in ajoutees] == \
            [("perso_1", "analyse_execution", 2), ("perso_2", None, 1)]
        assert d["reference"].startswith("note n°0999") and d["modifie"]
        assert next(t for t in d["tableaux"] if t["code"] == "T8")["exigence"] == "non_exigee"
        assert "Analyse de la soutenabilité financière" in d["modele"]["sans_ligne"]

        res = analyser(rapports["conforme"], InfosRapport(periode="2e trimestre 2099"), decrets=references["decret"],
                       situations=references["situation"])
        forme = {l.code: l for l in res.forme}
        assert forme["plan_strategique"].statut == "Non applicable" and "non exigée" in forme["plan_strategique"].precision
        # titre « II.1- Situation d'exécution du budget » trouvé (sans texte propre : ses sous-parties suivent)
        assert "Situation d'exécution du budget" in forme["perso_1"].precision
        assert forme["perso_2"].statut == "Non conforme"
        assert "Analyse de la soutenabilité financière" in forme["global_forme"].precision  # obligatoire, même sans ligne
        assert forme["T8"].statut == "Non applicable"
        assert "0999" in appreciation_forme_texte(res)
        sortie = remplir_modele(res, tmp_path / "analyse.xlsx")
        ws = openpyxl.load_workbook(sortie).worksheets[0]
        assert ws["C41"].value == forme["performance"].statut and ws["E41"].value
        assert ws["C103"].value and ws["A43"].value.startswith("Analyse de la gestion financi")
        assert ws["C23"].value == forme["introduction"].statut
        assert next(t for t in d["tableaux"] if t["code"] == "T5")["ligne"] == 70  # tableau 5 : 69 → 70
        assert ws["C70"].value == forme["T5"].statut and "recettes" in ws["A70"].value
        assert "Suite" in ws["A182"].value and ws["A183"].value
        assert ws.print_area == "'Feuil1'!$A$1:$E$186"

        # ---- retour au canevas et au modèle par défaut
        d = canevas.reinitialiser_modele()
        d = canevas.reinitialiser()
        assert not d["modifie"] and not d["modele"]["personnalise"] and not any(r["perso"] for r in d["rubriques"])
        assert next(r for r in d["rubriques"] if r["code"] == "gestion_financiere")["ligne"] == 42
    finally:
        for f in (canevas.chemin_config(), modele.chemin_personnalise(), tmp_path / modele.NOM_META):
            if f.exists():
                f.unlink()
        canevas.actualiser(force=True)


def appreciation_forme_texte(res) -> str:
    from analyse_cb.redaction import appreciation_forme
    return appreciation_forme(res)


def generer_canevas(dossier: Path) -> Path:
    """Canevas fictif : plan de la note n°0580, une partie nouvelle (soutenabilité financière) et un tableau 9 ; sans
    la partie « Analyse de la gestion financière »."""
    from docx import Document
    d = Document()
    for t in ("RÉPUBLIQUE DE CÔTE D'IVOIRE", "MINISTÈRE DU BUDGET ET DU PORTEFEUILLE DE L'ÉTAT",
              "DIRECTION DU CONTRÔLE BUDGÉTAIRE"):
        d.add_paragraph(t)
    d.add_paragraph("Note n°0123/MBPE/DGBF/DCB du 5 janvier 2099 portant canevas de rédaction des rapports des "
                    "Contrôleurs Budgétaires auprès des EPN (exemple fictif).")
    d.add_paragraph("CANEVAS DE RÉDACTION DU RAPPORT DU CONTRÔLEUR BUDGÉTAIRE")
    plan = [("INTRODUCTION", None), ("- Texte de création ;", None), ("- Rappel des missions ;", None),
            ("- Nombre d'antennes et lieu d'installation (le cas échéant) ;", None), ("- Mode de financement de l'EPN ;", None),
            ("- Organisation et effectif de l'EPN ;", None), ("Présentation du plan stratégique (le cas échéant)", "List Bullet"),
            ("Présentation du Programme Annuel d'Activités", "List Bullet"),
            ("I. PRÉSENTATION DU BUDGET", None), ("I.1 Présentation générale", None), ("I.2 Présentation des ressources", None),
            ("I.3 Présentation des emplois", None),
            ("II. ANALYSE DE L'EXÉCUTION DU BUDGET", None), ("II.1 Situation d'exécution du budget en recettes", None),
            ("II.2 Situation d'exécution du budget en dépenses", None), ("II.3 Analyse des différés et rejets", None),
            ("II.4 Analyse du résultat budgétaire", None), ("II.5 Analyse des ratios de gestion", None),
            ("III. ANALYSE DE LA PERFORMANCE", None), ("III.1 Programme d'activités", None),
            ("III.2 Évaluation de la réalisation des activités", None),
            ("IV. ANALYSE DE LA SOUTENABILITÉ FINANCIÈRE", None), ("IV.1 Niveau d'endettement de l'EPN", None),
            ("IV.2 Capacité d'autofinancement (rapport annuel)", None),
            ("V. ÉVALUATION DES DISPOSITIFS DE CONTRÔLE", None), ("V.1 Contrôle interne budgétaire", None),
            ("V.2 Contrôle de gestion", None), ("VI. SITUATION DU PATRIMOINE", None),
            ("- État du patrimoine existant ;", None), ("- Point des nouvelles acquisitions ;", None),
            ("- Mise en œuvre de la comptabilité des matières ;", None),
            ("VII. SITUATION DE LA GOUVERNANCE DE L'EPN", None), ("VII.1 COGES / Organes de supervision", None),
            ("VII.2 Comité de trésorerie", None), ("VIII. ANALYSE DE LA GESTION DES RISQUES", None),
            ("IX. DIFFICULTÉS ET SUGGESTIONS", None), ("IX.1 Difficultés", None), ("IX.2 Suggestions", None),
            ("CONCLUSION", None), ("ANNEXES", None), ("Tableaux à produire :", None)]
    for t, style in plan:
        d.add_paragraph(t, style=style) if style else d.add_paragraph(t)
    for i, t in enumerate(["Budget de l'année considérée comparé à celui de l'année précédente",
                           "Budgets des trois derniers exercices", "Présentation des ressources par nature économique",
                           "Présentation des emplois par nature de dépenses et par activité",
                           "Exécution détaillée du budget en recettes", "Exécution détaillée du budget en dépenses",
                           "Principaux motifs des différés", "Principaux motifs des rejets",
                           "Situation de l'endettement de l'EPN"], start=1):
        d.add_paragraph(f"- Tableau {i} : {t}")
    chemin = dossier / "Canevas_exemple.docx"
    d.save(chemin)
    return chemin


def test_actualiser_canevas_depuis_document(tmp_path, monkeypatch):
    """Un document de canevas est lu : référence, rubriques reconnues, nouvelles, absentes, tableaux ; les
    propositions retenues s'enregistrent dans le canevas (nouvelle partie placée à sa place dans le plan)."""
    _profil_temporaire(monkeypatch, tmp_path)
    from analyse_cb import canevas
    from analyse_cb.canevas_document import analyser_document, chemin_document
    try:
        p = analyser_document(generer_canevas(tmp_path), "Canevas_exemple.docx")
        assert p["reference"] == "note n°0123/MBPE/DGBF/DCB du 5 janvier 2099"
        reconnues = {r["code"] for r in p["retrouvees"]}
        assert {"introduction", "texte_creation", "antennes", "plan_strategique", "paa", "pres_ressources", "ratios",
                "performance", "patrimoine_existant", "compta_matieres", "coges", "comite_tresorerie", "risques",
                "difficultes", "suggestions", "conclusion", "annexes"} <= reconnues
        nouvelles = [(n["libelle"], n["niveau"], n["exigence"]) for n in p["nouvelles"]]
        assert nouvelles == [("Analyse de la soutenabilité financière", 1, "obligatoire"),
                             ("Niveau d'endettement de l'EPN", 2, "obligatoire"),
                             ("Capacité d'autofinancement", 2, "annuel")]
        partie = p["nouvelles"][0]
        assert partie["apres"] == "performance" and p["nouvelles"][1]["parent"] == partie["cle"]
        absentes = {a["code"] for a in p["absentes"]}
        assert {"gestion_financiere", "solde_tresorerie", "creances"} <= absentes and not absentes & reconnues
        assert [t["numero"] for t in p["tableaux"]] == list(range(1, 10)) and p["tableaux"][8]["code"] is None
        assert next(t for t in p["tableaux"] if t["numero"] == 5)["different"]  # « Exécution détaillée … »
        assert chemin_document().name == "Canevas_exemple.docx"

        # Propositions retenues (comme le bouton « Appliquer », puis « Enregistrer le canevas »)
        d = canevas.description()
        rubs = [{"code": r["code"], "libelle": r["libelle"], "exigence": r["exigence"], "titre_requis": r["titre_requis"],
                 "mots_min": r["mots_min"], "intitules": r["intitules"], "ligne": "auto"} for r in d["rubriques"]]
        for n in p["nouvelles"]:
            rubs.append({"code": n["cle"], "libelle": n["libelle"], "parent": n["parent"], "apres": n["apres"],
                         "exigence": n["exigence"], "intitules": []})
        d = canevas.enregistrer({"reference": p["reference"], "rubriques": rubs})
        codes = [r.code for r in canevas.RUBRIQUES]
        i = codes.index("perso_1")
        assert canevas.RUBRIQUES[i - 1].parent == "performance" or canevas.RUBRIQUES[i - 1].code == "performance"
        assert [(r.code, r.parent) for r in canevas.RUBRIQUES[i:i + 3]] == \
            [("perso_1", None), ("perso_2", "perso_1"), ("perso_3", "perso_1")]
        assert canevas.PAR_CODE["perso_3"].annuel_seulement and d["document"]["nom"] == "Canevas_exemple.docx"
        assert canevas.reference().startswith("note n°0123")
    finally:
        if canevas.chemin_config().exists():
            canevas.chemin_config().unlink()
        canevas.actualiser(force=True)


def test_fichier_analyse_word(res_anomalies_ref, tmp_path, monkeypatch):
    """Fichier d'analyse Word : structure et libellés du modèle de fichier d'analyse, statuts, textes rédigés."""
    _profil_temporaire(monkeypatch, tmp_path)
    from docx import Document
    from analyse_cb.excel import suite_a_donner
    from analyse_cb.word import rediger_word
    res = res_anomalies_ref
    f = rediger_word(res, tmp_path / "analyse.docx", institution={"ligne1": "Ministère des Finances et du Budget"})
    d = Document(f)
    textes = [p.text for p in d.paragraphs]
    assert textes[0].startswith("CANEVAS D'ANALYSE DES RAPPORTS")  # titre du modèle Excel
    for titre in ("I. DELAI DE TRANSMISSION", "II. ANALYSE DE LA FORME DU RAPPORT", "III. ANALYSE DU FOND DU RAPPORT",
                  "Appréciation générale du fond du rapport", "Suite à donner"):
        assert titre in textes, titre
    assert suite_a_donner(res) in textes and not any("{{" in t for t in textes)
    assert len(d.tables) == 6  # identification, délai, forme, fond, difficultés, suggestions
    ident, delai, forme, fond = d.tables[:4]
    assert ident.rows[0].cells[1].text == res.infos.epn and delai.rows[1].cells[4].text == res.appreciation_delai
    lignes_forme = {r.cells[0].text: r.cells[1].text for r in forme.rows[1:]}
    statuts = {l.code: l.statut for l in res.forme}
    assert lignes_forme["Présence de toutes les parties et sous-parties obligatoires du rapport"] == statuts["global_forme"]
    assert lignes_forme["Analyse des ratios de gestion"] == statuts["ratios"]
    lib_fond = [r.cells[0].text for r in fond.rows[1:]]
    assert "COGES / Organes de supervision (Conseil de gestion)" in lib_fond and "Comité de trésorerie" in lib_fond
    assert "Contrôle de trésorerie" not in lib_fond  # libellé erroné de la grille de la DCB corrigé
    assert res.infos.epn in d.sections[0].footer.paragraphs[0].text
    assert d.sections[0].header.paragraphs[0].text == "MINISTÈRE DES FINANCES ET DU BUDGET"


def test_modele_word_personnalise(res_conforme_ref, tmp_path, monkeypatch):
    """Modèle Word importé : champs {{…}} remplacés (corps, en-tête), grille insérée à l'emplacement de {{ANALYSE}}."""
    _profil_temporaire(monkeypatch, tmp_path)
    from docx import Document
    from analyse_cb import modele
    from analyse_cb.word import rediger_word
    m = Document()
    m.sections[0].header.paragraphs[0].text = "Direction du Contrôle Budgétaire – {{EPN}}"
    m.add_paragraph("FICHE D'ANALYSE – {{EPN}} ({{PERIODE}})")
    m.add_paragraph("{{ANALYSE}}")
    m.add_paragraph("Fait le {{DATE_ANALYSE}} – Le Chargé d'Études")
    m.save(tmp_path / "Mon modèle.docx")
    info = modele.importer_word(tmp_path / "Mon modèle.docx", "Mon modèle.docx")
    assert info["personnalise"] and info["repere_analyse"] and {"EPN", "PERIODE", "ANALYSE"} <= set(info["champs"])
    try:
        f = rediger_word(res_conforme_ref, tmp_path / "analyse.docx", modele.modele_word_courant())
        d = Document(f)
        assert d.paragraphs[0].text == f"FICHE D'ANALYSE – {res_conforme_ref.infos.epn} ({res_conforme_ref.periode.libelle})"
        assert d.sections[0].header.paragraphs[0].text.endswith(res_conforme_ref.infos.epn)
        assert len(d.tables) == 5  # pas de tableau d'identification : le modèle affiche lui-même {{EPN}}
        corps = list(d.element.body)
        dernier_tableau = max(i for i, e in enumerate(corps) if e.tag.endswith("}tbl"))
        signature = next(i for i, e in enumerate(corps) if "Fait le" in "".join(e.itertext()))
        assert dernier_tableau < signature and not any("{{" in p.text for p in d.paragraphs)
    finally:
        modele.reinitialiser_word()
    assert not modele.info_word()["personnalise"]


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice absent : conversion .doc non testable")
def test_document_doc_converti(rapports, tmp_path, monkeypatch):
    """Un rapport au format Word 97-2003 (.doc) est converti puis lu comme le .docx d'origine."""
    _profil_temporaire(monkeypatch, tmp_path)
    from analyse_cb.lecture import lire_rapport
    subprocess.run(["soffice", "--headless", "--convert-to", "doc", "--outdir", str(tmp_path), str(rapports["conforme"])],
                   capture_output=True, timeout=180)
    doc_97 = tmp_path / (Path(rapports["conforme"]).stem + ".doc")
    assert doc_97.exists()
    lu = lire_rapport(doc_97)
    assert lu.chemin == doc_97 and "INTRODUCTION" in lu.texte(avec_tableaux=False)


def test_doc_sans_convertisseur(tmp_path, monkeypatch):
    _profil_temporaire(monkeypatch, tmp_path)
    from analyse_cb import bureautique
    monkeypatch.setattr(bureautique, "_par_word", lambda s, c: False)
    monkeypatch.setattr(bureautique, "_par_libreoffice", lambda s, c: False)
    (tmp_path / "ancien.doc").write_bytes(b"\xd0\xcf\x11\xe0 document")
    with pytest.raises(ValueError, match="Enregistrer sous"):
        bureautique.doc_vers_docx(tmp_path / "ancien.doc")
