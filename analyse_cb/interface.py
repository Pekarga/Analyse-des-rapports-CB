"""Application de bureau : analyse des rapports des Contrôleurs Budgétaires.

Lancement : python -m analyse_cb.interface  (ou AnalyseRapportsCB.exe dans la version Windows)

L'interface (tableau de bord, analyse des rapports, alertes…) est servie par un petit serveur local (127.0.0.1,
jeton propre à chaque lancement). Elle s'affiche dans une fenêtre de Microsoft Edge en mode « application » (sans
barre d'adresse ni onglets, avec un profil propre à l'application), à défaut de Google Chrome, à défaut du navigateur
par défaut. Ce sont les navigateurs déjà utilisés sur le poste : aucun composant d'affichage n'est embarqué.

L'application reste ouverte tant qu'une fenêtre de l'interface l'est : chaque fenêtre signale régulièrement sa
présence et prévient de sa fermeture. Une seconde ouverture de l'application ouvre une nouvelle fenêtre sur la même
instance. Le déroulement est consigné dans %APPDATA%\\AnalyseRapportsCB\\journal.txt.

Options :
  --ligne-de-commande …       analyse en ligne de commande (mêmes options que « python -m analyse_cb »)
  --navigateur                affiche l'interface dans le navigateur par défaut
  --test-serveur [fichier]    vérifie le serveur et l'interface ; résultat écrit dans « fichier » (code 0 si tout va bien)
  --test-affichage [fichier]  ouvre la fenêtre comme au lancement normal, vérifie l'affichage, puis quitte
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from . import __version__
from .ressources import dossier_local, dossier_utilisateur

TITRE = "Analyse des rapports des Contrôleurs Budgétaires"
DELAI_PREMIER_AFFICHAGE = 45  # secondes pour que l'interface s'affiche, avant d'essayer le navigateur par défaut
DELAI_PRESENCE = 180          # une fenêtre sans signe de vie depuis ce délai est tenue pour fermée
DELAI_FERMETURE = 5           # délai de grâce après une fermeture (rechargement de la page)
DELAI_ABANDON = 1800          # sans aucun signe de vie de l'interface pendant ce délai, l'application s'arrête
JOURNAL = logging.getLogger("analyse_cb")


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


# ------------------------------------------------------------------ navigateurs
def _chemin_app_paths(exe: str) -> str:
    """Chemin d'un programme déclaré dans le registre Windows (App Paths)."""
    import winreg
    for racine in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(racine, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}") as cle:
                valeur, _ = winreg.QueryValueEx(cle, None)
                if valeur and Path(valeur.strip('"')).is_file():
                    return valeur.strip('"')
        except OSError:
            continue
    return ""


