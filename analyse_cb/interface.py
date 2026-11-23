"""Application de bureau (Tkinter) : analyse des rapports des Contrôleurs Budgétaires.

Lancement : python -m analyse_cb.interface  (ou AnalyseRapportsCB.exe dans la version Windows)
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import traceback
from datetime import date
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .analyse import (InfosRapport, analyser, charger_decrets, charger_parametres, charger_situations,
                      PARAMETRES_DEFAUT, REFERENTIEL_DEFAUT)
from .commentaires import aerer
from .controles import lire_date
from .excel import remplir_modele, suite_a_donner, tableau_de_bord
from .redaction import appreciation_generale
from .ressources import dossier_ressources, dossier_utilisateur

TITRE = "Analyse des rapports des Contrôleurs Budgétaires"
BLEU, BLEU_FONCE, GRIS, BLANC = "#1F4E78", "#163A5A", "#F2F4F7", "#FFFFFF"
VERT_TXT, ROUGE_TXT, ROUGE_FOND = "#1E6B3A", "#9C0006", "#FFE1E4"
EXT_RAPPORTS = (".docx", ".pdf")
EXT_DECRETS = (".pdf", ".docx", ".txt")
EXT_SITUATIONS = (".xlsx", ".xlsm", ".csv", ".pdf", ".docx")
POLICE = "Segoe UI" if sys.platform.startswith("win") else "DejaVu Sans"

ETATS = {"attente": "En attente", "cours": "En cours…", "ok": "Terminé", "erreur": "Erreur", "arret": "Non traité"}


def ouvrir(chemin: Path) -> None:
    """Ouvre un fichier ou un dossier avec l'application par défaut du système."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(chemin))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(chemin)])
        else:
            subprocess.Popen(["xdg-open", str(chemin)])
    except Exception as exc:  # pragma: no cover - dépend du poste
        messagebox.showerror(TITRE, f"Impossible d'ouvrir {chemin} :\n{exc}")


def dossier_sortie_defaut() -> Path:
    documents = Path.home() / "Documents"
    return (documents if documents.is_dir() else Path.home()) / "Analyses rapports CB"


# ------------------------------------------------------------------ préférences (Chargé d'Études, dossier)
def _fichier_preferences() -> Path:
    return dossier_utilisateur() / "preferences.json"


def lire_preferences() -> dict:
    try:
        return json.loads(_fichier_preferences().read_text(encoding="utf-8"))
    except Exception:
        return {}


def enregistrer_preferences(prefs: dict) -> None:
    try:
        _fichier_preferences().write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


class ListeFichiers(ttk.Frame):
    """Liste de fichiers avec boutons Ajouter / Retirer."""

    def __init__(self, parent, titre: str, extensions: tuple[str, ...], aide: str, hauteur: int = 4):
        super().__init__(parent, style="Carte.TFrame")
        self.extensions = extensions
        self.fichiers: list[Path] = []
        ttk.Label(self, text=titre, style="Sous.TLabel").pack(anchor="w")
        ttk.Label(self, text=aide, style="Aide.TLabel", wraplength=360, justify="left").pack(anchor="w", pady=(0, 3))
        cadre = ttk.Frame(self, style="Carte.TFrame")
        cadre.pack(fill="both", expand=True)
        self.liste = tk.Listbox(cadre, height=hauteur, activestyle="none", selectmode="extended", relief="solid",
                                borderwidth=1, highlightthickness=0, font=(POLICE, 9))
        barre = ttk.Scrollbar(cadre, orient="vertical", command=self.liste.yview)
        self.liste.configure(yscrollcommand=barre.set)
        self.liste.pack(side="left", fill="both", expand=True)
        barre.pack(side="left", fill="y")
        self.liste.bind("<Delete>", lambda e: self.retirer())
        boutons = ttk.Frame(self, style="Carte.TFrame")
        boutons.pack(anchor="w", pady=(4, 0))
        ttk.Button(boutons, text="Ajouter…", command=self.ajouter).pack(side="left")
        ttk.Button(boutons, text="Retirer", command=self.retirer).pack(side="left", padx=4)

    def ajouter(self):
        motifs = " ".join(f"*{e}" for e in self.extensions)
        for c in filedialog.askopenfilenames(title="Choisir des fichiers",
                                             filetypes=[("Fichiers acceptés", motifs), ("Tous les fichiers", "*.*")]):
            self.ajouter_chemin(Path(c))

    def ajouter_chemin(self, p: Path):
        if p not in self.fichiers:
            self.fichiers.append(p)
            self.liste.insert("end", p.name)

    def retirer(self):
        for i in sorted(self.liste.curselection(), reverse=True):
            self.liste.delete(i)
            del self.fichiers[i]


