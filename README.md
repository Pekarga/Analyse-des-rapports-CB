# Analyse automatisée des rapports des Contrôleurs Budgétaires (CB)

Cet outil automatise l'analyse des rapports périodiques des Contrôleurs Budgétaires auprès des EPN. Il s'appuie sur trois sources :

1. le **canevas de rédaction du rapport du CB** institué par la note n°0580/MBPE/DGBF/DCB du 26 juillet 2023 (décret n°2021-677 du 03 novembre 2021) ;
2. le **décret de création et d'organisation** de chaque EPN (PDF texte ou scanné, Word ou texte) ;
3. la **situation d'exécution du budget** à la date de la période du rapport (Excel, CSV, PDF ou Word), qui sert de donnée de référence.

Tous les résultats sont reportés dans le **fichier d'analyse de la DCB** (`modeles/Fichier_analyse_des_rapports_des_CB.xlsx`), que l'outil remplit. Un **référentiel des EPN** (`config/referentiel_epn.csv`) complète l'identification des EPN.

À partir d'un rapport au format Word (.docx) ou PDF, l'outil produit le fichier d'analyse rempli. Le Chargé d'Études n'a plus qu'à le relire, l'ajuster et le compléter. Le décret et la situation d'exécution sont facultatifs : sans eux, l'analyse porte sur le canevas seul.

> Par défaut, le fichier d'analyse est produit sous **forme définitive** (validation directe) : tous les statuts de la grille sont tranchés et les appréciations sont rédigées sans mention « à valider ». Pour revenir à un mode brouillon (statuts « À vérifier » / « À apprécier » laissés au Chargé d'Études, mention « Pré-rempli automatiquement »), indiquez `validation_directe = false` dans `config/parametres.toml`.

## Ce qui est automatisé