def navigateurs() -> list[tuple[str, str]]:
    """Navigateurs capables d'afficher l'interface en mode « application » : (nom, exécutable), par préférence.
    La variable ANALYSE_CB_NAVIGATEUR impose un exécutable (dépannage, vérifications)."""
    impose = os.environ.get("ANALYSE_CB_NAVIGATEUR")
    if impose:
        return [("Navigateur imposé", impose)]
    out: list[tuple[str, str]] = []
    if sys.platform.startswith("win"):
        programmes = [os.environ.get(v, "") for v in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
        for nom, exe, sous in (("Microsoft Edge", "msedge.exe", r"Microsoft\Edge\Application"),
                               ("Google Chrome", "chrome.exe", r"Google\Chrome\Application")):
            chemin = _chemin_app_paths(exe) or next(
                (str(Path(p) / sous / exe) for p in programmes if p and (Path(p) / sous / exe).is_file()), "")
            if chemin:
                out.append((nom, chemin))
    else:
        for nom, commande in (("Microsoft Edge", "microsoft-edge"), ("Google Chrome", "google-chrome"),
                              ("Chromium", "chromium"), ("Chromium", "chromium-browser")):
            chemin = shutil.which(commande)
            if chemin and all(chemin != c for _, c in out):
                out.append((nom, chemin))
    return out


class Affichage:
    """Fenêtre de l'interface : navigateur en mode application (profil propre à l'application) ou navigateur
    par défaut."""

    def __init__(self, url: str):
        self.url = url
        self.processus: subprocess.Popen | None = None
        self.mode = ""

    def commande(self, nom: str, exe: str) -> list[str]:
        profil = dossier_local() / "affichage" / re.sub(r"\W+", "_", nom)
        options = ["--no-first-run", "--no-default-browser-check", "--disable-session-crashed-bubble",
                   "--hide-crash-restore-bubble", "--window-size=1440,900"]
        options += os.environ.get("ANALYSE_CB_NAVIGATEUR_OPTIONS", "").split()
        return [exe, f"--user-data-dir={profil}", *options, f"--app={self.url}"]

    def ouvrir(self, navigateur_defaut: bool = False) -> str:
        if not navigateur_defaut:
            for nom, exe in navigateurs():
                try:
                    self.processus = subprocess.Popen(self.commande(nom, exe), stdin=subprocess.DEVNULL,
                                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.mode = nom
                    JOURNAL.info("Interface ouverte avec %s en mode application (%s).", nom, exe)
                    return nom
                except OSError:
                    JOURNAL.exception("Lancement de %s impossible.", nom)
        self.mode = "navigateur par défaut"
        JOURNAL.info("Interface ouverte dans le navigateur par défaut.")
        try:
            webbrowser.open(self.url)
        except Exception:
            JOURNAL.exception("Ouverture du navigateur par défaut impossible.")
        return self.mode

    def processus_actif(self) -> bool:
        return self.processus is not None and self.processus.poll() is None

    def fermer(self, attente: float = 3) -> None:
        """Ferme la fenêtre ouverte par l'application si elle ne s'est pas fermée d'elle-même."""
        if not self.processus_actif():
            return
        try:
            self.processus.wait(attente)
        except subprocess.TimeoutExpired:
            try:
                self.processus.terminate()
                self.processus.wait(5)
            except Exception:
                JOURNAL.exception("Fermeture de la fenêtre impossible.")


# ------------------------------------------------------------------ durée de vie de l'application
def attendre_fin(serveur, affichage: Affichage, delai_affichage: float | None = None) -> str:
    """Attend la fin de l'utilisation : « quitter » (bouton de l'interface), « fermee » (plus aucune fenêtre ouverte)
    ou « non_affichee » (l'interface ne s'est pas affichée dans le délai)."""
    app = serveur.app
    delai_affichage = DELAI_PREMIER_AFFICHAGE if delai_affichage is None else delai_affichage
    debut = time.time()
    while True:
        if app.quitter.wait(0.5):
            return "quitter"
        t = time.time()
        if not app.interface_chargee.is_set():
            if t - debut > delai_affichage:
                return "non_affichee"
            continue
        if app.pages_ouvertes(DELAI_PRESENCE) or app.analyse_en_cours():
            continue
        if t - app.dernier_signe < DELAI_FERMETURE:  # rechargement de la page en cours
            continue
        if app.derniere_fermeture and app.derniere_fermeture >= app.dernier_signe:
            return "fermee"
        # Plus de signe de vie sans signal de fermeture : fenêtre réduite (minuteries ralenties) ou fermée.
        if affichage.processus_actif() and t - app.dernier_signe < DELAI_ABANDON:
            continue
        return "fermee"


# ------------------------------------------------------------------ instance déjà ouverte
def _fichier_instance() -> Path:
    return dossier_utilisateur() / "instance.json"


def instance_active() -> str:
    """Adresse de l'instance déjà ouverte de l'application, s'il y en a une qui répond."""
    try:
        url = json.loads(_fichier_instance().read_text(encoding="utf-8"))["url"]
        jeton = url.split("jeton=", 1)[1]
        base = url.split("/?", 1)[0]
        req = urllib.request.Request(base + "/api/parametres", headers={"X-Jeton": jeton})
        with urllib.request.urlopen(req, timeout=3) as r:  # noqa: S310 - adresse locale
            return url if r.status == 200 else ""
    except Exception:
        return ""


def _enregistrer_instance(serveur) -> None:
    try:
        _fichier_instance().write_text(json.dumps({"url": serveur.url, "pid": os.getpid()}), encoding="utf-8")
    except OSError:
        JOURNAL.exception("Enregistrement de l'instance impossible.")


def _oublier_instance(serveur) -> None:
    try:
        if json.loads(_fichier_instance().read_text(encoding="utf-8")).get("url") == serveur.url:
            _fichier_instance().unlink()
    except Exception:
        pass


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


def message(texte: str, erreur: bool = True) -> None:
    """Boîte de message Windows (sans dépendance), sinon simple trace dans le journal."""
    JOURNAL.info("Message affiché : %s", texte.replace("\n", " "))
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, texte, TITRE, (0x10 if erreur else 0x40) | 0x40000)
        except Exception:
            JOURNAL.exception("Boîte de message impossible.")


def lancer(navigateur_defaut: bool = False) -> None:
    url = instance_active()
    if url:  # application déjà ouverte : nouvelle fenêtre sur la même instance
        JOURNAL.info("Application déjà ouverte : nouvelle fenêtre.")
        Affichage(url).ouvrir(navigateur_defaut)
        return
    serveur = demarrer_serveur()
    _enregistrer_instance(serveur)
    affichage = Affichage(serveur.url)
    try:
        affichage.ouvrir(navigateur_defaut)
        issue = attendre_fin(serveur, affichage)
        if issue == "non_affichee" and affichage.mode != "navigateur par défaut":
            JOURNAL.error("Interface non affichée avec %s au bout de %s s : navigateur par défaut.",
                          affichage.mode, DELAI_PREMIER_AFFICHAGE)
            affichage.fermer(0)
            affichage = Affichage(serveur.url)
            affichage.ouvrir(navigateur_defaut=True)
            issue = attendre_fin(serveur, affichage, 2 * DELAI_PREMIER_AFFICHAGE)
        if issue == "non_affichee":
            JOURNAL.error("L'interface ne s'est affichée dans aucun navigateur.")
            message("L'interface de l'application ne s'est pas affichée.\n\n"
                    f"Ouvrez cette adresse dans votre navigateur, puis cliquez sur OK une fois l'application utilisée :\n"
                    f"{serveur.url}\n\nDétail technique : {dossier_utilisateur() / 'journal.txt'}")
            if serveur.app.interface_chargee.is_set():
                attendre_fin(serveur, affichage)
        JOURNAL.info("Fin de l'utilisation (%s).", issue)
    finally:
        serveur.app.quitter.set()
        affichage.fermer()
        _oublier_instance(serveur)
        serveur.arreter()


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


def test_affichage() -> list[str]:
    """Ouvre la fenêtre exactement comme au lancement normal, attend que l'interface s'y affiche et se signale,
    puis quitte comme le bouton « Quitter l'application » (la fenêtre doit alors se fermer)."""
    if not navigateurs():
        return ["Aucun navigateur Edge ou Chrome trouvé : l'interface s'ouvrirait dans le navigateur par défaut."]
    serveur = demarrer_serveur()
    affichage = Affichage(serveur.url)
    problemes = []
    try:
        affichage.ouvrir()
        if not serveur.app.interface_chargee.wait(90):
            return [f"Interface non affichée avec {affichage.mode} au bout de 90 s."]
        debut = time.time()
        while not serveur.app.pages_ouvertes(DELAI_PRESENCE) and time.time() - debut < 30:
            time.sleep(0.5)
        if not serveur.app.pages_ouvertes(DELAI_PRESENCE):
            problemes.append("La fenêtre ne signale pas sa présence.")
        serveur.app.quitter.set()  # la fenêtre l'apprend à son prochain signal et se ferme
        debut = time.time()
        while time.time() - debut < 40 and not serveur.app.derniere_fermeture and affichage.processus_actif():
            time.sleep(0.5)
        if not serveur.app.derniere_fermeture and affichage.processus_actif():
            problemes.append("La fenêtre ne s'est pas fermée après « Quitter ».")
        JOURNAL.info("Vérification de l'affichage avec %s terminée.", affichage.mode)
    finally:
        affichage.fermer()
        serveur.arreter()
    return problemes


def _rendre_compte(problemes: list[str], fichier: str | None) -> int:
    texte = "OK" if not problemes else "\n".join(problemes)
    if fichier:
        Path(fichier).write_text(texte, encoding="utf-8")
    print(texte)
    return 0 if not problemes else 1


# ------------------------------------------------------------------ point d'entrée
TESTS = {"--test-serveur": test_serveur, "--test-affichage": test_affichage}


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
    try:
        lancer(navigateur_defaut="--navigateur" in args)
    except Exception:
        JOURNAL.exception("Erreur de l'application.")
        message(f"Erreur de l'application. Détail : {dossier_utilisateur() / 'journal.txt'}")
    JOURNAL.info("Fin de l'application.")


if __name__ == "__main__":
    main()