class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{TITRE} – version {__version__}")
        self.geometry("1180x800")
        self.minsize(1000, 700)
        self.configure(background=GRIS)
        self._icone()
        self._styles()
        self.prefs = lire_preferences()
        self.rapports: list[dict] = []  # {"chemin", "reception", "periode", "etat"}
        self.resultats: list[tuple] = []  # (ResultatAnalyse, Path)
        self.tableau_bord: Path | None = None
        self.file: queue.Queue = queue.Queue()
        self.en_cours = False
        self.arret_demande = threading.Event()
        self._menu()
        self._construire()
        self.protocol("WM_DELETE_WINDOW", self.quitter)
        self.after(200, self._verifier_ocr)

    # ------------------------------------------------------------------ présentation
    def _icone(self):
        try:
            if sys.platform.startswith("win"):
                ico = dossier_ressources() / "packaging" / "icone.ico"
                if ico.exists():
                    self.iconbitmap(default=str(ico))
            else:
                png = dossier_ressources() / "packaging" / "icone.png"
                if png.exists():
                    self._img_icone = tk.PhotoImage(file=str(png))
                    self.iconphoto(True, self._img_icone)
        except Exception:
            pass

    def _styles(self):
        st = ttk.Style(self)
        for theme in ("vista", "clam"):
            if theme in st.theme_names():
                st.theme_use(theme)
                break
        st.configure(".", font=(POLICE, 9))
        st.configure("TFrame", background=GRIS)
        st.configure("Carte.TFrame", background=BLANC)
        st.configure("TLabel", background=GRIS)
        st.configure("Carte.TLabel", background=BLANC)
        st.configure("Titre.TLabel", font=(POLICE, 16, "bold"), foreground=BLANC, background=BLEU)
        st.configure("SousTitre.TLabel", font=(POLICE, 9), foreground="#D6E4F0", background=BLEU)
        st.configure("Section.TLabel", font=(POLICE, 11, "bold"), foreground=BLEU, background=BLANC)
        st.configure("Sous.TLabel", font=(POLICE, 9, "bold"), background=BLANC)
        st.configure("Aide.TLabel", font=(POLICE, 8), foreground="#5A6270", background=BLANC)
        st.configure("Pied.TLabel", font=(POLICE, 8), foreground="#5A6270", background=GRIS)
        st.configure("Lancer.TButton", font=(POLICE, 11, "bold"), padding=(20, 8))
        st.configure("Treeview.Heading", font=(POLICE, 9, "bold"))
        st.configure("Treeview", rowheight=24, font=(POLICE, 9))
        st.configure("Bleu.Horizontal.TProgressbar", background=BLEU, troughcolor="#E1E5EA", thickness=12)
        st.configure("TNotebook", background=GRIS, borderwidth=0)
        st.configure("TNotebook.Tab", font=(POLICE, 10, "bold"), padding=(16, 6))

    def _menu(self):
        barre = tk.Menu(self)
        fichier = tk.Menu(barre, tearoff=False)
        fichier.add_command(label="Ajouter des rapports…", command=self.ajouter_rapports, accelerator="Ctrl+O")
        fichier.add_command(label="Ajouter un dossier de rapports…", command=self.ajouter_dossier)
        fichier.add_separator()
        fichier.add_command(label="Ouvrir le dossier des résultats", command=self.ouvrir_dossier_sortie)
        fichier.add_separator()
        fichier.add_command(label="Quitter", command=self.quitter)
        barre.add_cascade(label="Fichier", menu=fichier)
        reglages = tk.Menu(barre, tearoff=False)
        reglages.add_command(label="Modifier les paramètres (délais, seuils)…", command=lambda: ouvrir(PARAMETRES_DEFAUT))
        reglages.add_command(label="Modifier le référentiel des EPN…", command=lambda: ouvrir(REFERENTIEL_DEFAUT))
        reglages.add_command(label="Ouvrir le dossier des paramètres", command=lambda: ouvrir(PARAMETRES_DEFAUT.parent))
        barre.add_cascade(label="Paramètres", menu=reglages)
        aide = tk.Menu(barre, tearoff=False)
        aide.add_command(label="Mode d'emploi", command=self.mode_emploi)
        aide.add_command(label="Lecture des documents scannés (OCR)…", command=lambda: self._verifier_ocr(True))
        aide.add_command(label="À propos", command=self.a_propos)
        barre.add_cascade(label="Aide", menu=aide)
        self.config(menu=barre)
        self.bind_all("<Control-o>", lambda e: self.ajouter_rapports())

    def _construire(self):
        entete = tk.Frame(self, background=BLEU)
        entete.pack(fill="x")
        ttk.Label(entete, text=TITRE, style="Titre.TLabel").pack(anchor="w", padx=20, pady=(12, 0))
        ttk.Label(entete, text="Direction du Contrôle Budgétaire – canevas de la note n°0580/MBPE/DGBF/DCB du "
                               "26 juillet 2023, décret de création et situation d'exécution",
                  style="SousTitre.TLabel").pack(anchor="w", padx=20, pady=(0, 12))

        pied = ttk.Frame(self)
        pied.pack(side="bottom", fill="x", padx=16, pady=(4, 6))
        self.pied_ocr = tk.StringVar(value="")
        ttk.Label(pied, textvariable=self.pied_ocr, style="Pied.TLabel").pack(side="left")
        ttk.Label(pied, text=f"Version {__version__}", style="Pied.TLabel").pack(side="right")

        self.onglets = ttk.Notebook(self)
        self.onglets.pack(fill="both", expand=True, padx=14, pady=(10, 0))
        self.page_prep = ttk.Frame(self.onglets)
        self.page_res = ttk.Frame(self.onglets)
        self.onglets.add(self.page_prep, text="  1. Préparer l'analyse  ")
        self.onglets.add(self.page_res, text="  2. Résultats  ")
        self._construire_preparation(self.page_prep)
        self._construire_resultats(self.page_res)

    def _construire_preparation(self, page):
        page.columnconfigure(0, weight=3)
        page.columnconfigure(1, weight=2)
        page.rowconfigure(0, weight=1)

        # 1. Rapports
        carte = ttk.Frame(page, style="Carte.TFrame", padding=14)
        carte.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(10, 0))
        ttk.Label(carte, text="Rapports à analyser", style="Section.TLabel").pack(anchor="w")
        ttk.Label(carte, text="Fichiers Word ou PDF, y compris scannés. Double-cliquez sur un rapport pour saisir "
                              "sa date de réception à la DCB.", style="Aide.TLabel").pack(anchor="w", pady=(0, 6))
        cadre = ttk.Frame(carte, style="Carte.TFrame")
        cadre.pack(fill="both", expand=True)
        self.table = ttk.Treeview(cadre, columns=("fichier", "reception", "periode", "etat"), show="headings", height=9)
        for col, titre, largeur, ancre in (("fichier", "Rapport", 270, "w"), ("reception", "Date de réception", 130, "center"),
                                           ("periode", "Période (si non détectée)", 180, "w"), ("etat", "État", 90, "center")):
            self.table.heading(col, text=titre)
            self.table.column(col, width=largeur, anchor=ancre)
        self.table.tag_configure("ok", foreground=VERT_TXT)
        self.table.tag_configure("erreur", foreground=ROUGE_TXT)
        self.table.tag_configure("cours", foreground=BLEU)
        barre = ttk.Scrollbar(cadre, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=barre.set)
        self.table.pack(side="left", fill="both", expand=True)
        barre.pack(side="left", fill="y")
        self.table.bind("<Double-1>", lambda e: self.modifier_rapport())
        self.table.bind("<Delete>", lambda e: self.retirer_rapports())
        boutons = ttk.Frame(carte, style="Carte.TFrame")
        boutons.pack(fill="x", pady=(8, 0))
        ttk.Button(boutons, text="Ajouter des rapports…", command=self.ajouter_rapports).pack(side="left")
        ttk.Button(boutons, text="Ajouter un dossier…", command=self.ajouter_dossier).pack(side="left", padx=4)
        ttk.Button(boutons, text="Date de réception…", command=self.modifier_rapport).pack(side="left")
        ttk.Button(boutons, text="Même date pour tous…", command=self.date_pour_tous).pack(side="left", padx=4)
        ttk.Button(boutons, text="Retirer", command=self.retirer_rapports).pack(side="right")

        # 2. Références
        ref = ttk.Frame(page, style="Carte.TFrame", padding=14)
        ref.grid(row=0, column=1, sticky="nsew", pady=(10, 0))
        ttk.Label(ref, text="Documents de référence (facultatifs)", style="Section.TLabel").pack(anchor="w", pady=(0, 6))
        self.decrets = ListeFichiers(ref, "Décrets de création et d'organisation", EXT_DECRETS,
                                     "Chaque rapport est rapproché du décret de son EPN (dénomination ou sigle).", 3)
        self.decrets.pack(fill="both", expand=True, pady=(0, 10))
        self.situations = ListeFichiers(ref, "Situations d'exécution (SIGOBE, Excel, CSV, PDF)", EXT_SITUATIONS,
                                        "De préférence arrêtées à la fin de la période. Les états recettes et dépenses "
                                        "d'un même EPN sont réunis automatiquement.", 3)
        self.situations.pack(fill="both", expand=True)

        # 3. Paramètres et lancement
        bas = ttk.Frame(page, style="Carte.TFrame", padding=14)
        bas.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 10))
        ligne = ttk.Frame(bas, style="Carte.TFrame")
        ligne.pack(fill="x")
        ttk.Label(ligne, text="Chargé d'Études :", style="Sous.TLabel").pack(side="left")
        self.charge = tk.StringVar(value=self.prefs.get("charge", ""))
        ttk.Entry(ligne, textvariable=self.charge, width=28).pack(side="left", padx=(6, 18))
        ttk.Label(ligne, text="Dossier des résultats :", style="Sous.TLabel").pack(side="left")
        self.sortie = tk.StringVar(value=self.prefs.get("sortie") or str(dossier_sortie_defaut()))
        ttk.Button(ligne, text="Parcourir…", command=self.choisir_sortie).pack(side="right")
        ttk.Entry(ligne, textvariable=self.sortie).pack(side="left", fill="x", expand=True, padx=6)

        action = ttk.Frame(bas, style="Carte.TFrame")
        action.pack(fill="x", pady=(12, 0))
        self.bouton = ttk.Button(action, text="▶  Lancer l'analyse", style="Lancer.TButton", command=self.lancer)
        self.bouton.pack(side="left")
        self.bouton_arret = ttk.Button(action, text="Arrêter", command=self.arreter, state="disabled")
        self.bouton_arret.pack(side="left", padx=(6, 0))
        droite = ttk.Frame(action, style="Carte.TFrame")
        droite.pack(side="left", fill="x", expand=True, padx=(16, 0))
        self.progression = ttk.Progressbar(droite, mode="determinate", style="Bleu.Horizontal.TProgressbar")
        self.progression.pack(fill="x")
        self.etat = tk.StringVar(value="Ajoutez un ou plusieurs rapports, puis lancez l'analyse.")
        ttk.Label(droite, textvariable=self.etat, style="Carte.TLabel").pack(anchor="w", pady=(4, 0))

    def _construire_resultats(self, page):
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)
        haut = ttk.Frame(page, style="Carte.TFrame", padding=14)
        haut.grid(row=0, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(haut, text="Rapports analysés", style="Section.TLabel").pack(anchor="w")
        ttk.Label(haut, text="Sélectionnez un rapport pour lire son appréciation ; double-cliquez pour ouvrir le fichier "
                             "d'analyse Excel.", style="Aide.TLabel").pack(anchor="w", pady=(0, 6))
        cadre = ttk.Frame(haut, style="Carte.TFrame")
        cadre.pack(fill="x")
        cols = (("epn", "EPN", 280), ("periode", "Période", 190), ("forme", "Forme", 70), ("fond", "Fond", 70),
                ("maj", "Anomalies majeures", 130), ("suite", "Suite à donner", 260))
        self.res_table = ttk.Treeview(cadre, columns=[c[0] for c in cols], show="headings", height=6)
        for col, titre, largeur in cols:
            self.res_table.heading(col, text=titre)
            self.res_table.column(col, width=largeur, anchor="w" if col in ("epn", "periode", "suite") else "center")
        self.res_table.tag_configure("retour", foreground=ROUGE_TXT)
        self.res_table.tag_configure("ok", foreground=VERT_TXT)
        self.res_table.tag_configure("erreur", foreground=ROUGE_TXT, background=ROUGE_FOND)
        barre = ttk.Scrollbar(cadre, orient="vertical", command=self.res_table.yview)
        self.res_table.configure(yscrollcommand=barre.set)
        self.res_table.pack(side="left", fill="x", expand=True)
        barre.pack(side="left", fill="y")
        self.res_table.bind("<Double-1>", lambda e: self.ouvrir_resultat())
        self.res_table.bind("<<TreeviewSelect>>", lambda e: self.afficher_apercu())
        boutons = ttk.Frame(haut, style="Carte.TFrame")
        boutons.pack(fill="x", pady=(8, 0))
        ttk.Button(boutons, text="Ouvrir le fichier d'analyse", command=self.ouvrir_resultat).pack(side="left")
        self.bouton_tdb = ttk.Button(boutons, text="Ouvrir le tableau de bord", command=self.ouvrir_tableau_bord,
                                     state="disabled")
        self.bouton_tdb.pack(side="left", padx=4)
        ttk.Button(boutons, text="Ouvrir le dossier des résultats", command=self.ouvrir_dossier_sortie).pack(side="left")

        bas = ttk.Frame(page, style="Carte.TFrame", padding=14)
        bas.grid(row=1, column=0, sticky="nsew", pady=(10, 10))
        tete = ttk.Frame(bas, style="Carte.TFrame")
        tete.pack(fill="x")
        ttk.Label(tete, text="Appréciation générale", style="Section.TLabel").pack(side="left")
        ttk.Button(tete, text="Copier le texte", command=self.copier_apercu).pack(side="right")
        cadre = ttk.Frame(bas, style="Carte.TFrame")
        cadre.pack(fill="both", expand=True, pady=(6, 0))
        self.apercu = tk.Text(cadre, wrap="word", relief="flat", background="#FAFBFC", padx=14, pady=10,
                              font=(POLICE, 10), spacing1=1, spacing3=4, state="disabled", height=12)
        self.apercu.tag_configure("titre", font=(POLICE, 11, "bold"), foreground=BLEU, spacing3=6)
        self.apercu.tag_configure("chiffres", font=(POLICE, 9), foreground="#5A6270", spacing3=8)
        self.apercu.tag_configure("suite", font=(POLICE, 10, "bold"))
        barre = ttk.Scrollbar(cadre, orient="vertical", command=self.apercu.yview)
        self.apercu.configure(yscrollcommand=barre.set)
        self.apercu.pack(side="left", fill="both", expand=True)
        barre.pack(side="left", fill="y")
        self._ecrire_apercu([("Aucun résultat pour le moment. Lancez une analyse depuis l'onglet « Préparer l'analyse ».", "")])

    # ------------------------------------------------------------------ rapports
    def _ligne_rapport(self, i: int):
        r = self.rapports[i]
        valeurs = (r["chemin"].name, self._date_txt(r["reception"]), r["periode"], ETATS[r["etat"]])
        tag = {"ok": "ok", "erreur": "erreur", "cours": "cours"}.get(r["etat"], "")
        if self.table.exists(str(i)):
            self.table.item(str(i), values=valeurs, tags=(tag,))
        else:
            self.table.insert("", "end", iid=str(i), values=valeurs, tags=(tag,))

    def _ajouter(self, chemins):
        deja = {r["chemin"] for r in self.rapports}
        for c in chemins:
            p = Path(c)
            if p.suffix.lower() not in EXT_RAPPORTS or p.name.startswith("~$") or p in deja:
                continue
            self.rapports.append({"chemin": p, "reception": None, "periode": "", "etat": "attente"})
            self._ligne_rapport(len(self.rapports) - 1)
        self._maj_etat()

    def ajouter_rapports(self):
        self._ajouter(filedialog.askopenfilenames(title="Choisir les rapports des CB",
                                                  filetypes=[("Rapports", "*.docx *.pdf"), ("Tous les fichiers", "*.*")]))

    def ajouter_dossier(self):
        d = filedialog.askdirectory(title="Choisir un dossier de rapports")
        if d:
            self._ajouter(sorted(Path(d).iterdir()))

    def retirer_rapports(self):
        if self.en_cours:
            return
        retires = {int(i) for i in self.table.selection()}
        self.rapports = [r for i, r in enumerate(self.rapports) if i not in retires]
        self.table.delete(*self.table.get_children())
        for i in range(len(self.rapports)):
            self._ligne_rapport(i)
        self._maj_etat()

    @staticmethod
    def _date_txt(d):
        return d.strftime("%d/%m/%Y") if d else "à saisir"

    def _demander_date(self, titre: str, valeur: str = "", periode: str | None = None):
        """Petite fenêtre de saisie ; renvoie (date | None, période) ou None si annulé."""
        fen = tk.Toplevel(self)
        fen.title(titre)
        fen.transient(self)
        fen.resizable(False, False)
        cadre = ttk.Frame(fen, padding=16)
        cadre.pack(fill="both")
        ttk.Label(cadre, text=titre, font=(POLICE, 10, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(cadre, text="Date de réception à la DCB (jj/mm/aaaa) :").grid(row=1, column=0, sticky="w", pady=(10, 2))
        v_date = tk.StringVar(value=valeur)
        e = ttk.Entry(cadre, textvariable=v_date, width=14)
        e.grid(row=1, column=1, sticky="w", pady=(10, 2), padx=6)
        ttk.Button(cadre, text="Aujourd'hui", command=lambda: v_date.set(date.today().strftime("%d/%m/%Y"))).grid(
            row=1, column=2, pady=(10, 2))
        v_per = tk.StringVar(value=periode or "")
        if periode is not None:
            ttk.Label(cadre, text="Période (seulement si elle n'est pas détectée) :").grid(row=2, column=0, sticky="w")
            an = date.today().year
            ttk.Combobox(cadre, textvariable=v_per, width=26, values=[
                "", f"1er trimestre {an}", f"1er semestre {an}", f"3e trimestre {an}", f"4e trimestre {an}",
                f"exercice {an - 1}"]).grid(row=2, column=1, columnspan=2, sticky="w", padx=6)
        resultat = {}

        def valider(_=None):
            texte = v_date.get().strip()
            d = lire_date(texte) if texte else None
            if texte and not d:
                messagebox.showerror(TITRE, "Date non reconnue. Format attendu : jj/mm/aaaa.", parent=fen)
                return
            resultat["valeur"] = (d, v_per.get().strip())
            fen.destroy()

        b = ttk.Frame(cadre)
        b.grid(row=3, column=0, columnspan=3, sticky="e", pady=(14, 0))
        ttk.Button(b, text="Annuler", command=fen.destroy).pack(side="right")
        ttk.Button(b, text="Valider", command=valider).pack(side="right", padx=6)
        fen.bind("<Return>", valider)
        fen.bind("<Escape>", lambda _: fen.destroy())
        e.focus_set()
        fen.grab_set()
        self.wait_window(fen)
        return resultat.get("valeur")

    def modifier_rapport(self):
        sel = self.table.selection()
        if not sel:
            messagebox.showinfo(TITRE, "Sélectionnez d'abord un rapport dans la liste.")
            return
        i = int(sel[0])
        r = self.rapports[i]
        rep = self._demander_date(r["chemin"].name, r["reception"].strftime("%d/%m/%Y") if r["reception"] else "",
                                  r["periode"])
        if rep:
            r["reception"], r["periode"] = rep
            self._ligne_rapport(i)
            self._maj_etat()

    def date_pour_tous(self):
        if not self.rapports:
            messagebox.showinfo(TITRE, "Ajoutez d'abord des rapports.")
            return
        rep = self._demander_date("Même date de réception pour tous les rapports")
        if rep:
            for i, r in enumerate(self.rapports):
                r["reception"] = rep[0]
                self._ligne_rapport(i)
            self._maj_etat()

    def choisir_sortie(self):
        d = filedialog.askdirectory(title="Dossier où enregistrer les fichiers d'analyse")
        if d:
            self.sortie.set(d)

    def _maj_etat(self):
        n = len(self.rapports)
        sans_date = sum(1 for r in self.rapports if not r["reception"])
        if not n:
            self.etat.set("Ajoutez un ou plusieurs rapports, puis lancez l'analyse.")
        else:
            self.etat.set(f"{n} rapport{'s' if n > 1 else ''} à analyser"
                          + (f" – {sans_date} sans date de réception (double-clic pour la saisir)." if sans_date else "."))

    # ------------------------------------------------------------------ analyse
    def lancer(self):
        if self.en_cours:
            return
        if not self.rapports:
            messagebox.showwarning(TITRE, "Ajoutez au moins un rapport à analyser.")
            return
        sortie = Path(self.sortie.get().strip() or dossier_sortie_defaut())
        try:
            sortie.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(TITRE, f"Dossier des résultats inaccessible :\n{exc}")
            return
        self.prefs.update(charge=self.charge.get().strip(), sortie=str(sortie))
        enregistrer_preferences(self.prefs)
        self.en_cours = True
        self.arret_demande.clear()
        self.bouton.configure(state="disabled")
        self.bouton_arret.configure(state="normal")
        self.res_table.delete(*self.res_table.get_children())
        self.resultats, self.tableau_bord = [], None
        self.bouton_tdb.configure(state="disabled")
        for i, r in enumerate(self.rapports):
            r["etat"] = "attente"
            self._ligne_rapport(i)
        self.progression.configure(maximum=len(self.rapports) * 100, value=0)
        travail = [dict(r) for r in self.rapports]
        threading.Thread(target=self._analyser, args=(travail, sortie, self.charge.get().strip(),
                                                      list(self.decrets.fichiers), list(self.situations.fichiers)),
                         daemon=True).start()
        self.after(100, self._suivre)

    def arreter(self):
        self.arret_demande.set()
        self.bouton_arret.configure(state="disabled")
        self.etat.set("Arrêt demandé : l'analyse s'interrompra après le rapport en cours…")

    def _analyser(self, rapports, sortie, charge, decrets, situations):
        """Exécuté dans un fil séparé : communique avec l'interface par la file de messages."""
        from . import lecture
        f = self.file
        try:
            f.put(("etat", "Lecture des documents de référence…"))
            parametres = charger_parametres()
            liste_decrets = charger_decrets(decrets)
            liste_situations = charger_situations(situations)
        except Exception as exc:
            f.put(("fatal", f"Document de référence illisible : {exc}"))
            return
        resultats = []
        for k, r in enumerate(rapports):
            if self.arret_demande.is_set():
                for j in range(k, len(rapports)):
                    f.put(("etat_rapport", j, "arret"))
                break
            nom = r["chemin"].name
            lecture.RAPPEL_PROGRESSION = lambda page, total, k=k, nom=nom: f.put(
                ("progres", k * 100 + int(80 * page / max(total, 1)), f"{nom} : lecture du document scanné, page {page}/{total}…"))
            f.put(("etat_rapport", k, "cours"))
            f.put(("progres", k * 100, f"Analyse de {nom} ({k + 1}/{len(rapports)})…"))
            try:
                infos = InfosRapport(charge_etudes=charge, date_reception=r["reception"], periode=r["periode"] or None)
                res = analyser(r["chemin"], infos, parametres, None, decrets=liste_decrets, situations=liste_situations,
                               reference_unique=len(rapports) == 1)
                fichier = remplir_modele(res, sortie / f"Analyse_{r['chemin'].stem}.xlsx")
                resultats.append((res, fichier))
                f.put(("resultat", res, fichier))
                f.put(("etat_rapport", k, "ok"))
            except PermissionError:
                f.put(("erreur", nom, "le fichier d'analyse est ouvert dans Excel : fermez-le puis relancez."))
                f.put(("etat_rapport", k, "erreur"))
            except Exception as exc:
                f.put(("erreur", nom, str(exc)))
                f.put(("etat_rapport", k, "erreur"))
                traceback.print_exc()
        lecture.RAPPEL_PROGRESSION = None
        tdb = None
        if len(resultats) > 1:
            try:
                tdb = tableau_de_bord(resultats, sortie / "Tableau_de_bord_rapports_CB.xlsx")
            except PermissionError:
                f.put(("erreur", "Tableau de bord", "le tableau de bord est ouvert dans Excel : fermez-le puis relancez."))
            except Exception as exc:
                f.put(("erreur", "Tableau de bord", str(exc)))
        f.put(("fin", len(resultats), len(rapports), tdb, sortie))

    def _suivre(self):
        try:
            while True:
                msg = self.file.get_nowait()
                genre = msg[0]
                if genre == "etat":
                    self.etat.set(msg[1])
                elif genre == "progres":
                    self.progression.configure(value=msg[1])
                    self.etat.set(msg[2])
                elif genre == "etat_rapport":
                    if msg[1] < len(self.rapports):
                        self.rapports[msg[1]]["etat"] = msg[2]
                        self._ligne_rapport(msg[1])
                elif genre == "resultat":
                    self._afficher_resultat(msg[1], msg[2])
                elif genre == "erreur":
                    self.res_table.insert("", "end", values=(msg[1], "", "", "", "", f"Erreur : {msg[2]}"), tags=("erreur",))
                elif genre == "fatal":
                    self._terminer()
                    messagebox.showerror(TITRE, msg[1])
                    return
                elif genre == "fin":
                    _, ok, total, tdb, sortie = msg
                    self._terminer()
                    self.tableau_bord = tdb
                    if tdb:
                        self.bouton_tdb.configure(state="normal")
                    self.progression.configure(value=self.progression["maximum"])
                    self.etat.set(f"Analyse terminée : {ok} rapport{'s' if ok > 1 else ''} sur {total} traité"
                                  f"{'s' if ok > 1 else ''}. Fichiers enregistrés dans {sortie}.")
                    if ok:
                        self.onglets.select(self.page_res)
                        premier = self.res_table.get_children()
                        if premier:
                            self.res_table.selection_set(premier[0])
                    return
        except queue.Empty:
            pass
        self.after(150, self._suivre)

    def _terminer(self):
        self.en_cours = False
        self.bouton.configure(state="normal")
        self.bouton_arret.configure(state="disabled")

    def _afficher_resultat(self, res, fichier):
        self.resultats.append((res, fichier))
        retour = "retourné" in suite_a_donner(res)
        suite = "Retour au CB pour correction" if retour else "Rapport exploitable"
        fond = f"{res.score_fond:.0f} %" if res.score_fond is not None else "—"
        self.res_table.insert("", "end", iid=f"r{len(self.resultats) - 1}",
                              values=(res.infos.epn, res.periode.libelle, f"{res.score_forme:.0f} %", fond,
                                      res.nb_anomalies_majeures, suite), tags=("retour" if retour else "ok",))

    # ------------------------------------------------------------------ aperçu de l'appréciation
    def _ecrire_apercu(self, morceaux):
        self.apercu.configure(state="normal")
        self.apercu.delete("1.0", "end")
        for texte, tag in morceaux:
            self.apercu.insert("end", texte, tag)
        self.apercu.configure(state="disabled")

    def afficher_apercu(self):
        sel = [s for s in self.res_table.selection() if s.startswith("r")]
        if not sel:
            return
        res, fichier = self.resultats[int(sel[0][1:])]
        fond = f"{res.score_fond:.0f} %" if res.score_fond is not None else "non évalué"
        chiffres = (f"Forme : {res.score_forme:.0f} % ({res.mention(res.score_forme).lower()})   •   "
                    f"Fond : {fond}   •   Anomalies majeures : {res.nb_anomalies_majeures}   •   {res.appreciation_delai}\n")
        avert = "".join(f"⚠ {a}\n" for a in res.doc.avertissements)
        self._ecrire_apercu([
            (f"{res.infos.epn} – {res.periode.libelle}\n", "titre"),
            (chiffres, "chiffres"),
            (avert + ("\n" if avert else ""), "chiffres"),
            (aerer(appreciation_generale(res), 120) + "\n\n", ""),
            (suite_a_donner(res) + "\n", "suite"),
            (f"\nFichier d'analyse : {fichier}", "chiffres"),
        ])

    def copier_apercu(self):
        texte = self.apercu.get("1.0", "end").strip()
        if texte:
            self.clipboard_clear()
            self.clipboard_append(texte)
            self.etat.set("Appréciation copiée dans le presse-papiers.")

    # ------------------------------------------------------------------ ouverture des résultats
    def ouvrir_resultat(self):
        sel = [s for s in self.res_table.selection() if s.startswith("r")]
        if not sel:
            if len(self.resultats) == 1:
                ouvrir(self.resultats[0][1])
            else:
                messagebox.showinfo(TITRE, "Sélectionnez un résultat dans la liste.")
            return
        ouvrir(self.resultats[int(sel[0][1:])][1])

    def ouvrir_tableau_bord(self):
        if self.tableau_bord:
            ouvrir(self.tableau_bord)

    def ouvrir_dossier_sortie(self):
        d = Path(self.sortie.get().strip() or dossier_sortie_defaut())
        d.mkdir(parents=True, exist_ok=True)
        ouvrir(d)

    # ------------------------------------------------------------------ aide
    def _verifier_ocr(self, afficher: bool = False):
        from .ocr import ocr_disponible
        ok, message = ocr_disponible()
        self.pied_ocr.set("Lecture des documents scannés : disponible" if ok
                          else "Lecture des documents scannés : indisponible (menu Aide)")
        if afficher:
            if ok:
                messagebox.showinfo(TITRE, "La lecture des documents scannés (OCR, langue française) est opérationnelle.")
            else:
                messagebox.showwarning(TITRE, "Les documents scannés ne pourront pas être lus :\n" + message
                                       + "\n\nLes rapports Word et PDF « texte » restent analysés normalement.")

    def mode_emploi(self):
        messagebox.showinfo(TITRE, "1. Ajoutez les rapports (fichiers ou dossier) et saisissez leur date de réception "
                                   "par double-clic.\n\n2. Ajoutez, si vous les avez, les décrets de création et les "
                                   "situations d'exécution (SIGOBE).\n\n3. Indiquez le Chargé d'Études et le dossier des "
                                   "résultats, puis cliquez sur « Lancer l'analyse ».\n\nL'onglet « Résultats » affiche "
                                   "ensuite l'appréciation de chaque rapport ; un double-clic ouvre le fichier Excel.")

    def a_propos(self):
        messagebox.showinfo(TITRE, f"{TITRE}\nVersion {__version__}\n\n"
                                   "Analyse des rapports des CB au regard du canevas de la DCB (note n°0580/MBPE/DGBF/DCB "
                                   "du 26 juillet 2023), du décret de création de l'EPN et de la situation d'exécution.\n\n"
                                   f"Paramètres : {PARAMETRES_DEFAUT.parent}")

    def quitter(self):
        if self.en_cours and not messagebox.askyesno(TITRE, "Une analyse est en cours. Quitter quand même ?"):
            return
        self.prefs.update(charge=self.charge.get().strip(), sortie=self.sortie.get().strip())
        enregistrer_preferences(self.prefs)
        self.destroy()


def main() -> None:
    # Mode ligne de commande intégré à l'application : AnalyseRapportsCB.exe --ligne-de-commande rapport.pdf …
    if len(sys.argv) > 1 and sys.argv[1] == "--ligne-de-commande":
        from .__main__ import main as cli
        sys.exit(cli(sys.argv[2:]))
    if sys.platform.startswith("win"):
        try:  # affichage net sur les écrans à haute résolution
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    dossier_utilisateur()
    Application().mainloop()


if __name__ == "__main__":
    main()
