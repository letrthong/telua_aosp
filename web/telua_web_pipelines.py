#!/usr/bin/env python3
# ==============================================================================
# telua_web_pipelines.py — Parsing, serialization & rewriting of pipeline configs
# ==============================================================================

import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from flask import Blueprint, Response, abort, jsonify, request, stream_with_context
from telua_web_core import validate_content
from telua_web_terminal import _ACTIVE_TERM_LOCK, _ACTIVE_TERM_PROCS, _kill_term_proc

pipelines_bp = Blueprint("pipelines", __name__)

MY_GROUP_RE = re.compile(r'^\s*"([A-Za-z0-9_-]+)\s*::\s*([^"]*)"\s*$')
MY_STEP_RE = re.compile(r'^\s*"(.*)"\s*$')
CAR_VAR_RE = re.compile(r'^\s*(ADB_SHELL_[A-Z0-9_]+)\s*=\s*"((?:\\.|[^"\\])*)"\s*$')
CAR_ROW_RE = re.compile(r'^\s*"([A-Za-z0-9_-]+)\s*::\s*([^:]*?)\s*::\s*([^"]*)"\s*$')


def get_root() -> Path:
    """Dynamically get ROOT from telua_web if loaded, else fallback to toolkit root."""
    import sys
    if "telua_web" in sys.modules:
        tw = sys.modules["telua_web"]
        if hasattr(tw, "ROOT"):
            return tw.ROOT
    return Path(__file__).resolve().parent.parent


def get_pipeline_sources() -> Dict[str, Any]:
    root = get_root()
    my_cli = (
        (root / "config" / "overlay" / "cli" / "const_my_cli.config")
        if (root / "config" / "overlay" / "cli" / "const_my_cli.config").is_file()
        or not (root / "config" / "overlay" / "const_my_cli.config").is_file()
        else (root / "config" / "overlay" / "const_my_cli.config")
    )
    def _cli_cfg(fname: str) -> Path:
        p = root / "config" / "cli" / fname
        return p if p.is_file() else (root / "config" / fname)

    return {
        "my": {
            "file": my_cli,
            "prefix": "MY",
            "label": "Personal pipelines (telua my <name>)",
        },
        "multi": {
            "file": _cli_cfg("const_multi_cli.config"),
            "prefix": "MULTI",
            "label": "Multi-CLI pipelines (telua run <group>)",
        },
        "system": {
            "file": _cli_cfg("const_system_cli.config"),
            "prefix": "SYSTEM",
            "label": "System CLI pipelines (telua system <action>)",
        },
        "docker": {
            "file": _cli_cfg("const_system_cli.config"),
            "prefix": "SYSTEM",
            "label": "Docker CLI pipelines (telua system <action>)",
        },
        "car": {
            "file": _cli_cfg("const_car.config"),
            "prefix": "CAR",
            "label": "Android Car pipelines (telua car <action>)",
            "list_var": "CAR_CLI_LIST",
            "var_prefix": "ADB_SHELL_CAR_",
        },
        "dump": {
            "file": _cli_cfg("const_dumpsys.config"),
            "prefix": "DUMP",
            "label": "Android Dumpsys pipelines (telua dump <service>)",
            "list_var": "DUMP_CLI_LIST",
            "var_prefix": "ADB_SHELL_DUMP_",
        },
    }


PIPELINE_SOURCES = get_pipeline_sources()


def _pipeline_source(source):
    """Resolve a pipeline source key ('my' | 'multi' | 'system' | 'docker' | 'car' | 'dump') to its descriptor."""
    key = (source or "my").strip().lower()
    sources = get_pipeline_sources()
    if key not in sources:
        abort(400, description="Unknown pipeline source '%s' (use 'my', 'multi', 'system', 'car', or 'dump')." % key)
    return key, sources[key]


