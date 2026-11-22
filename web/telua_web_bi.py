#!/usr/bin/env python3
# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Author & Maintainer: Thong Le <letrthong@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
# ==============================================================================
#
# telua_web_bi.py — Excel/CSV to JSON converter & Power BI dashboard engine
# Zero mandatory external dependencies for CSV/TSV (built-in standard library).
# Optional openpyxl / pandas for Excel (.xlsx).
# ==============================================================================

import csv
import io
import json
import math
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, abort, jsonify, request

bi_bp = Blueprint("bi", __name__)


def get_root() -> Path:
    """Dynamically get ROOT from telua_web if loaded, else fallback to toolkit root."""
    if "telua_web" in sys.modules:
        tw = sys.modules["telua_web"]
        if hasattr(tw, "ROOT"):
            return tw.ROOT
    return Path(__file__).resolve().parent.parent


def _json_serializable(val: Any) -> Any:
    """Safely convert numpy/pandas/datetime types to standard Python JSON types."""
    if val is None:
        return None
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return None
        return round(val, 6) if abs(val) < 1e12 else val
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    val_type = type(val).__name__
    if "Timestamp" in val_type or "Datetime" in val_type:
        return str(val)
    if "int" in val_type.lower():
        try:
            return int(val)
        except Exception:
            return str(val)
    if "float" in val_type.lower():
        try:
            f = float(val)
            return None if math.isnan(f) or math.isinf(f) else round(f, 6)
        except Exception:
            return str(val)
    if "bool" in val_type.lower():
        return bool(val)
    return str(val) if not isinstance(val, (int, str, bool, list, dict)) else val


def _clean_cell_value(val: Any) -> Any:
    """Convert raw text or cell value into proper int, float, bool, or string."""
    if val is None:
        return None
    if isinstance(val, (int, float, bool)):
        return _json_serializable(val)
    s = str(val).strip()
    if s == "" or s.lower() in ("n/a", "null", "none", "nan", "-"):
        return None
    # Try integer
    if re.match(r"^-?\d+$", s):
        try:
            return int(s)
        except ValueError:
            pass
    # Try float (handling scientific notation or comma separators)
    s_num = s.replace(",", "")
    if re.match(r"^-?\d+(\.\d+)?([eE][-+]?\d+)?$", s_num):
        try:
            f = float(s_num)
            return round(f, 6) if abs(f) < 1e12 else f
        except ValueError:
            pass
    # Try boolean
    if s.lower() in ("true", "yes"):
        return True
    if s.lower() in ("false", "no"):
        return False
    return s


def _infer_column_type(values: List[Any]) -> str:
    """Infer high-level column type: 'number', 'date', 'boolean', or 'string'."""
    non_null = [v for v in values if v is not None and v != ""]
    if not non_null:
        return "string"

    if all(isinstance(v, bool) or str(v).lower() in ("true", "false", "yes", "no") for v in non_null[:30]):
        return "boolean"

    num_count = 0
    date_count = 0
    sample_size = min(len(non_null), 50)
    for v in non_null[:sample_size]:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            num_count += 1
            continue
        v_str = str(v).strip()
        try:
            float(v_str.replace(",", ""))
            num_count += 1
            continue
        except ValueError:
            pass
        if re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}", v_str) or re.match(r"^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", v_str):
            date_count += 1

    if num_count / sample_size >= 0.8:
        return "number"
    if date_count / sample_size >= 0.8:
        return "date"
    return "string"


