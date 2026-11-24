"""Serveur local de l'application : interface web (tableau de bord) et API de l'analyse.

Le serveur n'écoute que sur 127.0.0.1, sur un port libre, et chaque appel à l'API doit porter le jeton
aléatoire de la session (en-tête X-Jeton ou paramètre « jeton »).
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__, historique, tableau
from .analyse import InfosRapport, analyser, charger_decrets, charger_parametres, charger_situations
from .analyse import PARAMETRES_DEFAUT, REFERENTIEL_DEFAUT
from .controles import lire_date
from .ressources import dossier_local, dossier_ressources, dossier_utilisateur

EXT_ACCEPTEES = {"rapport": (".docx", ".pdf"), "decret": (".pdf", ".docx", ".txt"),
                 "situation": (".xlsx", ".xlsm", ".csv", ".pdf", ".docx"), "logo": (".png", ".jpg", ".jpeg", ".gif", ".svg")}
INSTITUTION_DEFAUT = {"ligne1": "Ministère des Finances et du Budget", "ligne2": "Côte d'Ivoire"}
JOURNAL = logging.getLogger("analyse_cb.serveur")


def dossier_web() -> Path:
    return dossier_ressources() / "analyse_cb" / "web"


def dossier_sortie_defaut() -> Path:
    documents = Path.home() / "Documents"
    return (documents if documents.is_dir() else Path.home()) / "Analyses rapports CB"


# ------------------------------------------------------------------ préférences
def fichier_preferences() -> Path:
    return dossier_utilisateur() / "preferences.json"


def lire_preferences() -> dict:
    try:
        return json.loads(fichier_preferences().read_text(encoding="utf-8"))
    except Exception:
        return {}


def enregistrer_preferences(prefs: dict) -> None:
    fichier_preferences().write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")


def _fusion(base: dict, ajouts: dict) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in (ajouts or {}).items():
        out[k] = _fusion(out.get(k, {}), v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def parametres_effectifs(prefs: dict | None = None) -> dict:
    """Paramètres du fichier config/parametres.toml, complétés par ceux saisis dans l'application."""
    prefs = lire_preferences() if prefs is None else prefs
    return _fusion(charger_parametres(), prefs.get("parametres", {}))


def ouvrir_systeme(chemin: Path) -> None:
    """Ouvre un fichier ou un dossier avec l'application par défaut du poste."""
    if os.environ.get("ANALYSE_CB_SANS_OUVERTURE"):
        return
    if sys.platform.startswith("win"):
        os.startfile(str(chemin))  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(chemin)])
    else:
        subprocess.Popen(["xdg-open", str(chemin)])


