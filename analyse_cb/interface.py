"""Application de bureau (Tkinter) : analyse des rapports des Contrôleurs Budgétaires.

Lancement : python -m analyse_cb.interface  (ou AnalyseRapportsCB.exe dans la version Windows)
"""
from __future__ import annotations

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
from .controles import lire_date
from .excel import remplir_modele, suite_a_donner, tableau_de_bord
from .ressources import dossier_utilisateur

TITRE = "Analyse des rapports des Contrôleurs Budgétaires"
BLEU, BLEU_CLAIR, GRIS = "#1F4E78", "#DDEBF7", "#F4F6F8"
EXT_RAPPORTS = (".docx", ".pdf")
EXT_DECRETS = (".pdf", ".docx", ".txt")
EXT_SITUATIONS = (".xlsx", ".xlsm", ".csv", ".pdf", ".docx")


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


class ListeFichiers(ttk.Frame):
    """Liste de fichiers avec boutons Ajouter / Retirer."""

    def __init__(self, parent, titre: str, extensions: tuple[str, ...], aide: str, hauteur: int = 4):
        super().__init__(parent)
        self.extensions = extensions
        self.fichiers: list[Path] = []
        ttk.Label(self, text=titre, style="Sous.TLabel").pack(anchor="w")
        ttk.Label(self, text=aide, style="Aide.TLabel", wraplength=330, justify="left").pack(anchor="w")
        cadre = ttk.Frame(self)
        cadre.pack(fill="both", expand=True, pady=(4, 4))
        self.liste = tk.Listbox(cadre, height=hauteur, activestyle="none", selectmode="extended",
                                relief="solid", borderwidth=1, highlightthickness=0)
        barre = ttk.Scrollbar(cadre, orient="vertical", command=self.liste.yview)
        self.liste.configure(yscrollcommand=barre.set)
        self.liste.pack(side="left", fill="both", expand=True)
        barre.pack(side="left", fill="y")
        boutons = ttk.Frame(self)
        boutons.pack(anchor="w")
        ttk.Button(boutons, text="Ajouter…", command=self.ajouter).pack(side="left")
        ttk.Button(boutons, text="Retirer", command=self.retirer).pack(side="left", padx=4)

    def ajouter(self):
        motifs = " ".join(f"*{e}" for e in self.extensions)
        chemins = filedialog.askopenfilenames(title="Choisir des fichiers", filetypes=[("Fichiers acceptés", motifs),
                                                                                         ("Tous les fichiers", "*.*")])
        for c in chemins:
            p = Path(c)
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
        self.geometry("1120x780")
        self.minsize(980, 680)
        self.configure(background=GRIS)
        self._styles()
        self.rapports: list[dict] = []  # {"chemin": Path, "reception": date|None, "periode": str}
        self.resultats: list[tuple] = []  # (ResultatAnalyse, Path)
        self.tableau_bord: Path | None = None
        self.file: queue.Queue = queue.Queue()
        self.en_cours = False
        self._menu()
        self._construire()
        self.after(150, self._verifier_ocr)

    # ------------------------------------------------------------------ présentation
    def _styles(self):
        st = ttk.Style(self)
        if "vista" in st.theme_names():
            st.theme_use("vista")
        elif "clam" in st.theme_names():
            st.theme_use("clam")
        st.configure("TFrame", background=GRIS)
        st.configure("Carte.TFrame", background="white", relief="solid", borderwidth=1)
        st.configure("TLabel", background=GRIS)
        st.configure("Carte.TLabel", background="white")
        st.configure("Titre.TLabel", font=("Segoe UI", 16, "bold"), foreground="white", background=BLEU)
        st.configure("SousTitre.TLabel", font=("Segoe UI", 10), foreground="#DDEBF7", background=BLEU)
        st.configure("Section.TLabel", font=("Segoe UI", 11, "bold"), foreground=BLEU, background="white")
        st.configure("Sous.TLabel", font=("Segoe UI", 9, "bold"), background="white")
        st.configure("Aide.TLabel", font=("Segoe UI", 8), foreground="#555555", background="white")
        st.configure("Etat.TLabel", font=("Segoe UI", 9), background=GRIS, foreground="#333333")
        st.configure("Lancer.TButton", font=("Segoe UI", 11, "bold"), padding=(18, 8))
        st.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        st.configure("Treeview", rowheight=24)
        st.configure("Bleu.Horizontal.TProgressbar", background=BLEU, troughcolor="#E1E5EA", thickness=14)

    def _menu(self):
        barre = tk.Menu(self)
        fichier = tk.Menu(barre, tearoff=False)
        fichier.add_command(label="Ajouter des rapports…", command=self.ajouter_rapports)
        fichier.add_command(label="Ajouter un dossier de rapports…", command=self.ajouter_dossier)
        fichier.add_separator()
        fichier.add_command(label="Ouvrir le dossier des résultats", command=self.ouvrir_dossier_sortie)
        fichier.add_separator()
        fichier.add_command(label="Quitter", command=self.destroy)
        barre.add_cascade(label="Fichier", menu=fichier)
        reglages = tk.Menu(barre, tearoff=False)
        reglages.add_command(label="Modifier les paramètres (délais, seuils)…", command=lambda: ouvrir(PARAMETRES_DEFAUT))
        reglages.add_command(label="Modifier le référentiel des EPN…", command=lambda: ouvrir(REFERENTIEL_DEFAUT))
        reglages.add_command(label="Ouvrir le dossier des paramètres", command=lambda: ouvrir(PARAMETRES_DEFAUT.parent))
        barre.add_cascade(label="Paramètres", menu=reglages)
        aide = tk.Menu(barre, tearoff=False)
        aide.add_command(label="Lecture des documents scannés (OCR)…", command=lambda: self._verifier_ocr(True))
        aide.add_command(label="À propos", command=self.a_propos)
        barre.add_cascade(label="Aide", menu=aide)
        self.config(menu=barre)

    def _construire(self):
        entete = tk.Frame(self, background=BLEU)
        entete.pack(fill="x")
        ttk.Label(entete, text=TITRE, style="Titre.TLabel").pack(anchor="w", padx=18, pady=(12, 0))
        ttk.Label(entete, text="Direction du Contrôle Budgétaire – canevas de la note n°0580/MBPE/DGBF/DCB du "
                               "26 juillet 2023, décret de création et situation d'exécution",
                  style="SousTitre.TLabel").pack(anchor="w", padx=18, pady=(0, 12))

        corps = ttk.Frame(self)
        corps.pack(fill="both", expand=True, padx=14, pady=10)
        corps.columnconfigure(0, weight=3)
        corps.columnconfigure(1, weight=2)
        corps.rowconfigure(1, weight=1)

        # 1. Rapports
        carte = ttk.Frame(corps, style="Carte.TFrame", padding=12)
        carte.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ttk.Label(carte, text="1. Rapports à analyser (.docx ou .pdf, y compris scannés)", style="Section.TLabel").pack(anchor="w")
        ttk.Label(carte, text="Double-cliquez sur un rapport pour saisir sa date de réception à la DCB ou, si besoin, "
                              "sa période (ex. « 3e trimestre 2026 »).", style="Aide.TLabel").pack(anchor="w", pady=(0, 4))
        cadre = ttk.Frame(carte, style="Carte.TFrame")
        cadre.pack(fill="both", expand=True)
        self.table = ttk.Treeview(cadre, columns=("fichier", "reception", "periode"), show="headings", height=7)
        for col, titre, largeur in (("fichier", "Rapport", 330), ("reception", "Date de réception", 120),
                                    ("periode", "Période (si non détectée)", 170)):
            self.table.heading(col, text=titre)
            self.table.column(col, width=largeur, anchor="w")
        barre = ttk.Scrollbar(cadre, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=barre.set)
        self.table.pack(side="left", fill="both", expand=True)
        barre.pack(side="left", fill="y")
        self.table.bind("<Double-1>", lambda e: self.modifier_rapport())
        boutons = ttk.Frame(carte, style="Carte.TFrame")
        boutons.pack(anchor="w", pady=(6, 0))
        ttk.Button(boutons, text="Ajouter des rapports…", command=self.ajouter_rapports).pack(side="left")
        ttk.Button(boutons, text="Ajouter un dossier…", command=self.ajouter_dossier).pack(side="left", padx=4)
        ttk.Button(boutons, text="Date de réception…", command=self.modifier_rapport).pack(side="left")
        ttk.Button(boutons, text="Retirer", command=self.retirer_rapports).pack(side="left", padx=4)

        # 2. Références
        ref = ttk.Frame(corps, style="Carte.TFrame", padding=12)
        ref.grid(row=0, column=1, sticky="nsew")
        ttk.Label(ref, text="2. Documents de référence (facultatifs)", style="Section.TLabel").pack(anchor="w")
        self.decrets = ListeFichiers(ref, "Décrets de création et d'organisation", EXT_DECRETS,
                                     "Chaque rapport est rapproché du décret de son EPN (dénomination ou sigle).", 3)
        self.decrets.configure(style="Carte.TFrame")
        self.decrets.pack(fill="both", expand=True, pady=(4, 8))
        self.situations = ListeFichiers(ref, "Situations d'exécution (SIGOBE, Excel, CSV, PDF)", EXT_SITUATIONS,
                                        "À la date de fin de période. Les états recettes et dépenses d'un même EPN "
                                        "sont réunis ; un fichier consolidé est filtré par EPN.", 3)
        self.situations.configure(style="Carte.TFrame")
        self.situations.pack(fill="both", expand=True)

        # 3. Paramètres + lancement
        bas = ttk.Frame(corps, style="Carte.TFrame", padding=12)
        bas.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        ligne = ttk.Frame(bas, style="Carte.TFrame")
        ligne.pack(fill="x")
        ttk.Label(ligne, text="3. Chargé d'Études :", style="Section.TLabel").pack(side="left")
        self.charge = tk.StringVar()
        ttk.Entry(ligne, textvariable=self.charge, width=26).pack(side="left", padx=(6, 18))
        ttk.Label(ligne, text="Dossier des résultats :", style="Carte.TLabel").pack(side="left")
        self.sortie = tk.StringVar(value=str(dossier_sortie_defaut()))
        ttk.Button(ligne, text="Parcourir…", command=self.choisir_sortie).pack(side="right")
        ttk.Entry(ligne, textvariable=self.sortie).pack(side="left", fill="x", expand=True, padx=6)

        action = ttk.Frame(bas, style="Carte.TFrame")
        action.pack(fill="x", pady=(10, 0))
        self.bouton = ttk.Button(action, text="▶  Lancer l'analyse", style="Lancer.TButton", command=self.lancer)
        self.bouton.pack(side="left")
        droite = ttk.Frame(action, style="Carte.TFrame")
        droite.pack(side="left", fill="x", expand=True, padx=(14, 0))
        self.progression = ttk.Progressbar(droite, mode="determinate", style="Bleu.Horizontal.TProgressbar")
        self.progression.pack(fill="x")
        self.etat = tk.StringVar(value="Ajoutez un ou plusieurs rapports, puis lancez l'analyse.")
        ttk.Label(droite, textvariable=self.etat, style="Carte.TLabel").pack(anchor="w", pady=(3, 0))

        ttk.Label(bas, text="Résultats (double-cliquez pour ouvrir le fichier d'analyse)", style="Sous.TLabel").pack(anchor="w", pady=(8, 2))
        cadre = ttk.Frame(bas, style="Carte.TFrame")
        cadre.pack(fill="both", expand=True)
        cols = (("epn", "EPN", 250), ("periode", "Période", 180), ("forme", "Forme", 70), ("fond", "Fond", 70),
                ("maj", "Anomalies majeures", 120), ("suite", "Suite à donner", 330))
        self.res_table = ttk.Treeview(cadre, columns=[c[0] for c in cols], show="headings", height=6)
        for col, titre, largeur in cols:
            self.res_table.heading(col, text=titre)
            self.res_table.column(col, width=largeur, anchor="w" if col in ("epn", "periode", "suite") else "center")
        self.res_table.tag_configure("retour", foreground="#9C0006")
        self.res_table.tag_configure("ok", foreground="#006100")
        self.res_table.tag_configure("erreur", foreground="#9C0006", background="#FFC7CE")
        barre = ttk.Scrollbar(cadre, orient="vertical", command=self.res_table.yview)
        self.res_table.configure(yscrollcommand=barre.set)
        self.res_table.pack(side="left", fill="both", expand=True)
        barre.pack(side="left", fill="y")
        self.res_table.bind("<Double-1>", lambda e: self.ouvrir_resultat())
        boutons = ttk.Frame(bas, style="Carte.TFrame")
        boutons.pack(anchor="w", pady=(6, 0))
        ttk.Button(boutons, text="Ouvrir le fichier d'analyse", command=self.ouvrir_resultat).pack(side="left")
        self.bouton_tdb = ttk.Button(boutons, text="Ouvrir le tableau de bord", command=self.ouvrir_tableau_bord,
                                     state="disabled")
        self.bouton_tdb.pack(side="left", padx=4)
        ttk.Button(boutons, text="Ouvrir le dossier des résultats", command=self.ouvrir_dossier_sortie).pack(side="left")

    # ------------------------------------------------------------------ rapports
    def _ajouter(self, chemins):
        deja = {r["chemin"] for r in self.rapports}
        for c in chemins:
            p = Path(c)
            if p.suffix.lower() not in EXT_RAPPORTS or p.name.startswith("~$") or p in deja:
                continue
            r = {"chemin": p, "reception": None, "periode": ""}
            self.rapports.append(r)
            self.table.insert("", "end", iid=str(len(self.rapports) - 1), values=(p.name, "à saisir", ""))
        self._maj_etat()

    def ajouter_rapports(self):
        self._ajouter(filedialog.askopenfilenames(title="Choisir les rapports des CB",
                                                  filetypes=[("Rapports", "*.docx *.pdf"), ("Tous les fichiers", "*.*")]))

    def ajouter_dossier(self):
        d = filedialog.askdirectory(title="Choisir un dossier de rapports")
        if d:
            self._ajouter(sorted(Path(d).iterdir()))

    def retirer_rapports(self):
        garder = [r for i, r in enumerate(self.rapports) if str(i) not in self.table.selection()]
        self.rapports = garder
        self.table.delete(*self.table.get_children())
        for i, r in enumerate(self.rapports):
            self.table.insert("", "end", iid=str(i), values=(r["chemin"].name, self._date_txt(r["reception"]), r["periode"]))
        self._maj_etat()

    @staticmethod
    def _date_txt(d):
        return d.strftime("%d/%m/%Y") if d else "à saisir"

    def modifier_rapport(self):
        sel = self.table.selection()
        if not sel:
            messagebox.showinfo(TITRE, "Sélectionnez d'abord un rapport dans la liste.")
            return
        r = self.rapports[int(sel[0])]
        fen = tk.Toplevel(self)
        fen.title("Informations de réception")
        fen.transient(self)
        fen.resizable(False, False)
        cadre = ttk.Frame(fen, padding=14)
        cadre.pack(fill="both")
        ttk.Label(cadre, text=r["chemin"].name, font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(cadre, text="Date de réception à la DCB (jj/mm/aaaa) :").grid(row=1, column=0, sticky="w", pady=(10, 2))
        v_date = tk.StringVar(value=r["reception"].strftime("%d/%m/%Y") if r["reception"] else "")
        e = ttk.Entry(cadre, textvariable=v_date, width=14)
        e.grid(row=1, column=1, sticky="w", pady=(10, 2), padx=6)
        ttk.Button(cadre, text="Aujourd'hui", command=lambda: v_date.set(date.today().strftime("%d/%m/%Y"))).grid(
            row=1, column=2, padx=2, pady=(10, 2))
        ttk.Label(cadre, text="Période (seulement si elle n'est pas détectée) :").grid(row=2, column=0, sticky="w")
        v_per = tk.StringVar(value=r["periode"])
        ttk.Combobox(cadre, textvariable=v_per, width=26, values=[
            "", f"1er trimestre {date.today().year}", f"1er semestre {date.today().year}",
            f"3e trimestre {date.today().year}", f"4e trimestre {date.today().year}",
            f"exercice {date.today().year - 1}"]).grid(row=2, column=1, columnspan=2, sticky="w", padx=6)

        def valider():
            texte = v_date.get().strip()
            d = lire_date(texte) if texte else None
            if texte and not d:
                messagebox.showerror(TITRE, "Date non reconnue. Format attendu : jj/mm/aaaa.", parent=fen)
                return
            r["reception"], r["periode"] = d, v_per.get().strip()
            self.table.item(sel[0], values=(r["chemin"].name, self._date_txt(d), r["periode"]))
            fen.destroy()

        b = ttk.Frame(cadre)
        b.grid(row=3, column=0, columnspan=3, sticky="e", pady=(14, 0))
        ttk.Button(b, text="Annuler", command=fen.destroy).pack(side="right")
        ttk.Button(b, text="Valider", command=valider).pack(side="right", padx=6)
        fen.bind("<Return>", lambda ev: valider())
        e.focus_set()
        fen.grab_set()

    def choisir_sortie(self):
        d = filedialog.askdirectory(title="Dossier où enregistrer les fichiers d'analyse")
        if d:
            self.sortie.set(d)

    def _maj_etat(self):
        n = len(self.rapports)
        self.etat.set("Ajoutez un ou plusieurs rapports, puis lancez l'analyse." if not n else
                      f"{n} rapport(s) à analyser. Pensez à saisir les dates de réception (double-clic).")

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
        self.en_cours = True
        self.bouton.configure(state="disabled")
        self.res_table.delete(*self.res_table.get_children())
        self.resultats, self.tableau_bord = [], None
        self.bouton_tdb.configure(state="disabled")
        self.progression.configure(maximum=len(self.rapports) * 100, value=0)
        travail = [dict(r) for r in self.rapports]
        threading.Thread(target=self._analyser, args=(travail, sortie, self.charge.get().strip(),
                                                      list(self.decrets.fichiers), list(self.situations.fichiers)),
                         daemon=True).start()
        self.after(100, self._suivre)

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
            nom = r["chemin"].name
            lecture.RAPPEL_PROGRESSION = lambda page, total, k=k, nom=nom: f.put(
                ("progres", k * 100 + int(80 * page / max(total, 1)), f"{nom} : lecture OCR, page {page}/{total}…"))
            f.put(("progres", k * 100, f"Analyse de {nom} ({k + 1}/{len(rapports)})…"))
            try:
                infos = InfosRapport(charge_etudes=charge, date_reception=r["reception"], periode=r["periode"] or None)
                res = analyser(r["chemin"], infos, parametres, None, decrets=liste_decrets, situations=liste_situations,
                               reference_unique=len(rapports) == 1)
                fichier = remplir_modele(res, sortie / f"Analyse_{r['chemin'].stem}.xlsx")
                resultats.append((res, fichier))
                f.put(("resultat", res, fichier))
            except PermissionError:
                f.put(("erreur", nom, "Fichier d'analyse ouvert dans Excel : fermez-le puis relancez."))
            except Exception as exc:
                f.put(("erreur", nom, f"{exc}"))
                traceback.print_exc()
        lecture.RAPPEL_PROGRESSION = None
        tdb = None
        if len(resultats) > 1:
            try:
                tdb = tableau_de_bord(resultats, sortie / "Tableau_de_bord_rapports_CB.xlsx")
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
                    self.etat.set(f"Analyse terminée : {ok}/{total} rapport(s) traité(s). Fichiers enregistrés dans {sortie}.")
                    return
        except queue.Empty:
            pass
        self.after(150, self._suivre)

    def _terminer(self):
        self.en_cours = False
        self.bouton.configure(state="normal")

    def _afficher_resultat(self, res, fichier):
        self.resultats.append((res, fichier))
        retour = "retourné" in suite_a_donner(res)
        suite = "Retour au CB pour correction" if retour else "Rapport exploitable"
        fond = f"{res.score_fond:.0f} %" if res.score_fond is not None else "—"
        self.res_table.insert("", "end", iid=f"r{len(self.resultats) - 1}",
                              values=(res.infos.epn, res.periode.libelle, f"{res.score_forme:.0f} %", fond,
                                      res.nb_anomalies_majeures, suite), tags=("retour" if retour else "ok",))
        for a in res.doc.avertissements:
            self.res_table.insert("", "end", values=("", "", "", "", "", f"⚠ {a}"))

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
        if afficher:
            if ok:
                messagebox.showinfo(TITRE, "La lecture des documents scannés (OCR, langue française) est opérationnelle.")
            else:
                messagebox.showwarning(TITRE, "Les documents scannés ne pourront pas être lus :\n" + message
                                       + "\n\nLes rapports Word et PDF « texte » restent analysés normalement.")
        elif not ok:
            self.etat.set("Attention : lecture des documents scannés indisponible (menu Aide > Lecture des documents "
                          "scannés). Les rapports Word et PDF « texte » restent analysés.")

    def a_propos(self):
        messagebox.showinfo(TITRE, f"{TITRE}\nVersion {__version__}\n\n"
                                   "Analyse des rapports des CB au regard du canevas de la DCB (note n°0580/MBPE/DGBF/DCB "
                                   "du 26 juillet 2023), du décret de création de l'EPN et de la situation d'exécution.\n\n"
                                   f"Paramètres : {PARAMETRES_DEFAUT.parent}")


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