def _rows_to_sheet_payload(rows: List[List[Any]], sheet_name: str) -> Dict[str, Any]:
    """Convert raw 2D row array into a structured sheet payload with metadata."""
    # Filter out empty rows
    valid_rows = [r for r in rows if r and any(c is not None and str(c).strip() != "" for c in r)]
    if not valid_rows:
        return {"name": sheet_name, "columns": [], "rows_count": 0, "data": []}

    raw_headers = valid_rows[0]
    headers = [str(h).strip() if h is not None and str(h).strip() else f"Column_{i+1}" for i, h in enumerate(raw_headers)]

    records: List[Dict[str, Any]] = []
    for r in valid_rows[1:]:
        row_dict = {}
        for idx, col in enumerate(headers):
            cell_val = r[idx] if idx < len(r) else None
            row_dict[col] = _clean_cell_value(cell_val)
        records.append(row_dict)

    # Compute column metadata
    columns_meta: List[Dict[str, Any]] = []
    for col in headers:
        col_vals = [r.get(col) for r in records]
        col_type = _infer_column_type(col_vals)
        non_null_vals = [v for v in col_vals if v is not None and v != ""]
        meta: Dict[str, Any] = {
            "name": col,
            "type": col_type,
            "count": len(col_vals),
            "non_null_count": len(non_null_vals),
        }
        if col_type == "number" and non_null_vals:
            nums = [float(v) for v in non_null_vals if isinstance(v, (int, float))]
            if nums:
                meta["sum"] = round(sum(nums), 2)
                meta["avg"] = round(sum(nums) / len(nums), 2)
                meta["min"] = min(nums)
                meta["max"] = max(nums)
        elif col_type == "string" and non_null_vals:
            meta["distinct_count"] = len(set(str(v) for v in non_null_vals))
            meta["sample_values"] = list(dict.fromkeys(str(v) for v in non_null_vals))[:5]
        columns_meta.append(meta)

    return {
        "name": sheet_name,
        "columns": columns_meta,
        "rows_count": len(records),
        "data": records,
    }


