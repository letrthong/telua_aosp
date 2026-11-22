#!/usr/bin/env python3
"""
Generate realistic generic Excel sample files in bi_studio/ for testing BI Studio.
No automotive or vehicle data - strictly general business, retail, HR, IT and finance.
"""

from pathlib import Path
import random
from datetime import date, timedelta
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
BI_STUDIO_DIR = ROOT / "bi_studio"
BI_STUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Styling helpers
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
SUBHEADER_FILL = PatternFill(start_color="2F5597", end_color="2F5597", fill_type="solid")
ZEBRA_FILL = PatternFill(start_color="F2F5F9", end_color="F2F5F9", fill_type="solid")
THIN_SIDE = Side(border_style="thin", color="D9D9D9")
CELL_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)

def style_worksheet(ws, header_fill=HEADER_FILL):
    """Apply styling, borders, and auto column widths."""
    ws.views.sheetView[0].showGridLines = True
    for col_idx, col in enumerate(ws.columns, start=1):
        max_len = 0
        for row_idx, cell in enumerate(col, start=1):
            cell.border = CELL_BORDER
            if row_idx == 1:
                cell.font = HEADER_FONT
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            else:
                if row_idx % 2 == 0:
                    cell.fill = ZEBRA_FILL
                # Alignment based on type
                if isinstance(cell.value, (int, float)):
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")

            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)
    ws.row_dimensions[1].height = 28


