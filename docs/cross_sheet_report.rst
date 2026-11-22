.. _cross_sheet_report:

==============================================================
Báo Cáo Phân Tích Liên Kết Đa Tab (Cross-Sheet Report)
==============================================================

**File:** ``DAP_EA_MVP_targets_V1_20260910.xlsx`` | **Số lượng Tab:** 6 | **Tổng bản ghi:** 490

Ma Trận So Sánh Tổng Hợp
========================

.. list-table:: Thống kê Đa Tab
   :widths: 25 15 25 35
   :header-rows: 1

   * - Tên Tab / Worksheet
     - Số bản ghi
     - Tổng chỉ số chính
     - Top Danh mục
   * - **E-OEM IN**
     - 100
     - 5050.0
     - BMW1267, BMW1228, MB154332, BMW1229
   * - **E-OEM TH**
     - 100
     - 5050.0
     - BMW0001254, MB0006569, BMW0001923, BMW0002175
   * - **EV-OEM IN**
     - 40
     - 820.0
     - WUL153762, HYU153869, WUL155988, QIN167968
   * - **EV-OEM TH**
     - 50
     - 1275.0
     - QIN0145956, QIN0146430, QIN0155241, QIN0152181
   * - **J-OEM IN**
     - 100
     - 5050.0
     - TOY3824, TOY3837, TOY4312, TOY4440
   * - **J-OEM TH**
     - 100
     - 5050.0
     - ISU0111709, TOY0004180, ISU0001183, HON0002434

Biểu đồ Tỷ trọng giữa các Tab
==============================

.. mermaid::

   pie showData
    title Phân bổ bản ghi giữa các Tab
    "E-OEM IN" : 100
    "E-OEM TH" : 100
    "EV-OEM IN" : 40
    "EV-OEM TH" : 50
    "J-OEM IN" : 100
    "J-OEM TH" : 100

Biểu đồ So sánh Chỉ số
======================

.. mermaid::

   xychart-beta
    title "So sánh số lượng bản ghi giữa các Tab"
    x-axis ["E-OEM IN", "E-OEM TH", "EV-OEM IN", "EV-OEM TH", "J-OEM IN", "J-OEM TH"]
    y-axis "Bản ghi" 0 --> 100
    bar [100, 100, 40, 50, 100, 100]