def parse_csv_text(text: str, default_sheet: str = "Sheet1") -> Dict[str, Any]:
    """Parse CSV text with built-in standard library, auto-detecting multi-section tables."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return {
            "ok": True,
            "filename": "pasted_data.csv",
            "sheets": [default_sheet],
            "active_sheet": default_sheet,
            "columns": [],
            "rows_count": 0,
            "data": [],
            "all_sheets": {default_sheet: {"columns": [], "rows_count": 0, "data": []}},
        }

    first_line = lines[0]
    sep = ","
    if "\t" in first_line:
        sep = "\t"
    elif ";" in first_line and "," not in first_line:
        sep = ";"

    header_pattern = first_line.split(sep)[0]
    sections: List[List[str]] = []
    current_sec: List[str] = []

    for ln in lines:
        parts = ln.split(sep)
        if parts[0] == header_pattern and len(current_sec) > 1:
            sections.append(current_sec)
            current_sec = [ln]
        else:
            current_sec.append(ln)
    if current_sec:
        sections.append(current_sec)

    sheets_dict: Dict[str, Any] = {}
    sheet_names: List[str] = []

    if len(sections) > 1:
        all_combined_rows: List[Dict[str, Any]] = []
        combined_headers: List[str] = []

        for idx, sec_lines in enumerate(sections):
            sec_text = "\n".join(sec_lines)
            reader = csv.reader(io.StringIO(sec_text), delimiter=sep)
            rows = list(reader)

            sheet_title = f"Section_{idx + 1}"
            if len(rows) > 1 and len(rows[0]) > 0:
                header_lower = [h.strip().lower() for h in rows[0]]
                if "brand category" in header_lower:
                    cat_idx = header_lower.index("brand category")
                    cat_val = rows[1][cat_idx].strip() if len(rows[1]) > cat_idx else ""
                    if cat_val == "A":
                        sheet_title = "Mass_Market (Cat A)"
                    elif cat_val == "B":
                        sheet_title = "Luxury (Cat B)"
                    elif cat_val == "C":
                        sheet_title = "EV_Electric (Cat C)"
                    elif cat_val:
                        sheet_title = f"Category_{cat_val}"
                elif idx == 0:
                    sheet_title = "Thailand_Market"
                elif idx == 1:
                    sheet_title = "Indonesia_Market"

            orig_title = sheet_title
            suffix = 2
            while sheet_title in sheets_dict:
                sheet_title = f"{orig_title}_{suffix}"
                suffix += 1

            sheet_names.append(sheet_title)
            payload = _rows_to_sheet_payload(rows, sheet_title)
            sheets_dict[sheet_title] = payload
            all_combined_rows.extend(payload.get("data", []))
            if not combined_headers:
                combined_headers = [c["name"] for c in payload.get("columns", [])]

        if all_combined_rows:
            combined_sheet = "All_Combined"
            sheet_names.insert(0, combined_sheet)
            combined_rows_2d = [combined_headers] + [[r.get(c) for c in combined_headers] for r in all_combined_rows]
            sheets_dict[combined_sheet] = _rows_to_sheet_payload(combined_rows_2d, combined_sheet)
    else:
        reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=sep)
        rows = list(reader)
        sheet_names = [default_sheet]
        sheets_dict[default_sheet] = _rows_to_sheet_payload(rows, default_sheet)

    active = sheet_names[0]
    return {
        "ok": True,
        "filename": "dataset.csv",
        "sheets": sheet_names,
        "active_sheet": active,
        "columns": sheets_dict[active]["columns"],
        "rows_count": sheets_dict[active]["rows_count"],
        "data": sheets_dict[active]["data"],
        "all_sheets": sheets_dict,
    }


def _consolidate_multi_sheets(
    sheets_dict: Dict[str, Dict[str, Any]],
    sheet_names: List[str],
    active_sheet: Optional[str] = None,
) -> Tuple[List[str], str]:
    """If an Excel workbook has multiple sheets, automatically add an 'All_Sheets (Combined)' master view."""
    if len(sheet_names) > 1 and "All_Sheets (Combined)" not in sheet_names:
        all_records = []
        combined_columns = []
        for s_name in list(sheet_names):
            sp = sheets_dict.get(s_name, {})
            for r in sp.get("data", []):
                r_copy = dict(r)
                r_copy["Sheet"] = s_name
                all_records.append(r_copy)
            if not combined_columns and sp.get("columns"):
                combined_columns = [dict(c) for c in sp["columns"]]
        if combined_columns:
            combined_columns.append({
                "name": "Sheet",
                "type": "string",
                "count": len(all_records),
                "distinct_count": len(sheet_names),
                "sample_values": sheet_names[:5],
            })
            combined_name = "All_Sheets (Combined)"
            sheets_dict[combined_name] = {
                "name": combined_name,
                "columns": combined_columns,
                "rows_count": len(all_records),
                "data": all_records,
            }
            sheet_names.append(combined_name)
    return sheet_names, active_sheet or (sheet_names[0] if sheet_names else "Sheet1")


def parse_excel_or_csv_bytes(
    file_bytes: bytes,
    filename: str,
    active_sheet: Optional[str] = None,
) -> Dict[str, Any]:
    """Parse Excel (.xlsx, .xls) or CSV bytes into structured multi-sheet JSON."""
    fname = filename.lower()

    # 1. Handle CSV / TSV / Plain text (Zero dependency!)
    if fname.endswith(".csv") or fname.endswith(".tsv") or fname.endswith(".txt"):
        for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
            try:
                text = file_bytes.decode(enc)
                result = parse_csv_text(text, default_sheet="Sheet1")
                result["filename"] = filename
                return result
            except UnicodeDecodeError:
                continue
        text = file_bytes.decode("latin-1", errors="replace")
        result = parse_csv_text(text, default_sheet="Sheet1")
        result["filename"] = filename
        return result

    # 2. Handle Excel (.xlsx, .xls)
    sheets_dict: Dict[str, Dict[str, Any]] = {}
    sheet_names: List[str] = []

    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        sheet_names = wb.sheetnames
        if not sheet_names:
            abort(400, description="The uploaded Excel file contains no worksheets.")

        target_sheet = active_sheet if active_sheet in sheet_names else sheet_names[0]
        active_sheet = target_sheet

        for s_name in sheet_names[:10]:
            ws = wb[s_name]
            raw_rows = list(ws.iter_rows(values_only=True))
            sheets_dict[s_name] = _rows_to_sheet_payload(raw_rows, s_name)

        sheet_names, active_sheet = _consolidate_multi_sheets(sheets_dict, sheet_names, active_sheet)
        active_payload = sheets_dict.get(active_sheet, {})
        return {
            "ok": True,
            "filename": filename,
            "sheets": sheet_names,
            "active_sheet": active_sheet,
            "columns": active_payload.get("columns", []),
            "rows_count": active_payload.get("rows_count", 0),
            "data": active_payload.get("data", []),
            "all_sheets": sheets_dict,
        }
    except ImportError:
        pass
    except Exception:
        pass

    try:
        import pandas as pd
        excel_file = pd.ExcelFile(io.BytesIO(file_bytes))
        sheet_names = excel_file.sheet_names
        target_sheet = active_sheet if active_sheet in sheet_names else sheet_names[0]
        active_sheet = target_sheet

        for s_name in sheet_names[:10]:
            df = pd.read_excel(excel_file, sheet_name=s_name)
            df = df.dropna(how="all").dropna(axis=1, how="all")
            raw_rows = [list(df.columns)] + df.values.tolist()
            sheets_dict[s_name] = _rows_to_sheet_payload(raw_rows, s_name)

        active_payload = sheets_dict.get(active_sheet, {})
        return {
            "ok": True,
            "filename": filename,
            "sheets": sheet_names,
            "active_sheet": active_sheet,
            "columns": active_payload.get("columns", []),
            "rows_count": active_payload.get("rows_count", 0),
            "data": active_payload.get("data", []),
            "all_sheets": sheets_dict,
        }
    except ImportError:
        pass

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "openpyxl"],
            capture_output=True,
            timeout=30,
        )
        if proc.returncode == 0:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
            sheet_names = wb.sheetnames
            target_sheet = active_sheet if active_sheet in sheet_names else sheet_names[0]
            for s_name in sheet_names[:10]:
                ws = wb[s_name]
                raw_rows = list(ws.iter_rows(values_only=True))
                sheets_dict[s_name] = _rows_to_sheet_payload(raw_rows, s_name)
            active_payload = sheets_dict.get(target_sheet, {})
            return {
                "ok": True,
                "filename": filename,
                "sheets": sheet_names,
                "active_sheet": target_sheet,
                "columns": active_payload.get("columns", []),
                "rows_count": active_payload.get("rows_count", 0),
                "data": active_payload.get("data", []),
                "all_sheets": sheets_dict,
            }
    except Exception:
        pass

    abort(
        500,
        description=(
            "Excel (.xlsx) parsing requires 'openpyxl'. Please run: pip install openpyxl\n"
            "Tip: You can save your file as .csv and upload or paste it immediately without any extra packages!"
        ),
    )


# ------------------------------------------------------------------------------
# Real Workspace Datasets Loader (No Mock / No Fake Data)
# ------------------------------------------------------------------------------
def get_real_workspace_datasets() -> Dict[str, Any]:
    """Scan and load real Excel/CSV datasets from bi_studio/ and workspace (no mock data)."""
    root = get_root()
    real_datasets: Dict[str, Any] = {}

    # Generic sample Excel workbooks in bi_studio/ (Retail, HR, IT, Finance)
    bi_dir = root / "bi_studio"
    if bi_dir.is_dir():
        for f in sorted(bi_dir.glob("*.xlsx")):
            key = f.stem.lower().replace(" ", "_")
            try:
                parsed = parse_excel_or_csv_bytes(f.read_bytes(), f.name)
                real_datasets[key] = {
                    "title": f.name,
                    "description": f"Generic Excel workbook ({parsed.get('rows_count', 0)} records, {len(parsed.get('sheets', []))} sheets)",
                    "filename": f"bi_studio/{f.name}",
                    "sheets": parsed.get("sheets", []),
                    "active_sheet": parsed.get("active_sheet", ""),
                    "columns": parsed.get("columns", []),
                    "rows_count": parsed.get("rows_count", 0),
                    "data": parsed.get("data", []),
                    "all_sheets": parsed.get("all_sheets", {}),
                }
            except Exception:
                pass

    return real_datasets


# Backward compatibility alias - strictly real workspace datasets (no mock data)
SAMPLE_DATASETS = get_real_workspace_datasets()


# ------------------------------------------------------------------------------
# Flask API Routes
# ------------------------------------------------------------------------------
@bi_bp.route("/api/bi/load-workspace-file", methods=["POST"])
def api_bi_load_workspace_file():
    """Load an Excel or CSV file that already exists in the workspace."""
    req = request.get_json(silent=True) or {}
    rel_path = req.get("path") or "bi_studio/global_retail_sales.xlsx"
    target_sheet = req.get("sheet")

    root = get_root()
    full_path = (root / rel_path).resolve()
    if root.resolve() not in full_path.parents and full_path != root.resolve():
        abort(400, description="Path escapes the workspace root.")

    if not full_path.is_file():
        abort(404, description=f"File '{rel_path}' not found in workspace.")

    try:
        content = full_path.read_bytes()
        result = parse_excel_or_csv_bytes(content, full_path.name, active_sheet=target_sheet)
        return jsonify(result)
    except Exception as e:
        abort(500, description=f"Failed to load workspace file '{rel_path}': {str(e)}")


@bi_bp.route("/api/bi/convert", methods=["POST"])
def api_bi_convert():
    """Convert an uploaded Excel (.xlsx, .xls) or CSV file to structured JSON."""
    active_sheet = request.form.get("sheet") or request.args.get("sheet")

    if "file" not in request.files:
        abort(400, description="No file uploaded. Expected 'file' field in multipart/form-data.")

    file = request.files["file"]
    filename = file.filename or "uploaded_data.xlsx"

    if not filename:
        abort(400, description="Uploaded file must have a filename.")

    allowed_exts = (".xlsx", ".xls", ".csv", ".tsv", ".txt")
    if not any(filename.lower().endswith(ext) for ext in allowed_exts):
        abort(400, description=f"Unsupported file format '{filename}'. Supported: .xlsx, .xls, .csv, .tsv, .txt")

    try:
        content = file.read()
        if len(content) == 0:
            abort(400, description="Uploaded file is empty (0 bytes).")
        result = parse_excel_or_csv_bytes(content, filename, active_sheet=active_sheet)
        return jsonify(result)
    except Exception as e:
        abort(500, description=f"Failed to convert Excel/CSV to JSON: {str(e)}")


@bi_bp.route("/api/bi/paste", methods=["POST"])
def api_bi_paste():
    """Convert raw pasted CSV, TSV, or tab-delimited text directly into JSON."""
    req = request.get_json(silent=True) or {}
    text = req.get("text", "")
    filename = req.get("filename") or "pasted_data.csv"

    if not text.strip():
        abort(400, description="Pasted text is empty.")

    try:
        result = parse_csv_text(text, default_sheet="Sheet1")
        result["filename"] = filename
        return jsonify(result)
    except Exception as e:
        abort(500, description=f"Failed to parse pasted table: {str(e)}")


@bi_bp.route("/api/bi/samples", methods=["GET"])
def api_bi_samples():
    """List available real datasets from the workspace (no mock data)."""
    datasets = get_real_workspace_datasets()
    sample_key = request.args.get("key")
    if sample_key:
        if sample_key not in datasets:
            abort(404, description=f"Dataset '{sample_key}' not found.")
        payload = dict(datasets[sample_key])
        payload["ok"] = True
        payload["rows_count"] = len(payload.get("data", []))
        return jsonify(payload)

    summary = []
    for k, v in datasets.items():
        summary.append({
            "key": k,
            "title": v["title"],
            "description": v["description"],
            "filename": v["filename"],
            "rows_count": len(v.get("data", [])),
            "columns_count": len(v.get("columns", [])),
        })
    return jsonify({"ok": True, "samples": summary})


@bi_bp.route("/api/bi/export-excel", methods=["POST"])
def api_bi_export_excel():
    """Convert filtered JSON records back into a downloadable Excel (.xlsx) or CSV file."""
    req = request.get_json(silent=True) or {}
    data = req.get("data")
    sheet_name = req.get("sheet_name") or "Export"
    filename = req.get("filename") or "telua_bi_export.xlsx"

    if not isinstance(data, list) or not data:
        abort(400, description="Invalid or empty data array for export.")

    from flask import send_file

    # Try openpyxl
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = sheet_name[:31]

        headers = list(data[0].keys())
        ws.append(headers)
        for r in data:
            ws.append([r.get(h) for h in headers])

        out_buf = io.BytesIO()
        wb.save(out_buf)
        out_buf.seek(0)

        if not filename.endswith(".xlsx"):
            filename = filename.replace(".csv", "") + ".xlsx"

        return send_file(
            out_buf,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception:
        pass

    # Fallback to standard CSV output (zero external dependencies!)
    out_buf = io.StringIO()
    headers = list(data[0].keys())
    writer = csv.DictWriter(out_buf, fieldnames=headers)
    writer.writeheader()
    writer.writerows(data)

    csv_bytes = io.BytesIO(out_buf.getvalue().encode("utf-8-sig"))
    csv_filename = filename.replace(".xlsx", ".csv")

    return send_file(
        csv_bytes,
        as_attachment=True,
        download_name=csv_filename,
        mimetype="text/csv",
    )


@bi_bp.route("/api/bi/cross-report", methods=["POST"])
def api_bi_cross_report():
    """Generate a multi-tab cross-relational executive report with comparison matrix, ER links & charts."""
    req = request.get_json(silent=True) or {}
    all_sheets = req.get("all_sheets", {})
    filename = req.get("filename", "Excel_Workbook.xlsx")

    if not all_sheets:
        root = get_root()
        candidates = []
        bi_dir = root / "bi_studio"
        if bi_dir.is_dir():
            candidates.extend(sorted(bi_dir.glob("*.xlsx")))

        if candidates:
            target_f = candidates[0]
            res = parse_excel_or_csv_bytes(target_f.read_bytes(), target_f.name)
            all_sheets = res.get("all_sheets", {})
            filename = target_f.name

    if not all_sheets:
        abort(400, description="No sheets data provided for cross-tab analysis.")

    # Filter out 'All_Sheets' to analyze individual source tabs
    source_sheets = {k: v for k, v in all_sheets.items() if not k.startswith("All_Sheets")}
    if not source_sheets:
        source_sheets = all_sheets

    matrix = []
    col_sheet_map: Dict[str, List[str]] = {}
    total_records = 0
    total_population = 0.0

    for s_name, sp in source_sheets.items():
        rows = sp.get("data", [])
        cols = sp.get("columns", [])
        r_cnt = len(rows)
        total_records += r_cnt

        for c in cols:
            c_name = c["name"]
            col_sheet_map.setdefault(c_name, []).append(s_name)

        num_cols = [c for c in cols if c.get("type") == "number"]
        primary_sum = 0.0
        primary_num_name = ""
        if num_cols:
            primary_num_name = num_cols[0]["name"]
            primary_sum = sum(float(r.get(primary_num_name) or 0) for r in rows)
            total_population += primary_sum

        str_cols = [c for c in cols if c.get("type") == "string"]
        top_cats = []
        if str_cols:
            top_col = str_cols[0]["name"]
            top_cats = list(dict.fromkeys(str(r.get(top_col)) for r in rows if r.get(top_col)))[:4]

        matrix.append({
            "sheet_name": s_name,
            "rows_count": r_cnt,
            "columns_count": len(cols),
            "primary_metric": primary_num_name,
            "primary_sum": round(primary_sum, 2),
            "top_categories": top_cats,
        })

    # Common Keys across sheets
    shared_keys = [k for k, sheets in col_sheet_map.items() if len(sheets) >= 2 and k != "Sheet"]

    # Mermaid Pie
    pie_lines = [f'    "{m["sheet_name"]}" : {m["rows_count"]}' for m in matrix]
    mermaid_pie = "pie showData\n    title Phân bổ bản ghi giữa các Tab\n" + "\n".join(pie_lines)

    # Mermaid Bar
    bar_x = [m["sheet_name"].replace('"', '') for m in matrix]
    bar_y = [m["rows_count"] for m in matrix]
    bar_x_str = json.dumps(bar_x, ensure_ascii=False)
    bar_y_str = json.dumps(bar_y)
    max_bar = max(bar_y) if bar_y else 100
    mermaid_bar = f'xychart-beta\n    title "So sánh số lượng bản ghi giữa các Tab"\n    x-axis {bar_x_str}\n    y-axis "Bản ghi" 0 --> {max_bar}\n    bar {bar_y_str}'

    # Mermaid ER Diagram
    er_lines = []
    sheet_list = list(source_sheets.keys())
    if len(sheet_list) >= 2 and shared_keys:
        key_label = " / ".join(shared_keys[:3])
        for i in range(len(sheet_list) - 1):
            s1 = re.sub(r'[^a-zA-Z0-9_]', '_', sheet_list[i])
            s2 = re.sub(r'[^a-zA-Z0-9_]', '_', sheet_list[i+1])
            er_lines.append(f'    {s1} }}|..|{{ {s2} : "links via {key_label}"')
    mermaid_er = "erDiagram\n" + ("\n".join(er_lines) if er_lines else '    SHEET1 ||--|| SHEET2 : "relates"')

    # Markdown report
    md_lines = [
        f"# Báo Cáo Phân Tích Đa Tab (Cross-Sheet Executive Report)",
        f"**File nguồn:** `{filename}` | **Số Tab phân tích:** {len(source_sheets)} tabs | **Tổng bản ghi:** {total_records:,}",
        "",
        "## 1. Bảng Ma Trận So Sánh Các Tab (Cross-Tab Comparison Matrix)",
        "",
        "| Tên Tab / Sheet | Số lượng bản ghi | Số cột | Chỉ số chính | Tổng giá trị | Top Danh mục tiêu biểu |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for m in matrix:
        top_str = ", ".join(m["top_categories"]) if m["top_categories"] else "—"
        md_lines.append(f"| **{m['sheet_name']}** | {m['rows_count']:,} | {m['columns_count']} | {m['primary_metric'] or '—'} | {m['primary_sum']:,} | {top_str} |")

    md_lines.extend([
        "",
        "## 2. Các Trường Dữ Liệu Liên Kết Chung (Shared Dimensions & Keys)",
        f"Các trường liên kết xuất hiện xuyên suốt giữa các Tab: **{', '.join(shared_keys) if shared_keys else 'Không có'}**.",
        "",
        "## 3. Biểu đồ Phân Bổ Bản Ghi",
        "```mermaid",
        mermaid_pie,
        "```",
        "",
        "## 4. Biểu đồ So Sánh Giữa Các Tab",
        "```mermaid",
        mermaid_bar,
        "```",
    ])
    markdown_report = "\n".join(md_lines)

    # RST report
    rst_report = f""".. _cross_sheet_report:

