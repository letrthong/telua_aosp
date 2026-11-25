#!/usr/bin/env python3
# ==============================================================================
# Tests for web/telua_web_bi.py (Excel/CSV to JSON & Power BI API)
# ==============================================================================

import io
import json
import unittest
import pandas as pd

from web.telua_web import app
from web.telua_web_bi import parse_excel_or_csv_bytes, _infer_column_type, SAMPLE_DATASETS


class TestTeluaWebBI(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_infer_column_type(self):
        self.assertEqual(_infer_column_type([1, 2, 3.5, 10]), "number")
        self.assertEqual(_infer_column_type(["A", "B", "C"]), "string")
        self.assertEqual(_infer_column_type(["2026-01-01", "2026-01-02"]), "date")
        self.assertEqual(_infer_column_type([True, False, True]), "boolean")

    def test_parse_csv_bytes(self):
        csv_data = b"Module,Build_Time,Passed\ncar_audio,45.2,True\noem_service,120.0,False\n"
        res = parse_excel_or_csv_bytes(csv_data, "test.csv")
        self.assertTrue(res["ok"])
        self.assertEqual(res["rows_count"], 2)
        self.assertEqual(len(res["columns"]), 3)
        self.assertEqual(res["data"][0]["Module"], "car_audio")
        self.assertEqual(res["data"][0]["Build_Time"], 45.2)

    def test_parse_excel_bytes_multi_sheet(self):
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df1 = pd.DataFrame({"ID": [1, 2], "Name": ["Alpha", "Beta"]})
            df2 = pd.DataFrame({"Metric": ["CPU", "RAM"], "Value": [45, 80]})
            df1.to_excel(writer, sheet_name="SheetA", index=False)
            df2.to_excel(writer, sheet_name="SheetB", index=False)
        buf.seek(0)

        res = parse_excel_or_csv_bytes(buf.getvalue(), "multisheet.xlsx")
        self.assertTrue(res["ok"])
        self.assertIn("SheetA", res["sheets"])
        self.assertIn("SheetB", res["sheets"])
        self.assertEqual(res["active_sheet"], "SheetA")
        self.assertEqual(res["rows_count"], 2)
        self.assertIn("SheetB", res["all_sheets"])
        self.assertEqual(res["all_sheets"]["SheetB"]["rows_count"], 2)

    def test_api_bi_samples(self):
        # List samples (workspace real datasets)
        resp = self.app.get("/api/bi/samples")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertGreaterEqual(len(data["samples"]), 1)

        # Get specific real generic dataset
        resp = self.app.get("/api/bi/samples?key=global_retail_sales")
        self.assertEqual(resp.status_code, 200)
        sample = resp.get_json()
        self.assertTrue(sample["ok"])
        self.assertIn("global_retail_sales.xlsx", sample["filename"])
        self.assertGreater(len(sample["data"]), 0)

    def test_bi_studio_generic_samples(self):
        # Load generic retail sales workbook from bi_studio
        resp = self.app.post(
            "/api/bi/load-workspace-file",
            json={"path": "bi_studio/global_retail_sales.xlsx"},
        )
        self.assertEqual(resp.status_code, 200)
        res = resp.get_json()
        self.assertTrue(res["ok"])
        self.assertIn("Sales_Transactions", res["sheets"])
        self.assertIn("Regional_Targets", res["sheets"])
        self.assertIn("Product_Catalog", res["sheets"])
        self.assertIn("Sales_Reps", res["sheets"])
        self.assertEqual(res["active_sheet"], "Sales_Transactions")
        self.assertGreaterEqual(res["rows_count"], 100)

        # Load HR workforce workbook
        resp_hr = self.app.post(
            "/api/bi/load-workspace-file",
            json={"path": "bi_studio/hr_workforce_analytics.xlsx"},
        )
        self.assertEqual(resp_hr.status_code, 200)
        res_hr = resp_hr.get_json()
        self.assertTrue(res_hr["ok"])
        self.assertIn("Employee_Directory", res_hr["sheets"])
        self.assertGreaterEqual(res_hr["rows_count"], 80)

    def test_api_bi_convert_endpoint(self):
        buf = io.BytesIO()
        df = pd.DataFrame({"ColX": [10, 20, 30], "Label": ["L1", "L2", "L3"]})
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="TestSheet", index=False)
        buf.seek(0)

        resp = self.app.post(
            "/api/bi/convert",
            data={"file": (buf, "test_upload.xlsx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 200)
        json_res = resp.get_json()
        self.assertTrue(json_res["ok"])
        self.assertEqual(json_res["filename"], "test_upload.xlsx")
        self.assertEqual(json_res["rows_count"], 3)
        self.assertEqual(json_res["columns"][0]["name"], "ColX")

    def test_api_bi_convert_errors(self):
        # Missing file field
        resp = self.app.post("/api/bi/convert", data={})
        self.assertEqual(resp.status_code, 400)

        # Unsupported extension
        resp = self.app.post(
            "/api/bi/convert",
            data={"file": (io.BytesIO(b"abc"), "invalid.exe")},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 400)

    def test_api_bi_export_excel(self):
        payload = {
            "filename": "exported_data.xlsx",
            "sheet_name": "Results",
            "data": [
                {"A": 1, "B": "test1"},
                {"A": 2, "B": "test2"}
            ]
        }
        resp = self.app.post(
            "/api/bi/export-excel",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/vnd.openxmlformats", resp.content_type)
        # Verify exported excel can be read
        df_read = pd.read_excel(io.BytesIO(resp.data), sheet_name="Results")
        self.assertEqual(len(df_read), 2)
        self.assertEqual(list(df_read.columns), ["A", "B"])

    def test_api_bi_paste_multi_section(self):
        text = (
            "RANK,FASKey,BRAND,Vehicle Series,Vehicle Type,Latest Popul.,MY,% of VIO,MVP,Brand Category\n"
            "1,ISU0111709,ISUZU,D-Max,D-Max III 1.9 DDi Pickup,499460,2019,0.0254,Y,A\n"
            "2,TOY0004180,TOYOTA,Hilux,Hilux VIII 2.4 Pickup 4WD,301650,2015,0.0153,Y,A\n"
            "RANK,FASKey,BRAND,Vehicle Series,Vehicle Type,Latest Popul.,Model Year,% of VIO,MVP,Brand Category\n"
            "1,BMW0001254,BMW,3 Series,320d (F30),13617,2012,0.00069,N,B\n"
        )
        resp = self.app.post(
            "/api/bi/paste",
            data=json.dumps({"text": text, "filename": "vehicles.csv"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertIn("All_Combined", data["sheets"])
        self.assertEqual(data["rows_count"], 3)  # combined 2 + 1 = 3 rows
        self.assertEqual(data["data"][0]["BRAND"], "ISUZU")
        self.assertEqual(data["data"][0]["Latest Popul."], 499460)

    def test_api_bi_load_workspace_file(self):
        resp = self.app.post(
            "/api/bi/load-workspace-file",
            data=json.dumps({"path": "bi_studio/global_retail_sales.xlsx"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["filename"], "global_retail_sales.xlsx")
        self.assertEqual(len(data["sheets"]), 5)  # 4 sheets + 1 All_Sheets (Combined)
        self.assertIn("All_Sheets (Combined)", data["sheets"])
        self.assertIn("Sales_Transactions", data["sheets"])
        self.assertEqual(data["active_sheet"], "Sales_Transactions")
        self.assertGreaterEqual(data["rows_count"], 100)
        self.assertGreaterEqual(data["all_sheets"]["All_Sheets (Combined)"]["rows_count"], 100)

    def test_api_bi_cross_report(self):
        resp = self.app.post(
            "/api/bi/cross-report",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertGreaterEqual(data["total_sheets"], 2)
        self.assertGreater(data["total_records"], 0)
        self.assertIn("matrix", data)
        self.assertIn("shared_keys", data)
        self.assertIn("mermaid_pie", data)
        self.assertIn("markdown_report", data)

    def test_api_bi_save_doc(self):
        resp = self.app.post(
            "/api/bi/save-doc",
            data=json.dumps({
                "path": "docs/test_cross_report.rst",
                "content": "Test Report Title\n=================\nSample content"
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["bytes"] > 0)

    def test_api_bi_generate_config(self):
        resp = self.app.post(
            "/api/bi/generate-config",
            data=json.dumps({
                "filename": "custom_sales.xlsx",
                "sheets": ["Q1_Sales", "Q2_Sales"],
                "columns": [{"name": "Region"}, {"name": "Revenue"}],
                "rows_count": 500,
                "save_to_disk": False,
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertIn("CONFIG_EXCEL_SOURCE=\"custom_sales.xlsx\"", data["bash_config"])
        self.assertIn("CONFIG_EXCEL_TOTAL_ROWS=500", data["bash_config"])
        self.assertIn("\"Q1_Sales\"", data["bash_config"])

    def test_api_bi_visual_config(self):
        sample_visuals = [
            {"id": "vis_1", "type": "bar", "title": "Test Bar", "x": "Category", "y": "Amount", "agg": "sum"}
        ]
        # POST
        resp = self.app.post(
            "/api/bi/visual-config",
            data=json.dumps({"dataset": "test.xlsx", "visuals": sample_visuals}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["visuals_count"], 1)

        # GET
        resp_get = self.app.get("/api/bi/visual-config")
        self.assertEqual(resp_get.status_code, 200)
        data_get = resp_get.get_json()
        self.assertTrue(data_get["ok"])
        self.assertTrue(data_get["exists"])
        self.assertEqual(len(data_get["config"]["visuals"]), 1)



if __name__ == "__main__":
    unittest.main()
