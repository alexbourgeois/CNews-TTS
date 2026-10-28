# Transcription continue du direct CNews — conception

Date : 2026-10-28

## Intention

Constituer, en continu, un corpus texte de tout ce qui se dit sur le direct de CNews, afin que l'utilisateur puisse ensuite faire de l'**analyse de fréquence de mots** (évolution dans le temps : par jour, par tranche horaire).

Ce projet s'arrête à la production des transcriptions horodatées. L'analyse elle-même est faite par l'utilisateur, à part.

## Objectifs

1. **Capture continue** : un programme, lancé par l'utilisateur et laissé tourner sur ce PC, enregistre l'audio du direct CNews en continu, découpé en fichiers de quelques minutes horodatés.
2. **Transcription par lots** : un second programme, lancé périodiquement par l'utilisateur à la main, transcrit tous les fichiers audio terminés et pas encore traités, puis supprime l'audio correspondant.
3. **Sortie exploitable** : des transcriptions en texte, chaque segment portant son heure absolue (date + heure), faciles à charger pour compter des mots par période.
4. **Couverture connue** : on sait à tout moment quelles périodes ont été captées et lesquelles manquent (coupure réseau, PC en veille, flux tombé), pour que les comparaisons de fréquences entre périodes ne soient pas faussées par des trous invisibles.

## Non-objectifs

- L'analyse de fréquence de mots elle-même (fait par l'utilisateur).
- Le temps réel : la transcription peut avoir du retard, tant que chaque lancement rattrape le stock.
- Identifier qui parle (diarisation) : confirmé par l'utilisateur, pas besoin. Ce ne sera pas rattrapable après coup puisque l'audio est supprimé.
- Identifier quelle émission est diffusée : reconstituable plus tard par l'utilisateur en croisant les horodatages avec la grille des programmes.
- Retirer les publicités / jingles : la pub parlée sera transcrite comme le reste. *(Choix de Claude ; à signaler dans le README pour que l'utilisateur en tienne compte dans ses comptages.)*
- Lancement automatique au démarrage de Windows, service, tâche planifiée : l'utilisateur lance les programmes lui-même.
- Capturer CNEWS PRIME ou d'autres chaînes (l'identifiant du flux reste toutefois configurable).

## Anti-objectifs (échec même si « ça marche »)

