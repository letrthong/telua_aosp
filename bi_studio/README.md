# BI Studio - Generic Sample Excel Files

Thư mục này chứa các file Excel mẫu chuẩn (`.xlsx`) đa dạng về nghiệp vụ (bán hàng, nhân sự, dự án CNTT, tài chính doanh nghiệp) phục vụ việc kiểm thử các tính năng của **BI Studio** (chuyển đổi Excel → JSON, Power BI dashboard, Slicers, Multi-Tab Relational Report, Cross-sheet Consolidation).

Tất cả các file đều là file Excel thật định dạng `.xlsx`, có định dạng tiêu đề, xen kẽ màu (zebra striping), kiểu dữ liệu chuẩn (chuỗi, số, ngày tháng, phần trăm), và chia làm **nhiều sheet (Multi-tab)** có quan hệ với nhau.

---

## Danh mục file mẫu

| File | Lĩnh vực | Số Sheet | Số dòng chính | Các Sheet bên trong |
|---|---|:---:|:---:|---|
| [`global_retail_sales.xlsx`](./global_retail_sales.xlsx) | Bán lẻ & Thương mại điện tử | 4 | 150 giao dịch | `Sales_Transactions`, `Regional_Targets`, `Product_Catalog`, `Sales_Reps` |
| [`hr_workforce_analytics.xlsx`](./hr_workforce_analytics.xlsx) | Quản trị nhân sự & Lương thưởng | 3 | 90 nhân viên | `Employee_Directory`, `Department_Budgets`, `Retention_Attrition` |
| [`it_project_portfolio.xlsx`](./it_project_portfolio.xlsx) | Quản lý dự án CNTT & Cloud | 3 | 12 dự án lớn | `Projects`, `Sprint_Delivery`, `Cloud_Costs` |
| [`financial_budget_opex.xlsx`](./financial_budget_opex.xlsx) | Tài chính & Chi phí vận hành | 2 | 200 bản ghi chi phí | `Monthly_OpEx`, `Revenue_Streams` |

---

## Chi tiết cấu trúc từng file

### 1. `global_retail_sales.xlsx`
Phù hợp nhất để kiểm thử biểu đồ Combo (Doanh thu & Biên lợi nhuận), biểu đồ Bar/Donut theo Khu vực/Ngành hàng, và tạo báo cáo quan hệ giữa Doanh số và Chỉ tiêu vùng:
- **`Sales_Transactions`**: `Order_ID`, `Order_Date`, `Customer_ID`, `Customer_Segment` (Enterprise, Small Business, Consumer), `Region`, `Country`, `Category`, `Sub_Category`, `Units_Sold`, `Unit_Price`, `Revenue`, `Discount_Pct`, `Profit`, `Margin_Pct`.
- **`Regional_Targets`**: Chỉ tiêu doanh số `Q1_Target`, `Q2_Target`, `Q3_Target`, `Q4_Target`, `Annual_Target` theo từng Quốc gia & Khu vực.
- **`Product_Catalog`**: Bảng giá niêm yết, chi phí tiêu chuẩn và tỷ lệ biên lợi nhuận mục tiêu.
- **`Sales_Reps`**: Doanh số và tỷ lệ hoàn thành KPI (`Quota_Attainment_Pct`) của các đại diện kinh doanh.

### 2. `hr_workforce_analytics.xlsx`
Phù hợp để phân tích cơ cấu nhân sự, chi phí lương thưởng, tỉ lệ làm việc từ xa (Remote/Hybrid) và tỷ lệ giữ chân nhân viên:
- **`Employee_Directory`**: `Employee_ID`, `Full_Name`, `Department`, `Job_Title`, `Office_Location`, `Country`, `Hire_Date`, `Employment_Type`, `Base_Salary`, `Bonus_Pct`, `Performance_Rating` (1-5), `Remote_Status`.
- **`Department_Budgets`**: Ngân sách đào tạo, ngân sách phần mềm và tỷ lệ giải ngân theo phòng ban.
- **`Retention_Attrition`**: Số liệu tuyển mới, nghỉ việc và `Retention_Rate_Pct` qua các năm 2024–2026.

### 3. `it_project_portfolio.xlsx`
Phù hợp để theo dõi tiến độ dự án (Progress %), mức độ rủi ro (Health Status Green/Yellow/Red), hiệu suất Sprint Agile và chi phí hạ tầng điện toán đám mây:
- **`Projects`**: `Project_ID`, `Project_Name`, `Business_Unit`, `Project_Manager`, `Priority`, `Phase`, `Start_Date`, `Target_End_Date`, `Budget_USD`, `Actual_Cost_USD`, `Progress_Pct`, `Health_Status`.
- **`Sprint_Delivery`**: Điểm Story Point cam kết và hoàn thành, số lỗi phát hiện/sửa đổi theo từng Sprint.
- **`Cloud_Costs`**: Chi phí hàng tháng giữa AWS, Azure, Google Cloud theo từng môi trường (Production/Staging/Dev).

### 4. `financial_budget_opex.xlsx`
Phù hợp để kiểm thử phân tích chênh lệch ngân sách (Budget vs Actual Variance) và doanh thu định kỳ (ARR/SaaS):
- **`Monthly_OpEx`**: `Period` (2026-01 đến 2026-08), `Cost_Center`, `Expense_Category`, `Budget_USD`, `Actual_USD`, `Variance_USD`, `Variance_Pct`, `Status` (Over/Under Budget).
- **`Revenue_Streams`**: `Period`, `Business_Line`, `Customer_Tier`, `Recurring_ARR`, `Professional_Services`, `Total_Revenue`, `Gross_Margin_Pct`.

---

## Cách sử dụng khi test BI Studio

1. **Cách 1 - Upload trực tiếp**:
   - Trong giao diện **BI Studio**, nhấn nút **📂 Upload Excel / CSV** (hoặc kéo thả file vào vùng dropzone).
   - Chọn một trong các file trong thư mục `D:\wmshare\telua_aosp\bi_studio\`.
2. **Cách 2 - Chọn từ dropdown**:
   - Chọn trực tiếp một trong 4 file trên từ menu **Select Excel Dataset** trên thanh tiêu đề của BI Studio.
3. **Kiểm thử Multi-Tab / Quan hệ đa bảng**:
   - Sử dụng thanh **Sheet Tabs Bar** bên dưới để chuyển đổi qua lại giữa các sheet.
   - Nhấn nút **📑 Multi-Tab Report** để hệ thống tự động phát hiện khóa chung (Join Key), đối chiếu ma trận dữ liệu và tạo báo cáo tổng hợp.
