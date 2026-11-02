"""
AI MC - admin panel + show screen for the award ceremony.

  python app.py
  admin : http://<this-pc>:8090/admin   (operator: write lines, generate voice, fire cues)
  show  : http://<this-pc>:8090/show    (orb on a chroma-key background; OBS / projector)

The admin panel pushes commands to every open show page over Server-Sent
Events; the show page plays the audio itself, so plug the venue sound (or the
OBS capture) into whichever machine runs the show page.
"""

import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser

from flask import Flask, Response, abort, jsonify, redirect, request, send_from_directory

import config
import store
import tts

WEB = os.path.join(config.ASSETS, "web")
UPLOAD_TYPES = {".wav", ".mp3", ".m4a", ".ogg", ".aac"}

app = Flask(__name__, static_folder=None)


class Hub:
    """Fans events out to every open admin/show page."""

    def __init__(self) -> None:
        self.clients: list[tuple[str, queue.Queue]] = []
        self.lock = threading.Lock()
        self.now_playing: dict | None = None
        self.generating: dict[str, str] = {}   # cue id -> "busy" | error text

    def subscribe(self, role: str) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=100)
        with self.lock:
            self.clients.append((role, q))
        self.presence()
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self.lock:
            self.clients = [c for c in self.clients if c[1] is not q]
        self.presence()

    def shows(self) -> int:
        with self.lock:
            return sum(1 for role, _ in self.clients if role == "show")

    def publish(self, event: dict, role: str | None = None) -> None:
        """role=None reaches every page; "show" also reaches the admin's preview."""
        roles = {role, "preview"} if role == "show" else {role}
        msg = json.dumps(event, ensure_ascii=False)
        with self.lock:
            targets = [q for r, q in self.clients if role is None or r in roles]
        for q in targets:
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass  # a stalled tab; it will resync from /api/state on reconnect

    def presence(self) -> None:
        self.publish({"type": "presence", "shows": self.shows()}, role="admin")


hub = Hub()


def state() -> dict:
    data = store.snapshot()
    return {**data, "voices": config.VOICES, "styles": list(config.VOICE_STYLES),
            "now_playing": hub.now_playing, "generating": hub.generating,
            "shows": hub.shows()}


def push_cues() -> None:
    hub.publish({"type": "cues", "state": state()}, role="admin")


def remove_audio(cue: dict | None) -> None:
    if cue and cue.get("audio"):
        try:
            os.remove(os.path.join(config.AUDIO_DIR, cue["audio"]))
        except OSError:
            pass


# ---------------- pages ----------------

@app.get("/")
def index():
    return redirect("/admin")


@app.get("/admin")
def admin_page():
    return send_from_directory(WEB, "admin.html", max_age=0)


@app.get("/show")
def show_page():
    return send_from_directory(WEB, "show.html", max_age=0)


@app.get("/static/<path:name>")
def static_file(name: str):
    return send_from_directory(WEB, name)


@app.get("/audio/<path:name>")
def audio(name: str):
    return send_from_directory(config.AUDIO_DIR, name, max_age=0)


# ---------------- live events ----------------

@app.get("/api/events")
def events():
    role = request.args.get("role")
    role = role if role in ("show", "preview") else "admin"
    q = hub.subscribe(role)

    def stream():
        try:
            yield f"data: {json.dumps({'type': 'hello', 'state': state()}, ensure_ascii=False)}\n\n"
            while True:
                try:
                    yield f"data: {q.get(timeout=15)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            hub.unsubscribe(q)

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/api/state")
def get_state():
    return jsonify(state())


# ---------------- cues ----------------

@app.post("/api/cues")
def add_cue():
    body = request.get_json(force=True)
    text = (body.get("text") or "").strip()
    if not text:
        abort(400, "text is required")
    cue = store.add_cue(text, body.get("voice", ""), body.get("style", ""))
    push_cues()
    return jsonify(cue), 201


@app.patch("/api/cues/<cue_id>")
def edit_cue(cue_id: str):
    body = request.get_json(force=True)
    fields = {k: body[k] for k in ("text", "voice", "style") if k in body}
    cue = store.update_cue(cue_id, **fields)
    if cue is None:
        abort(404)
    push_cues()
    return jsonify(cue)


@app.delete("/api/cues/<cue_id>")
def delete_cue(cue_id: str):
    remove_audio(store.delete_cue(cue_id))
    hub.generating.pop(cue_id, None)
    push_cues()
    return "", 204


@app.post("/api/cues/reorder")
def reorder():
    store.reorder(request.get_json(force=True).get("ids", []))
    push_cues()
    return "", 204


