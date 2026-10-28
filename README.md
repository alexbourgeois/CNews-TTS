# CNews-TTS

Enregistre en continu le son du direct de CNews et le transcrit en texte horodaté avec Whisper, pour l'analyse de fréquence de mots.

Deux commandes indépendantes :

- **`capture`** tourne en permanence et enregistre le direct en fichiers audio de 10 minutes ;
- **`transcribe`** se lance de temps en temps : elle transcrit tout l'audio en attente, puis supprime l'audio transcrit.

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

La capture se relance seule si le flux coupe (réseau, jeton expiré, flux figé), avec une attente croissante entre les essais (5 s à 5 min).

**PC portable : empêchez la mise en veille** (Paramètres › Système › Alimentation › « Mettre en veille après » : Jamais, au moins sur secteur). Une mise en veille arrête l'enregistrement ; au réveil la capture repart, et le trou apparaît dans la couverture.

### Transcription

```powershell
.\.venv\Scripts\python -m cnews_tts transcribe
```

À lancer quand vous voulez, y compris pendant que la capture tourne. Elle traite les fichiers du plus ancien au plus récent, affiche la vitesse obtenue, puis s'arrête. On peut l'interrompre à tout moment : rien n'est perdu ni transcrit deux fois. Un fichier illisible est signalé, laissé en place et retenté au lancement suivant.

### Couverture

```powershell
.\.venv\Scripts\python -m cnews_tts coverage
.\.venv\Scripts\python -m cnews_tts coverage --since 2026-10-28
```

Affiche la période enregistrée, le pourcentage couvert et chaque trou (heure de Paris). La cause d'un trou se trouve dans `data/logs/capture.log` à la même heure. Tenez compte des trous quand vous comparez des fréquences entre périodes.

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
- Les **noms propres** sont parfois mal orthographiés (ex. « Didier von Kovlert » pour Van Cauwelaert).
- Les heures sont celles de réception du flux : quelques dizaines de secondes de retard sur la diffusion TV, et les noms de fichiers peuvent être décalés de quelques secondes par rapport à l'heure ronde.
- Les phrases que Whisper invente sur les silences et la musique (« Sous-titrage ST' 501 »…) sont retirées ; leur nombre est indiqué dans le journal de transcription. La liste est modifiable dans `config.toml`.
- Pour lire le flux Dailymotion, **yt-dlp se fait passer pour un navigateur** (module `curl_cffi`). C'est un choix délibéré : sans cela Dailymotion refuse l'accès. Cela peut cesser de fonctionner si Dailymotion renforce sa protection.

## Réglages (`config.toml`)

| Clé | Rôle |
|---|---|
| `capture.video_id` | Direct Dailymotion : `x3b68jn` (Live CNEWS) ; secours : `x5idxxp` |
| `capture.segment_minutes` | Durée des fichiers audio (10) |
| `capture.stall_timeout_s` | Relance si le flux est figé depuis ce délai (120 s) |
| `capture.drift_tolerance_s` | Relance si l'horloge et le flux divergent de plus de ce délai (120 s) |
| `transcribe.model` | `large-v3` ; `large-v3-turbo` si la vitesse manque |
| `transcribe.device` / `compute_type` | `cuda` / `float16` ; sans carte NVIDIA : `cpu` / `int8` avec un modèle plus petit (`small`, `medium`), nettement moins précis et sans doute trop lent pour suivre le direct |
| `transcribe.hallucination_blacklist` | Phrases retirées de la sortie |

## Fichiers

```
data/
  work/<run>/          audio en cours d'écriture (ne pas toucher)
  audio/               audio terminé, en attente de transcription
  transcripts/         une transcription par jour
  coverage.csv         intervalles enregistrés
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