def _pipeline_config_path(source):
    """Resolve the config file for a source (fall back to the .example)."""
    root = get_root()
    key, _ = _pipeline_source(source)
    if key == "my":
        candidates = [
            root / "config" / "overlay" / "cli" / "const_my_cli.config",
            root / "config" / "overlay" / "const_my_cli.config",
            root / "config" / "const_my_cli.config",
            root / "config" / "overlay" / "cli" / "const_my_cli.config.example",
            root / "config" / "overlay" / "const_my_cli.config.example",
            root / "config" / "const_my_cli.config.example",
        ]
    elif key in ("docker", "system"):
        candidates = [
            root / "config" / "overlay" / "cli" / "const_system_cli.config",
            root / "config" / "overlay" / "const_system_cli.config",
            root / "config" / "cli" / "const_system_cli.config",
            root / "config" / "const_system_cli.config",
            root / "const_system_cli.config",
        ]
    elif key == "car":
        candidates = [
            root / "config" / "overlay" / "cli" / "const_car.config",
            root / "config" / "overlay" / "const_car.config",
            root / "config" / "cli" / "const_car.config",
            root / "config" / "const_car.config",
            root / "const_car.config",
        ]
    elif key == "dump":
        candidates = [
            root / "config" / "overlay" / "cli" / "const_dumpsys.config",
            root / "config" / "overlay" / "const_dumpsys.config",
            root / "config" / "cli" / "const_dumpsys.config",
            root / "config" / "const_dumpsys.config",
            root / "const_dumpsys.config",
        ]
    else:
        candidates = [
            root / "config" / "cli" / "const_multi_cli.config",
            root / "config" / "const_multi_cli.config",
            root / "config" / "const_multi_cli.config.example",
        ]
    for cand in candidates:
        if cand.is_file():
            return cand
    return None


def parse_pipelines(source="my"):
    """Parse <PREFIX>_GROUP_LIST + <PREFIX>_CMD_* arrays (or CAR_CLI_LIST / DUMP_CLI_LIST) into pipeline dicts."""
    key, desc = _pipeline_source(source)
    path = _pipeline_config_path(source)
    if not path:
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    if key == "car":
        return _parse_cli_list_pipelines(lines, desc["list_var"], desc["var_prefix"])
    if key == "dump":
        has_group = any(re.match(r'^\s*DUMP_GROUP_LIST\s*=', l) for l in lines)
        has_cmd = any(re.match(r'^\s*DUMP_CMD_', l) for l in lines)
        if has_group or has_cmd:
            return parse_array_pipelines(lines, "DUMP")
        return _parse_cli_list_pipelines(lines, "DUMP_CLI_LIST", "ADB_SHELL_DUMP_")
    return parse_array_pipelines(lines, desc["prefix"])


def rewrite_pipeline_config(pipelines, source="my"):
    """Rewrite <PREFIX>_GROUP_LIST and every <PREFIX>_CMD_* array in the file."""
    root = get_root()
    key, desc = _pipeline_source(source)
    path = _pipeline_config_path(source)
    if not path:
        abort(404, description="Pipeline config for '%s' not found (run 'telua init' first)." % source)
    if not os.access(path, os.W_OK):
        abort(403, description="%s is read-only." % path.name)

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    if key == "car":
        out = _rewrite_cli_list_lines(lines, pipelines, desc["list_var"], desc["var_prefix"])
    else:
        out = rewrite_array_pipeline_lines(lines, pipelines, desc["prefix"])

    new_text = "\n".join(out)
    if text.endswith("\n") or not text:
        new_text += "\n"

    error = validate_content("bash", new_text)
    if error:
        abort(400, description="Rewrite would break bash syntax: %s" % error)

    backup = None
    try:
        backup_path = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup_path)
        backup = str(backup_path.relative_to(root)).replace(os.sep, "/")
    except OSError:
        backup = None

    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(new_text)
    return backup


@pipelines_bp.get("/api/pipelines")
def api_pipelines():
    root = get_root()
    source = request.args.get("source", "my")
    _, desc = _pipeline_source(source)
    path = _pipeline_config_path(source)
    return jsonify({
        "ok": True,
        "source": _pipeline_source(source)[0],
        "label": desc["label"],
        "file": str(path.relative_to(root)).replace(os.sep, "/") if path else None,
        "pipelines": parse_pipelines(source),
    })