==============================================================
Báo Cáo Phân Tích Liên Kết Đa Tab (Cross-Sheet Report)
==============================================================

**File:** ``{filename}`` | **Số lượng Tab:** {len(source_sheets)} | **Tổng bản ghi:** {total_records}

Ma Trận So Sánh Tổng Hợp
========================

.. list-table:: Thống kê Đa Tab
   :widths: 25 15 25 35
   :header-rows: 1

   * - Tên Tab / Worksheet
     - Số bản ghi
     - Tổng chỉ số chính
     - Top Danh mục
"""
    for m in matrix:
        top_str = ", ".join(m["top_categories"]) if m["top_categories"] else "—"
        rst_report += f"""   * - **{m['sheet_name']}**
     - {m['rows_count']}
     - {m['primary_sum']}
     - {top_str}
"""

    rst_report += f"""
Biểu đồ Tỷ trọng giữa các Tab
==============================

.. mermaid::

   {mermaid_pie}

Biểu đồ So sánh Chỉ số
======================

.. mermaid::

   {mermaid_bar}
"""

    return jsonify({
        "ok": True,
        "filename": filename,
        "total_sheets": len(source_sheets),
        "total_records": total_records,
        "total_population": total_population,
        "matrix": matrix,
        "shared_keys": shared_keys,
        "mermaid_pie": mermaid_pie,
        "mermaid_bar": mermaid_bar,
        "mermaid_er": mermaid_er,
        "markdown_report": markdown_report,
        "rst_report": rst_report,
    })


@bi_bp.route("/api/bi/save-doc", methods=["POST"])
def api_bi_save_doc():
    """Save generated report into docs directory for Sphinx documentation."""
    req = request.get_json(silent=True) or {}
    rel_path = req.get("path") or "docs/cross_sheet_report.rst"
    content = req.get("content", "")

    if not content:
        abort(400, description="Content is empty.")

    root = get_root()
    target_file = (root / rel_path).resolve()
    if root.resolve() not in target_file.parents and target_file != root.resolve():
        abort(400, description="Path escapes workspace.")

    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(content, encoding="utf-8")
    return jsonify({"ok": True, "path": rel_path, "bytes": len(content.encode('utf-8'))})


@bi_bp.route("/api/bi/generate-config", methods=["POST"])
def api_bi_generate_config():
    """Generate dynamic bash .config and .json from current active dataset."""
    req = request.get_json(silent=True) or {}
    filename = req.get("filename") or "dataset.xlsx"
    sheets = req.get("sheets") or []
    columns = req.get("columns") or []
    rows_count = req.get("rows_count") or 0

    # Build bash config content
    sheets_str = " ".join([f'"{s}"' for s in sheets])
    col_names = [c["name"] if isinstance(c, dict) else str(c) for c in columns]
    cols_str = " ".join([f'"{c}"' for c in col_names[:25]])

    bash_content = f"""# ==============================================================================
# BI Excel Dataset Configuration (Auto-generated)
# Source: {filename}
# Total Rows: {rows_count}
# ==============================================================================

CONFIG_EXCEL_SOURCE="{filename}"
CONFIG_EXCEL_TOTAL_ROWS={rows_count}
CONFIG_EXCEL_SHEETS=({sheets_str})
CONFIG_EXCEL_COLUMNS=({cols_str})
"""
    json_content = {
        "source": filename,
        "total_records": rows_count,
        "sheets": sheets,
        "columns": col_names,
    }

    save_to_disk = req.get("save_to_disk", False)
    if save_to_disk:
        root = get_root()
        cfg_path = root / "config" / "bi_active.config"
        json_path = root / "config" / "bi_active.json"
        cfg_path.write_text(bash_content, encoding="utf-8")
        json_path.write_text(json.dumps(json_content, indent=2), encoding="utf-8")

    return jsonify({
        "ok": True,
        "filename": filename,
        "bash_config": bash_content,
        "json_config": json_content,
    })