def create_retail_sales():
    """1. global_retail_sales.xlsx - E-Commerce & Retail Sales & Margin"""
    wb = openpyxl.Workbook()
    random.seed(42)

    # --- Sheet 1: Sales_Transactions ---
    ws1 = wb.active
    ws1.title = "Sales_Transactions"
    headers1 = [
        "Order_ID", "Order_Date", "Customer_ID", "Customer_Segment",
        "Region", "Country", "Category", "Sub_Category",
        "Product_Name", "Units_Sold", "Unit_Price", "Revenue", "Discount_Pct", "Profit", "Margin_Pct"
    ]
    ws1.append(headers1)

    regions_countries = {
        "North America": ["United States", "Canada", "Mexico"],
        "Europe": ["United Kingdom", "Germany", "France", "Netherlands"],
        "Asia Pacific": ["Japan", "Singapore", "Australia", "Vietnam"],
        "Latin America": ["Brazil", "Chile", "Colombia"],
    }
    categories = {
        "Technology": [
            ("Laptops", 950.0), ("Smartphones", 650.0), ("Monitors", 280.0),
            ("Wireless Keyboards", 45.0), ("Noise-Canceling Headsets", 160.0)
        ],
        "Office Supplies": [
            ("Ergonomic Desk Chairs", 210.0), ("Standing Desks", 340.0),
            ("Storage Cabinets", 180.0), ("Laser Printer Paper", 25.0), ("Desk Organizers", 18.0)
        ],
        "Cloud & Software": [
            ("Productivity Suite 365", 120.0), ("Cybersecurity Agent", 85.0),
            ("Cloud Backup Storage", 60.0), ("Developer Tooling Kit", 220.0)
        ]
    }
    segments = ["Enterprise", "Small Business", "Consumer"]

    start_date = date(2026, 1, 5)
    for i in range(1, 151):
        reg = random.choice(list(regions_countries.keys()))
        country = random.choice(regions_countries[reg])
        cat = random.choice(list(categories.keys()))
        subcat, base_price = random.choice(categories[cat])
        seg = random.choice(segments)
        
        order_date = start_date + timedelta(days=random.randint(0, 240))
        units = random.randint(1, 25) if seg != "Consumer" else random.randint(1, 4)
        price = round(base_price * random.uniform(0.9, 1.15), 2)
        disc = round(random.choice([0.0, 0.05, 0.1, 0.15, 0.2]), 2)
        gross_rev = round(units * price, 2)
        net_rev = round(gross_rev * (1.0 - disc), 2)
        cost = round(gross_rev * random.uniform(0.55, 0.75), 2)
        profit = round(net_rev - cost, 2)
        margin = round((profit / net_rev) * 100, 2) if net_rev else 0.0

        ws1.append([
            f"ORD-2026-{i:04d}", order_date.strftime("%Y-%m-%d"),
            f"CUST-{random.randint(100, 350)}", seg,
            reg, country, cat, subcat, subcat,
            units, price, net_rev, disc, profit, margin
        ])
    style_worksheet(ws1)

    # --- Sheet 2: Regional_Targets ---
    ws2 = wb.create_sheet(title="Regional_Targets")
    headers2 = ["Region", "Country", "Q1_Target", "Q2_Target", "Q3_Target", "Q4_Target", "Annual_Target"]
    ws2.append(headers2)
    for reg, countries in regions_countries.items():
        for country in countries:
            q1 = random.randint(30, 80) * 1000
            q2 = random.randint(35, 90) * 1000
            q3 = random.randint(40, 95) * 1000
            q4 = random.randint(50, 120) * 1000
            ws2.append([reg, country, q1, q2, q3, q4, q1 + q2 + q3 + q4])
    style_worksheet(ws2, HEADER_FILL)

    # --- Sheet 3: Product_Catalog ---
    ws3 = wb.create_sheet(title="Product_Catalog")
    headers3 = ["Product_ID", "Category", "Sub_Category", "Standard_Cost", "List_Price", "Target_Margin_Pct"]
    ws3.append(headers3)
    p_id = 1
    for cat, items in categories.items():
        for subcat, list_price in items:
            cost = round(list_price * 0.62, 2)
            margin = round(((list_price - cost) / list_price) * 100, 1)
            ws3.append([f"PROD-{p_id:03d}", cat, subcat, cost, list_price, margin])
            p_id += 1
    style_worksheet(ws3, SUBHEADER_FILL)

    # --- Sheet 4: Sales_Reps ---
    ws4 = wb.create_sheet(title="Sales_Reps")
    headers4 = ["Rep_ID", "Rep_Name", "Region", "Quota_Annual", "Deals_Won", "Revenue_Closed", "Quota_Attainment_Pct"]
    ws4.append(headers4)
    reps = [
        ("Sarah Jenkins", "North America", 650000), ("Michael Chang", "Asia Pacific", 580000),
        ("Emma Schmidt", "Europe", 540000), ("David Tanaka", "Asia Pacific", 510000),
        ("Elena Rostova", "Europe", 490000), ("Carlos Silva", "Latin America", 420000),
        ("James Wilson", "North America", 620000), ("Chloe Dupont", "Europe", 530000),
    ]
    for idx, (name, reg, quota) in enumerate(reps, start=1):
        deals = random.randint(18, 45)
        rev = round(quota * random.uniform(0.85, 1.25), 2)
        attain = round((rev / quota) * 100, 1)
        ws4.append([f"REP-{idx:03d}", name, reg, quota, deals, rev, attain])
    style_worksheet(ws4, SUBHEADER_FILL)

    out_path = BI_STUDIO_DIR / "global_retail_sales.xlsx"
    wb.save(out_path)
    print(f"Created: {out_path} ({len(wb.sheetnames)} sheets, {ws1.max_row - 1} sales rows)")


