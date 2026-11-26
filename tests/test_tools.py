"""Walls at the tool layer (TeamShift fork, metadata-strip-only): T1 (no values anywhere), T8, T9."""
import importlib, json, os, sqlite3, sys
from pathlib import Path
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import test_walls as W                                                   # reuses the planted-secret photos
from test_walls import folder  # noqa: F401  (pytest fixture)

tools = importlib.import_module("sharewise.tools"); meta = importlib.import_module("sharewise.meta")


class State(dict):
    def get(self, k, default=None): return json.loads(json.dumps(super().get(k, default)))
    def set(self, k, v): self[k] = json.loads(json.dumps(v))


class Ctx:
    def __init__(self): self.state = State()


@pytest.fixture
def sw(folder):
    return tools.Sharewise(Ctx())


def call_share(s, args):
    gate = s.approval_request(args)
    if gate and gate.get("action") == "block":
        return {"blocked": gate["message"]}
    return json.loads(s.share(args))


# T1 ------------------------------------------------------------------ no value in any output or stored file
def test_T1_no_secret_anywhere(sw, folder):
    outs = [sw.check({"folder": str(folder)})]
    cid = json.loads(outs[0])["check_id"]
    r = call_share(sw, {"check_id": cid})
    outs.append(json.dumps(r))
    assert r["copies"] == 2 and not r["failed"]
    for o in outs:
        assert not W.leaked(o.encode()), W.leaked(o.encode())
    from plugins.plugin_storage import plugin_data_dir
    for p in plugin_data_dir("sharewise").rglob("*"):
        if p.is_file(): assert not W.leaked(p.read_bytes())
    for p in (folder / "Sharewise").iterdir():
        assert not W.leaked(p.read_bytes()) and not meta.risky(meta.findings(p)) and meta.findings(p)["copyright"]


# T9 ------------------------------------------------------------------ fixed arguments only
def test_T9_paths_and_unknown_arguments_are_blocked(sw, folder):
    cid = json.loads(sw.check({"folder": str(folder)}))["check_id"]
    for bad in ({"check_id": cid, "paths": ["/etc/passwd"]}, {"check_id": cid, "keep": ["serials"]},
                {"check_id": "deadbeef"}, {"check_id": cid, "selection_codes": ["SW1.0000.1.0.none.zz"]},
                {"check_id": cid, "add_areas": [{"photo": 1, "box": [0, 0, 0.5, 0.5]}]}):
        assert "blocked" in call_share(sw, bad), bad
    assert "refused" in json.loads(sw.share({"check_id": cid}))["error"]          # the hook was not reached


# T8 ------------------------------------------------------------------ keeping location needs the approval prompt
def test_T8_keep_location_goes_to_the_approval_gate(sw, folder):
    cid = json.loads(sw.check({"folder": str(folder)}))["check_id"]
    gate = sw.approval_request({"check_id": cid, "keep": ["location"]})
    assert gate["action"] == "approve" and "location" in gate["message"].lower()
    assert sw.approval_request({"check_id": cid, "keep": ["time"]}) is None       # no prompt needed for time


# TeamShift fork ------------------------------------------------------------------ the workspace's attachments
def test_attachment_cache_check_and_share(sw, folder):
    docs = Path(os.environ["HERMES_HOME"]) / "cache" / "documents"; docs.mkdir(parents=True)
    W.secret_jpeg(docs / "doc_ab12_photo.jpg")
    d = json.loads(sw.check({"folder": str(docs)}))
    assert d["photos"] == 1 and d["what_they_reveal"]
    r = call_share(sw, {"check_id": d["check_id"]})
    out = docs / "Sharewise" / r["made"][0]["copy"]
    assert r["copies"] == 1 and out.exists() and not W.leaked(out.read_bytes())
    assert r["copy_paths"] == [str(out)]
    assert json.loads(sw.check({"folder": str(docs)}))["photos"] == 1             # its own output folder is never re-checked


def test_only_check_and_share_are_registered():
    import sharewise
    seen = {"tools": [], "hooks": [], "commands": []}

    class Reg:
        state = State()
        def register_tool(self, name, **_): seen["tools"].append(name)
        def register_hook(self, name, fn): seen["hooks"].append(name)
        def register_command(self, name, **_): seen["commands"].append(name)
        def register_skill(self, *a, **_): pass
    sharewise.register(Reg())
    assert seen == {"tools": ["sharewise_check", "sharewise_share"], "hooks": ["pre_tool_call"], "commands": ["sharewise"]}
    root = Path(sharewise.__file__).parent
    assert not any((root / f).exists() for f in ("detect.py", "review.py", "redact.py"))
    told = (root / "schemas.py").read_text() + (root / "skills" / "sharewise" / "SKILL.md").read_text()   # model-facing text
    assert not any(w in told for w in ("sharewise_review", "sharewise_look", "Vision", "review page", "Hermes"))
    assert not any("import Vision" in f.read_text() or "numpy" in f.read_text() for f in root.glob("*.py"))
