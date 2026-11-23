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
    return analyser(rapports["conforme"], InfosRapport(date_reception=date(2099, 7, 28)),
                    decrets=references["decret"], situations=references["situation"])


@pytest.fixture(scope="session")
def res_anomalies_ref(rapports, references):
    return analyser(rapports["anomalies"], InfosRapport(date_reception=date(2099, 8, 12)),
                    decrets=references["decret"], situations=references["situation_ecarts"])


@pytest.fixture(scope="session")
def res_conforme(rapports):
    return analyser(rapports["conforme"], InfosRapport(date_reception=date(2099, 7, 28), charge_etudes="CE"))


@pytest.fixture(scope="session")
def res_anomalies(rapports):
    return analyser(rapports["anomalies"], InfosRapport(date_reception=date(2099, 8, 12)))


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
    assert r.date_limite == date(2099, 7, 31)
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
    assert statut(r, "antennes") == "À vérifier"
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
    assert res_anomalies.ecart_jours == 12


# ------------------------------------------------------------------ Excel
def test_remplissage_excel(res_anomalies, tmp_path):
    sortie = remplir_modele(res_anomalies, tmp_path / "analyse.xlsx")
    wb = openpyxl.load_workbook(sortie)
    ws = wb.worksheets[0]
    assert ws["A1"].value.startswith("CANEVAS D'ANALYSE")  # modèle conservé
    assert ws["B14"].value.date() == date(2099, 7, 31)
    assert ws["D14"].value.startswith("=IF(")
    assert ws["C40"].value == "Non conforme"  # ratios
    assert ws["C101"].value == "Non renseigné"
    assert ws["C97"].value == "Non fiable"
    assert "Retard" in ws["E136"].value
    assert {"Synthèse auto", "Contrôle structure", "Contrôles automatiques", "Ratios",
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
    assert r.appreciation_decret == "Conforme au décret"
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
    assert "Situation d'exécution" in wb.worksheets[0]["A127"].value
    valeurs = [c.value for row in wb["Situation d'exécution"].iter_rows() for c in row]
    assert "Écart" in valeurs and "Concordant" in valeurs
    tdb = openpyxl.load_workbook(tableau_de_bord([(res_anomalies_ref, sortie)], tmp_path / "tdb.xlsx")).active
    entetes = [c.value for c in tdb[1]]
    assert tdb.cell(2, entetes.index("Conformité au décret de création") + 1).value.startswith("Écarts")


def test_cli_references(rapports, references, tmp_path):
    code = main([str(rapports["anomalies"]), "--decret", str(references["decret"]),
                 "--situation", str(references["situation_ecarts"]), "-o", str(tmp_path / "out")])
    assert code == 0
    wb = openpyxl.load_workbook(tmp_path / "out" / "Analyse_rapport_exemple_anomalies.xlsx")
    assert "Situation d'exécution" in wb.sheetnames