def create_hr_workforce():
    """2. hr_workforce_analytics.xlsx - Headcount, Salaries, Retention"""
    wb = openpyxl.Workbook()
    random.seed(101)

    # --- Sheet 1: Employee_Directory ---
    ws1 = wb.active
    ws1.title = "Employee_Directory"
    headers1 = [
        "Employee_ID", "Full_Name", "Department", "Job_Title",
        "Office_Location", "Country", "Hire_Date", "Employment_Type",
        "Base_Salary", "Bonus_Pct", "Performance_Rating", "Remote_Status"
    ]
    ws1.append(headers1)

    departments = {
        "Engineering": [
            ("Senior Backend Engineer", 115000), ("Frontend Developer", 88000),
            ("DevOps Architect", 125000), ("QA Automation Engineer", 78000),
            ("Engineering Manager", 145000)
        ],
        "Product & Design": [
            ("Lead UI/UX Designer", 92000), ("Principal Product Manager", 138000),
            ("Technical Writer", 68000)
        ],
        "Sales & Marketing": [
            ("Enterprise Account Executive", 95000), ("Growth Marketing Lead", 85000),
            ("Customer Success Manager", 72000), ("Content Strategist", 64000)
        ],
        "Finance & Operations": [
            ("Senior Financial Analyst", 89000), ("HR Business Partner", 80000),
            ("Legal Counsel", 130000), ("Operations Coordinator", 58000)
        ]
    }
    locations = [
        ("San Francisco", "United States"), ("London", "United Kingdom"),
        ("Tokyo", "Japan"), ("Singapore", "Singapore"),
        ("Berlin", "Germany"), ("Sydney", "Australia")
    ]
    first_names = ["Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Sam", "Jamie", "Chris", "Pat", "Robin", "Jesse"]
    last_names = ["Chen", "Smith", "Mueller", "Kim", "Patel", "Garcia", "Johnson", "Nakamura", "Dubois", "Santos", "Tanaka"]

    start_date = date(2020, 1, 15)
    for i in range(1, 91):
        dept = random.choice(list(departments.keys()))
        title, base = random.choice(departments[dept])
        salary = round(base * random.uniform(0.92, 1.15), 0)
        loc, country = random.choice(locations)
        hire = start_date + timedelta(days=random.randint(0, 2100))
        emp_type = "Full-time" if random.random() > 0.08 else "Contract"
        bonus = round(random.uniform(5.0, 20.0), 1)
        rating = random.choice([3, 4, 4, 4, 5, 5, 2])
        remote = random.choice(["Remote", "Hybrid", "Hybrid", "On-site"])
        full_name = f"{random.choice(first_names)} {random.choice(last_names)}"

        ws1.append([
            f"EMP-{i:04d}", full_name, dept, title,
            loc, country, hire.strftime("%Y-%m-%d"), emp_type,
            salary, bonus, rating, remote
        ])
    style_worksheet(ws1)

    # --- Sheet 2: Department_Budgets ---
    ws2 = wb.create_sheet(title="Department_Budgets")
    headers2 = ["Department", "Headcount", "Total_Payroll", "Training_Budget", "Software_Budget", "Budget_Utilization_Pct"]
    ws2.append(headers2)
    dept_stats = {
        "Engineering": (38, 4200000, 180000, 240000, 94.5),
        "Product & Design": (16, 1680000, 75000, 110000, 89.2),
        "Sales & Marketing": (22, 1850000, 95000, 140000, 92.1),
        "Finance & Operations": (14, 1220000, 50000, 85000, 86.8),
    }
    for d_name, (hc, payroll, train, sw, util) in dept_stats.items():
        ws2.append([d_name, hc, payroll, train, sw, util])
    style_worksheet(ws2, HEADER_FILL)

    # --- Sheet 3: Retention_Attrition ---
    ws3 = wb.create_sheet(title="Retention_Attrition")
    headers3 = ["Department", "Year", "Headcount_Start", "New_Hires", "Departures", "Headcount_End", "Retention_Rate_Pct"]
    ws3.append(headers3)
    for year in [2024, 2025, 2026]:
        for d_name in dept_stats.keys():
            start = random.randint(12, 35)
            hires = random.randint(3, 10)
            departures = random.randint(1, 4)
            end = start + hires - departures
            retention = round(((start - departures) / start) * 100, 1)
            ws3.append([d_name, year, start, hires, departures, end, retention])
    style_worksheet(ws3, SUBHEADER_FILL)

    out_path = BI_STUDIO_DIR / "hr_workforce_analytics.xlsx"
    wb.save(out_path)
    print(f"Created: {out_path} ({len(wb.sheetnames)} sheets, {ws1.max_row - 1} employee rows)")


