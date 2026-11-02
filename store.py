"""Cue list and show settings, kept in data/show.json."""

import json
import os
import threading
import time
import uuid

import config

PATH = os.path.join(config.DATA_DIR, "show.json")
_lock = threading.Lock()

DEFAULT_SETTINGS = {
    "bg": "#00ff00",        # chroma-key colour behind the orb
    "orb_scale": 1.0,       # orb size multiplier
    "orb_color": "#8c7650", # dot colour (muted gold, as in the nominees orb)
    "captions": False,      # show the spoken text under the orb
    "force_speak": False,   # hold the orb in its speaking animation, audio or not
    "voice": "ash",
    "style": "natural",
    "speed": config.VOICE_SPEED,
}

# The assistant's lines from "عريف الحفل يتحدث مع AI.docx", so the panel is not empty.
SEED = [
    "مرحباً بك أخي سعيد العتيبي، وأسعد الله مساءكم جميعاً.",
    "بكل سرور! ولكن قبل الإعلان عن الجهة الفائزة، دعوني أوضح أن هذه الجائزة تُمنح للجهة "
    "الحكومية التي تميزت في تبني وتوظيف تقنيات الذكاء الاصطناعي بفاعلية، وحققت من خلالها "
    "نتائج وأثراً ملموساً في تطوير الخدمات الحكومية، ورفع الكفاءة المؤسسية، وتحسين جودة "
    "القرارات، وتعزيز تجربة المتعاملين.",
    "والآن، يسعدني أن أعلن أن الجهة الفائزة في فئة «أفضل جهة في تطبيقات الذكاء الاصطناعي» هي... "
    "[اسم الجهة الفائزة]. ألف مبروك للجهة الفائزة على هذا الإنجاز المتميز!",
    "أخي سعيد العتيبي، أشكرك على إتاحة الفرصة لي للمشاركة في هذا الحفل المتميز. والآن، أترك لك "
    "المجال لاستكمال الإعلان عن بقية فئات جائزة محمد بن راشد للأداء الحكومي المتميز. مع أطيب "
    "تمنياتي بالتوفيق والنجاح لجميع الفائزين، ومزيد من التميز والريادة لحكومة دولة الإمارات "
    "العربية المتحدة.",
]


def _new_cue(text: str, voice: str = "", style: str = "") -> dict:
    return {"id": uuid.uuid4().hex[:10], "text": text, "voice": voice, "style": style,
            "audio": None, "duration": 0.0, "audio_text": None}


def _load() -> dict:
    try:
        with open(PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        # Save the seed at once, or every read would mint new cue ids.
        data = {"cues": [_new_cue(t) for t in SEED]}
        data["settings"] = dict(DEFAULT_SETTINGS)
        _save(data)
    data["settings"] = {**DEFAULT_SETTINGS, **data.get("settings", {})}
    return data


def _save(data: dict) -> None:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    # Antivirus / the indexer briefly lock a freshly written file on Windows.
    for attempt in range(20):
        try:
            os.replace(tmp, PATH)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


def snapshot() -> dict:
    with _lock:
        return _load()


def get_cue(cue_id: str) -> dict | None:
    return next((c for c in snapshot()["cues"] if c["id"] == cue_id), None)


def add_cue(text: str, voice: str = "", style: str = "") -> dict:
    with _lock:
        data = _load()
        cue = _new_cue(text, voice, style)
        data["cues"].append(cue)
        _save(data)
        return cue


def update_cue(cue_id: str, **fields) -> dict | None:
    with _lock:
        data = _load()
        for cue in data["cues"]:
            if cue["id"] == cue_id:
                cue.update(fields)
                _save(data)
                return cue
        return None


def delete_cue(cue_id: str) -> dict | None:
    with _lock:
        data = _load()
        cue = next((c for c in data["cues"] if c["id"] == cue_id), None)
        if cue:
            data["cues"].remove(cue)
            _save(data)
        return cue


def reorder(ids: list[str]) -> None:
    with _lock:
        data = _load()
        pos = {cid: i for i, cid in enumerate(ids)}
        data["cues"].sort(key=lambda c: pos.get(c["id"], len(pos)))
        _save(data)


def update_settings(**fields) -> dict:
    with _lock:
        data = _load()
        data["settings"].update({k: v for k, v in fields.items() if k in DEFAULT_SETTINGS})
        _save(data)
        return data["settings"]