# ------------------------------------------------------------------ application
class Application:
    def __init__(self):
        self.jeton = secrets.token_urlsafe(18)
        self.depot = dossier_local() / "documents"
        self.depot.mkdir(parents=True, exist_ok=True)
        self.fichiers: dict[str, dict] = {}
        self.travail: dict | None = None
        self.verrou = threading.Lock()
        self.arret = threading.Event()
        self.quitter = threading.Event()
        self.interface_chargee = threading.Event()  # l'interface a interrogé le serveur (affichage effectif)
        # Fenêtres de l'interface ouvertes : identifiant de page → dernier signe de vie (voir interface.py)
        self.pages: dict[str, float] = {}
        self.verrou_pages = threading.Lock()
        self.dernier_signe = 0.0
        self.derniere_fermeture = 0.0

    # -- fichiers déposés depuis l'interface
    def deposer(self, nom: str, categorie: str, contenu: bytes) -> dict:
        nom = Path(nom).name or "document"
        nom = re.sub(r"[\\/:*?\"<>|]+", "_", nom)
        if categorie not in EXT_ACCEPTEES:
            raise ValueError("Catégorie de document inconnue.")
        if Path(nom).suffix.lower() not in EXT_ACCEPTEES[categorie]:
            raise ValueError(f"Format non accepté pour ce document : {Path(nom).suffix or 'sans extension'}.")
        if categorie == "logo":
            for ancien in dossier_utilisateur().glob("logo.*"):
                ancien.unlink()
            cible = dossier_utilisateur() / f"logo{Path(nom).suffix.lower()}"
            cible.write_bytes(contenu)
            return {"id": "logo", "nom": nom}
        ident = uuid.uuid4().hex[:12]
        dossier = self.depot / ident
        dossier.mkdir(parents=True, exist_ok=True)
        chemin = dossier / nom
        chemin.write_bytes(contenu)
        self.fichiers[ident] = {"chemin": chemin, "nom": nom, "categorie": categorie, "taille": len(contenu)}
        return {"id": ident, "nom": nom, "taille": len(contenu)}

    # -- fenêtres de l'interface (présence régulière, signal de fermeture)
    def presence(self, page: str) -> None:
        with self.verrou_pages:
            nouvelle = page not in self.pages
            self.pages[page] = self.dernier_signe = time.time()
        if nouvelle:
            JOURNAL.info("Fenêtre de l'interface affichée.")
        self.interface_chargee.set()

    def fermeture(self, page: str) -> None:
        with self.verrou_pages:
            self.pages.pop(page, None)
            self.derniere_fermeture = self.dernier_signe = time.time()
        JOURNAL.info("Fenêtre de l'interface fermée.")

    def pages_ouvertes(self, delai: float) -> int:
        """Nombre de fenêtres ayant donné signe de vie depuis moins de `delai` secondes."""
        t = time.time()
        with self.verrou_pages:
            for page, vu in list(self.pages.items()):
                if t - vu > delai:
                    del self.pages[page]
            return len(self.pages)

    def analyse_en_cours(self) -> bool:
        return bool(self.travail and self.travail.get("en_cours"))

    def logo(self) -> Path | None:
        return next(iter(sorted(dossier_utilisateur().glob("logo.*"))), None)

    # -- état général
    def etat(self) -> dict:
        from .ocr import ocr_disponible
        prefs = lire_preferences()
        ok, message = ocr_disponible()
        utilisateur = prefs.get("utilisateur", {})
        liste = historique.periodes()
        badge = 0
        if liste:
            try:
                badge = tableau.toutes_alertes(liste[0]["cle"], parametres_effectifs(prefs))["alertes"]
                badge = sum(1 for a in badge if a["niveau"] in ("critique", "attention"))
            except Exception:
                badge = 0
        return {
            "version": __version__, "ocr": {"ok": ok, "message": message},
            "utilisateur": {"nom": utilisateur.get("nom", ""), "fonction": utilisateur.get("fonction", "Chargé d'Études")},
            "institution": {**INSTITUTION_DEFAUT, **prefs.get("institution", {})},
            "logo": self.logo() is not None, "sortie": prefs.get("sortie") or str(dossier_sortie_defaut()),
            "periodes": liste, "badge": badge, "en_cours": bool(self.travail and self.travail.get("en_cours")),
        }

    # -- paramètres
    def parametres(self) -> dict:
        prefs = lire_preferences()
        eff = parametres_effectifs(prefs)
        return {
            "utilisateur": prefs.get("utilisateur", {"nom": "", "fonction": "Chargé d'Études"}),
            "institution": {**INSTITUTION_DEFAUT, **prefs.get("institution", {})},
            "sortie": prefs.get("sortie") or str(dossier_sortie_defaut()),
            "delais": eff.get("delais", {}), "appreciation": eff.get("appreciation", {}),
            "execution": {"seuil_vigilance": 10, "seuil_sous_execution": 20, **eff.get("execution", {})},
            "analyse": {"validation_directe": True, **eff.get("analyse", {})},
            "fichiers": {"parametres": str(PARAMETRES_DEFAUT), "referentiel": str(REFERENTIEL_DEFAUT),
                         "historique": str(historique.chemin_base()),
                         "journal": str(dossier_utilisateur() / "journal.txt")},
        }

    def enregistrer_parametres(self, data: dict) -> dict:
        prefs = lire_preferences()
        for cle in ("utilisateur", "institution"):
            if isinstance(data.get(cle), dict):
                prefs[cle] = {k: str(v).strip() for k, v in data[cle].items()}
        if data.get("sortie"):
            prefs["sortie"] = str(data["sortie"]).strip()
        p = prefs.setdefault("parametres", {})
        for section, champs in (("delais", ("rapport_etape_date_limite", "rapport_annuel_date_limite",
                                            "rapport_trimestriel_delai_jours")),
                                ("appreciation", ("tres_bien", "bien", "passable", "retour_cb_si_score_forme_inferieur_a",
                                                  "retour_cb_si_anomalies_majeures")),
                                ("execution", ("seuil_vigilance", "seuil_sous_execution")),
                                ("analyse", ("validation_directe",))):
            for champ in champs:
                v = (data.get(section) or {}).get(champ)
                if v is None or v == "":
                    continue
                if champ.endswith("date_limite"):
                    if not re.fullmatch(r"\d{1,2}/\d{1,2}", str(v).strip()):
                        raise ValueError(f"Date limite invalide (format jj/mm attendu) : {v}")
                    v = str(v).strip()
                elif champ == "validation_directe":
                    v = bool(v)
                else:
                    v = float(str(v).replace(",", "."))
                    v = int(v) if v.is_integer() else v
                p.setdefault(section, {})[champ] = v
        enregistrer_preferences(prefs)
        return self.parametres()

    # -- analyse en arrière-plan
    def lancer(self, demande: dict) -> dict:
        with self.verrou:
            if self.travail and self.travail.get("en_cours"):
                raise ValueError("Une analyse est déjà en cours.")
            rapports = [r for r in demande.get("rapports", []) if r.get("id") in self.fichiers]
            if not rapports:
                raise ValueError("Ajoutez au moins un rapport à analyser.")
            sortie = Path(demande.get("sortie") or lire_preferences().get("sortie") or dossier_sortie_defaut())
            sortie.mkdir(parents=True, exist_ok=True)
            prefs = lire_preferences()
            prefs["sortie"] = str(sortie)
            enregistrer_preferences(prefs)
            self.arret.clear()
            self.travail = {
                "en_cours": True, "progres": 0, "message": "Préparation de l'analyse…", "sortie": str(sortie),
                "rapports": [{"id": r["id"], "nom": self.fichiers[r["id"]]["nom"], "etat": "attente", "erreur": ""}
                             for r in rapports],
                "resultats": [], "tableau_de_bord": None, "erreur": "", "erreur_tdb": "",
            }  # toutes les clés existent dès le départ : le fil d'analyse n'en ajoute pas pendant leur lecture
            threading.Thread(target=self._executer, args=(rapports, demande, sortie), daemon=True).start()
            return self.travail

    def _executer(self, rapports, demande, sortie):
        from . import lecture
        from .excel import remplir_modele, suite_a_donner, tableau_de_bord
        t = self.travail
        try:
            parametres = parametres_effectifs()
            t["message"] = "Lecture des documents de référence…"
            decrets = charger_decrets([self.fichiers[i]["chemin"] for i in demande.get("decrets", []) if i in self.fichiers])
            situations = charger_situations([self.fichiers[i]["chemin"] for i in demande.get("situations", [])
                                             if i in self.fichiers])
        except Exception as exc:
            t.update(en_cours=False, erreur=f"Document de référence illisible : {exc}", message="Analyse interrompue.")
            return
        charge = (demande.get("charge") or "").strip()
        resultats = []
        n = len(rapports)
        for k, r in enumerate(rapports):
            if self.arret.is_set():
                for j in range(k, n):
                    t["rapports"][j]["etat"] = "arret"
                break
            fichier = self.fichiers[r["id"]]
            t["rapports"][k]["etat"] = "cours"
            t["progres"] = int(100 * k / n)
            t["message"] = f"Analyse de {fichier['nom']} ({k + 1}/{n})…"

            def progression(page, total, k=k, nom=fichier["nom"]):
                t["progres"] = int(100 * (k + 0.85 * page / max(total, 1)) / n)
                t["message"] = f"{nom} : lecture du document scanné, page {page}/{total}…"
            lecture.RAPPEL_PROGRESSION = progression
            try:
                infos = InfosRapport(charge_etudes=charge, date_reception=lire_date(r.get("reception")),
                                     periode=(r.get("periode") or None))
                res = analyser(fichier["chemin"], infos, parametres, None, decrets=decrets, situations=situations,
                               reference_unique=n == 1)
                sortie_xlsx = remplir_modele(res, sortie / f"Analyse_{fichier['chemin'].stem}.xlsx")
                ident = historique.enregistrer(res, sortie_xlsx)
                resultats.append((res, sortie_xlsx))
                t["resultats"].append({
                    "id": ident, "epn": res.infos.epn, "periode": res.periode.libelle,
                    "forme": res.score_forme, "fond": res.score_fond, "anomalies_majeures": res.nb_anomalies_majeures,
                    "retour": "retourné" in suite_a_donner(res), "fichier": str(sortie_xlsx),
                    "avertissements": list(res.doc.avertissements)})
                t["rapports"][k]["etat"] = "ok"
            except PermissionError:
                t["rapports"][k].update(etat="erreur", erreur="Le fichier d'analyse est ouvert dans Excel : fermez-le puis relancez.")
            except Exception as exc:
                traceback.print_exc()
                JOURNAL.exception("Analyse de %s", fichier["nom"])
                t["rapports"][k].update(etat="erreur", erreur=str(exc))
        lecture.RAPPEL_PROGRESSION = None
        if len(resultats) > 1:
            try:
                t["tableau_de_bord"] = str(tableau_de_bord(resultats, sortie / "Tableau_de_bord_rapports_CB.xlsx"))
            except Exception as exc:
                t["erreur_tdb"] = str(exc)
        ok = len(resultats)
        t.update(en_cours=False, progres=100,
                 message=f"Analyse terminée : {ok} rapport{'s' if ok > 1 else ''} sur {n} traité{'s' if ok > 1 else ''}.")

    # -- ouverture de fichiers
    def ouvrir(self, data: dict) -> None:
        quoi = data.get("quoi")
        if quoi in ("fichier", "dossier") and data.get("id"):
            r = historique.obtenir(int(data["id"]))
            if not r:
                raise ValueError("Analyse introuvable.")
            chemin = Path(r["fichier_analyse"])
            if not chemin.exists():
                raise ValueError(f"Le fichier d'analyse n'existe plus : {chemin}")
            ouvrir_systeme(chemin if quoi == "fichier" else chemin.parent)
        elif quoi == "chemin" and data.get("chemin"):
            ouvrir_systeme(Path(data["chemin"]))
        elif quoi == "sortie":
            d = Path(lire_preferences().get("sortie") or dossier_sortie_defaut())
            d.mkdir(parents=True, exist_ok=True)
            ouvrir_systeme(d)
        elif quoi in ("parametres", "referentiel", "dossier_parametres"):
            ouvrir_systeme({"parametres": PARAMETRES_DEFAUT, "referentiel": REFERENTIEL_DEFAUT,
                            "dossier_parametres": PARAMETRES_DEFAUT.parent}[quoi])
        elif quoi == "journal":
            journal = dossier_utilisateur() / "journal.txt"
            if not journal.exists():
                raise ValueError("Le journal de l'application est vide.")
            ouvrir_systeme(journal)
        else:
            raise ValueError("Demande d'ouverture invalide.")

    def exporter(self, periode: str | None) -> str:
        from .excel import exporter_tableau_de_bord
        donnees = tableau.tableau_de_bord(periode, parametres_effectifs())
        if donnees.get("vide"):
            raise ValueError("Aucune analyse à exporter.")
        sortie = Path(lire_preferences().get("sortie") or dossier_sortie_defaut())
        chemin = sortie / f"Tableau_de_bord_{donnees['periode']['cle']}.xlsx"
        exporter_tableau_de_bord(donnees, chemin)
        return str(chemin)