def create_it_project_portfolio():
    """3. it_project_portfolio.xlsx - Software Projects, Sprints, Cloud Bills"""
    wb = openpyxl.Workbook()
    random.seed(202)

    # --- Sheet 1: Projects ---
    ws1 = wb.active
    ws1.title = "Projects"
    headers1 = [
        "Project_ID", "Project_Name", "Business_Unit", "Project_Manager",
        "Priority", "Phase", "Start_Date", "Target_End_Date",
        "Budget_USD", "Actual_Cost_USD", "Progress_Pct", "Health_Status"
    ]
    ws1.append(headers1)

    projects_def = [
        ("Cloud Infrastructure Modernization", "Core Platform", "Sophia Martinez", "High", "Execution", 450000, 310000, 72, "Green"),
        ("Mobile Customer Portal 3.0", "Digital Banking", "Lucas Meyer", "Critical", "Execution", 380000, 290000, 80, "Green"),
        ("Enterprise Data Lakehouse", "AI & Analytics", "Priya Sharma", "High", "Planning", 520000, 95000, 25, "Yellow"),
        ("Zero-Trust Security Framework", "Cybersecurity", "Alexandre Martin", "Critical", "Execution", 320000, 260000, 85, "Green"),
        ("Automated CI/CD Pipeline v2", "Core Platform", "Kenji Sato", "Medium", "Testing", 160000, 155000, 92, "Green"),
        ("AI Conversational Assistant", "Customer Care", "Olivia Taylor", "High", "Execution", 280000, 240000, 65, "Yellow"),
        ("ERP Accounting Integration", "Finance Operations", "Daniel Rossi", "Medium", "Execution", 240000, 255000, 60, "Red"),
        ("Multi-Region Disaster Recovery", "Infrastructure", "Marcus Brown", "High", "Initiation", 350000, 30000, 12, "Green"),
        ("Supply Chain Tracking Webhook", "Operations", "Hannah Lee", "Low", "Deployed", 110000, 108000, 100, "Green"),
        ("Global Identity & SSO Gateway", "Cybersecurity", "Victor Hugo", "Critical", "Testing", 290000, 280000, 95, "Green"),
        ("API Gateway Rate-Limiting Mesh", "Core Platform", "Sophia Martinez", "Medium", "Deployed", 95000, 92000, 100, "Green"),
        ("Real-time Fraud Detection Engine", "Risk Management", "Priya Sharma", "Critical", "Execution", 480000, 390000, 78, "Green"),
    ]

    for idx, row in enumerate(projects_def, start=1):
        s_date = date(2026, 1, 15) + timedelta(days=idx * 12)
        e_date = s_date + timedelta(days=random.randint(120, 280))
        ws1.append([
            f"PRJ-{idx:03d}", row[0], row[1], row[2],
            row[3], row[4], s_date.strftime("%Y-%m-%d"), e_date.strftime("%Y-%m-%d"),
            row[5], row[6], row[7], row[8]
        ])
    style_worksheet(ws1)

    # --- Sheet 2: Sprint_Delivery ---
    ws2 = wb.create_sheet(title="Sprint_Delivery")
    headers2 = [
        "Sprint_ID", "Team_Name", "Sprint_Start", "Committed_Points",
        "Completed_Points", "Velocity", "Defects_Found", "Defects_Resolved", "Delivery_Pct"
    ]
    ws2.append(headers2)
    teams = ["Platform Alpha", "Mobile Titans", "Data Ninjas", "Cyber Shield"]
    sp_date = date(2026, 1, 8)
    sprint_num = 1
    for w in range(1, 11):
        s_start = sp_date + timedelta(days=(w - 1) * 14)
        for t in teams:
            committed = random.randint(45, 75)
            completed = random.randint(committed - 8, committed + 4)
            velocity = completed
            defects = random.randint(2, 9)
            resolved = min(defects, random.randint(2, 8))
            delivery_rate = round((completed / committed) * 100, 1)
            ws2.append([
                f"SPR-2026-{sprint_num:03d}", t, s_start.strftime("%Y-%m-%d"),
                committed, completed, velocity, defects, resolved, delivery_rate
            ])
            sprint_num += 1
    style_worksheet(ws2, HEADER_FILL)

    # --- Sheet 3: Cloud_Infrastructure_Costs ---
    ws3 = wb.create_sheet(title="Cloud_Costs")
    headers3 = ["Account_ID", "Cloud_Provider", "Service_Category", "Environment", "Monthly_Cost_USD", "Budget_USD", "Cost_Variance"]
    ws3.append(headers3)
    cloud_services = [
        ("AWS", "Managed Kubernetes (EKS)", "Production", 14200, 13500),
        ("AWS", "Relational Database (RDS Aurora)", "Production", 9800, 10000),
        ("AWS", "Cloud Object Storage (S3)", "Production", 3400, 3500),
        ("AWS", "Dev/Staging EC2 & EKS", "Staging", 6200, 6000),
        ("Google Cloud", "BigQuery Lakehouse", "Production", 11500, 10500),
        ("Google Cloud", "Vertex AI Inference", "Production", 7800, 7000),
        ("Microsoft Azure", "Active Directory & SSO", "Production", 4600, 4800),
        ("Microsoft Azure", "DevOps Pipelines & Artifacts", "Dev", 2900, 3000),
    ]
    for idx, (provider, srv, env, cost, budget) in enumerate(cloud_services, start=1):
        ws3.append([f"ACC-{idx:03d}", provider, srv, env, cost, budget, cost - budget])
    style_worksheet(ws3, SUBHEADER_FILL)

    out_path = BI_STUDIO_DIR / "it_project_portfolio.xlsx"
    wb.save(out_path)
    print(f"Created: {out_path} ({len(wb.sheetnames)} sheets, {ws1.max_row - 1} project rows)")


