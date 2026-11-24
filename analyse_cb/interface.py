"""Application de bureau : analyse des rapports des Contrôleurs Budgétaires.

Lancement : python -m analyse_cb.interface  (ou AnalyseRapportsCB.exe dans la version Windows)

L'interface (tableau de bord, analyse des rapports, alertes…) est servie par un petit serveur local (127.0.0.1)
et s'affiche :
- sous Windows, dans une fenêtre de l'application (moteur Microsoft Edge WebView2, présent sur Windows 10 et 11) ;
- à défaut, dans le navigateur par défaut, une petite fenêtre permettant alors de la rouvrir ou de quitter.
Si l'interface ne s'est pas affichée dans la fenêtre au bout de quelques secondes, l'application bascule d'elle-même
sur le navigateur. Le déroulement est consigné dans le journal %APPDATA%\\AnalyseRapportsCB\\journal.txt.

Options :
  --ligne-de-commande …    analyse en ligne de commande (mêmes options que « python -m analyse_cb »)
  --navigateur             affiche l'interface dans le navigateur par défaut
  --test-serveur [fichier] vérifie le serveur et l'interface, écrit le résultat dans « fichier » (code 0 si tout va bien)
  --test-fenetre [fichier] ouvre la fenêtre comme au lancement normal, vérifie l'affichage de l'interface, la referme
  --test-repli [fichier]   vérifie la bascule automatique vers le navigateur quand la fenêtre n'affiche rien
"""
from __future__ import annotations

import json
import logging
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from . import __version__
from .ressources import dossier_utilisateur

TITRE = "Analyse des rapports des Contrôleurs Budgétaires"
CLE_WEBVIEW2 = r"SOFTWARE\{}Microsoft\EdgeUpdate\Clients\{{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}}"
# Paramètres de webview.start(), identiques au lancement normal et lors des vérifications : mode privé par défaut
# (dossier de données temporaire). Ne pas passer « storage_path » : avec pywebview 5.4, cette option emprunte une
# autre initialisation de WebView2 qui peut échouer sans erreur visible (fenêtre restée vide).
OPTIONS_FENETRE = {"gui": "edgechromium"}
DELAI_AFFICHAGE = 25  # secondes accordées à l'interface pour s'afficher dans la fenêtre avant la bascule
JOURNAL = logging.getLogger("analyse_cb")
_fenetre_active = None


