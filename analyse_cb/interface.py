"""Application de bureau : analyse des rapports des Contrôleurs Budgétaires.

Lancement : python -m analyse_cb.interface  (ou AnalyseRapportsCB.exe dans la version Windows)

L'interface (tableau de bord, analyse des rapports, alertes…) est servie par un petit serveur local (127.0.0.1)
et s'affiche :
- sous Windows, dans une fenêtre de l'application (moteur Microsoft Edge WebView2, présent sur Windows 10 et 11) ;
- à défaut, dans le navigateur par défaut, une petite fenêtre permettant alors de la rouvrir ou de quitter.

Options :
  --ligne-de-commande …   analyse en ligne de commande (mêmes options que « python -m analyse_cb »)
  --test-serveur [fichier] vérifie le serveur et l'interface, écrit le résultat dans « fichier » (code 0 si tout va bien)
  --test-fenetre [fichier] ouvre la fenêtre, vérifie que l'interface s'y affiche, puis la referme
  --navigateur             force l'affichage dans le navigateur par défaut
"""
from __future__ import annotations

import json
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from . import __version__
from .ressources import dossier_utilisateur

TITRE = "Analyse des rapports des Contrôleurs Budgétaires"
CLE_WEBVIEW2 = r"SOFTWARE\{}Microsoft\EdgeUpdate\Clients\{{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}}"


def webview2_installe() -> bool:
    """Indique si le moteur Microsoft Edge WebView2 est installé (Windows uniquement)."""
    if not sys.platform.startswith("win"):
        return False
    import winreg
    for racine, sous in ((winreg.HKEY_LOCAL_MACHINE, "WOW6432Node\\"), (winreg.HKEY_LOCAL_MACHINE, ""),
                         (winreg.HKEY_CURRENT_USER, "")):
        try:
            with winreg.OpenKey(racine, CLE_WEBVIEW2.format(sous)) as cle:
                version, _ = winreg.QueryValueEx(cle, "pv")
                if version and version != "0.0.0.0":
                    return True
        except OSError:
            continue
    return False


def demarrer_serveur():
    from .serveur import Serveur, nettoyer_depot
    dossier_utilisateur()
    try:
        nettoyer_depot()
    except Exception:
        pass
    return Serveur().demarrer()


# ------------------------------------------------------------------ fenêtre de l'application (WebView2)
def fenetre_native(serveur, verification=None) -> bool:
    """Affiche l'interface dans une fenêtre de l'application. Renvoie False si c'est impossible sur ce poste."""
    if not webview2_installe():
        return False
    try:
        import webview
    except Exception:
        return False
    try:
        fenetre = webview.create_window(TITRE, serveur.url, width=1440, height=900, min_size=(1100, 700),
                                        background_color="#F3F6FA", text_select=True)

        def fermer_sur_demande():
            serveur.app.quitter.wait()
            try:
                fenetre.destroy()
            except Exception:
                pass
        threading.Thread(target=fermer_sur_demande, daemon=True).start()

        def avant_fermeture(window):  # renvoyer False annule la fermeture de la fenêtre
            travail = serveur.app.travail
            if serveur.app.quitter.is_set() or not (travail and travail.get("en_cours")):
                return True
            return bool(window.create_confirmation_dialog(
                TITRE, "Une analyse est en cours. Quitter quand même l'application ?"))
        try:
            fenetre.events.closing += avant_fermeture
        except Exception:
            pass
        if verification:
            webview.start(verification, (fenetre,), gui="edgechromium")
        else:
            webview.start(gui="edgechromium", private_mode=False,
                          storage_path=str(dossier_utilisateur() / "fenetre"))
        return True
    except Exception:
        traceback.print_exc()
        return False


# ------------------------------------------------------------------ repli : navigateur par défaut
def fenetre_navigateur(serveur) -> None:
    """Ouvre l'interface dans le navigateur ; une petite fenêtre permet de la rouvrir ou de quitter."""
    webbrowser.open(serveur.url)
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        tk = None
    if tk is None:
        try:
            serveur.app.quitter.wait()
        except KeyboardInterrupt:
            pass
        return
    if sys.platform.startswith("win"):
        try:  # affichage net sur les écrans à haute résolution
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    try:
        racine = tk.Tk()
    except Exception:  # pas d'affichage graphique
        try:
            serveur.app.quitter.wait()
        except KeyboardInterrupt:
            pass
        return
    racine.title(TITRE)
    racine.resizable(False, False)
    try:
        from .ressources import dossier_ressources
        racine.iconphoto(True, tk.PhotoImage(file=str(dossier_ressources() / "packaging" / "icone.png")))
    except Exception:
        pass
    cadre = ttk.Frame(racine, padding=18)
    cadre.pack(fill="both", expand=True)
    ttk.Label(cadre, text=TITRE, font=("Segoe UI", 12, "bold")).pack(anchor="w")
    ttk.Label(cadre, text="L'application est ouverte dans votre navigateur internet.\n"
                          "Gardez cette fenêtre ouverte pendant son utilisation.",
              justify="left").pack(anchor="w", pady=(6, 12))
    boutons = ttk.Frame(cadre)
    boutons.pack(fill="x")

    def quitter():
        serveur.app.quitter.set()
        racine.destroy()
    ttk.Button(boutons, text="Rouvrir l'application", command=lambda: webbrowser.open(serveur.url)).pack(side="left")
    ttk.Button(boutons, text="Quitter", command=quitter).pack(side="right")
    racine.protocol("WM_DELETE_WINDOW", quitter)

    def surveiller():  # « Quitter l'application » depuis l'interface
        if serveur.app.quitter.is_set():
            racine.destroy()
        else:
            racine.after(500, surveiller)
    racine.after(500, surveiller)
    racine.mainloop()


