"""Sharewise: tool handlers (TeamShift fork: metadata-strip-only).

Roles, enforced here:
  * The plugin reads, cleans and verifies. It never reports a metadata value.
  * The agent explains and runs the steps. It passes only check ids, photo numbers and fixed choices (T9).
  * The user decides. Keeping location needs the approval prompt (T8).
Every copy is cleaned and re-read before it is handed over. This fork has no face or sign detection, no review page,
no hidden areas and no visual check: those needed Apple Vision and a local HTML page a workspace user cannot open.
No network access, no model calls, no shell commands, no process-wide settings changed.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from . import clean, guard, meta, video

PLUGIN = "sharewise"
MAX_PHOTOS = 200
KEEP_CHECKS = 10
LABEL = {"location": "exact location (GPS)", "location_detail": "altitude, speed or direction",
         "time": "exact date and time", "device": "phone or camera model", "serials": "unique device or photo IDs",
         "owner": "owner or author name", "comments": "captions or comments", "hidden_thumbnail": "a hidden thumbnail of the original",
         "edit_history": "editing history", "depth_map": "a depth map / extra images",
         "face_data": "per-frame face positions recorded by the camera (videos)"}
APPROVAL_WINDOW = 600.0


def _ok(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _err(message: str, **extra: Any) -> str:
    return json.dumps({"error": message, **extra}, ensure_ascii=False)


def _session_dir() -> Path:
    try:
        from agent.runtime_cwd import resolve_agent_cwd
        return Path(resolve_agent_cwd())
    except Exception:
        return Path.home()


def _display(p: str) -> str:
    home = str(Path.home())
    return "~" + p[len(home):] if p.startswith(home + "/") else p


class Sharewise:
    def __init__(self, ctx):
        self.ctx = ctx
        self._db = None
        self._approvals: dict[str, float] = {}

    # ── storage ─────────────────────────────────────────────────────────
    def _conn(self):
        if self._db is None:
            from plugins.plugin_storage import plugin_db
            self._db = plugin_db(PLUGIN)
            self._db.execute("CREATE TABLE IF NOT EXISTS checks (id TEXT PRIMARY KEY, created REAL, data TEXT)")
            self._db.commit()
        return self._db

    def _state_get(self, key, default=None):
        try:
            return self.ctx.state.get(key, default=default)
        except TypeError:
            return self.ctx.state.get(key, default)

    def _state_set(self, key, value):
        self.ctx.state.set(key, value)

    def _save(self, c: dict) -> None:
        db = self._conn()
        db.execute("INSERT OR REPLACE INTO checks(id, created, data) VALUES (?,?,?)", (c["id"], c["created"], json.dumps(c)))
        db.execute("DELETE FROM checks WHERE id IN (SELECT id FROM checks ORDER BY created DESC LIMIT -1 OFFSET ?)", (KEEP_CHECKS,))
        db.commit()

    def _load(self, cid: Optional[str]) -> Optional[dict]:
        cid = cid or self._state_get("last_check")
        if not cid:
            return None
        row = self._conn().execute("SELECT data FROM checks WHERE id = ?", (cid,)).fetchone()
        return json.loads(row[0]) if row else None

    # ── 1. check: what would these photos reveal? (yes/no only) ─────────
    def check(self, args: dict, **_: Any) -> str:
        verdict = guard.check(str(args.get("folder") or ""), _session_dir())
        recursive = bool(args.get("include_subfolders"))
        if not verdict.allowed:
            return _err(f"refused: {verdict.reason}", requested={"folder": args.get("folder")},
                        rule=("Sharewise only reads folders inside the home folder, on external drives or the workspace's attachment folders. "
                              "Ask the user; do not try another path."))
        root = verdict.path; skipped: dict = {}; photos = []; other_media = 0
        from . import scan_walk
        for p, st in scan_walk.walk(root, recursive, skipped):
            ext = p.suffix.lower()
            if ext in meta.SUPPORTED or ext in video.VIDEO_EXT:
                if len(photos) < MAX_PHOTOS:
                    photos.append(str(p))
            elif ext in scan_walk.OTHER_MEDIA:
                other_media += 1
        if not photos:
            return _err("no supported photos (JPEG, HEIC, PNG, WebP) or videos (MOV, MP4, M4V, 3GP) in that folder",
                        scanned_exactly=_display(str(root)))
        items = []
        for p in photos:
            is_video = Path(p).suffix.lower() in video.VIDEO_EXT
            f = video.findings(Path(p)) if is_video else meta.findings(Path(p))
            items.append({"path": p, "video": is_video, "findings": {k: bool(v) for k, v in f.items()}})
        c = {"id": uuid.uuid4().hex[:8], "created": time.time(), "folder": str(root), "include_subfolders": recursive,
             "photos": items, "areas": {}, "outputs": {}}
        self._save(c); self._state_set("last_check", c["id"])
        counts = {k: sum(1 for i in items if i["findings"].get(k)) for k in meta.SENSITIVE + ("face_data",)}
        n_video = sum(1 for i in items if i["video"])
        return _ok({
            "check_id": c["id"], "scanned_exactly": _display(str(root)), "include_subfolders": recursive,
            "photos": len(items) - n_video, "videos": n_video,
            "photo_names": [f"{n + 1}. {Path(i['path']).name}" for n, i in enumerate(items[:40])],
            "what_they_reveal": {LABEL[k]: f"{v} of {len(items)} files" for k, v in counts.items() if v},
            **({"videos_note": "Videos: location, dates and device are removed from the copies without re-encoding. Faces and "
                               "signs inside a video are NOT hidden."} if n_video else {}),
            "copyright_notices_kept": sum(1 for i in items if i["findings"].get("copyright")),
            "not_checked": {**({"RAW, TIFF and other formats (they can carry location too)": other_media} if other_media else {}),
                            **{k: v[0] for k, v in skipped.items()}},
            "note": "Only yes/no is reported: Sharewise never reads out a location, a time, a device or any text in a photo.",
            "rules_for_you": ("Explain the risks in plain words without guessing values. Clean copies are made only with "
                              "sharewise_share. Faces, signs and plates in the picture itself are not hidden: say so."),
        })

    # ── 2. share: clean, verify ─────────────────────────────
    KEEPABLE = ("time", "device", "location")

    def _validate_share(self, args: dict):
        extra = sorted(set(args) - {"check_id", "keep", "photos"})
        if extra:
            return None, f"only check_id, photos and keep are accepted (got {extra}); never file paths"
        cid = args.get("check_id")
        c = self._load(cid)
        if c is None or (cid and cid != c["id"]):
            return None, "unknown or missing check_id; run sharewise_check first"
        keep = args.get("keep") or []
        if isinstance(keep, str): keep = [keep]
        bad = [k for k in keep if k not in self.KEEPABLE]
        if bad:
            return None, f"keep can only contain {list(self.KEEPABLE)} (got {bad}); everything else is always removed"
        nums = args.get("photos") or list(range(1, len(c["photos"]) + 1))
        nums = [n for n in nums if isinstance(n, int) and 1 <= n <= len(c["photos"])]
        return {"check": c, "keep": set(keep), "photos": nums}, None

    def selection_key(self, args: dict) -> str:
        return json.dumps({k: args.get(k) for k in sorted(args)}, sort_keys=True, default=str)

    def approval_request(self, args: dict) -> Optional[dict]:
        """pre_tool_call hook: block invalid requests; send 'keep location' to the approval gate (T8)."""
        sel, error = self._validate_share(args or {})
        if error:
            return {"action": "block", "message": f"Sharewise: {error}"}
        self._approvals[self.selection_key(args)] = time.time()
        if "location" in sel["keep"]:
            return {"action": "approve",
                    "message": (f"Sharewise will make {len(sel['photos'])} {'copy' if len(sel['photos']) == 1 else 'copies'} that KEEP "
                                "the exact location where each photo was taken. Anyone who receives them can see that place on a map."),
                    "rule_key": f"sharewise_keep_location:{uuid.uuid4().hex[:8]}"}
        return None

    def share(self, args: dict, **_: Any) -> str:
        key = self.selection_key(args)
        reached = self._approvals.pop(key, None)
        if reached is None or time.time() - reached > APPROVAL_WINDOW:
            return _err("refused: this request did not pass Sharewise's pre_tool_call check; nothing was written")
        sel, error = self._validate_share(args)
        if error:
            return _err(error)
        c, keep = sel["check"], sel["keep"]
        out_dir = Path(c["folder"]) / "Sharewise"
        if out_dir.exists() and (out_dir.is_symlink() or not out_dir.is_dir()):
            return _err("the Sharewise output folder is not a plain folder; nothing was written")
        made, failed = [], []
        for n in sel["photos"]:
            item = c["photos"][n - 1]; src = Path(item["path"])
            prev = c["outputs"].get(str(n))
            try:
                if prev and Path(prev).exists() and Path(prev).parent == out_dir:
                    Path(prev).unlink()                      # replace this check's own earlier copy, nothing else
                if item.get("video"):
                    dest = video.clean_copy(src, out_dir)   # all metadata blanked; keep options do not apply to videos
                else:
                    dest = clean.clean_copy(src, out_dir, keep)
                c["outputs"][str(n)] = str(dest)
                made.append({"photo": n, "copy": dest.name, **({"video": True} if item.get("video") else {})})
            except (clean.CleanError, ValueError) as exc:
                failed.append({"photo": n, "name": src.name, "why": str(exc)})
            except Exception as exc:
                failed.append({"photo": n, "name": src.name, "why": type(exc).__name__})
        self._save(c)
        return _ok({"copies": len(made), "folder": _display(str(out_dir)), "made": made[:40], "failed": failed[:20],
                    "verified": "every copy was re-read: no location" + ("" if "location" not in keep else " except the kept location") +
                                ", no hidden thumbnails or depth maps, no IDs, names or comments" +
                                (", kept: " + ", ".join(sorted(keep)) if keep else ""),
                    "tell_the_user": ("Share the files in the Sharewise folder, not the originals. Originals were not changed. "
                                      "Faces, signs and plates in the picture itself are not hidden."),
                    "copy_paths": [str(out_dir / m["copy"]) for m in made[:40]]})

    # ── slash command: literal, no model ─────────────────────────────────
    def slash(self, raw: str = "", **_: Any) -> str:
        parts = (raw or "").strip().split(None, 1); sub = parts[0].lower() if parts else "help"
        rest = parts[1].strip() if len(parts) > 1 else ""
        if sub == "guard-test":
            v = guard.check(rest, _session_dir())
            return f"Guard: {'ALLOWED' if v.allowed else 'REFUSED'} ({v.reason}) for {str(v.path) if v.path else repr(rest)}. No file was opened."
        if sub == "check":
            d = json.loads(self.check({"folder": rest}))
            if "error" in d: return "Sharewise: " + d["error"]
            vids = d.get("videos", 0)
            lines = [f"Sharewise checked exactly {d['scanned_exactly']}: {d['photos']} photo{'s' if d['photos'] != 1 else ''}"
                     + (f" and {vids} video{'s' if vids != 1 else ''}" if vids else "") + f" (check {d['check_id']})."]
            lines += [f"  {k}: {v}" for k, v in d["what_they_reveal"].items()] or ["  nothing sensitive found"]
            return "\n".join(lines + ["Nothing was changed."])
        return ("Sharewise commands (run as typed, no AI):\n"
                "  /sharewise check <folder>        what these photos reveal (yes/no only)\n"
                "  /sharewise guard-test <path>     is this path allowed? reads nothing")