| Partie de la grille | Contrôles automatiques |
|---|---|
| **En-tête** | Repérage de l'EPN (via le référentiel ou la page de garde), du CB signataire et de la période (rapport d'étape au 30 juin ou rapport annuel). Vérification de l'usage du canevas en vigueur : rubriques propres au canevas 2023 et présentation par activités (budget-programmes). |
| **I. Délai** | Période reconnue (1er semestre, 1er à 4e trimestre, exercice annuel ; le rapport du 2e trimestre est traité comme le rapport d'étape au 30 juin), date de fin de période, date limite (paramétrable), écart en jours et appréciation. L'écart et l'appréciation sont des formules Excel : ils se recalculent si vous corrigez une date. |
| **II. Forme** | Présence de chaque partie et sous-partie du canevas, y compris les éléments de l'introduction (texte de création, missions, antennes, financement, effectif…). Les rubriques « le cas échéant » sont signalées, et celles qui ne concernent que le rapport annuel sont marquées « Non applicable » dans un rapport d'étape. L'outil vérifie aussi la présence des 8 tableaux (avec titre et source), la cohérence entre le sommaire et les titres, et la présence d'une date et d'un signataire. Les rubriques trop peu développées sont signalées. |
| **III. Fond** | **Fiabilité** : recalcul de tous les tableaux (montant actuel = initial + modifications, sous-totaux, totaux, taux de réalisation et d'exécution, écarts, variations, taux des motifs de différés et de rejets). Les calculs écrits dans le texte sont aussi vérifiés (« 352 776 576 − 219 352 902 = 133 423 674 », SNT, ratios). **Cohérence** : entre tableaux (T1↔T2, T1↔T3, équilibre T3 = T4, T5↔T3, T6↔T4, mêmes activités aux tableaux 4 et 6) et entre le texte et les tableaux (taux cités, sens et montant du résultat budgétaire, ratios RRP, RDP, RDF et RDI recalculés). Le texte de création est comparé au référentiel des EPN. |
| **IV. Difficultés et suggestions** | Extraction des difficultés et suggestions formulées par le CB, classées dans les 3 catégories de la grille (exécution du budget, contrôle de l'exécution, gestion de l'établissement). |
| **Décret de création et d'organisation** | Lecture du décret, découpé en articles : référence (numéro et date), dénomination, sigle, catégorie, tutelles, siège, antennes, missions, organes, périodicité des sessions du Conseil de gestion, ressources. Puis confrontation avec le rapport : texte de création cité avec le bon numéro et la bonne date, missions toutes rappelées, sources de financement conformes (et ressources du tableau 3 prévues par le décret), organes évoqués, nombre de sessions du Conseil de gestion sur la période (au prorata de la périodicité fixée par le décret). Les écarts alimentent les lignes « Texte de création », « Rappel des missions », « Mode de financement », « Organisation » et « COGES » de la partie III. |
| **Situation d'exécution** | Lecture de la situation (feuilles « Recettes » / « Dépenses » ou fichier unique ; colonnes reconnues d'après leur intitulé). Un fichier **consolidé** (colonne « EPN » ou « Sigle ») est filtré sur l'EPN du rapport. Contrôle de la date d'arrêté (= fin de la période). Rapprochement **à l'unité près** des tableaux 3 à 6 avec la situation : prévisions initiales et finales, recouvrements, ressources propres, budget actuel, ordonnancements par grande nature (personnel, biens et services, transferts, investissements), taux de réalisation et d'exécution, résultat budgétaire, puis **ligne à ligne** par code (nature économique ou activité). Un écart rend la rubrique « Non fiable » dans la partie III. |
| **V. Appréciation générale** | Projet d'appréciation (points forts, insuffisances, recommandations au CB) et proposition de suite à donner (retour au CB ou rapport exploitable). |

Le fichier produit contient aussi des onglets de détail : **Synthèse**, **Contrôle structure** (toutes les rubriques du canevas 2023, y compris celles absentes de la grille), **Contrôles automatiques** (chaque anomalie avec la valeur attendue et la valeur constatée), **Ratios**, **Difficultés-Suggestions**, **Décret de création** (éléments lus dans le décret et points de contrôle), **Situation d'exécution** (rapprochement des agrégats et des lignes, données retenues) et **Tableaux extraits** (pour vérifier la lecture des tableaux).

Quand plusieurs rapports sont analysés ensemble, un **tableau de bord consolidé** récapitule tous les EPN : délais, taux de conformité, rubriques absentes, anomalies, conformité au décret, concordance avec la situation d'exécution et suite à donner.

## Application de bureau Windows (recommandée)

L'outil est disponible sous forme d'**application Windows** : un installateur `AnalyseRapportsCB-Installation-x.y.z.exe` installe le programme (sans droits d'administrateur), crée les raccourcis dans le menu Démarrer et sur le Bureau, et intègre la lecture des documents scannés (Tesseract OCR, langue française). Aucun autre logiciel n'est nécessaire.

**Obtenir l'installateur** : il est fabriqué automatiquement sur GitHub à chaque modification de l'outil (onglet **Actions** du dépôt → workflow « Application Windows » → dernière exécution → artefact **AnalyseRapportsCB-Windows**, qui contient l'installateur et une version portable en .zip). Pour une version publiée, poussez un tag `vX.Y.Z` : l'installateur est alors joint à la « Release » correspondante.

**Utilisation** : l'application s'ouvre sur un **tableau de bord** et comporte, dans la barre latérale :

- **Choix de l'EPN** : en haut du tableau de bord, de la comparaison, des ratios, de la nature économique et des alertes, le sélecteur **EPN** fait porter la page sur un EPN ou sur l'ensemble des EPN ; le choix est mémorisé et, après une analyse, l'application se place sur l'EPN analysé ;
- **Tableau de bord** : pour l'EPN choisi (ou l'ensemble des EPN), crédits, exécution, taux d'exécution et écarts de la période choisie (avec l'évolution par rapport à la période précédente), évolution de l'exécution sur l'exercice, **analyse des ratios** de gestion (RRP, RDP, RDF, RDI de l'ensemble des EPN, ratios cités par les CB), synthèse et alertes avec une recommandation, exécution par catégorie de dépense pour un EPN, détail par EPN ou par ministère pour l'ensemble (un clic sur un EPN affiche son tableau de bord ; statut « OK », « À surveiller », « Sous-exécution » ou « Dépassement » selon le taux attendu à la fin de la période : 25 %, 50 %, 75 % ou 100 %), graphique prévu / réalisé (par trimestre pour un EPN, par EPN pour l'ensemble, ou par nature de dépense) et **difficultés et suggestions** formulées par les CB, classées par catégorie (exécution du budget, contrôle de l'exécution, gestion de l'établissement). Le bouton **Exporter** produit ce tableau de bord au format Excel (indicateurs, ratios, difficultés et suggestions, alertes) ;
- **Analyse des rapports** : déposer les rapports (Word ou PDF, y compris scannés), saisir leur date de réception, ajouter si possible les décrets de création et les situations d'exécution (SIGOBE, Excel, CSV, PDF), puis **Lancer l'analyse**. Chaque rapport donne son fichier d'analyse Excel (grille de la DCB rédigée) et alimente le tableau de bord ;
- **Comparaison budgétaire** : les **rapports de l'EPN pour un exercice (1er au 4e trimestre, et rapport annuel s'il est analysé)** côte à côte : crédits, engagements, ordonnancements cumulés et exécutés au cours du trimestre, taux d'exécution et statut, recettes prévues et recouvrées, **prévisions et recouvrements par nature économique de recettes** (par groupe de ressources — budget général, ressources propres, autres — puis nature par nature : prévisions actuelles, avec les prévisions initiales lorsqu'elles ont été modifiées, recouvrements cumulés, taux de recouvrement et montant recouvré au cours du trimestre, avec un graphique et une lecture rédigée), dépenses par catégorie, ratios de gestion, qualité du rapport (forme, fond, anomalies, délai de transmission, suite à donner), graphiques et lecture rédigée de l'évolution ; un trimestre dont la date limite n'est pas atteinte est indiqué « à venir ». L'option « Ensemble des EPN » cumule tous les EPN trimestre par trimestre ;
- **Analyse des ratios** : ratios du canevas (ressources propres, dépenses de personnel, de fonctionnement, d'investissement, d'abonnement) par EPN et pour l'ensemble, calculés sur la situation d'exécution (SIGOBE) lorsqu'elle est fournie, sinon sur les tableaux du rapport ; valeurs citées par le CB et concordance avec ses tableaux ; structure des dépenses ; lecture rédigée des ratios de chaque EPN ; évolution d'une période à l'autre ;
- **Nature économique** : exécution des dépenses et des recettes nature par nature (code à 6 chiffres), pour un EPN ou pour l'ensemble des EPN de la période, à partir de la situation d'exécution SIGOBE (lignes cumulées sur les activités), à défaut des tableaux du rapport : crédits initiaux et actuels, engagements, ordonnancements, taux et statut (« Dépassement », « Non engagé », « Crédits supprimés »…), points d'attention (natures sans engagement, reste à payer, crédits réduits par la régulation, concentration, natures d'investissement inscrites dans une autre catégorie), lecture rédigée, principales natures. Le fichier d'analyse de chaque rapport comporte un onglet « Nature économique » et l'export du tableau de bord un onglet « Natures économiques » ;
- **Alertes & Anomalies** : rapports à retourner au CB, textes de création mal cités, montants contredits par la situation d'exécution, régulation non répercutée, Conseil de gestion non réuni, dépassements et sous-exécutions… ;
- **Analyses par EPN** : les analyses effectuées, **rangées par EPN** (fiche de chaque EPN : analyses par exercice et par trimestre, délais, conformité, suite à donner, accès au tableau de bord et à la comparaison de l'EPN) ; la vue « Toutes les analyses » donne la liste chronologique. Un clic ouvre l'appréciation générale, les alertes, les principaux constats et les montants retenus du rapport, ainsi que son fichier Excel et le rapport du CB. Chaque nouvelle analyse est rangée dans le dossier des résultats, dans un **dossier propre à l'EPN** (`<dossier des résultats>\<EPN>\<période>\` : fichier d'analyse et copie du rapport) ;
- **Paramètres**, en trois onglets :
  - **Général** : profil (nom, fonction), institution et logo affichés dans la barre latérale, dossier des résultats, dates limites de transmission, seuils d'appréciation et d'exécution ;
  - **Canevas des rapports** : texte qui institue le canevas (cité dans l'appréciation de la forme) ; pour chaque partie, rubrique et tableau : libellé, exigence (obligatoire, le cas échéant, rapport annuel seulement, non exigée), titre exigé, volume minimal, autres intitulés acceptés et ligne du modèle où l'appréciation est reportée ; ajout de rubriques (nouvelle partie ou sous-rubrique d'une partie) ; retour au canevas de la note n°0580. **Actualiser à partir d'un nouveau canevas** : déposer la note ou le canevas de la DCB (Word ou PDF, y compris scanné) ; l'application en lit la référence et le plan (parties, sous-parties, éléments énumérés, tableaux prescrits), le compare au canevas en vigueur et propose les mises à jour — rubriques nouvelles (placées à leur rang dans le plan), libellés différents, rubriques et tableaux absents du document, nouvelle référence — à cocher puis à enregistrer ; le dernier document importé est conservé et peut être rouvert. Le canevas est conservé dans `%APPDATA%\AnalyseRapportsCB\canevas.json` ;
  - **Modèle du fichier d'analyse** (document de restitution) : exporter le modèle en vigueur, le modifier dans Excel (mise en forme, logo, en-tête, libellés, nouvelles lignes de rubriques), puis l'importer ; retour au modèle de la DCB. Les lignes à remplir sont retrouvées d'après les intitulés de la colonne A : un modèle dont des lignes ont été ajoutées ou déplacées reste utilisable, et le tableau « Lignes repérées dans le modèle » indique la ligne retenue pour chaque élément. Un modèle dont des intitulés indispensables (parties II à V, « Suite à donner ») sont introuvables est refusé.

**Montants** : dans l'interface comme dans les fichiers Excel, les montants sont écrits en entier, en FCFA, avec séparateur de milliers (ex. 803 512 450). Seuls les graphiques utilisent une unité abrégée (M FCFA ou Mds FCFA), indiquée dans leur légende.

**Dates limites de transmission des rapports à la DCB** (modifiables dans les Paramètres ou dans `config/parametres.toml`) : 1er trimestre le 15 avril, 2e trimestre (rapport d'étape au 30 juin) le 15 juillet, 3e trimestre le 15 octobre, 4e trimestre le 15 janvier de l'année suivante, rapport annuel le 30 avril de l'année suivante. Le délai est apprécié à partir de la date de réception saisie pour chaque rapport : il figure dans la grille d'analyse, l'appréciation générale, les alertes (« Rapport transmis hors délai ») et le tableau de bord.

L'interface est servie par un petit serveur interne à l'application (adresse locale 127.0.0.1, protégée par un jeton propre à chaque lancement) et s'affiche dans une fenêtre de **Microsoft Edge en mode « application »** (sans barre d'adresse ni onglets, avec un profil propre à l'application dans `%LOCALAPPDATA%\AnalyseRapportsCB`), à défaut de Google Chrome, à défaut du navigateur par défaut : aucun composant d'affichage n'est embarqué. L'application reste ouverte tant qu'une de ses fenêtres l'est ; une seconde ouverture ouvre une nouvelle fenêtre sur la même instance. Si l'interface ne s'affiche pas dans Edge au bout de 45 secondes, elle s'ouvre dans le navigateur par défaut ; le menu Démarrer propose aussi un raccourci « … (dans le navigateur) ». Le déroulement de chaque lancement est consigné dans `%APPDATA%\AnalyseRapportsCB\journal.txt` (bouton « Journal de l'application » dans les Paramètres). Les analyses sont conservées dans `%APPDATA%\AnalyseRapportsCB\historique.db` ; une nouvelle analyse du même EPN pour la même période remplace la précédente. Aucune donnée n'est envoyée sur Internet.

Construction manuelle (poste Windows avec Python 3.12) : `pip install -r requirements-dev.txt`, puis `pyinstaller packaging/AnalyseRapportsCB.spec` et `iscc packaging\installateur.iss` (Inno Setup 6). Placez au préalable le dossier de Tesseract (avec `tessdata\fra.traineddata`) dans `tesseract\` à la racine du dépôt pour l'intégrer à l'application.

## Installation (une seule fois)

Prérequis : Python 3.11 ou plus récent (https://www.python.org, cocher « Add Python to PATH » sous Windows).

```bash
pip install -r requirements.txt
```

**Pour les rapports scannés** (cas le plus fréquent : PDF issus d'un scanner), il faut aussi le logiciel de reconnaissance de caractères **Tesseract OCR** avec la langue française :

- Windows : installateur disponible sur https://github.com/UB-Mannheim/tesseract/wiki. Pendant l'installation, cochez la langue **French** (« Additional language data »), puis ajoutez le dossier d'installation (par ex. `C:\Program Files\Tesseract-OCR`) à la variable PATH.
- Linux : `sudo apt install tesseract-ocr tesseract-ocr-fra`

Sans Tesseract, les rapports Word et les PDF « texte » restent analysés normalement. Un PDF scanné est alors refusé avec un message explicite.

Pour l'interface web (facultatif) :

```bash
pip install streamlit pandas
```

## Utilisation

### 1. Application de bureau (avec Python installé)

```bash
python -m analyse_cb.interface
```

(ou double-clic sur `AnalyseRapportsCB.pyw`). L'interface s'ouvre dans Edge (ou Chrome, Chromium) en mode application ; avec l'option `--navigateur`, dans le navigateur par défaut.

### 2. Interface web

```bash
streamlit run app.py
```

Le navigateur s'ouvre. Il suffit ensuite de déposer les rapports (et, si vous les avez, les décrets de création et la ou les situations d'exécution), de saisir les dates de réception, de cliquer sur **Lancer l'analyse** et de télécharger les fichiers d'analyse (et le tableau de bord s'il y a plusieurs rapports). Tout se passe sur le poste : aucun document n'est envoyé sur Internet.

### 3. Ligne de commande

Un seul rapport :

```bash
python -m analyse_cb "Rapport CB ANEX S1 2025.docx" --reception 05/08/2025 --charge "M. KONAN"
```

Avec le décret de création et la situation d'exécution de l'EPN :

```bash
python -m analyse_cb "Rapport CB ANEX S1 2025.pdf" --decret "Decret creation ANEX.pdf" --situation "Situation execution 30-06-2025.xlsx" --reception 05/08/2025
```

Tous les rapports d'un dossier, avec un dossier de décrets et une situation consolidée de tous les EPN (chaque rapport est associé automatiquement au décret et aux lignes de son EPN, d'après la dénomination ou le sigle) :

```bash
python -m analyse_cb rapports_recus/ --decret decrets/ --situation situation_EPN_30062025.xlsx --sortie resultats/
```

Tous les rapports d'un dossier, avec le registre de réception :

```bash
python -m analyse_cb rapports_recus/ --registre registre_reception.csv --sortie resultats/
```

Le **registre de réception** est un fichier CSV (séparateur `;`, peut être enregistré depuis Excel) :

```
fichier;epn;controleur;periode;date_reception;charge_etudes
Rapport CB ANEX S1 2025.docx;;;;05/08/2025;M. KONAN
Rapport CB OFEX 2024.pdf;Office d'Exemple;;exercice 2024;12/05/2025;Mme TRAORE
```

Les colonnes vides sont détectées automatiquement dans le rapport. Deux colonnes facultatives, `decret` et `situation`, permettent d'indiquer pour chaque rapport le fichier du décret et celui de la situation d'exécution (chemins relatifs au registre).

### Format de la situation d'exécution

La situation est lue à partir des intitulés de colonnes, quel que soit leur ordre :

| Contenu | Intitulés reconnus (exemples) |
|---|---|
| EPN (fichier consolidé) | EPN, Sigle, Établissement, Structure |
| Code | Code, Compte, Imputation, Code activité |
| Libellé | Libellé, Désignation, Intitulé |
| Grande nature (facultatif) | Nature, Catégorie, Titre |
| Montants | Prévision / crédit initial(e), Budget actuel / Prévision finale / Dotation, Engagements, Liquidations, Ordonnancements / Mandats, Recouvrements / Encaissements |

**États SIGOBE** : les situations d'exécution éditées depuis SIGOBE (« Situation d'exécution des recettes – EPN » et « Situation d'exécution Annexe EPN », en PDF) sont lues directement. La nomenclature hiérarchique (EPN > catégorie > programme > activité > nature économique, en-têtes répétés à chaque page) est reconnue et seules les lignes de dernier niveau sont additionnées. Les colonnes « Recette Emise », « Eng ViseCf », « Liquid Visecf », « OP Emis » et « OP PEC » sont reconnues. Les deux fichiers (recettes et dépenses) d'un même EPN peuvent être fournis ensemble : ils sont réunis automatiquement.

La date d'arrêté est lue dans le titre (« Situation au 30/06/2025 »), dans le nom du fichier ou dans les premières lignes. Les lignes « Total » et « Sous-total » sont ignorées (les totaux sont recalculés). Pour les dépenses, la grande nature est prise dans la colonne « Nature », dans les lignes de regroupement (« Personnel », « Biens et services »…) ou, à défaut, déduite du code de nature économique (66 personnel, 60 à 63 biens et services, 64-65 transferts, 2 investissements). Pour les recettes, les codes 73 sont classés en ressources du budget général et les autres codes 7 en ressources propres. Les fichiers .xls doivent être enregistrés en .xlsx.

Autres options : `--epn`, `--controleur`, `--periode "1er semestre 2025"`, `--parametres`, `--referentiel`, `--modele` (voir `python -m analyse_cb --help`).

## Paramétrage

- **`config/parametres.toml`** : dates limites de transmission (rapport d'étape, rapports trimestriels et rapport annuel), seuils des appréciations et critères de la proposition « retour au CB ». **Les dates limites par défaut (31/07 pour le rapport d'étape, 30/04 de N+1 pour le rapport annuel) sont à confirmer selon les instructions de la DCB.**
- **`config/referentiel_epn.csv`** : une ligne par EPN (sigle, dénomination, décret de création, tutelle, CB en poste et, facultativement, `fichier_decret` et `fichier_situation` : chemins des fichiers de référence de l'EPN, relatifs au dossier `config/`). Plus il est complet, meilleure est l'identification des EPN et la vérification du texte de création. La ligne fournie est un exemple fictif à remplacer. Quand le décret est fourni, c'est lui qui sert de référence pour le texte de création.
- **`modeles/Fichier_analyse_des_rapports_des_CB.xlsx`** : le modèle de la DCB. Si vous le modifiez, conservez la position des lignes, ou adaptez `ligne_forme` dans `analyse_cb/canevas.py`.
- **`analyse_cb/canevas.py`** : le référentiel des rubriques du canevas, avec les expressions qui servent à les reconnaître. C'est ici qu'il faut intervenir si le canevas évolue ou si certains CB intitulent leurs parties autrement.

## Points d'attention

- **Rapports scannés** : l'outil le détecte et lit automatiquement le document par OCR. Il redresse les pages (inclinaison, pages à l'italienne), lit les titres en bandeau et reconstitue les tableaux à partir de leur quadrillage. Les montants sont relus cellule par cellule en mode « chiffres uniquement ». Compter environ 1 à 2 minutes pour 30 pages. Le résultat est ensuite mis en cache : une nouvelle analyse du même fichier est immédiate. Les anomalies chiffrées portent la mention « à confirmer sur l'original », car une erreur de lecture reste possible. L'onglet « Tableaux extraits » montre ce qui a été lu. Les tampons et les signatures manuscrites ne sont pas lisibles par l'OCR : la signature, le visa, le nom du CB et la date de réception sont donc à vérifier ou à saisir.
- **Formats** : .docx et .pdf (texte ou scanné). Les fichiers .doc doivent d'abord être enregistrés en .docx.
- **Décret** : la lecture suppose la présentation habituelle des décrets (« Article 1 : … », énumérations à tirets). Les missions sont jugées « rappelées » quand l'essentiel de leurs mots-clés figure dans l'introduction du rapport : un écart signale une mission à vérifier, pas forcément une erreur du CB. L'onglet « Décret de création » montre tout ce qui a été lu.
- **Situation d'exécution** : si sa date d'arrêté diffère de la fin de la période, l'outil le signale. Les montants d'exécution (engagements, ordonnancements, recouvrements, prises en charge) étant cumulés, un montant du rapport **supérieur** à celui d'une situation arrêtée plus tard est impossible : il est signalé comme anomalie majeure. Un montant inférieur est classé « Écart (décalage de date) », sans être compté comme erreur. Les écarts sur les prévisions sont signalés « à confirmer ». Pour un rapprochement exact, éditer la situation à la date de fin de la période (ex. 30/09 pour le 3e trimestre).
- **Signature** : la présence d'une date et du nom du CB est vérifiée automatiquement. La signature manuscrite et le cachet restent à contrôler visuellement (statut « À vérifier »).
- **Grille Excel et canevas 2023** : la grille actuelle ne reprend pas certaines rubriques du canevas 2023 (III Analyse de la performance, IV.5 SNT, VIII Gestion des risques, IX Autres points, annonce du plan). L'outil les contrôle quand même et les présente dans l'onglet « Contrôle structure ». Par ailleurs, dans la grille, les lignes « Gouvernance » s'intitulent « Contrôle de gestion / Contrôle de trésorerie » alors que le canevas prévoit « COGES / Organes de supervision » et « Comité de trésorerie » : l'outil les traite au sens du canevas et corrige ces libellés dans le fichier produit. Les numéros des tableaux 1 et 2 sont aussi inversés dans la grille, et l'encadré du fond y est intitulé « Appréciation générale de la forme » : ces libellés sont également rectifiés dans le fichier produit (le modèle d'origine n'est pas modifié).

## Tests

```bash
python exemples/generer_exemple.py      # génère des rapports FICTIFS (conforme / avec anomalies), un décret et deux situations d'exécution
python -m pytest
```

## Structure du projet

```
analyse_cb/
  lecture.py     lecture .docx / .pdf → blocs (paragraphes, tableaux, sommaire)
  ocr.py         lecture des PDF scannés : redressement, bandeaux, quadrillage des tableaux, OCR
  canevas.py     référentiel des rubriques et tableaux du canevas + lignes de la grille Excel
  structure.py   repérage des rubriques, découpage en sections, contrôle du sommaire
  tableaux.py    identification des tableaux 1 à 8, contrôles arithmétiques et de cohérence
  controles.py   période, délai, signature, référentiel EPN, résultat budgétaire, ratios, difficultés
  decret.py      lecture du décret de création et d'organisation, confrontation avec le rapport
  situation.py   lecture de la situation d'exécution, rapprochement avec les tableaux du rapport
  analyse.py     orchestration et appréciations (forme / fond)
  excel.py       remplissage du modèle, onglets de détail, tableau de bord
  __main__.py    ligne de commande
  historique.py  historique des analyses (base SQLite locale) et indicateurs de chaque rapport
  tableau.py     indicateurs du tableau de bord (taux, statuts, écarts, ratios, difficultés, alertes, synthèse)
  ratios.py      ratios de gestion du canevas : calcul, agrégation, lecture rédigée
  natures.py     analyse de l'exécution par nature économique (statuts, points d'attention, lecture)
  serveur.py     serveur local de l'application (interface et API)
  web/           interface de l'application (HTML, CSS, JavaScript, sans dépendance externe)
  interface.py   lanceur de l'application (Edge en mode application, ou navigateur) et durée de vie
  ressources.py  emplacement des ressources (application empaquetée, Tesseract intégré)
app.py           interface web (Streamlit)
packaging/       construction de l'application Windows (PyInstaller, installateur Inno Setup, icône)
config/          paramètres et référentiel des EPN
modeles/         fichier d'analyse de la DCB
exemples/        générateur de rapports fictifs pour les tests
tests/           tests automatisés
```
