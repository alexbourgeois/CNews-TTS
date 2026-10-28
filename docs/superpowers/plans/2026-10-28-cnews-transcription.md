# Transcription continue du direct CNews — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** deux commandes Python : `capture` enregistre en continu l'audio du direct CNews (Dailymotion) en fichiers de 10 min horodatés, et `transcribe` (lancée à la main) les transcrit avec faster-whisper en JSON Lines par jour puis supprime l'audio.

**Architecture :** les deux programmes ne communiquent que par le disque. `capture` résout l'URL HLS avec yt-dlp, lance ffmpeg (audio copié sans ré-encodage, muxer `segment` calé sur l'horloge) dans un dossier de travail par « run », et *promeut* chaque segment terminé vers `data/audio/<UTC>.aac` en notant l'intervalle dans `data/coverage.csv`. `transcribe` ne lit que `data/audio/`, écrit les transcriptions de façon atomique, puis supprime l'audio.

**Tech Stack :** Python 3.12, yt-dlp (API Python), ffmpeg/ffprobe (déjà installés), faster-whisper (CTranslate2, CUDA), tzdata, pytest.

**Spec :** [docs/superpowers/specs/2026-10-28-cnews-transcription-design.md](../specs/2026-10-28-cnews-transcription-design.md)

## Global Constraints

- Windows 11, PowerShell ; Python 3.12 dans `.venv` à la racine du projet ; paquet `src/cnews_tts`, tests dans `tests/`.
- Source : Dailymotion `x3b68jn` via yt-dlp, sélecteur de format `bestaudio/worst`. **Ne jamais** charger cnews.fr ni contourner une protection anti-bot (pas d'User-Agent forgé à la main) : seuls les en-têtes fournis par yt-dlp sont transmis à ffmpeg.
- Segments de **600 s**, calés sur l'horloge (`-segment_atclocktime 1`), audio copié sans ré-encodage (`-c:a copy`, ADTS `.aac`).
- Noms de fichiers et de runs en **UTC** : `YYYYMMDDTHHMMSSZ` (ex. `20261028T180000Z.aac`).
- Horodatages de sortie : ISO 8601 à la milliseconde avec décalage, fuseau `Europe/Paris` (ex. `2026-10-28T19:00:03.120+01:00`). Le paquet `tzdata` est obligatoire sous Windows.
- Whisper : modèle `large-v3`, `device="cuda"`, `compute_type="float16"`, `language="fr"`, `vad_filter=True`, `condition_on_previous_text=False`.
- Un audio n'est supprimé **qu'après** écriture atomique (fichier `.tmp` puis `os.replace`) de sa transcription.
- `transcribe` ne lit **que** `data/audio/*.aac`, jamais `data/work/`.
- Débit de transcription cible ≥ **5× temps réel** sur la RTX 3070 Laptop.
- Messages console, journaux et README en **français**.

## Review Focus

1. **PC mis en veille pendant la capture** → au réveil, ffmpeg est arrêté en quelques secondes, un nouveau run démarre et le trou apparaît dans la couverture ; aucun texte n'est daté avec des heures de retard. (Tests `loop_was_suspended` / `is_drifted`, tâche 6.)
2. **Capture tuée brutalement** (fenêtre fermée, plantage) → au lancement suivant, les fichiers du run abandonné sont récupérés et promus, rien n'est perdu. (Test `recover_runs`, tâche 4.)
3. **Transcription lancée pendant que la capture écrit** → elle ne voit ni `data/work/` ni les `.tmp`. (Test `pending_audio`, tâche 4.)
4. **Fichier audio illisible** → la transcription le signale, le laisse en place, et continue avec les suivants. (Test `failed`, tâche 8.)
5. **Nuit du changement d'heure** (25 oct. 2026, 02:00–03:00 jouée deux fois) → noms de fichiers uniques, décalages `+02:00` puis `+01:00` corrects. (Test DST, tâche 2.)

---

## Structure des fichiers

```
pyproject.toml                 dépendances, pytest, paquet src/
config.toml                    réglages (valeurs ci-dessous)
.gitignore                     .venv/, data/, __pycache__/, *.egg-info/
README.md
src/cnews_tts/
  __init__.py
  __main__.py                  CLI : capture | transcribe | coverage
  config.py                    Config + load_config
  timeutil.py                  horodatages UTC / Paris
  coverage.py                  coverage.csv : écrire, lire, trous, rapport
  segments.py                  liste ffmpeg, promotion, récupération, pending_audio
  stream.py                    résolution yt-dlp → StreamInfo
  media.py                     commande ffmpeg, ffprobe, arrêt propre
  capture.py                   boucle de capture + détecteurs
  hallucinations.py            normalisation + liste noire
  transcripts.py               enregistrements, fichiers jour, écriture atomique
  transcribe.py                DLL CUDA, modèle, boucle de transcription
tests/ test_<module>.py        un fichier par module
data/ (ignoré par git)
  work/<run UTC>/seg_00000.aac, segments.csv     en cours d'écriture
  audio/<UTC>.aac                                terminés, à transcrire
  transcripts/<AAAA-MM-JJ>.jsonl
  coverage.csv
  logs/capture.log, transcribe.log, ffmpeg.log
```

---

### Task 1 : test du flux (gate)

But : prouver qu'on obtient l'audio du direct avant d'écrire du code produit. **Si une étape échoue, s'arrêter et rendre compte à l'utilisateur** (ne pas chercher d'autre contournement).