@pipelines_bp.post("/api/pipelines")
def api_pipelines_save():
    data = request.get_json(silent=True) or {}
    source = data.get("source", "my")
    pipelines = data.get("pipelines")
    if not isinstance(pipelines, list):
        abort(400, description="Missing 'pipelines' list in request body.")

    cleaned = []
    names = set()
    for p in pipelines:
        if not isinstance(p, dict):
            abort(400, description="Each pipeline must be an object.")
        name = str(p.get("name", "")).strip().lower()
        if not name or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            abort(400, description="Invalid pipeline name '%s' (use letters, digits, - _)." % name)
        if name in names:
            abort(400, description="Duplicate pipeline name '%s'." % name)
        names.add(name)
        steps = p.get("steps", [])
        if not isinstance(steps, list) or not all(isinstance(s, str) for s in steps):
            abort(400, description="Pipeline '%s': 'steps' must be a list of strings." % name)
        cleaned.append({
            "name": name,
            "description": str(p.get("description", "")).strip(),
            "steps": steps,
            "orphan": bool(p.get("orphan", False)),
        })

    backup = rewrite_pipeline_config(cleaned, source)
    return jsonify({
        "ok": True,
        "source": _pipeline_source(source)[0],
        "count": len(cleaned),
        "backup": backup,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


@pipelines_bp.post("/api/pipeline/run")
def api_pipeline_run():
    """Execute one pipeline via 'telua my <name>' or 'telua run <group>'."""
    root = get_root()
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    source = data.get("source", "my")
    if not name or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        abort(400, description="Invalid pipeline name.")
    key, _ = _pipeline_source(source)
    known = {p["name"] for p in parse_pipelines(key)}
    if name not in known:
        group_var = {
            "my": "MY_GROUP_LIST",
            "multi": "MULTI_GROUP_LIST",
            "docker": "SYSTEM_GROUP_LIST",
            "system": "SYSTEM_GROUP_LIST",
            "car": "CAR_CLI_LIST",
            "dump": "DUMP_GROUP_LIST",
        }[key]
        abort(404, description="Pipeline '%s' not found in %s." % (name, group_var))
    script = root / "build_apk.sh"
    if not script.is_file():
        abort(404, description="build_apk.sh not found in %s" % root)
    subcommand = {"my": "my", "multi": "run", "docker": "system", "system": "system", "car": "car", "dump": "dump"}[key]
    try:
        proc = subprocess.run(
            ["bash", str(script), subcommand, name],
            cwd=str(root), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
        output = (proc.stdout or "") + (proc.stderr or "")
        code = proc.returncode
    except subprocess.TimeoutExpired:
        output, code = "[ERROR] Pipeline '%s' timed out after 300s." % name, 124
    except Exception as exc:  # pragma: no cover
        output, code = "[ERROR] Failed to run pipeline: %s" % exc, 1
    return jsonify({"ok": code == 0, "exit_code": code, "output": output})


@pipelines_bp.post("/api/pipeline/stream")
def api_pipeline_stream():
    """Stream pipeline execution output line-by-line in real time."""
    root = get_root()
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    source = data.get("source", "my")
    if not name or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        abort(400, description="Invalid pipeline name.")
    key, _ = _pipeline_source(source)
    known = {p["name"] for p in parse_pipelines(key)}
    if name not in known:
        group_var = {
            "my": "MY_GROUP_LIST",
            "multi": "MULTI_GROUP_LIST",
            "docker": "SYSTEM_GROUP_LIST",
            "system": "SYSTEM_GROUP_LIST",
            "car": "CAR_CLI_LIST",
            "dump": "DUMP_GROUP_LIST",
        }[key]
        abort(404, description="Pipeline '%s' not found in %s." % (name, group_var))
    script = root / "build_apk.sh"
    if not script.is_file():
        abort(404, description="build_apk.sh not found in %s" % root)
    subcommand = {"my": "my", "multi": "run", "docker": "system", "system": "system", "car": "car", "dump": "dump"}[key]

    def generate():
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        proc = None
        try:
            proc = subprocess.Popen(
                ["bash", str(script), subcommand, name],
                cwd=str(root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                bufsize=1,
                env=env,
                start_new_session=(os.name != "nt"),
            )
            with _ACTIVE_TERM_LOCK:
                _ACTIVE_TERM_PROCS.add(proc)
            if proc.stdout is not None:
                for line in iter(proc.stdout.readline, ""):
                    yield line
                proc.stdout.close()
            code = proc.wait(timeout=300)
        except Exception as exc:  # pragma: no cover
            yield "\n[ERROR] Failed to stream pipeline: %s\n" % exc
            code = 1
        finally:
            if proc is not None:
                with _ACTIVE_TERM_LOCK:
                    _ACTIVE_TERM_PROCS.discard(proc)
                if proc.poll() is None:
                    _kill_term_proc(proc)
        yield "\n__TELUA_EXIT_CODE__:%d\n" % code

    return Response(
        stream_with_context(generate()),
        mimetype="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )



def _bash_quote(step: str) -> str:
    """Quote a step for safe embedding in a double-quoted bash array element."""
    return step.replace("\\", "\\\\").replace('"', '\\"')


def _parse_cli_list_pipelines(lines, list_var="CAR_CLI_LIST", var_prefix="ADB_SHELL_CAR_"):
    """Parse ADB_SHELL_* variables + <LIST_VAR>=( ... ) from const_car/const_dumpsys.config."""
    vars_map = {}
    for line in lines:
        m = CAR_VAR_RE.match(line)
        if m:
            vars_map[m.group(1)] = m.group(2).replace('\\"', '"').replace("\\\\", "\\")

    list_re = re.compile(r"^\s*%s\s*=\s*\(" % re.escape(list_var))
    in_list = False
    pipelines = []
    for line in lines:
        if list_re.match(line):
            in_list = True
            continue
        if in_list:
            if line.strip().startswith(")"):
                in_list = False
                continue
            m = CAR_ROW_RE.match(line)
            if not m:
                continue
            name = m.group(1).strip()
            desc = m.group(2).strip()
            cmd_expr = m.group(3).strip()
            ref_match = re.fullmatch(r"\$\{?([A-Za-z0-9_]+)\}?", cmd_expr)
            if ref_match:
                var_name = ref_match.group(1)
                resolved_cmd = vars_map.get(var_name, cmd_expr)
            else:
                suffix = re.sub(r"[^A-Za-z0-9]", "_", name).upper()
                var_name = "%s%s" % (var_prefix, suffix)
                resolved_cmd = cmd_expr
            pipelines.append({
                "name": name,
                "description": desc,
                "array": var_name,
                "steps": [resolved_cmd] if resolved_cmd else [],
            })
    return pipelines


def parse_array_pipelines(lines, prefix="MY"):
    """Parse <PREFIX>_GROUP_LIST + <PREFIX>_CMD_* arrays from config lines."""
    group_list_re = re.compile(r'^\s*%s_GROUP_LIST\s*=\s*\(' % prefix)
    cmd_re = re.compile(r'^\s*%s_CMD_([A-Z0-9_]+)\s*=\s*\(\s*$' % prefix)

    # 1. Registry entries from <PREFIX>_GROUP_LIST=( ... )
    registry = []
    in_group_list = False
    for line in lines:
        if group_list_re.match(line):
            in_group_list = True
            continue
        if in_group_list:
            if line.strip().startswith(")"):
                in_group_list = False
                continue
            m = MY_GROUP_RE.match(line)
            if m:
                registry.append({"name": m.group(1).strip(), "description": m.group(2).strip()})

    # 2. Step arrays: <PREFIX>_CMD_<SUFFIX>=( "step" ... ) possibly spanning lines.
    arrays = {}
    current_suffix = None
    current_steps = []
    for line in lines:
        stripped = line.strip()
        if current_suffix is None:
            m = cmd_re.match(line)
            if m:
                current_suffix = m.group(1)
                current_steps = []
            continue
        if stripped.startswith(")"):
            arrays[current_suffix] = current_steps
            current_suffix = None
            current_steps = []
            continue
        m = MY_STEP_RE.match(stripped)
        if m:
            current_steps.append(m.group(1).replace('\\"', '"').replace("\\\\", "\\"))

    # 3. Merge: one pipeline per registry entry (steps may be missing).
    pipelines = []
    seen = set()
    for item in registry:
        name = item["name"]
        suffix = re.sub(r"[^A-Za-z0-9]", "_", name).upper()
        seen.add(suffix)
        pipelines.append({
            "name": name,
            "description": item["description"],
            "array": "%s_CMD_%s" % (prefix, suffix),
            "steps": arrays.get(suffix, []),
        })

    # 4. Orphan arrays (defined but not registered) are still shown, flagged.
    for suffix, steps in arrays.items():
        if suffix not in seen:
            pipelines.append({
                "name": suffix.lower(),
                "description": "(not registered in %s_GROUP_LIST)" % prefix,
                "array": "%s_CMD_%s" % (prefix, suffix),
                "steps": steps,
                "orphan": True,
            })
    return pipelines


def serialize_pipelines(pipelines, prefix="MY"):
    """Rebuild the <PREFIX>_GROUP_LIST block and all <PREFIX>_CMD_* arrays."""
    group_lines = ["%s_GROUP_LIST=(" % prefix]
    for p in pipelines:
        if p.get("orphan"):
            continue
        group_lines.append('    "%s :: %s"' % (p["name"], p.get("description", "")))
    group_lines.append(")")

    cmd_blocks = []
    for p in pipelines:
        suffix = re.sub(r"[^A-Za-z0-9]", "_", p["name"]).upper()
        block = ["%s_CMD_%s=(" % (prefix, suffix)]
        for step in p.get("steps", []):
            block.append('    "%s"' % _bash_quote(step))
        block.append(")")
        cmd_blocks.append((p["name"], block))
    return group_lines, cmd_blocks


def _rewrite_cli_list_lines(lines, pipelines, list_var="CAR_CLI_LIST", var_prefix="ADB_SHELL_CAR_"):
    """Rewrite ADB_SHELL_* variables and <LIST_VAR>=( ... ) in const_car/const_dumpsys.config."""
    vars_map = {}
    orig_row_var = {}
    list_re = re.compile(r"^\s*%s\s*=\s*\(" % re.escape(list_var))
    in_list = False
    for line in lines:
        m = CAR_VAR_RE.match(line)
        if m:
            vars_map[m.group(1)] = m.group(2).replace('\\"', '"').replace("\\\\", "\\")
        if list_re.match(line):
            in_list = True
            continue
        if in_list:
            if line.strip().startswith(")"):
                in_list = False
                continue
            rm = CAR_ROW_RE.match(line)
            if rm:
                rname = rm.group(1).strip()
                rcmd = rm.group(3).strip()
                ref = re.fullmatch(r"\$\{?([A-Za-z0-9_]+)\}?", rcmd)
                if ref:
                    orig_row_var[rname] = ref.group(1)

    new_vars = dict(vars_map)
    resolved_rows = []
    for p in pipelines:
        if p.get("orphan"):
            continue
        name = p["name"]
        cmd_str = " && ".join(s.strip() for s in p.get("steps", []) if s.strip())
        var_name = orig_row_var.get(
            name,
            "%s%s" % (var_prefix, re.sub(r"[^A-Za-z0-9]", "_", name).upper()),
        )
        old_val = vars_map.get(var_name)
        if var_name not in new_vars or cmd_str != old_val:
            new_vars[var_name] = cmd_str
        resolved_rows.append((p, var_name))

    list_lines = ["%s=(" % list_var]
    for p, var_name in resolved_rows:
        list_lines.append('    "%-18s :: %-44s :: $%s"' % (p["name"], p.get("description", ""), var_name))
    list_lines.append(")")

    out = []
    written_vars = set()
    replaced_list = False
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        m = CAR_VAR_RE.match(line)
        if m:
            vname = m.group(1)
            written_vars.add(vname)
            if vname in new_vars:
                out.append('%s="%s"' % (vname, _bash_quote(new_vars[vname])))
            else:
                out.append(line)
            i += 1
            continue

        if not replaced_list and list_re.match(line):
            for _, vname in resolved_rows:
                if vname not in written_vars:
                    out.append('%s="%s"' % (vname, _bash_quote(new_vars.get(vname, ""))))
                    written_vars.add(vname)
            j = i
            while j < n and not lines[j].strip().startswith(")"):
                j += 1
            out.extend(list_lines)
            replaced_list = True
            i = j + 1
            continue

        out.append(line)
        i += 1

    if not replaced_list:
        for _, vname in resolved_rows:
            if vname not in written_vars:
                out.append('%s="%s"' % (vname, _bash_quote(new_vars.get(vname, ""))))
                written_vars.add(vname)
        out.extend(list_lines)
    return out


def rewrite_array_pipeline_lines(lines, pipelines, prefix="MY"):
    """Rewrite <PREFIX>_GROUP_LIST and <PREFIX>_CMD_* blocks in lines."""
    group_list_re = re.compile(r"^\s*%s_GROUP_LIST\s*=\s*\(" % prefix)
    cmd_re = re.compile(r'^\s*%s_CMD_([A-Z0-9_]+)\s*=\s*\(\s*$' % prefix)
    group_lines, cmd_blocks = serialize_pipelines(pipelines, prefix)
    out = []
    i = 0
    n = len(lines)
    replaced_groups = False
    replaced_arrays = set()

    while i < n:
        line = lines[i]
        if not replaced_groups and group_list_re.match(line):
            j = i
            while j < n and not lines[j].strip().startswith(")"):
                j += 1
            out.extend(group_lines)
            replaced_groups = True
            i = j + 1
            continue

        m = cmd_re.match(line)
        if m:
            suffix = m.group(1)
            j = i
            while j < n and not lines[j].strip().startswith(")"):
                j += 1
            for name_hint, block in cmd_blocks:
                block_suffix = re.sub(r"[^A-Za-z0-9]", "_", name_hint).upper()
                if block_suffix == suffix:
                    out.extend(block)
                    replaced_arrays.add(suffix)
                    break
            i = j + 1
            continue

        out.append(line)
        i += 1

    for name_hint, block in cmd_blocks:
        suffix = re.sub(r"[^A-Za-z0-9]", "_", name_hint).upper()
        if suffix not in replaced_arrays:
            if out and out[-1].strip() != "":
                out.append("")
            out.extend(block)

    return out

