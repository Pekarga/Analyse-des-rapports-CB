# -*- mode: python ; coding: utf-8 -*-
# Construction : pyinstaller packaging/AnalyseRapportsCB.spec --noconfirm   (depuis la racine du dépôt)
# Si un dossier « tesseract » (Tesseract OCR + tessdata/fra.traineddata) est présent à la racine, il est intégré.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

racine = Path(SPECPATH).parent
datas = [(str(racine / "config"), "config"), (str(racine / "modeles"), "modeles"),
         (str(racine / "packaging" / "icone.ico"), "packaging"), (str(racine / "packaging" / "icone.png"), "packaging"),
         (str(racine / "analyse_cb" / "web"), "analyse_cb/web")]
datas += collect_data_files("docx") + collect_data_files("pdfminer") + collect_data_files("pypdfium2")
datas += collect_data_files("pypdfium2_raw")
binaries = collect_dynamic_libs("pypdfium2_raw") + collect_dynamic_libs("pypdfium2")
if (racine / "tesseract").is_dir():
    datas.append((str(racine / "tesseract"), "tesseract"))

a = Analysis(
    [str(racine / "packaging" / "lanceur.py")],
    pathex=[str(racine)],
    binaries=binaries,
    datas=datas,
    hiddenimports=["analyse_cb.interface", "analyse_cb.__main__", "analyse_cb.serveur", "analyse_cb.historique",
                   "analyse_cb.tableau", "analyse_cb.ratios", "analyse_cb.natures", "analyse_cb.modele", "analyse_cb.canevas_document", "analyse_cb.word", "analyse_cb.bureautique", "pytesseract", "cv2", "numpy", "numpy.core.multiarray"]
                  + collect_submodules("numpy.core") + collect_submodules("numpy._core"),
    excludes=["streamlit", "pandas", "matplotlib", "IPython", "pytest", "webview", "clr", "pythonnet"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="AnalyseRapportsCB",
    console=False,
    icon=str(racine / "packaging" / "icone.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="AnalyseRapportsCB")
