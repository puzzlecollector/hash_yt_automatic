"""In-process scheduler controlled from the admin page."""
import json, threading, time, traceback
from datetime import datetime, timedelta
from . import config, settings

STATUS = config.STATE / "scheduler.json"
_lock = threading.Lock()
_state = {"running": False, "current": None, "last_start": None, "last_end": None, "next_run": None, "last_error": None, "last_results": []}


def _save():
    config.STATE.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(_state, ensure_ascii=False, indent=1, default=str))


def status():
    s = settings.load()
    return {**_state, "enabled": s["enabled"], "interval_h": s["interval_h"]}


def run_now():
    if _lock.locked(): return False
    threading.Thread(target=_cycle, daemon=True).start()
    return True


def _cycle():
    from . import pipeline
    with _lock:
        _state.update(running=True, last_start=datetime.now().isoformat(), last_error=None, current="트렌드 조회 중"); _save()
        try:
            settings.apply()
            res = pipeline.run_once(progress=lambda m: (_state.update(current=m), _save()))
            _state["last_results"] = [{k: r.get(k) for k in ("keyword", "status", "note", "out")} for r in res["results"]]
        except Exception:
            _state["last_error"] = traceback.format_exc()[-1500:]
        finally:
            s = settings.load()
            _state.update(running=False, current=None, last_end=datetime.now().isoformat(),
                          next_run=(datetime.now() + timedelta(hours=float(s["interval_h"]))).isoformat() if s["enabled"] else None)
            _save()


def loop():
    """Background thread: start a cycle when enabled and due."""
    if STATUS.exists():
        try: _state.update({k: v for k, v in json.loads(STATUS.read_text()).items() if k in ("last_start", "last_end", "next_run", "last_results")})
        except Exception: pass
    _state["running"] = False
    while True:
        s = settings.load()
        if s["enabled"] and not _lock.locked():
            nr = _state.get("next_run")
            if not nr or datetime.fromisoformat(nr) <= datetime.now():
                run_now()
        elif not s["enabled"]:
            _state["next_run"] = None
        time.sleep(20)


def set_enabled(on):
    s = settings.load(); s["enabled"] = bool(on); settings.save(s)
    if on and not _state.get("next_run"): _state["next_run"] = datetime.now().isoformat()   # start right away
    if not on: _state["next_run"] = None
    _save()


def set_interval(h):
    s = settings.load(); s["interval_h"] = max(0.5, float(h)); settings.save(s)
    if _state.get("last_start") and s["enabled"]:
        _state["next_run"] = (datetime.fromisoformat(_state["last_start"]) + timedelta(hours=s["interval_h"])).isoformat()
    _save()
