# Analyse automatisée des rapports des Contrôleurs Budgétaires (CB)

Cet outil automatise l'analyse des rapports périodiques des Contrôleurs Budgétaires auprès des EPN. Il s'appuie sur trois sources :

1. le **canevas de rédaction du rapport du CB** institué par la note n°0580/MBPE/DGBF/DCB du 26 juillet 2023 (décret n°2021-677 du 03 novembre 2021) ;
2. le **décret de création et d'organisation** de chaque EPN (PDF texte ou scanné, Word ou texte) ;
3. la **situation d'exécution du budget** à la date de la période du rapport (Excel, CSV, PDF ou Word), qui sert de donnée de référence.

Tous les résultats sont reportés dans le **fichier d'analyse de la DCB** (`modeles/Fichier_analyse_des_rapports_des_CB.xlsx`), que l'outil pré-remplit. Un **référentiel des EPN** (`config/referentiel_epn.csv`) complète l'identification des EPN.

À partir d'un rapport au format Word (.docx) ou PDF, l'outil produit le fichier d'analyse rempli. Le Chargé d'Études n'a plus qu'à le relire, l'ajuster et le compléter. Le décret et la situation d'exécution sont facultatifs : sans eux, l'analyse porte sur le canevas seul.

> L'outil prépare l'analyse, il ne remplace pas le Chargé d'Études. Tout ce qui est rempli automatiquement est signalé comme « à valider ». Les rubriques qui demandent un jugement qualitatif sont marquées **« À apprécier »**.

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

Le fichier produit contient aussi des onglets de détail : **Synthèse auto**, **Contrôle structure** (toutes les rubriques du canevas 2023, y compris celles absentes de la grille), **Contrôles automatiques** (chaque anomalie avec la valeur attendue et la valeur constatée), **Ratios**, **Difficultés-Suggestions**, **Décret de création** (éléments lus dans le décret et points de contrôle), **Situation d'exécution** (rapprochement des agrégats et des lignes, données retenues) et **Tableaux extraits** (pour vérifier la lecture des tableaux).

Quand plusieurs rapports sont analysés ensemble, un **tableau de bord consolidé** récapitule tous les EPN : délais, taux de conformité, rubriques absentes, anomalies, conformité au décret, concordance avec la situation d'exécution et suite à donner.

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

### 1. Interface web (recommandée pour les Chargés d'Études)

```bash
streamlit run app.py
```

Le navigateur s'ouvre. Il suffit ensuite de déposer les rapports (et, si vous les avez, les décrets de création et la ou les situations d'exécution), de saisir les dates de réception, de cliquer sur **Lancer l'analyse** et de télécharger les fichiers d'analyse (et le tableau de bord s'il y a plusieurs rapports). Tout se passe sur le poste : aucun document n'est envoyé sur Internet.

### 2. Ligne de commande

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
- **Situation d'exécution** : si sa date d'arrêté diffère de la fin de la période, l'outil le signale et les écarts sont classés « mineurs », car ils peuvent provenir du décalage de date.
- **Signature** : la présence d'une date et du nom du CB est vérifiée automatiquement. La signature manuscrite et le cachet restent à contrôler visuellement (statut « À vérifier »).
- **Grille Excel et canevas 2023** : la grille actuelle ne reprend pas certaines rubriques du canevas 2023 (III Analyse de la performance, IV.5 SNT, VIII Gestion des risques, IX Autres points, annonce du plan). L'outil les contrôle quand même et les présente dans l'onglet « Contrôle structure ». Par ailleurs, dans la grille, les lignes « Gouvernance » s'intitulent « Contrôle de gestion / Contrôle de trésorerie » alors que le canevas prévoit « COGES / Organes de supervision » et « Comité de trésorerie » : l'outil les traite au sens du canevas. Les libellés des tableaux 1 et 2 sont aussi inversés par rapport au canevas : chaque tableau est rattaché à la ligne de la grille qui porte le même contenu.

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
app.py           interface web (Streamlit)
config/          paramètres et référentiel des EPN
modeles/         fichier d'analyse de la DCB
exemples/        générateur de rapports fictifs pour les tests
tests/           tests automatisés
```