def configurer_journal() -> Path | None:
    """Journal de l'application (profil de l'utilisateur) : démarrage, affichage, erreurs."""
    try:
        chemin = dossier_utilisateur() / "journal.txt"
        if chemin.exists() and chemin.stat().st_size > 1_000_000:
            chemin.replace(chemin.with_name("journal.ancien.txt"))
        gestionnaire = logging.FileHandler(chemin, encoding="utf-8")
        gestionnaire.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s %(name)s : %(message)s",
                                                    "%d/%m/%Y %H:%M:%S"))
        racine = logging.getLogger()
        racine.addHandler(gestionnaire)
        racine.setLevel(logging.INFO)

        def erreur_fil(args):
            JOURNAL.error("Erreur dans un fil d'exécution", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        threading.excepthook = erreur_fil
        return chemin
    except Exception:
        return None


def version_webview2() -> str:
    """Version du moteur Microsoft Edge WebView2 installé (Windows uniquement), chaîne vide s'il est absent."""
    if not sys.platform.startswith("win"):
        return ""
    import winreg
    for racine, sous in ((winreg.HKEY_LOCAL_MACHINE, "WOW6432Node\\"), (winreg.HKEY_LOCAL_MACHINE, ""),
                         (winreg.HKEY_CURRENT_USER, "")):
        try:
            with winreg.OpenKey(racine, CLE_WEBVIEW2.format(sous)) as cle:
                version, _ = winreg.QueryValueEx(cle, "pv")
                if version and version != "0.0.0.0":
                    return str(version)
        except OSError:
            continue
    return ""


def webview2_installe() -> bool:
    return bool(version_webview2())


def demarrer_serveur():
    from .serveur import Serveur, nettoyer_depot
    dossier_utilisateur()
    try:
        nettoyer_depot()
    except Exception:
        JOURNAL.exception("Nettoyage des documents déposés impossible.")
    serveur = Serveur().demarrer()
    JOURNAL.info("Serveur local démarré sur le port %s.", serveur.port)
    return serveur


# ------------------------------------------------------------------ fenêtre de l'application (WebView2)
def fenetre_native(serveur, url: str | None = None, delai: float = DELAI_AFFICHAGE) -> str:
    """Affiche l'interface dans une fenêtre de l'application.

    Renvoie « ok » (fenêtre fermée normalement), « repli » (l'interface ne s'est pas affichée à temps : la fenêtre a
    été refermée) ou « indisponible » (fenêtre impossible sur ce poste)."""
    global _fenetre_active
    version = version_webview2()
    if not version:
        JOURNAL.warning("Moteur Microsoft Edge WebView2 introuvable : affichage dans le navigateur.")
        return "indisponible"
    try:
        import webview
    except Exception:
        JOURNAL.exception("Module d'affichage (pywebview) indisponible.")
        return "indisponible"
    JOURNAL.info("Ouverture de la fenêtre (WebView2 %s, pywebview %s).", version, getattr(webview, "__version__", "?"))
    issue = {"repli": False}
    try:
        fenetre = webview.create_window(TITRE, url or serveur.url, width=1440, height=900, min_size=(1100, 700),
                                        background_color="#F3F6FA", text_select=True)
        _fenetre_active = fenetre

        def fermer_sur_demande():  # « Quitter l'application » depuis l'interface
            serveur.app.quitter.wait()
            try:
                fenetre.destroy()
            except Exception:
                pass
        threading.Thread(target=fermer_sur_demande, daemon=True).start()

        def surveiller_affichage():  # bascule sur le navigateur si l'interface ne s'affiche pas
            if serveur.app.interface_chargee.wait(delai):
                JOURNAL.info("Interface affichée dans la fenêtre de l'application.")
                return
            if serveur.app.quitter.is_set():
                return
            JOURNAL.error("L'interface ne s'est pas affichée dans la fenêtre au bout de %s s : "
                          "bascule sur le navigateur.", delai)
            issue["repli"] = True
            try:
                fenetre.destroy()
            except Exception:
                JOURNAL.exception("Fermeture de la fenêtre impossible.")
        threading.Thread(target=surveiller_affichage, daemon=True).start()

        def avant_fermeture(window):  # renvoyer False annule la fermeture de la fenêtre
            travail = serveur.app.travail
            if issue["repli"] or serveur.app.quitter.is_set() or not (travail and travail.get("en_cours")):
                return True
            return bool(window.create_confirmation_dialog(
                TITRE, "Une analyse est en cours. Quitter quand même l'application ?"))
        try:
            fenetre.events.closing += avant_fermeture
        except Exception:
            JOURNAL.exception("Confirmation de fermeture indisponible.")
        webview.start(**OPTIONS_FENETRE)
    except Exception:
        JOURNAL.exception("Échec de la fenêtre de l'application.")
        return "repli" if issue["repli"] else "indisponible"
    finally:
        _fenetre_active = None
    JOURNAL.info("Fenêtre de l'application fermée%s.", " (bascule sur le navigateur)" if issue["repli"] else "")
    return "repli" if issue["repli"] else "ok"


# ------------------------------------------------------------------ repli : navigateur par défaut
def fenetre_navigateur(serveur, repli: bool = False) -> None:
    """Ouvre l'interface dans le navigateur ; une petite fenêtre permet de la rouvrir ou de quitter."""
    JOURNAL.info("Affichage de l'interface dans le navigateur par défaut.")
    try:
        webbrowser.open(serveur.url)
    except Exception:
        JOURNAL.exception("Ouverture du navigateur impossible.")
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
    message = ("L'application est ouverte dans votre navigateur internet.\n"
               "Gardez cette fenêtre ouverte pendant son utilisation.")
    if repli:
        message = ("L'affichage dans la fenêtre de l'application n'a pas fonctionné sur ce poste :\n"
                   "l'application est ouverte dans votre navigateur internet.\n"
                   "Gardez cette fenêtre ouverte pendant son utilisation.\n\n"
                   f"Détail technique : {dossier_utilisateur() / 'journal.txt'}")
    ttk.Label(cadre, text=message, justify="left").pack(anchor="w", pady=(6, 12))
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
    """Ouvre la fenêtre exactement comme au lancement normal, vérifie que l'interface s'y affiche et appelle le
    serveur, puis quitte comme le bouton « Quitter l'application »."""
    if not webview2_installe():
        return ["Moteur Microsoft Edge WebView2 absent : l'interface s'ouvrirait dans le navigateur."]
    serveur = demarrer_serveur()
    resultat = {"menu": 0, "erreur": ""}

    def verifier():
        try:
            if not serveur.app.interface_chargee.wait(DELAI_AFFICHAGE - 5):
                resultat["erreur"] = "l'interface n'a pas interrogé le serveur"
                return
            for _ in range(40):
                time.sleep(0.5)
                try:
                    n = _fenetre_active.evaluate_js("document.querySelectorAll('.nav a').length")
                    if n and int(n) >= 8:
                        resultat["menu"] = int(n)
                        return
                except Exception as exc:
                    resultat["erreur"] = str(exc)
        finally:
            serveur.app.quitter.set()
    threading.Thread(target=verifier, daemon=True).start()
    issue = fenetre_native(serveur)
    serveur.arreter()
    if issue != "ok":
        return [f"Fenêtre de l'application : {issue} ({resultat['erreur'] or 'sans détail'})."]
    if resultat["menu"] < 8:
        return [f"Interface non affichée dans la fenêtre ({resultat['erreur'] or 'menu absent'})."]
    return []


def test_repli() -> list[str]:
    """Simule une fenêtre qui n'affiche pas l'interface : l'application doit la refermer d'elle-même (bascule)."""
    if not webview2_installe():
        return ["Moteur Microsoft Edge WebView2 absent."]
    serveur = demarrer_serveur()
    debut = time.time()
    issue = fenetre_native(serveur, url=f"http://127.0.0.1:{serveur.port}/static/app.css", delai=8)
    serveur.arreter()
    if issue != "repli":
        return [f"Bascule attendue, obtenu « {issue} »."]
    if time.time() - debut > 60:
        return ["Bascule trop lente."]
    return []


def _rendre_compte(problemes: list[str], fichier: str | None) -> int:
    texte = "OK" if not problemes else "\n".join(problemes)
    if fichier:
        Path(fichier).write_text(texte, encoding="utf-8")
    print(texte)
    return 0 if not problemes else 1


# ------------------------------------------------------------------ point d'entrée
TESTS = {"--test-serveur": test_serveur, "--test-fenetre": test_fenetre, "--test-repli": test_repli}


def main() -> None:
    args = sys.argv[1:]
    # Mode ligne de commande intégré à l'application : AnalyseRapportsCB.exe --ligne-de-commande rapport.pdf …
    if args and args[0] == "--ligne-de-commande":
        from .__main__ import main as cli
        sys.exit(cli(args[1:]))
    if args and args[0] in ("--version", "-V"):
        print(__version__)
        return
    configurer_journal()
    JOURNAL.info("Démarrage de l'application %s (%s).", __version__, " ".join(args) or "lancement normal")
    if args and args[0] in TESTS:
        fichier = args[1] if len(args) > 1 else None
        try:
            problemes = TESTS[args[0]]()
        except Exception as exc:
            JOURNAL.exception("Vérification %s", args[0])
            problemes = [f"Erreur : {exc}"]
        JOURNAL.info("Vérification %s : %s", args[0], "OK" if not problemes else " ; ".join(problemes))
        sys.exit(_rendre_compte(problemes, fichier))
    serveur = demarrer_serveur()
    try:
        issue = "navigateur" if "--navigateur" in args else fenetre_native(serveur)
        if issue != "ok" and not serveur.app.quitter.is_set():
            fenetre_navigateur(serveur, repli=issue == "repli")
    except Exception:
        JOURNAL.exception("Erreur de l'application.")
        raise
    finally:
        serveur.app.quitter.set()
        serveur.arreter()
        JOURNAL.info("Fin de l'application.")


if __name__ == "__main__":
    main()
