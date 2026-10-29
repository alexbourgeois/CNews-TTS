# CNews-TTS

Enregistre en continu le son du direct de CNews et le transcrit en texte horodaté avec Whisper, pour l'analyse de fréquence de mots.

Deux commandes indépendantes :

- **`capture`** tourne en permanence et enregistre le direct en fichiers audio d'1 minute ;
- **`transcribe`** transcrit tout l'audio en attente puis supprime l'audio transcrit — de temps en temps, ou en continu avec `--watch` ;
- **`follow`** affiche le texte au fur et à mesure, avec 1 à 2 minutes de retard sur le direct.

## Prérequis

- Windows, Python 3.12, `ffmpeg` et `ffprobe` dans le `PATH`.
- Une carte graphique NVIDIA (testé sur RTX 3070 Laptop 8 Go : ~9× plus rapide que le temps réel). Sans carte NVIDIA, voir « Réglages ».
- Une connexion internet permanente : le son seul représente ~1,4 Go par jour.

## Installation

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

Le premier lancement de `transcribe` télécharge le modèle Whisper (~3 Go). Si ce téléchargement échoue (« connexion fermée par l'hôte distant »), relancez simplement la commande : il reprend où il s'était arrêté.

## Utilisation

### Capture

```powershell
.\.venv\Scripts\python -m cnews_tts capture
```

Laissez la fenêtre ouverte. **Ctrl+C** arrête proprement (le dernier morceau d'audio est conservé). Si la fenêtre est fermée ou si le PC plante, les morceaux en cours sont récupérés au lancement suivant.

La capture se relance seule si le flux coupe (réseau, jeton expiré, flux figé) ou après une erreur inattendue, avec une attente croissante entre les essais (5 s à 5 min). Les erreurs sont détaillées dans `data/logs/capture.log`.

**PC portable : empêchez la mise en veille** (Paramètres › Système › Alimentation › « Mettre en veille après » : Jamais, au moins sur secteur). Une mise en veille arrête l'enregistrement ; au réveil la capture repart, et le trou apparaît dans la couverture.

### Transcription

```powershell
.\.venv\Scripts\python -m cnews_tts transcribe
```

À lancer quand vous voulez, y compris pendant que la capture tourne. Elle traite les fichiers du plus ancien au plus récent, affiche la vitesse obtenue, puis s'arrête. On peut l'interrompre à tout moment : rien n'est perdu ni transcrit deux fois. Un fichier illisible est signalé, laissé en place et retenté au lancement suivant.

En continu, dans une deuxième fenêtre :

```powershell
.\.venv\Scripts\python -m cnews_tts transcribe --watch
```

Le modèle reste chargé sur la carte graphique (~3-4 Go de mémoire vidéo) et chaque fichier est transcrit dès qu'il est terminé. Ctrl+C pour arrêter.

### Direct à quelques secondes : `live`

```powershell
.\.venv\Scripts\python -m cnews_tts live --alert
```

Une seule commande, indépendante de `capture` / `transcribe` : ffmpeg envoie le son du direct directement à Whisper (`large-v3-turbo`, plus rapide), découpé en mémoire aux pauses de parole (5 s au plus). Chaque phrase s'affiche **5 à 8 s après son début** ; `--alert` joue le son et marque la ligne quand un mot de la liste `[alert]` est prononcé. `--speak` lit chaque phrase à voix haute, sans l'heure ni le marqueur d'alerte, avec une voix neuronale française (Piper, hors ligne, calculée sur le processeur ~0,2 s par phrase) ; la voix (~60 Mo) est téléchargée dans `data/voices/` au premier lancement. Si la lecture prend du retard, les phrases les plus anciennes sont sautées pour rester au direct. Débit : `LENGTH_SCALE` dans `speech.py` (< 1 plus rapide) ; autre voix : `[speech] voice` dans `config.toml`. `--condense` n'affiche (et ne lit) que les mots-clés de chaque phrase : noms, noms propres, verbes à l'infinitif, adjectifs et nombres, sans articles, pronoms, prépositions, ni « être » / « avoir » (analyse grammaticale spaCy, hors ligne) ; l'alerte, elle, porte toujours sur la phrase entière. Exemple : « Ce n'est pas parce qu'il a 18 ans… » → `devoir éduquer enfant bout 18 ans responsable enfant`. `--color` colore chaque mot selon sa charge : rouge pour les mots négatifs, vert pour les positifs, d'autant plus vif que le mot est chargé (« guerre », « viol » en rouge vif ; « victoire », « formidable » en vert vif) ; les mots neutres gardent la couleur normale. Les notes viennent du lexique VADER traduit en français (~9 000 mots, notes de -4 à +4) : elles jugent le mot seul, sans le contexte (« pas grave » colore « grave » en rouge), et certaines traductions sont approximatives. Se combine avec `--condense`. `--window` ouvre une fenêtre où chaque mot tombe en bloc coloré (même code couleur que `--color`, gris-bleu si neutre) : les blocs rebondissent sur les bords, s'empilent, et s'effacent au bout de 10 s (`[window] lifetime_s` dans `config.toml`). On peut attraper un bloc à la souris, le déplacer et le lancer ; un bloc tenu ne disparaît pas. La fenêtre se redimensionne ; la fermer arrête `live`. À combiner avec `--condense` pour n'y voir que les mots-clés : `live --condense --window`. Rien n'est enregistré : pour le corpus d'analyse, gardez `capture` + `transcribe` (meilleure qualité, avec contexte). Le flux Dailymotion a lui-même quelques dizaines de secondes de retard sur la diffusion TV.

### Jeu multijoueur : `live --game`

```powershell
.\.venv\Scripts\python -m cnews_tts live --condense --game
```

Ouvre la fenêtre des mots (à mettre sur un grand écran) et un petit serveur web. Les joueurs, sur le même Wi-Fi / réseau, ouvrent dans leur navigateur l'adresse affichée en haut de la fenêtre (ex. `http://192.168.1.20:8000`), choisissent un nom, et n'ont qu'un champ texte : ils regardent l'écran et tapent les mots qui tombent pour les effacer (Entrée ou espace ; accents et majuscules ignorés).

- **1 point** par mot effacé ; un mot qui disparaît sans avoir été tapé compte comme « raté ».
- **Mot rouge** : il explose (souffle les blocs voisins) et enlève des PV à tous les **autres** joueurs, d'autant plus qu'il est négatif (« guerre » : 23 PV).
- **Mot vert** : il rend des PV à celui qui l'a tapé (100 au plus).
- **0 PV** : KO pendant 10 s, puis retour avec 100 PV.

Pas de compte ni de mot de passe : le nom suffit, et le reprendre (même depuis un autre appareil) reprend la partie de ce joueur. Au premier lancement, Windows demande s'il faut autoriser Python sur le réseau : acceptez pour les **réseaux privés**. Port : `[game] port` dans `config.toml` (8000).

### Suivre le texte transcrit par `transcribe --watch`

Avec `capture` et `transcribe --watch` lancés, dans une troisième fenêtre :

```powershell
.\.venv\Scripts\python -m cnews_tts follow
```

Affiche les 10 dernières phrases (`--lines N` pour en voir plus), puis chaque nouvelle phrase dès qu'elle est transcrite :

```
19:39:09  Et si on sait se persuader que le nouveau monde c'est celui de cette violence, on est foutu.
19:39:15  Merci beaucoup Didier von Kovlert, écrivain, prix Goncourt…
```

**Alerte sonore** : `follow --alert` (comme `live --alert`) joue un son et marque la ligne (`<<< immigr`) quand un mot lié à l'immigration est prononcé. La liste est dans la section `[alert]` de `config.toml` (accents et majuscules ignorés ; `immigr` couvre immigration, immigrés…). Pour votre propre son, indiquez un fichier `.wav` dans `sound` de cette section (chemin relatif à `config.toml`, ex. `sound = "alerte.wav"`) ; sinon c'est le son d'alerte de Windows.

Le texte arrive par blocs d'une minute, 1 à 2 minutes après la diffusion. Pour moins de fichiers (et moins de coupures, voir plus bas), augmentez `segment_minutes` dans `config.toml` : le retard augmente d'autant.

### Couverture

```powershell
.\.venv\Scripts\python -m cnews_tts coverage
.\.venv\Scripts\python -m cnews_tts coverage --since 2026-10-28
```

Affiche la période enregistrée, le pourcentage couvert et chaque trou (heure de Paris). La cause d'un trou se trouve dans `data/logs/capture.log` à la même heure. Tenez compte des trous quand vous comparez des fréquences entre périodes.

Limite : si la connexion saute quelques secondes sans couper l'enregistrement, ffmpeg recolle l'audio sans laisser de trou. La capture le détecte dès que le décalage dépasse 30 s (`drift_tolerance_s`) et redémarre ; les micro-coupures plus courtes n'apparaissent pas dans la couverture.

**Ne gardez pas `coverage.csv` ni les `.jsonl` ouverts dans Excel** : Excel verrouille les fichiers. La capture ne s'arrête pas pour autant (elle réessaie et le note dans le journal), mais les fichiers audio terminés attendent dans `data/work/` tant que le verrou dure.

## Les transcriptions

Un fichier par jour : `data/transcripts/AAAA-MM-JJ.jsonl`, une ligne JSON par phrase.

```json
{"start": "2026-10-28T19:39:09.420+01:00", "end": "2026-10-28T19:39:15.980+01:00", "text": "Et si on sait se persuader que le nouveau monde c'est celui de cette violence, on est foutu.", "source": "20261028T183849Z.aac", "avg_logprob": -0.084, "no_speech_prob": 0.001, "compression_ratio": 1.582}
```

- `start` / `end` : heure de Paris avec décalage horaire (sans ambiguïté au changement d'heure).
- `source` : fichier audio d'origine (nom en heure UTC).
- `avg_logprob`, `no_speech_prob`, `compression_ratio` : indices de confiance de Whisper, pour filtrer si besoin (`avg_logprob` très bas ou `compression_ratio` > 2,4 = transcription douteuse).
- Tout le texte d'un fichier audio va dans le jour où ce fichier commence.

Exemple de comptage de mots par jour (`pip install pandas`) :

```python
import glob
import pandas as pd

df = pd.concat(pd.read_json(f, lines=True) for f in glob.glob("data/transcripts/*.jsonl"))
df["jour"] = df["start"].astype(str).str[:10]
mots = df.assign(mot=df["text"].str.lower().str.findall(r"\w+")).explode("mot")
print(mots.groupby("jour")["mot"].value_counts().groupby(level=0).head(20))
```

## À savoir pour l'analyse

- **Les publicités et jingles parlés sont transcrits** comme le reste.
- L'audio est découpé chaque minute : **un mot à cheval sur deux fichiers peut être perdu ou écorché**, soit au pire un mot par minute (moins de 1 % du texte).
- Les **noms propres** sont parfois mal orthographiés (ex. « Didier von Kovlert » pour Van Cauwelaert).
- Les heures sont celles de réception du flux : quelques dizaines de secondes de retard sur la diffusion TV, et les noms de fichiers peuvent être décalés de quelques secondes par rapport à l'heure ronde.
- Les phrases que Whisper invente sur les silences et la musique (« Sous-titrage ST' 501 »…) sont retirées ; leur nombre est indiqué dans le journal de transcription. La liste est modifiable dans `config.toml`.
- Pour lire le flux Dailymotion, **yt-dlp se fait passer pour un navigateur** (module `curl_cffi`). C'est un choix délibéré : sans cela Dailymotion refuse l'accès. Cela peut cesser de fonctionner si Dailymotion renforce sa protection.

## Réglages (`config.toml`)

| Clé | Rôle |
|---|---|
| `capture.video_id` | Direct Dailymotion : `x3b68jn` (Live CNEWS) ; secours : `x5idxxp` |
| `capture.segment_minutes` | Durée des fichiers audio (1) : plus court = texte plus tôt, plus long = moins de mots coupés |
| `capture.stall_timeout_s` | Relance si le flux est figé depuis ce délai (120 s) |
| `capture.drift_tolerance_s` | Relance si l'horloge et le flux divergent de plus de ce délai (30 s) |
| `transcribe.model` | `large-v3` ; `large-v3-turbo` si la vitesse manque |
| `transcribe.device` / `compute_type` | `cuda` / `float16` ; sans carte NVIDIA : `cpu` / `int8` avec un modèle plus petit (`small`, `medium`), nettement moins précis et sans doute trop lent pour suivre le direct |
| `transcribe.hallucination_blacklist` | Phrases retirées de la sortie |
| `alert.keywords` / `alert.sound` | Mots déclenchant l'alerte ; son `.wav` joué (facultatif) |
| `speech.voice` | Voix Piper de `live --speak` (`fr_FR-siwis-medium`) |

## Fichiers

```
data/
  work/<run>/          audio en cours d'écriture (ne pas toucher)
  audio/               audio terminé, en attente de transcription
  transcripts/         une transcription par jour
  coverage.csv         intervalles enregistrés
  voices/              voix de live --speak
  logs/                capture.log, transcribe.log, ffmpeg.log
```

## Dépannage

- **« Impossible de résoudre le flux »** en boucle : mettez yt-dlp à jour (`.\.venv\Scripts\python -m pip install -U "yt-dlp[curl-cffi]"`), ou essayez le flux de secours dans `config.toml`.
- **Erreurs de ffmpeg** : voir `data/logs/ffmpeg.log` (les messages « Found duplicated MOOV Atom » sont normaux).
- **`av` / `metadata_errors`** : faster-whisper 1.2.1 exige PyAV < 19 (déjà fixé dans `pyproject.toml`).

## Vérifications à faire soi-même

Testé pendant le développement : capture réelle, reprise après arrêt forcé de ffmpeg, récupération du dernier morceau, transcription sur GPU (~9× le temps réel). Restent à vérifier sur la durée :

1. Laisser la capture tourner **24 h**, puis lancer `transcribe` : ~24 h de texte, `coverage` montre les éventuels trous.
2. **Couper le Wi-Fi** quelques minutes pendant la capture : elle reprend seule et le trou apparaît dans `coverage`.
3. **Ctrl+C** pendant la capture : le dernier morceau est dans `data/audio/`.
4. **Fermer la fenêtre** de `transcribe` en plein travail, puis la relancer : aucune perte, aucun doublon.
