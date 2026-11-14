#!/usr/bin/env python3
# ==============================================================================
# telua_web_pipelines.py — Parsing, serialization & rewriting of pipeline configs
# ==============================================================================

import re

MY_GROUP_RE = re.compile(r'^\s*"([A-Za-z0-9_-]+)\s*::\s*([^"]*)"\s*$')
MY_STEP_RE = re.compile(r'^\s*"(.*)"\s*$')
CAR_VAR_RE = re.compile(r'^\s*(ADB_SHELL_[A-Z0-9_]+)\s*=\s*"((?:\\.|[^"\\])*)"\s*$')
CAR_ROW_RE = re.compile(r'^\s*"([A-Za-z0-9_-]+)\s*::\s*([^:]*?)\s*::\s*([^"]*)"\s*$')


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