- **Texte inventé dans le corpus** : Whisper hallucine des phrases sur les silences / la musique (en français, typiquement « Sous-titrage ST' 501 », « Sous-titres réalisés par la communauté d'Amara.org », « Merci d'avoir regardé cette vidéo »). Ces phrases fausseraient directement les fréquences. Elles doivent être évitées (VAD) et filtrées.
- **Trous silencieux** : une capture qui s'arrête sans que ce soit visible nulle part.
- **Audio perdu avant transcription** : un fichier audio ne doit jamais être supprimé tant que sa transcription n'est pas écrite de façon complète sur disque.
- **Fichier transcrit à moitié** : la transcription ne doit jamais traiter le fichier audio en cours d'écriture par la capture.
- **Contournement de protections anti-bot** : ne pas chercher à contourner Cloudflare ou des protections similaires (voir « Source du flux »).

## Contraintes

- **Machine** : ce PC Windows 11 portable — AMD Ryzen 7 5800H (8 cœurs), 28 Go de RAM, **NVIDIA RTX 3070 Laptop 8 Go** (pilote 610.88), 152 Go libres sur F:.
- **Logiciels présents** : Python 3.12.2, ffmpeg (build gyan.dev de 2022-05). yt-dlp n'est pas installé.
- **Langage** : Python. Dépendances isolées dans un environnement virtuel du projet.
- **Réseau** : connexion suffisante et sans limite de volume (confirmé par l'utilisateur). Les variantes HLS de Dailymotion contiennent probablement image + son ensemble : il faut alors télécharger de la vidéo pour obtenir l'audio, plusieurs Go/jour. Toujours choisir la **variante au débit le plus bas** (ou une piste audio seule si le flux en propose une).
- **PC portable** : la mise en veille arrête la capture. On ne la gère pas, mais elle doit apparaître comme un trou dans la couverture.
- **Débit de transcription** : en moyenne, la transcription doit aller nettement plus vite que le temps réel, sinon le stock grossit sans fin. Cible : au moins 5× le temps réel sur cette carte graphique.

## Source du flux (reconnaissance faite le 2026-10-28)

- `https://www.cnews.fr/le-direct` est derrière une page de vérification Cloudflare (« Just a moment… ») : **on n'utilise pas cette page**.
- Le direct est publié par le compte Dailymotion officiel de CNews :
  - `x3b68jn` — « Live CNEWS » (**flux principal**)
  - `x5idxxp` — « Live CNEWS (Backup stream) »
  - `x9u4hka` — « Live CNEWS PRIME » (hors périmètre)
  - Vérifiable via `https://api.dailymotion.com/user/cnews/videos?fields=id,title,mode,onair&flags=live_onair`.
- Les métadonnées du lecteur Dailymotion renvoient une URL HLS signée (`cdndirector.dailymotion.com/...m3u8?sec=...`) qui **expire** ; un `curl` direct sur cette URL a renvoyé 403.
- **Décision** : résoudre l'URL du flux avec **yt-dlp** (extracteur Dailymotion standard), et la re-résoudre à chaque (re)démarrage de la capture.
- **Première étape de la construction** : vérifier que yt-dlp + ffmpeg récupèrent ~30 s d'audio de `x3b68jn`. Si ça échoue, s'arrêter et en parler à l'utilisateur avant toute autre piste — en particulier ne pas tenter de se faire passer pour un navigateur pour franchir une protection.

## Conception

Deux programmes indépendants qui communiquent uniquement par le disque.

```
[Dailymotion live x3b68jn]
        │  yt-dlp (résout l'URL HLS)
        ▼
   capture  ──ffmpeg (audio seul, découpé)──►  audio/…  (fichiers terminés + fichier en cours)
                                                  │
                         transcribe (lancé à la main de temps en temps)
                                                  │  faster-whisper large-v3, GPU
                                                  ▼
                                     transcripts/…  puis suppression de l'audio
```

### Capture

- Résout l'URL HLS du direct via yt-dlp, puis lance ffmpeg pour **extraire uniquement l'audio** et le **découper en fichiers de durée fixe** (10 min par défaut, configurable).
- Découpage **aligné sur l'horloge** (…:00, …:10, …:20) et nom de fichier contenant l'heure de début, pour que chaque fichier corresponde à une tranche horaire nette.
- Les horodatages doivent être **non ambigus** (UTC, ou heure locale avec décalage explicite) pour éviter les doublons/chevauchements lors des changements d'heure.
- **Résilience** : quand ffmpeg s'arrête (jeton expiré, coupure réseau, flux tombé), la capture re-résout l'URL et redémarre, avec un délai croissant entre les tentatives. Elle tourne jusqu'à ce que l'utilisateur l'arrête (Ctrl+C), et s'arrête proprement (le dernier fichier est clos correctement).
- **Couverture** : la capture tient un journal lisible des intervalles effectivement enregistrés et des interruptions (heure de début, de fin, cause si connue).
- **Marquage des fichiers terminés** : la capture doit rendre explicite quels fichiers sont complets (par exemple liste de segments terminés tenue par ffmpeg, ou écriture sous un nom temporaire puis renommage). La transcription ne lit que ceux-là.
- Préférence : copier le flux audio d'origine **sans ré-encodage** (charge CPU quasi nulle, aucune perte). Environ 0,7 à 1,4 Go/jour d'audio en attente de transcription.

### Transcription

- **Moteur** : faster-whisper, modèle **large-v3**, sur le GPU (CUDA), langue forcée **français**. *(Choix de Claude : meilleure qualité disponible, et la RTX 3070 8 Go la fait tourner bien plus vite que le temps réel.)* Le modèle est configurable (ex. `large-v3-turbo` si la vitesse manque).
- **Anti-hallucination** : filtre VAD activé (pour ne pas transcrire silences et musique), ne pas conditionner sur le texte précédent (évite les boucles de répétition), et une **liste noire configurable** des phrases d'hallucination connues, retirées de la sortie et comptées dans le journal.
- Traite tous les fichiers audio terminés et non encore transcrits, **du plus ancien au plus récent**, puis s'arrête. Relançable sans risque à tout moment (idempotent) : rien n'est transcrit deux fois, rien n'est sauté.
- **Ordre de sûreté** : écrire la transcription complète (écriture atomique : fichier temporaire puis renommage), **puis seulement** supprimer l'audio. En cas de plantage au milieu, le fichier audio est simplement retraité au lancement suivant.
- Affiche la progression et, à la fin, le débit obtenu (× temps réel) et le stock restant.
- Peut tourner pendant que la capture tourne.

### Format de sortie

*(Choix de Claude.)* Fichiers **JSON Lines**, un fichier par jour, une ligne par segment Whisper :

```json
{"start": "2026-10-28T19:00:03.120+01:00", "end": "2026-10-28T19:00:07.800+01:00", "text": "…", "source": "<fichier audio d'origine>"}
```

- `start` / `end` : heure absolue = heure de début du fichier audio + décalage du segment, en ISO 8601 avec décalage horaire, heure de Paris.
- Champs de confiance de Whisper en plus (ex. `avg_logprob`, `no_speech_prob`) pour permettre un filtrage ultérieur.
- Format choisi parce qu'il se charge directement en pandas / se lit ligne à ligne, et permet de regrouper par heure ou par jour.
- Volume indicatif : ~1 à 2 Mo de texte par jour.

## Critères de réussite

1. Après ~24 h de capture puis un lancement de la transcription : environ 24 h de texte en français lisible, horodaté, sans phrases d'hallucination de la liste noire.
2. Le journal de couverture montre précisément les trous éventuels.
3. Débit de transcription ≥ 5× temps réel sur la RTX 3070.
4. Couper le réseau quelques minutes pendant la capture : elle reprend seule, et le trou apparaît dans la couverture.
5. Tuer la transcription au milieu puis la relancer : aucune perte, aucun doublon.

## Laissé au constructeur

- Organisation du code, des dossiers (`audio/`, `transcripts/`, journaux), configuration (fichier ou arguments).
- Conteneur audio exact et mécanisme de marquage des fichiers terminés.
- Bascule éventuelle sur le flux de secours `x5idxxp` en cas d'échec répété du principal.
- Installation de CUDA/cuDNN pour faster-whisper sous Windows (CTranslate2 attend CUDA 12 + cuDNN 9 ; les DLL doivent être trouvables, par exemple via les paquets pip `nvidia-cublas-cu12` / `nvidia-cudnn-cu12`). Le ffmpeg de 2022 suffit a priori ; le mettre à jour seulement si nécessaire.
- Tests : tests unitaires sur ce qui est logique pure (calcul des horodatages, détection des fichiers terminés, filtrage des hallucinations, idempotence) ; vérification manuelle pour la capture réelle.
- README court : comment installer, lancer la capture, lancer la transcription, lire la couverture, et la mise en garde sur les pubs transcrites.
