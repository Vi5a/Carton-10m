# Analyse de cartons – Pistolet 10 m : version Android

Même analyse que la version PC (même code de détection et de calcul), avec une interface tactile.

- Les photos sont **choisies dans la galerie** du téléphone (choix multiple).
- L'application **n'utilise pas l'appareil photo** et ne demande **aucune permission**.
- Les exports vont dans **Images › AnalyseCartons** (image de la séance) et **Téléchargements › AnalyseCartons** (CSV). Un bouton **Partager** permet ensuite d'envoyer le fichier par mail, WhatsApp, etc.

## Obtenir l'APK (compilation gratuite par GitHub, une seule fois)

Un APK se compile sous Linux avec les outils Android. Le plus simple est de laisser GitHub le faire : le fichier `.github/workflows/build-apk.yml` contient toute la procédure.

1. Créez un compte sur github.com (gratuit), puis **New repository**, par exemple `analyse-cartons`. Il peut être **privé**.
2. Mettez **le contenu de ce dossier** à la racine du dépôt, y compris le dossier caché `.github` :
   - avec GitHub Desktop ou `git` : copiez les fichiers dans le dépôt, puis *commit* et *push* ;
   - ou par le site : **Add file › Upload files** et glissez tous les fichiers. Si le dossier `.github` n'est pas pris en compte (dossier caché), faites **Add file › Create new file**, tapez le nom `.github/workflows/build-apk.yml`, collez-y le contenu du fichier, puis validez.
3. La compilation démarre toute seule, onglet **Actions**. La **première fois elle dure environ 1 h** (OpenCV est compilé pour Android). Les suivantes prennent environ 10 min grâce au cache.
4. Quand c'est vert ✔, l'APK est dans l'onglet **Releases** du dépôt (`AnalyseCartons-N.apk`). Il est aussi dans l'onglet **Actions** › la compilation › *Artifacts*, sous forme de zip.

Si la compilation échoue (croix rouge), ouvrez-la, copiez les dernières lignes du journal et envoyez-les-moi.

## Installer sur le téléphone

1. Sur le téléphone, ouvrez la page **Releases** du dépôt (connecté à GitHub si le dépôt est privé) et touchez le fichier `.apk`.
2. Android demande d'**autoriser l'installation depuis cette source** (navigateur ou gestionnaire de fichiers) : acceptez.
3. Installez. Play Protect peut avertir d'une « application inconnue », c'est normal pour une application qui ne vient pas du Play Store : choisissez « Installer quand même ».

Il faut Android 7 ou plus récent, sur un téléphone 64 bits (tous les téléphones depuis 2017 environ).

## Utilisation

Barre du bas : **Cartons**, **Carton**, **Séance**. Le bouton retour d'Android revient à la liste.

**Cartons**
- Titre de la séance, nombre de **plombs par carton**, puis **Ajouter des photos (galerie)**. L'analyse prend quelques secondes par carton.
- La liste affiche pour chaque carton le nombre de plombs trouvés / tirés (en rouge si différent) et le score. Touchez un carton pour l'ouvrir.
- **Sensibilité** + **Redétecter tout** si des trous ne sont pas vus (augmenter) ou si de faux trous apparaissent (diminuer).

**Carton** (corriger la détection)
- Deux doigts : zoom et déplacement. Double-toucher : vue entière. `<` `>` : carton précédent / suivant.
- Touchez un plomb pour le **sélectionner**, puis **glissez-le** pour le déplacer, ou **Supprimer**.
- **+ Ajouter** puis touchez l'emplacement d'un plomb manquant.
- `−` `+` : nombre de plombs tirés sur ce carton. La détection est relancée.
- **Calibrer** si le visuel n'est pas trouvé : touchez 6 à 10 points sur le bord du visuel noir, puis **Valider**.
- **Annuler** revient en arrière (toutes les modifications, y compris celles de l'écran Séance).

**Séance** (analyse)
- Image globale : tous les plombs (une couleur par carton), centre fictif (croix rouge), score entier et au dixième. La ligne du centre fictif se termine par la valeur au dixième du centre fictif.
- Touchez un impact puis **Ignorer dans l'analyse** pour écarter une erreur flagrante. L'impact reste **compté dans le score**, mais sort du centre fictif, du rayon moyen et du groupement. Même bouton pour le **réintégrer**.
- **Exporter l'image** / **Exporter CSV**, puis **Partager** si besoin.

## Conseils photo

Les mêmes que sur PC :
- carton posé sur un **fond de couleur moyenne** (bleu, rouge, vert, gris), ni blanc ni noir ;
- photo prise bien **en face** ;
- carton **à l'endroit** ;
- bonne lumière, sans reflet.

## Essayer sur ordinateur

```
pip install kivy numpy opencv-python pillow
python main.py
```
La même interface s'ouvre dans une fenêtre de format téléphone. Les photos se choisissent alors dans un explorateur de fichiers, et les exports vont dans `~/AnalyseCartons`.

## Fichiers

| Fichier | Contenu |
|---|---|
| `main.py` | interface tactile (Kivy) |
| `android_io.py` | galerie, enregistrement et partage sous Android |
| `cible.py`, `detection.py`, `rendu.py` | calculs et analyse d'image, **identiques à la version PC** |
| `buildozer.spec` | configuration de l'APK (aucune permission, Android 7+, arm64) |
| `.github/workflows/build-apk.yml` | compilation automatique sur GitHub |
| `icone.png`, `presplash.png` | icône et écran de démarrage |