@app.post("/api/cues/<cue_id>/generate")
def generate(cue_id: str):
    cue = store.get_cue(cue_id)
    if cue is None:
        abort(404)
    if hub.generating.get(cue_id) == "busy":
        return jsonify({"status": "busy"}), 202
    settings = store.snapshot()["settings"]
    voice = cue.get("voice") or settings["voice"]
    style = cue.get("style") or settings["style"]
    speed = float(settings["speed"])
    text = cue["text"]
    hub.generating[cue_id] = "busy"
    push_cues()

    def work():
        name = f"{cue_id}-{int(time.time())}.wav"
        try:
            seconds = tts.generate(text, voice, style, os.path.join(config.AUDIO_DIR, name), speed)
        except Exception as exc:
            hub.generating[cue_id] = f"error: {exc}"
            print(f"[generate] {cue_id} failed: {exc}")
        else:
            old = store.get_cue(cue_id)
            if old is None:   # deleted while generating
                os.remove(os.path.join(config.AUDIO_DIR, name))
            else:
                remove_audio(old)
                store.update_cue(cue_id, audio=name, duration=round(seconds, 1),
                                 audio_text=text, audio_voice=f"{voice} / {style} / ×{speed:g}")
            hub.generating.pop(cue_id, None)
        push_cues()

    threading.Thread(target=work, daemon=True).start()
    return jsonify({"status": "busy"}), 202


@app.post("/api/cues/<cue_id>/upload")
def upload(cue_id: str):
    cue = store.get_cue(cue_id)
    f = request.files.get("file")
    if cue is None or f is None:
        abort(404 if cue is None else 400)
    ext = os.path.splitext(f.filename or "")[1].lower()
    if ext not in UPLOAD_TYPES:
        abort(400, f"use one of {', '.join(sorted(UPLOAD_TYPES))}")
    name = f"{cue_id}-{int(time.time())}{ext}"
    os.makedirs(config.AUDIO_DIR, exist_ok=True)
    f.save(os.path.join(config.AUDIO_DIR, name))
    remove_audio(cue)
    # Duration is filled in by the admin page once the browser has loaded the file.
    store.update_cue(cue_id, audio=name, duration=0.0, audio_text=cue["text"],
                     audio_voice="uploaded")
    push_cues()
    return "", 204


@app.post("/api/cues/<cue_id>/duration")
def set_duration(cue_id: str):
    store.update_cue(cue_id, duration=round(float(request.get_json(force=True)["duration"]), 1))
    return "", 204


# ---------------- show control ----------------

@app.post("/api/play/<cue_id>")
def play(cue_id: str):
    cue = store.get_cue(cue_id)
    if cue is None or not cue.get("audio"):
        abort(400, "generate the voice for this line first")
    hub.publish({"type": "play", "id": cue_id, "url": f"/audio/{cue['audio']}",
                 "text": cue.get("audio_text") or cue["text"]}, role="show")
    return jsonify({"shows": hub.shows()})


@app.post("/api/stop")
def stop():
    hub.publish({"type": "stop"}, role="show")
    return "", 204


@app.post("/api/settings")
def settings():
    s = store.update_settings(**request.get_json(force=True))
    hub.publish({"type": "settings", "settings": s})
    return jsonify(s)


@app.post("/api/show-status")
def show_status():
    """The show page reports what it is playing, so the admin sees it live."""
    body = request.get_json(force=True)
    hub.now_playing = body if body.get("state") == "playing" else None
    hub.publish({"type": "now_playing", "now_playing": hub.now_playing}, role="admin")
    return "", 204


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def stop_previous_instance() -> None:
    """Kill whatever still listens on our port (an old window left open)."""
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True,
                             text=True, creationflags=subprocess.CREATE_NO_WINDOW).stdout
    except (OSError, AttributeError):
        return  # not Windows
    pids = {parts[-1] for parts in (line.split() for line in out.splitlines())
            if len(parts) >= 5 and parts[1].endswith(f":{config.PORT}")
            and parts[2].endswith(":0")   # listening; the state word is localised
            and parts[-1] != str(os.getpid())}
    for pid in pids:
        print(f"[start] stopping previous instance (pid {pid})")
        subprocess.run(["taskkill", "/F", "/T", "/PID", pid], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    if pids:
        time.sleep(1)  # let Windows release the port and the data files


def reset_session() -> None:
    """Start from a clean cue list (the seed lines) with no old audio."""
    shutil.rmtree(config.DATA_DIR, ignore_errors=True)
    print("[start] previous session cleared")


def open_tabs(host: str) -> None:
    time.sleep(1.5)  # give the server a moment to start listening
    webbrowser.open(f"http://{host}:{config.PORT}/admin")
    webbrowser.open(f"http://{host}:{config.PORT}/show")


if __name__ == "__main__":
    stop_previous_instance()
    if "--keep" not in sys.argv:
        reset_session()
    os.makedirs(config.AUDIO_DIR, exist_ok=True)
    host = "127.0.0.1" if config.HOST in ("0.0.0.0", "") else config.HOST
    print(f"admin : http://{host}:{config.PORT}/admin")
    print(f"show  : http://{host}:{config.PORT}/show")
    if config.HOST in ("0.0.0.0", ""):
        print(f"LAN   : http://{lan_ip()}:{config.PORT}/show")
    if not config.API_KEY:
        print("[warn] no Azure key found - voice generation is off, uploads still work.")
    if "--no-browser" not in sys.argv:
        threading.Thread(target=open_tabs, args=(host,), daemon=True).start()
    app.run(host=config.HOST, port=config.PORT, threaded=True, debug=False)