# ------------------------------------------------------------------ HTTP
class Gestionnaire(BaseHTTPRequestHandler):
    server_version = "AnalyseRapportsCB"

    @property
    def app(self) -> Application:
        return self.server.app  # type: ignore[attr-defined]

    def log_message(self, *args):  # pas de journal dans la console
        pass

    def _json(self, data, statut: int = 200):
        corps = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(statut)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def _erreur(self, message: str, statut: int = 400):
        self._json({"erreur": message}, statut)

    def _fichier(self, chemin: Path, type_mime: str | None = None):
        if not chemin.is_file():
            self.send_error(404)
            return
        corps = chemin.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", type_mime or mimetypes.guess_type(chemin.name)[0] or "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def _autorise(self, requete) -> bool:
        jeton = self.headers.get("X-Jeton") or (parse_qs(requete.query).get("jeton") or [""])[0]
        return secrets.compare_digest(jeton, self.app.jeton)

    def _corps(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def do_GET(self):
        req = urlparse(self.path)
        chemin = req.path
        if chemin in ("/", "/index.html"):
            return self._fichier(dossier_web() / "index.html", "text/html; charset=utf-8")
        if chemin.startswith("/static/"):
            nom = Path(unquote(chemin[len("/static/"):])).name
            return self._fichier(dossier_web() / nom)
        if chemin == "/favicon.ico":
            return self._fichier(dossier_ressources() / "packaging" / "icone.png", "image/png")
        if not chemin.startswith("/api/"):
            return self.send_error(404)
        if not self._autorise(req):
            return self._erreur("Accès refusé.", 403)
        q = {k: v[0] for k, v in parse_qs(req.query).items()}
        try:
            if chemin == "/api/etat":
                if not self.app.interface_chargee.is_set():
                    self.app.interface_chargee.set()
                    JOURNAL.info("Interface chargée (%s).", (self.headers.get("User-Agent") or "")[:160])
                return self._json(self.app.etat())
            if chemin == "/api/tableau":
                return self._json(tableau.tableau_de_bord(q.get("periode"), parametres_effectifs()))
            if chemin == "/api/comparaison":
                return self._json(tableau.comparaison(q.get("periode"), parametres_effectifs()))
            if chemin == "/api/ratios":
                return self._json(tableau.analyse_ratios(q.get("periode")))
            if chemin == "/api/alertes":
                return self._json(tableau.toutes_alertes(q.get("periode"), parametres_effectifs()))
            if chemin == "/api/rapports":
                lignes = []
                for r in historique.lister(q.get("periode") or None):
                    d = r["donnees"]
                    lignes.append({k: r[k] for k in ("id", "epn", "sigle", "tutelle", "periode_cle", "controleur", "charge",
                                                     "date_analyse", "date_reception", "ecart_jours", "score_forme",
                                                     "score_fond", "anomalies_majeures", "retour", "rapport")}
                                  | {"periode": historique.libelle_periode(r["periode_cle"], True),
                                     "delai": d.get("delai", ""), "alertes": len(d.get("alertes", []))})
                return self._json({"rapports": lignes, "periodes": historique.periodes()})
            if chemin == "/api/rapport":
                r = historique.obtenir(int(q.get("id", 0)))
                if not r:
                    return self._erreur("Analyse introuvable.", 404)
                r["periode"] = historique.libelle_periode(r["periode_cle"])
                r["fichier_existe"] = Path(r["fichier_analyse"]).exists()
                info = r["donnees"].get("ratios") or {}
                if info.get("liste"):
                    from .ratios import lecture
                    r["lecture_ratios"] = lecture(info["liste"], info.get("base") or "dépenses engagées")
                return self._json(r)
            if chemin == "/api/travail":
                return self._json(self.app.travail or {"en_cours": False})
            if chemin == "/api/parametres":
                return self._json(self.app.parametres())
            if chemin == "/api/logo":
                logo = self.app.logo()
                return self._fichier(logo) if logo else self.send_error(404)
        except Exception as exc:
            traceback.print_exc()
            return self._erreur(str(exc), 500)
        return self._erreur("Ressource inconnue.", 404)

    def do_POST(self):
        req = urlparse(self.path)
        if not req.path.startswith("/api/") or not self._autorise(req):
            return self._erreur("Accès refusé.", 403)
        try:
            if req.path == "/api/televerser":
                nom = unquote(self.headers.get("X-Nom-Fichier") or "document")
                categorie = self.headers.get("X-Categorie") or "rapport"
                return self._json(self.app.deposer(nom, categorie, self._corps()))
            data = json.loads(self._corps() or b"{}")
            if req.path == "/api/analyser":
                return self._json(self.app.lancer(data))
            if req.path == "/api/arreter":
                self.app.arret.set()
                return self._json({"ok": True})
            if req.path == "/api/parametres":
                return self._json(self.app.enregistrer_parametres(data))
            if req.path == "/api/ouvrir":
                self.app.ouvrir(data)
                return self._json({"ok": True})
            if req.path == "/api/supprimer":
                historique.supprimer(int(data.get("id", 0)))
                return self._json({"ok": True})
            if req.path == "/api/supprimer_logo":
                for f in dossier_utilisateur().glob("logo.*"):
                    f.unlink()
                return self._json({"ok": True})
            if req.path == "/api/exporter":
                chemin = self.app.exporter(data.get("periode"))
                if data.get("ouvrir", True):
                    ouvrir_systeme(Path(chemin))
                return self._json({"chemin": chemin})
            page = (parse_qs(req.query).get("page") or ["?"])[0][:64]
            if req.path == "/api/presence":
                self.app.presence(page)
                return self._json({"quitter": self.app.quitter.is_set()})
            if req.path == "/api/fermeture":
                self.app.fermeture(page)
                return self._json({"ok": True})
            if req.path == "/api/journal":  # erreurs relevées par l'interface
                JOURNAL.error("Interface : %s", str(data.get("message", ""))[:2000])
                return self._json({"ok": True})
            if req.path == "/api/quitter":
                self.app.quitter.set()
                return self._json({"ok": True})
        except ValueError as exc:
            return self._erreur(str(exc), 400)
        except Exception as exc:
            traceback.print_exc()
            return self._erreur(str(exc), 500)
        return self._erreur("Ressource inconnue.", 404)


class Serveur:
    """Serveur HTTP local lancé dans un fil d'exécution séparé."""

    def __init__(self, port: int = 0):
        self.app = Application()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Gestionnaire)
        self.httpd.daemon_threads = True
        self.httpd.app = self.app  # type: ignore[attr-defined]
        self.fil: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self.httpd.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/?jeton={self.app.jeton}"

    def demarrer(self) -> "Serveur":
        self.fil = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.fil.start()
        return self

    def arreter(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def nettoyer_depot(jours: int = 30) -> None:
    """Supprime les documents déposés depuis plus de `jours` jours."""
    import time
    depot = dossier_local() / "documents"
    if not depot.is_dir():
        return
    limite = time.time() - jours * 86400
    for d in depot.iterdir():
        try:
            if d.is_dir() and d.stat().st_mtime < limite:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


__all__ = ["Serveur", "Application", "parametres_effectifs", "lire_preferences"]