**Files :**
- Create : `.gitignore`
- Modify : `docs/superpowers/specs/2026-10-28-cnews-transcription-design.md` (ajout d'une section « Résultats du test du flux »)
- Script jetable dans le scratchpad de la session (pas dans le dépôt)

- [ ] **Step 1 : dépôt + venv**

```powershell
git init
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -U pip yt-dlp
```
Créer `.gitignore` (`.venv/`, `data/`, `__pycache__/`, `*.egg-info/`, `.pytest_cache/`).

- [ ] **Step 2 : lister les formats**

Run : `.\.venv\Scripts\yt-dlp -F https://www.dailymotion.com/video/x3b68jn`
Attendu : une liste de formats HLS (ex. `hls-380`, …). Noter s'il existe un format audio seul et le débit du plus léger.

- [ ] **Step 3 : capture de 30 s avec la vraie commande**

Script jetable : `yt_dlp.YoutubeDL({"format": "bestaudio/worst", "quiet": True}).extract_info(URL, download=False)` → `url`, `http_headers` ; puis ffmpeg avec exactement les options de la tâche 5 (`-segment_time 10`, plus `-t 30`) vers un dossier du scratchpad.
Attendu : 3–4 fichiers `seg_0000N.aac`, un `segments.csv` (`seg_00000.aac,<début>,<fin>` — noter si la colonne 1 est un nom de base et si le premier `<début>` est proche de 0), et `ffprobe -v error -show_entries stream=codec_name -of csv=p=0 seg_00001.aac` → `aac`. Écouter un fichier : c'est bien CNews.

- [ ] **Step 4 : consigner les résultats**

Ajouter à la spec une section « Résultats du test du flux (date) » : formats disponibles, format choisi et son débit (→ Go/jour), codec audio, en-têtes nécessaires ou non, contenu observé de `segments.csv`. Si un résultat contredit la tâche 4 ou 5 (ex. CSV avec chemins complets, premier début ≠ 0), ajuster ces tâches avant de continuer.

- [ ] **Step 5 : commit**

```powershell
git add .gitignore docs/
git commit -m "docs: conception, plan et résultats du test du flux CNews"
```

---

### Task 2 : squelette, configuration, horodatages

**Files :**
- Create : `pyproject.toml`, `config.toml`, `src/cnews_tts/__init__.py`, `src/cnews_tts/config.py`, `src/cnews_tts/timeutil.py`
- Test : `tests/test_config.py`, `tests/test_timeutil.py`

**Interfaces :**
- Produces :
  - `config.Config` (dataclass gelée) : `video_id: str`, `format_selector: str`, `segment_seconds: int`, `stall_timeout_s: float`, `drift_tolerance_s: float`, `data_dir: Path`, `model: str`, `device: str`, `compute_type: str`, `language: str`, `timezone: str`, `hallucination_blacklist: tuple[str, ...]` ; propriétés `work_dir`, `audio_dir`, `transcripts_dir`, `logs_dir` (= `data_dir/"work"` etc.), `coverage_csv` (= `data_dir/"coverage.csv"`).
  - `config.load_config(path: Path) -> Config` — `data_dir` relatif résolu par rapport au dossier du fichier ; `segment_seconds = segment_minutes * 60`.
  - `timeutil.format_stamp(dt: datetime) -> str` (UTC, secondes tronquées), `timeutil.parse_stamp(s: str) -> datetime` (UTC aware, `ValueError` sinon), `timeutil.to_local_iso(dt: datetime, tz: str) -> str`, `timeutil.local_day(dt: datetime, tz: str) -> str`, `timeutil.utc_now() -> datetime`.

- [ ] **Step 1 : `pyproject.toml` et `config.toml`**

`pyproject.toml` : paquet `cnews_tts` en layout `src/`, `requires-python = ">=3.12"`, dépendances `yt-dlp`, `faster-whisper`, `tzdata`, `nvidia-cublas-cu12`, `nvidia-cudnn-cu12>=9,<10` ; extra `dev = ["pytest"]` ; `[tool.pytest.ini_options] testpaths = ["tests"]`.

`config.toml` (valeurs exactes) :
```toml
[capture]
video_id = "x3b68jn"          # Live CNEWS (secours : "x5idxxp")
format = "bestaudio/worst"    # audio seul si dispo, sinon la variante la plus légère
segment_minutes = 10
stall_timeout_s = 120
drift_tolerance_s = 120

[paths]
data_dir = "data"

[transcribe]
model = "large-v3"
device = "cuda"
compute_type = "float16"
language = "fr"
timezone = "Europe/Paris"
hallucination_blacklist = [
  "Sous-titrage ST' 501",
  "Sous-titres réalisés par la communauté d'Amara.org",
  "Sous-titrage Société Radio-Canada",
  "Merci d'avoir regardé cette vidéo",
]
```

Run : `.\.venv\Scripts\python -m pip install -e .[dev]` → succès (télécharge faster-whisper et les DLL NVIDIA).

- [ ] **Step 2 : tests qui échouent**

```python
# tests/test_config.py
REPO = Path(__file__).resolve().parents[1]

def test_load_repo_config():
    cfg = load_config(REPO / "config.toml")
    assert cfg.video_id == "x3b68jn"
    assert cfg.format_selector == "bestaudio/worst"
    assert cfg.segment_seconds == 600
    assert cfg.data_dir == REPO / "data"
    assert cfg.audio_dir == REPO / "data" / "audio"
    assert cfg.coverage_csv == REPO / "data" / "coverage.csv"
    assert cfg.model == "large-v3" and cfg.language == "fr"
    assert "Sous-titrage ST' 501" in cfg.hallucination_blacklist
```
```python
# tests/test_timeutil.py
UTC = timezone.utc

def test_stamp_roundtrip():
    dt = datetime(2026, 10, 28, 18, 0, 0, tzinfo=UTC)
    assert format_stamp(dt) == "20261028T180000Z"
    assert parse_stamp("20261028T180000Z") == dt

def test_format_stamp_truncates_subseconds():
    assert format_stamp(datetime(2026, 10, 28, 18, 0, 0, 999000, tzinfo=UTC)) == "20261028T180000Z"

def test_parse_stamp_rejects_other_names():
    with pytest.raises(ValueError):
        parse_stamp("seg_00001")

def test_local_iso_millis_and_offset():
    dt = datetime(2026, 10, 28, 18, 0, 3, 120000, tzinfo=UTC)
    assert to_local_iso(dt, "Europe/Paris") == "2026-10-28T19:00:03.120+01:00"

def test_dst_fallback_hour_is_unambiguous():
    a = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    b = datetime(2026, 10, 25, 1, 30, tzinfo=UTC)
    assert to_local_iso(a, "Europe/Paris") == "2026-10-25T02:30:00.000+02:00"
    assert to_local_iso(b, "Europe/Paris") == "2026-10-25T02:30:00.000+01:00"
    assert format_stamp(a) != format_stamp(b)

def test_local_day_uses_paris_date():
    assert local_day(datetime(2026, 10, 28, 23, 30, tzinfo=UTC), "Europe/Paris") == "2026-10-29"
```

- [ ] **Step 3 : vérifier l'échec** — Run : `.\.venv\Scripts\python -m pytest tests/test_config.py tests/test_timeutil.py -v` → FAIL (import).
- [ ] **Step 4 : implémenter** `config.py` (via `tomllib`) et `timeutil.py` (via `zoneinfo.ZoneInfo`, `isoformat(timespec="milliseconds")`).
- [ ] **Step 5 : vérifier** — même commande → PASS.
- [ ] **Step 6 : commit** — `git add pyproject.toml config.toml src tests` ; `git commit -m "feat: squelette, configuration et horodatages"`.

---

### Task 3 : journal de couverture + commande `coverage`

**Files :**
- Create : `src/cnews_tts/coverage.py`, `src/cnews_tts/__main__.py`
- Test : `tests/test_coverage.py`

**Interfaces :**
- Consumes : `timeutil.to_local_iso`, `Config`, `load_config`.
- Produces :
  - `coverage.append_interval(coverage_csv: Path, start: datetime, end: datetime, audio_name: str) -> None` — CSV `start_utc,end_utc,audio` (en-tête écrit si le fichier n'existe pas ; dates en ISO UTC).
  - `coverage.read_intervals(coverage_csv: Path) -> list[tuple[datetime, datetime]]` — `[]` si absent.
  - `coverage.find_gaps(intervals, tolerance_s: float = 5.0) -> list[tuple[datetime, datetime]]` — trie, fusionne chevauchements et intervalles espacés de ≤ `tolerance_s`, renvoie les trous entre premier début et dernière fin.
  - `coverage.coverage_report(coverage_csv: Path, tz: str, since: datetime | None = None) -> str`.
  - `__main__.py` : `python -m cnews_tts [--config config.toml] coverage [--since AAAA-MM-JJ]` ; sous-commandes `capture` et `transcribe` ajoutées aux tâches 6 et 8.

- [ ] **Step 1 : tests qui échouent**

```python
UTC = timezone.utc
def t(h, m, s=0): return datetime(2026, 10, 28, h, m, s, tzinfo=UTC)

def test_append_and_read(tmp_path):
    csv = tmp_path / "coverage.csv"
    append_interval(csv, t(18, 0), t(18, 10), "a.aac")
    append_interval(csv, t(18, 10), t(18, 20), "b.aac")
    assert read_intervals(csv) == [(t(18, 0), t(18, 10)), (t(18, 10), t(18, 20))]

def test_read_missing_file(tmp_path):
    assert read_intervals(tmp_path / "nope.csv") == []

def test_no_gap_for_contiguous_overlapping_or_duplicate():
    iv = [(t(18, 10, 2), t(18, 20)), (t(18, 0), t(18, 10)), (t(18, 0), t(18, 10)), (t(18, 15), t(18, 20))]
    assert find_gaps(iv, tolerance_s=5) == []

def test_gap_reported():
    assert find_gaps([(t(18, 0), t(18, 10)), (t(18, 14), t(18, 20))], tolerance_s=5) == [(t(18, 10), t(18, 14))]

def test_report_shows_gap_in_paris_time(tmp_path):
    csv = tmp_path / "coverage.csv"
    append_interval(csv, t(18, 0), t(18, 10), "a.aac")
    append_interval(csv, t(18, 14), t(18, 20), "b.aac")
    r = coverage_report(csv, "Europe/Paris")
    assert "Trous (1)" in r and "19:10:00" in r and "19:14:00" in r

def test_report_without_data(tmp_path):
    assert "Aucune donnée de couverture" in coverage_report(tmp_path / "nope.csv", "Europe/Paris")
```

- [ ] **Step 2 : vérifier l'échec** — `.\.venv\Scripts\python -m pytest tests/test_coverage.py -v` → FAIL.
- [ ] **Step 3 : implémenter** `coverage.py` et `__main__.py` (argparse, sous-commande `coverage`). Le rapport donne la période couverte, la durée enregistrée / durée totale (%), et chaque trou en heure de Paris avec sa durée.
- [ ] **Step 4 : vérifier** — tests PASS ; `.\.venv\Scripts\python -m cnews_tts coverage` → « Aucune donnée de couverture ».
- [ ] **Step 5 : commit** — `feat: journal et rapport de couverture`.

---

### Task 4 : promotion des segments terminés

**Files :**
- Create : `src/cnews_tts/segments.py`
- Test : `tests/test_segments.py`

**Interfaces :**
- Consumes : `timeutil.format_stamp/parse_stamp`, `coverage.append_interval`.
- Produces :
  - `SegmentEntry(filename: str, start_rel: float, end_rel: float)` (dataclass gelée).
  - `Promoted(path: Path, start: datetime, end: datetime)` (dataclass gelée).
  - `read_segment_list(csv_path: Path) -> list[SegmentEntry]` — ignore une dernière ligne sans `\n` (en cours d'écriture) ; garde `Path(col1).name`.
  - `promote_completed(run_dir: Path, audio_dir: Path, coverage_csv: Path) -> list[Promoted]` — pour chaque entrée listée dont le fichier est encore dans `run_dir` : `start = parse_stamp(run_dir.name) + start_rel`, `end = … + end_rel` ; **d'abord** `append_interval`, **puis** déplacement vers `audio_dir / f"{format_stamp(start)}.aac"` (`os.replace`, même volume).
  - `finalize_run(run_dir, audio_dir, coverage_csv, probe_duration: Callable[[Path], float]) -> list[Promoted]` — `promote_completed`, puis chaque `seg_*.aac` restant non listé : début = fin de la dernière entrée listée (0.0 sinon), durée = `probe_duration` ; supprimé si durée < 1 s, sinon promu ; enfin supprime `run_dir`.
  - `recover_runs(work_dir: Path, audio_dir: Path, coverage_csv: Path, probe_duration) -> list[Promoted]` — `finalize_run` sur chaque sous-dossier de `work_dir`.
  - `pending_audio(audio_dir: Path) -> list[Path]` — `*.aac` directement dans `audio_dir`, triés par nom (= chronologique).
  - Constantes : `SEGMENT_LIST = "segments.csv"`, `SEGMENT_PATTERN = "seg_%05d.aac"`.

- [ ] **Step 1 : tests qui échouent**

```python
UTC = timezone.utc
RUN = "20261028T175812Z"

def make_run(root, csv_text, files):
    run = root / "work" / RUN
    run.mkdir(parents=True)
    for f in files:
        (run / f).write_bytes(b"x" * 10)
    if csv_text is not None:
        (run / "segments.csv").write_text(csv_text, encoding="utf-8")
    return run

def test_read_segment_list_ignores_partial_last_line(tmp_path):
    p = tmp_path / "segments.csv"
    p.write_text("seg_00000.aac,0.000000,108.000000\nseg_00001.aac,108.0000", encoding="utf-8")
    assert read_segment_list(p) == [SegmentEntry("seg_00000.aac", 0.0, 108.0)]

def test_promote_completed_leaves_in_progress_file(tmp_path):
    run = make_run(tmp_path, "seg_00000.aac,0.000000,108.000000\n", ["seg_00000.aac", "seg_00001.aac"])
    audio, cov = tmp_path / "audio", tmp_path / "coverage.csv"
    out = promote_completed(run, audio, cov)
    assert [p.path.name for p in out] == ["20261028T175812Z.aac"]
    assert out[0].end == datetime(2026, 10, 28, 18, 0, 0, tzinfo=UTC)
    assert (audio / "20261028T175812Z.aac").exists()
    assert (run / "seg_00001.aac").exists()
    assert read_intervals(cov) == [(out[0].start, out[0].end)]

def test_promote_completed_is_idempotent(tmp_path):
    run = make_run(tmp_path, "seg_00000.aac,0.000000,108.000000\n", ["seg_00000.aac"])
    promote_completed(run, tmp_path / "audio", tmp_path / "c.csv")
    assert promote_completed(run, tmp_path / "audio", tmp_path / "c.csv") == []

def test_finalize_run_promotes_unlisted_last_segment(tmp_path):
    run = make_run(tmp_path, "seg_00000.aac,0.000000,108.000000\n", ["seg_00000.aac", "seg_00001.aac"])
    out = finalize_run(run, tmp_path / "audio", tmp_path / "c.csv", probe_duration=lambda p: 42.0)
    assert sorted(p.path.name for p in out) == ["20261028T175812Z.aac", "20261028T180000Z.aac"]
    assert max(p.end for p in out) == datetime(2026, 10, 28, 18, 0, 42, tzinfo=UTC)
    assert not run.exists()

def test_finalize_run_drops_tiny_leftover(tmp_path):
    run = make_run(tmp_path, None, ["seg_00000.aac"])
    assert finalize_run(run, tmp_path / "audio", tmp_path / "c.csv", probe_duration=lambda p: 0.4) == []
    assert not run.exists()

def test_recover_runs_handles_abandoned_run_without_list(tmp_path):
    make_run(tmp_path, None, ["seg_00000.aac"])
    out = recover_runs(tmp_path / "work", tmp_path / "audio", tmp_path / "c.csv", probe_duration=lambda p: 300.0)
    assert [p.path.name for p in out] == ["20261028T175812Z.aac"]
    assert list((tmp_path / "work").iterdir()) == []

def test_pending_audio_sorted_and_ignores_tmp_and_subdirs(tmp_path):
    audio = tmp_path / "audio"; audio.mkdir()
    for n in ["20261028T181000Z.aac", "20261028T180000Z.aac", "x.aac.tmp"]:
        (audio / n).write_bytes(b"x")
    (audio / "sub").mkdir(); (audio / "sub" / "20261028T170000Z.aac").write_bytes(b"x")
    assert [p.name for p in pending_audio(audio)] == ["20261028T180000Z.aac", "20261028T181000Z.aac"]
```

- [ ] **Step 2 : vérifier l'échec** — `.\.venv\Scripts\python -m pytest tests/test_segments.py -v` → FAIL.
- [ ] **Step 3 : implémenter** `segments.py` (créer `audio_dir` au besoin).
- [ ] **Step 4 : vérifier** — PASS, puis suite complète `.\.venv\Scripts\python -m pytest` → PASS.
- [ ] **Step 5 : commit** — `feat: promotion et récupération des segments audio`.

---

### Task 5 : résolution du flux et ffmpeg

**Files :**
- Create : `src/cnews_tts/stream.py`, `src/cnews_tts/media.py`
- Test : `tests/test_stream.py`, `tests/test_media.py`

**Interfaces :**
- Consumes : `segments.SEGMENT_LIST`, `segments.SEGMENT_PATTERN`.
- Produces :
  - `stream.StreamInfo(url: str, headers: dict[str, str])` (dataclass gelée) ; `stream.StreamError(Exception)`.
  - `stream.stream_info_from_ytdlp(info: dict) -> StreamInfo` — `info["url"]`, `info.get("http_headers", {})` ; `StreamError` si pas d'`url`.
  - `stream.resolve_stream(video_id: str, format_selector: str) -> StreamInfo` — `yt_dlp.YoutubeDL({"format": format_selector, "quiet": True, "no_warnings": True}).extract_info(f"https://www.dailymotion.com/video/{video_id}", download=False)` ; toute exception yt-dlp → `StreamError`.
  - `media.build_ffmpeg_cmd(stream: StreamInfo, run_dir: Path, segment_seconds: int) -> list[str]`.
  - `media.probe_duration(path: Path) -> float` — `ffprobe -v error -show_entries format=duration -of csv=p=0` ; 0.0 si illisible.
  - `media.stop_ffmpeg(proc: subprocess.Popen, timeout_s: float = 15.0) -> None` — envoie `q` sur stdin (arrêt propre, ffmpeg écrit la fin du segment et la liste), attend, sinon `kill()`.

Commande ffmpeg attendue (ordre des options d'entrée avant `-i`) :
```
ffmpeg -hide_banner -nostats -loglevel warning -rw_timeout 30000000 [-headers "K: V\r\n…"] -i <url>
       -map 0:a:0 -vn -c:a copy
       -f segment -segment_format adts -segment_time <s> -segment_atclocktime 1
       -segment_list <run_dir>/segments.csv -segment_list_type csv
       <run_dir>/seg_%05d.aac
```

- [ ] **Step 1 : tests qui échouent**

```python
# tests/test_stream.py
def test_stream_info_from_ytdlp():
    s = stream_info_from_ytdlp({"url": "https://x/live.m3u8?sec=abc", "http_headers": {"Referer": "https://www.dailymotion.com/"}})
    assert s == StreamInfo("https://x/live.m3u8?sec=abc", {"Referer": "https://www.dailymotion.com/"})

def test_stream_info_without_url_raises():
    with pytest.raises(StreamError):
        stream_info_from_ytdlp({"formats": []})
```
```python
# tests/test_media.py
def test_build_ffmpeg_cmd(tmp_path):
    cmd = build_ffmpeg_cmd(StreamInfo("https://x/live.m3u8", {"User-Agent": "UA"}), tmp_path, 600)
    arg = lambda flag: cmd[cmd.index(flag) + 1]
    assert cmd[0] == "ffmpeg"
    assert arg("-i") == "https://x/live.m3u8"
    assert arg("-headers") == "User-Agent: UA\r\n"
    assert cmd.index("-headers") < cmd.index("-i") and cmd.index("-rw_timeout") < cmd.index("-i")
    for flag, val in [("-rw_timeout", "30000000"), ("-map", "0:a:0"), ("-c:a", "copy"), ("-f", "segment"),
                      ("-segment_format", "adts"), ("-segment_time", "600"), ("-segment_atclocktime", "1"),
                      ("-segment_list_type", "csv")]:
        assert arg(flag) == val
    assert "-vn" in cmd
    assert arg("-segment_list") == str(tmp_path / "segments.csv")
    assert cmd[-1] == str(tmp_path / "seg_%05d.aac")

def test_build_ffmpeg_cmd_without_headers(tmp_path):
    assert "-headers" not in build_ffmpeg_cmd(StreamInfo("u", {}), tmp_path, 600)

def test_probe_duration_on_generated_aac(tmp_path):
    f = tmp_path / "x.aac"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=d=3", "-c:a", "aac", str(f)], check=True)
    assert abs(probe_duration(f) - 3.0) < 0.3

def test_probe_duration_unreadable(tmp_path):
    (tmp_path / "bad.aac").write_bytes(b"not audio")
    assert probe_duration(tmp_path / "bad.aac") == 0.0

def test_stop_ffmpeg_is_graceful():
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine", "-f", "null", "-"], stdin=subprocess.PIPE)
    stop_ffmpeg(p, timeout_s=10)
    assert p.returncode == 0
```

- [ ] **Step 2 : vérifier l'échec** — `.\.venv\Scripts\python -m pytest tests/test_stream.py tests/test_media.py -v` → FAIL.
- [ ] **Step 3 : implémenter** `stream.py` et `media.py`.
- [ ] **Step 4 : vérifier** — PASS ; puis réseau réel : `.\.venv\Scripts\python -c "from cnews_tts.stream import resolve_stream; print(resolve_stream('x3b68jn','bestaudio/worst').url[:80])"` → une URL `.m3u8`.
- [ ] **Step 5 : commit** — `feat: résolution du flux Dailymotion et commande ffmpeg`.

---

### Task 6 : boucle de capture + commande `capture`

**Files :**
- Create : `src/cnews_tts/capture.py`
- Modify : `src/cnews_tts/__main__.py` (sous-commande `capture`, journalisation console + `data/logs/capture.log`)
- Test : `tests/test_capture.py`

**Interfaces :**
- Consumes : `Config`, `timeutil.utc_now/format_stamp`, `segments.promote_completed/finalize_run/recover_runs`, `stream.resolve_stream/StreamError`, `media.build_ffmpeg_cmd/probe_duration/stop_ffmpeg`.
- Produces :
  - `next_backoff(current: float, productive: bool, base: float = 5.0, cap: float = 300.0) -> float` — `base` si le run a promu au moins un segment, sinon `min(current * 2, cap)`.
  - `is_drifted(now: datetime, last_end: datetime, tolerance_s: float) -> bool` — `abs(now - last_end) > tolerance_s`.
  - `loop_was_suspended(elapsed_s: float, expected_s: float, slack_s: float = 30.0) -> bool` — `elapsed_s > expected_s + slack_s`.
  - `StallDetector(timeout_s: float, now: float)` avec `update(total_bytes: int, now: float) -> bool` (True = aucune croissance depuis plus de `timeout_s`).
  - `run_capture(cfg: Config) -> None`.

Algorithme de `run_capture` (le reste est laissé à l'implémenteur) :
```
recover_runs(...) au démarrage ; journaliser ce qui a été récupéré
backoff = 5
boucle :
    résoudre le flux ; StreamError → journal, attendre backoff, backoff = next_backoff(backoff, False), continuer
    run_dir = work_dir / format_stamp(utc_now()) ; lancer ffmpeg (stdin=PIPE, stderr → logs/ffmpeg.log en ajout)
    toutes les 5 s tant que ffmpeg tourne :
        si loop_was_suspended(temps écoulé réel, 5) → journal « réveil après veille », stop_ffmpeg, sortir
        promoted = promote_completed(...) ; pour le dernier : si is_drifted(utc_now(), end, tolérance) → journal, stop_ffmpeg, sortir
        si stall.update(taille totale de run_dir) → journal « flux figé », stop_ffmpeg, sortir
    finalize_run(..., probe_duration) ; journaliser le code de sortie de ffmpeg
    backoff = next_backoff(backoff, productive) ; attendre backoff
Ctrl+C (KeyboardInterrupt) à tout moment → stop_ffmpeg, finalize_run, journal « arrêt demandé », sortie 0
```

- [ ] **Step 1 : tests qui échouent**

```python
UTC = timezone.utc
def t(h, m, s=0): return datetime(2026, 10, 28, h, m, s, tzinfo=UTC)

def test_next_backoff():
    assert next_backoff(80, productive=True) == 5
    assert next_backoff(5, productive=False) == 10
    assert next_backoff(200, productive=False) == 300

def test_is_drifted():
    assert not is_drifted(t(18, 10, 30), t(18, 10), 120)
    assert is_drifted(t(18, 10, 30), t(17, 0), 120)    # horloge partie devant (veille)
    assert is_drifted(t(17, 0), t(18, 10), 120)

def test_loop_was_suspended():
    assert not loop_was_suspended(5.4, expected_s=5)
    assert loop_was_suspended(3600, expected_s=5)

def test_stall_detector():
    d = StallDetector(timeout_s=120, now=0)
    assert not d.update(100, now=10)
    assert not d.update(100, now=129)
    assert d.update(100, now=131)
    assert not d.update(200, now=140)
```

- [ ] **Step 2 : vérifier l'échec** — `.\.venv\Scripts\python -m pytest tests/test_capture.py -v` → FAIL.
- [ ] **Step 3 : implémenter** les helpers, `run_capture` et la sous-commande `capture`.
- [ ] **Step 4 : vérifier** — tests PASS ; suite complète PASS.
- [ ] **Step 5 : vérification réelle (≈ 25 min)** — lancer `.\.venv\Scripts\python -m cnews_tts capture` en arrière-plan. Attendu :
  - au premier passage à …:x0:00, un fichier apparaît dans `data/audio/` (nom UTC aligné à quelques secondes près) ;
  - pendant la capture, `taskkill /IM ffmpeg.exe /F` → le journal montre l'arrêt, puis un nouveau run quelques secondes après ; le segment partiel est promu ;
  - `python -m cnews_tts coverage` montre ce trou de quelques secondes ;
  - débit réseau : noter le volume téléchargé (Gestionnaire des tâches) pour confirmer l'ordre de grandeur Go/jour.
  Garder l'audio produit pour la tâche 8.
- [ ] **Step 6 : commit** — `feat: boucle de capture continue`.

---

### Task 7 : filtrage des hallucinations et fichiers de transcription

**Files :**
- Create : `src/cnews_tts/hallucinations.py`, `src/cnews_tts/transcripts.py`
- Test : `tests/test_hallucinations.py`, `tests/test_transcripts.py`

**Interfaces :**
- Consumes : `timeutil.to_local_iso/local_day`.
- Produces :
  - `hallucinations.normalize(text: str) -> str` — NFKD sans accents, minuscules, `’`→`'`, tout caractère non alphanumérique → espace, espaces fusionnés.
  - `hallucinations.is_hallucination(text: str, blacklist: Iterable[str]) -> bool` — vrai si le texte normalisé est vide ou **contient** une entrée normalisée.
  - `transcripts.make_record(audio_start: datetime, seg_start: float, seg_end: float, text: str, source: str, tz: str, avg_logprob: float, no_speech_prob: float, compression_ratio: float) -> dict` — clés dans cet ordre : `start`, `end`, `text` (strippé), `source`, `avg_logprob`, `no_speech_prob`, `compression_ratio` (arrondis à 3 décimales).
  - `transcripts.day_file(transcripts_dir: Path, audio_start: datetime, tz: str) -> Path` — `transcripts_dir / f"{local_day(audio_start, tz)}.jsonl"` (tout le contenu d'un fichier audio va dans le jour de **son début**).
  - `transcripts.already_transcribed(day_path: Path, source: str) -> bool`.
  - `transcripts.append_records_atomic(day_path: Path, records: list[dict]) -> None` — lit l'existant, écrit existant + nouvelles lignes (`json.dumps(..., ensure_ascii=False)`, UTF-8) dans `<nom>.tmp`, puis `os.replace` ; ne fait rien si `records` est vide.

- [ ] **Step 1 : tests qui échouent**

```python
# tests/test_hallucinations.py
BL = ("Sous-titrage ST' 501", "Sous-titres réalisés par la communauté d'Amara.org",
      "Sous-titrage Société Radio-Canada", "Merci d'avoir regardé cette vidéo")

@pytest.mark.parametrize("text", [" Sous-titrage ST' 501", "Sous-titrage ST’ 501.",
    "SOUS-TITRES RÉALISÉS PAR LA COMMUNAUTÉ D'AMARA.ORG", "Merci d'avoir regardé cette vidéo !", " ...", ""])
def test_hallucinations_dropped(text):
    assert is_hallucination(text, BL)

@pytest.mark.parametrize("text", ["Le gouvernement a présenté son budget.", "Merci d'avoir été avec nous ce soir."])
def test_real_speech_kept(text):
    assert not is_hallucination(text, BL)
```
```python
# tests/test_transcripts.py
UTC = timezone.utc

def test_make_record():
    r = make_record(datetime(2026, 10, 28, 18, 0, tzinfo=UTC), 3.12, 7.8, "  Bonjour à tous. ",
                    "20261028T180000Z.aac", "Europe/Paris", avg_logprob=-0.21234, no_speech_prob=0.01, compression_ratio=1.4)
    assert r == {"start": "2026-10-28T19:00:03.120+01:00", "end": "2026-10-28T19:00:07.800+01:00",
                 "text": "Bonjour à tous.", "source": "20261028T180000Z.aac",
                 "avg_logprob": -0.212, "no_speech_prob": 0.01, "compression_ratio": 1.4}

def test_day_file_uses_paris_date(tmp_path):
    assert day_file(tmp_path, datetime(2026, 10, 28, 23, 30, tzinfo=UTC), "Europe/Paris") == tmp_path / "2026-10-29.jsonl"

def test_append_atomic_and_already_transcribed(tmp_path):
    p = tmp_path / "2026-10-28.jsonl"
    append_records_atomic(p, [{"source": "a.aac", "text": "Été"}])
    append_records_atomic(p, [{"source": "b.aac", "text": "x"}])
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and "Été" in lines[0]
    assert already_transcribed(p, "a.aac") and not already_transcribed(p, "c.aac")
    assert list(tmp_path.glob("*.tmp")) == []

def test_append_empty_is_noop(tmp_path):
    append_records_atomic(tmp_path / "d.jsonl", [])
    assert not (tmp_path / "d.jsonl").exists()

def test_already_transcribed_missing_file(tmp_path):
    assert not already_transcribed(tmp_path / "nope.jsonl", "a.aac")
```

- [ ] **Step 2 : vérifier l'échec** — `.\.venv\Scripts\python -m pytest tests/test_hallucinations.py tests/test_transcripts.py -v` → FAIL.
- [ ] **Step 3 : implémenter** les deux modules.
- [ ] **Step 4 : vérifier** — PASS.
- [ ] **Step 5 : commit** — `feat: filtrage des hallucinations et fichiers de transcription`.

---

### Task 8 : transcription + commande `transcribe`

**Files :**
- Create : `src/cnews_tts/transcribe.py`
- Modify : `src/cnews_tts/__main__.py` (sous-commande `transcribe`, journal `data/logs/transcribe.log`)
- Test : `tests/test_transcribe.py`

**Interfaces :**
- Consumes : `Config`, `segments.pending_audio`, `timeutil.parse_stamp`, `hallucinations.is_hallucination`, `transcripts.*`.
- Produces :
  - `register_nvidia_dlls() -> None` — pour `nvidia.cublas` et `nvidia.cudnn` s'ils sont importables : `os.add_dll_directory(<pkg>/bin)` et ajout en tête de `PATH`. Appelé avant d'importer `faster_whisper`.
  - `load_model(cfg: Config)` → `faster_whisper.WhisperModel(cfg.model, device=cfg.device, compute_type=cfg.compute_type)`.
  - `transcribe_file(model, audio_path: Path, cfg: Config) -> tuple[list[dict], float, int]` — (enregistrements gardés, durée audio `info.duration`, nombre de segments écartés) ; appelle `model.transcribe(str(audio_path), language=cfg.language, vad_filter=True, condition_on_previous_text=False, beam_size=5)`.
  - `TranscribeSummary(files: int, failed: int, audio_seconds: float, wall_seconds: float, dropped: int)` avec propriété `speed` (= audio/wall).
  - `run_transcribe(cfg: Config, model=None) -> TranscribeSummary` — charge le modèle seulement s'il reste un fichier à transcrire. Répète `pending_audio` (hors fichiers en échec de ce lancement) jusqu'à épuisement, pour inclure les fichiers terminés pendant le traitement. Par fichier : si `already_transcribed` → supprimer l'audio sans appeler le modèle ; sinon transcrire → `append_records_atomic` → supprimer l'audio. Exception sur un fichier → journaliser, le laisser en place, compter dans `failed`, continuer. Affiche `[i] <nom> — <durée> s en <temps> s (<x>×)` puis un résumé (fichiers, heures d'audio, vitesse moyenne, segments écartés, fichiers en échec restants).

- [ ] **Step 1 : tests qui échouent**

```python
REPO = Path(__file__).resolve().parents[1]

class Seg:
    def __init__(self, start, end, text):
        self.start, self.end, self.text = start, end, text
        self.avg_logprob, self.no_speech_prob, self.compression_ratio = -0.2, 0.01, 1.3

class FakeModel:
    def __init__(self, fail_on=None):
        self.calls, self.fail_on = [], fail_on
    def transcribe(self, path, **kw):
        self.calls.append((Path(path).name, kw))
        if Path(path).name == self.fail_on:
            raise RuntimeError("fichier illisible")
        return iter([Seg(0.0, 2.0, "Bonjour."), Seg(2.0, 4.0, "Sous-titrage ST' 501")]), SimpleNamespace(duration=600.0)

A, B = "20261028T180000Z.aac", "20261028T181000Z.aac"

@pytest.fixture
def cfg(tmp_path):
    c = dataclasses.replace(load_config(REPO / "config.toml"), data_dir=tmp_path)
    c.audio_dir.mkdir(parents=True)
    for n in (A, B):
        (c.audio_dir / n).write_bytes(b"x")
    return c

def sources(cfg):
    return [json.loads(l)["source"] for l in (cfg.transcripts_dir / "2026-10-28.jsonl").read_text(encoding="utf-8").splitlines()]

def test_transcribes_filters_and_deletes_audio(cfg):
    s = run_transcribe(cfg, model=FakeModel())
    assert (s.files, s.failed, s.dropped) == (2, 0, 2)
    assert sources(cfg) == [A, B]
    assert list(cfg.audio_dir.iterdir()) == []

def test_whisper_options(cfg):
    m = FakeModel()
    run_transcribe(cfg, model=m)
    kw = m.calls[0][1]
    assert kw["language"] == "fr" and kw["vad_filter"] is True and kw["condition_on_previous_text"] is False

def test_failed_file_is_kept_and_rerun_has_no_loss_or_duplicate(cfg):
    s = run_transcribe(cfg, model=FakeModel(fail_on=B))
    assert s.failed == 1 and not (cfg.audio_dir / A).exists() and (cfg.audio_dir / B).exists()
    run_transcribe(cfg, model=FakeModel())
    assert sources(cfg) == [A, B]

def test_already_transcribed_audio_deleted_without_model_call(cfg):
    run_transcribe(cfg, model=FakeModel())
    (cfg.audio_dir / A).write_bytes(b"x")          # simule un arrêt entre écriture et suppression
    m = FakeModel()
    run_transcribe(cfg, model=m)
    assert m.calls == [] and not (cfg.audio_dir / A).exists()
    assert sources(cfg) == [A, B]
```

- [ ] **Step 2 : vérifier l'échec** — `.\.venv\Scripts\python -m pytest tests/test_transcribe.py -v` → FAIL.
- [ ] **Step 3 : implémenter** `transcribe.py` et la sous-commande `transcribe`.
- [ ] **Step 4 : vérifier** — PASS ; suite complète PASS.
- [ ] **Step 5 : vérifier le GPU** — `.\.venv\Scripts\python -c "from cnews_tts.transcribe import register_nvidia_dlls; register_nvidia_dlls(); import ctranslate2; print(ctranslate2.__version__, ctranslate2.get_cuda_device_count())"` → nombre ≥ 1. Si le chargement CUDA échoue (DLL introuvable, version CUDA/cuDNN attendue par la version installée de ctranslate2 différente de cu12/cuDNN 9), ajuster les paquets `nvidia-*` dans `pyproject.toml` selon les notes de version de ctranslate2.
- [ ] **Step 6 : vérification réelle** — `.\.venv\Scripts\python -m cnews_tts transcribe` sur l'audio de la tâche 6 (le premier lancement télécharge le modèle, ~3 Go). Attendu : vitesse moyenne affichée ≥ 5× ; `data/transcripts/<jour>.jsonl` lisible en français, horodatages cohérents avec l'heure de capture ; `data/audio/` vide.
- [ ] **Step 7 : commit** — `feat: transcription par lots avec faster-whisper`.

---

### Task 9 : README et recette

**Files :**
- Create : `README.md`

- [ ] **Step 1 : rédiger le README (français)** — installation (`py -3.12 -m venv .venv`, `pip install -e .[dev]`, ffmpeg requis dans le PATH) ; lancer la capture et l'arrêter (Ctrl+C) ; empêcher la mise en veille du PC portable ; lancer la transcription ; lire la couverture (`coverage`) et `data/logs/capture.log` pour la cause des trous ; format JSON Lines avec un exemple de ligne et un exemple pandas de comptage de mots par jour ; **mise en garde : les publicités sont transcrites** ; liste noire modifiable dans `config.toml` ; flux de secours `x5idxxp` ; `pip install -U yt-dlp` si la résolution du flux échoue.
- [ ] **Step 2 : recette** — suite complète `.\.venv\Scripts\python -m pytest` → PASS ; relire chaque critère de réussite de la spec et noter dans le README (section « Vérifications à faire ») ceux qui demandent l'utilisateur : capture de 24 h, coupure réseau de quelques minutes, Ctrl+C pendant la capture, arrêt forcé de la transcription en cours.
- [ ] **Step 3 : commit** — `docs: README`.