def create_financial_budget():
    """4. financial_budget_opex.xlsx - Operating Expenses & Revenue Streams"""
    wb = openpyxl.Workbook()
    random.seed(303)

    # --- Sheet 1: Monthly_OpEx ---
    ws1 = wb.active
    ws1.title = "Monthly_OpEx"
    headers1 = [
        "Period", "Cost_Center", "Expense_Category", "Budget_USD",
        "Actual_USD", "Variance_USD", "Variance_Pct", "Status"
    ]
    ws1.append(headers1)

    cost_centers = ["R&D Engineering", "Global Sales", "Marketing & Growth", "General & Administrative", "Customer Success"]
    categories = [
        ("Salaries & Payroll", 120000, 280000),
        ("Cloud & SaaS Subscriptions", 15000, 45000),
        ("Office Lease & Facilities", 18000, 35000),
        ("Travel & Entertainment", 8000, 22000),
        ("Marketing Campaigns", 12000, 65000),
        ("Legal & Professional Fees", 5000, 18000),
    ]
    months = [f"2026-{m:02d}" for m in range(1, 9)]

    for month in months:
        for cc in cost_centers:
            for cat, min_b, max_b in categories:
                # Only some combinations apply to keep it realistic
                if cc != "Marketing & Growth" and cat == "Marketing Campaigns":
                    continue
                if cc == "Marketing & Growth" and cat == "Legal & Professional Fees":
                    continue
                budget = random.randint(min_b // 1000, max_b // 1000) * 1000
                actual = round(budget * random.uniform(0.91, 1.12), 0)
                variance = actual - budget
                var_pct = round((variance / budget) * 100, 2)
                status = "Over Budget" if variance > 0 else "Under Budget"
                ws1.append([month, cc, cat, budget, actual, variance, var_pct, status])
    style_worksheet(ws1)

    # --- Sheet 2: Revenue_Streams ---
    ws2 = wb.create_sheet(title="Revenue_Streams")
    headers2 = [
        "Period", "Business_Line", "Customer_Tier", "Recurring_ARR",
        "Professional_Services", "Total_Revenue", "Gross_Margin_Pct"
    ]
    ws2.append(headers2)
    biz_lines = ["Cloud Platform SaaS", "Enterprise Software Suite", "API Developer Platform"]
    tiers = ["Enterprise", "Mid-Market", "SMB"]

    for month in months:
        for bl in biz_lines:
            for tier in tiers:
                arr = random.randint(40, 140) * 1000
                services = random.randint(8, 30) * 1000 if tier == "Enterprise" else random.randint(2, 10) * 1000
                tot = arr + services
                margin = round(random.uniform(76.0, 88.0), 1)
                ws2.append([month, bl, tier, arr, services, tot, margin])
    style_worksheet(ws2, HEADER_FILL)

    out_path = BI_STUDIO_DIR / "financial_budget_opex.xlsx"
    wb.save(out_path)
    print(f"Created: {out_path} ({len(wb.sheetnames)} sheets, {ws1.max_row - 1} OpEx rows)")


if __name__ == "__main__":
    print("Generating generic sample Excel files in bi_studio/...")
    create_retail_sales()
    create_hr_workforce()
    create_it_project_portfolio()
    create_financial_budget()
    print("All generic Excel files generated successfully!")