# ------------------------------------------------------------------ vérifications (intégration continue)
def _lire(url: str, jeton: str | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"X-Jeton": jeton} if jeton else {})
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 - adresse locale
        return r.status, r.read()


def test_serveur() -> list[str]:
    """Démarre le serveur, interroge l'interface et l'API ; renvoie la liste des problèmes constatés."""
    problemes = []
    serveur = demarrer_serveur()
    base = f"http://127.0.0.1:{serveur.port}"
    try:
        for chemin, attendu in (("/", b'id="contenu"'), ("/static/app.js", b"function router"),
                                ("/static/app.css", b".kpis")):
            statut, corps = _lire(base + chemin)
            if statut != 200 or attendu not in corps:
                problemes.append(f"{chemin} : réponse inattendue ({statut}).")
        for chemin in ("/api/etat", "/api/tableau", "/api/alertes", "/api/rapports", "/api/parametres"):
            statut, corps = _lire(base + chemin, serveur.app.jeton)
            donnees = json.loads(corps)
            if statut != 200 or "erreur" in donnees:
                problemes.append(f"{chemin} : {donnees.get('erreur', statut)}")
        try:
            _lire(base + "/api/etat")
            problemes.append("/api/etat accessible sans jeton.")
        except urllib.error.HTTPError as exc:
            if exc.code != 403:
                problemes.append(f"/api/etat sans jeton : code {exc.code}.")
    except Exception as exc:
        problemes.append(f"Serveur injoignable : {exc}")
    finally:
        serveur.arreter()
    return problemes


def test_fenetre() -> list[str]:
    """Ouvre la fenêtre de l'application et vérifie que l'interface s'y affiche."""
    if not webview2_installe():
        return ["Moteur Microsoft Edge WebView2 absent : l'interface s'ouvrirait dans le navigateur."]
    serveur = demarrer_serveur()
    resultat = {"elements": 0, "erreur": ""}

    def verifier(fenetre):
        try:
            for _ in range(80):
                time.sleep(0.5)
                try:
                    n = fenetre.evaluate_js("document.querySelectorAll('.nav a').length")
                    if n and int(n) >= 8:
                        resultat["elements"] = int(n)
                        break
                except Exception as exc:
                    resultat["erreur"] = str(exc)
        finally:
            fenetre.destroy()
    ok = fenetre_native(serveur, verifier)
    serveur.arreter()
    if not ok:
        return ["La fenêtre de l'application n'a pas pu être ouverte."]
    if resultat["elements"] < 8:
        return [f"Interface non affichée dans la fenêtre ({resultat['erreur'] or 'menu absent'})."]
    return []


def _rendre_compte(problemes: list[str], fichier: str | None) -> int:
    texte = "OK" if not problemes else "\n".join(problemes)
    if fichier:
        Path(fichier).write_text(texte, encoding="utf-8")
    print(texte)
    return 0 if not problemes else 1


# ------------------------------------------------------------------ point d'entrée
def main() -> None:
    args = sys.argv[1:]
    # Mode ligne de commande intégré à l'application : AnalyseRapportsCB.exe --ligne-de-commande rapport.pdf …
    if args and args[0] == "--ligne-de-commande":
        from .__main__ import main as cli
        sys.exit(cli(args[1:]))
    if args and args[0] in ("--test-serveur", "--test-fenetre"):
        fichier = args[1] if len(args) > 1 else None
        try:
            problemes = test_serveur() if args[0] == "--test-serveur" else test_fenetre()
        except Exception as exc:
            problemes = [f"Erreur : {exc}"]
        sys.exit(_rendre_compte(problemes, fichier))
    if args and args[0] in ("--version", "-V"):
        print(__version__)
        return
    serveur = demarrer_serveur()
    try:
        if "--navigateur" in args or not fenetre_native(serveur):
            fenetre_navigateur(serveur)
    finally:
        serveur.app.quitter.set()
        serveur.arreter()


if __name__ == "__main__":
    main()
