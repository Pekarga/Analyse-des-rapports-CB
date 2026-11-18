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
from generer_exemple import generer  # noqa: E402


@pytest.fixture(scope="session")
def rapports(tmp_path_factory):
    d = tmp_path_factory.mktemp("rapports")
    return {"conforme": generer(d, False), "anomalies": generer(d, True)}


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
