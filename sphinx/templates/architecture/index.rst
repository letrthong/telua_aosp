Tài Liệu Thiết Kế Kiến Trúc Hệ Thống (Software Architecture Design)
=====================================================================

Chào mừng đến với tài liệu đặc tả kiến trúc phần mềm chuẩn công nghiệp (**Software Architecture & System Design Document**).

Tài liệu được cấu trúc theo phương pháp luận thiết kế hệ thống tiêu chuẩn quốc tế, phân chia rõ ràng các cấp độ từ tổng quan nghiệp vụ đến chi tiết kỹ thuật, quy trình vận hành và kiểm thử chất lượng:

.. list-table:: **Khung Kiến Trúc Phần Mềm (Software Architecture Framework)**
   :widths: 20 40 40
   :header-rows: 1

   * - Phần
     - Tên Chương
     - Mục Tiêu & Trọng Tâm Kỹ Thuật
   * - **Chương 1**
     - **Tổng Quan Hệ Thống (System Overview)**
     - Bối cảnh nghiệp vụ, mục tiêu dự án, phạm vi (Scope/Non-Scope) và thuộc tính chất lượng (SLA/SLO).
   * - **Chương 2**
     - **Yêu Cầu & Ca Sử Dụng (Requirements & Use Cases)**
     - Danh sách tác nhân (Actors), sơ đồ Use Case, ma trận yêu cầu chức năng (FR) và phi chức năng (NFR).
   * - **Chương 3**
     - **Thiết Kế Mức Cao (High-Level Design - HLD)**
     - Kiến trúc tổng thể phân tầng C4, tương tác giữa các Service/Subsystem, giao thức IPC và dòng dữ liệu.
   * - **Chương 4**
     - **Thiết Kế Mức Chi Tiết (Low-Level Design - LLD)**
     - Thiết kế hướng đối tượng (Class Diagram), máy trạng thái (State Machine), cấu trúc dữ liệu và Data Schema.
   * - **Chương 5**
     - **Đóng Gói & Triển Khai (Build & Deployment)**
     - Quy trình biên dịch tự động, CI/CD Pipeline, sơ đồ hạ tầng triển khai (Topology) và sổ tay vận hành (Runbook).
   * - **Chương 6**
     - **Đảm Bảo Chất Lượng & Kiểm Thử Tự Động (Quality & Automated Testing)**
     - Mô hình kim tự tháp kiểm thử, kiểm thử đơn vị & mocking (JUnit/GTest), Android CTS/VTS và tiêu chuẩn Quality Gates.

Tính Năng Tương Tác Trực Quan (Interactive Features)
-----------------------------------------------------
- **Sơ đồ Mermaid đa dạng**: Hỗ trợ trực tiếp Class Diagram, Sequence Diagram, State Diagram, Flowchart, C4 Block.
- **Trình xem phóng to tương tác (Zoom Modal)**: Phóng to toàn màn hình, lăn chuột (mouse wheel) để zoom tự do, kéo thả (pan/drag) linh hoạt.
- **Tải ảnh Vector (SVG Export)**: Tải trực tiếp sơ đồ vector độ phân giải cao không vỡ nét để chèn vào báo cáo hoặc tài liệu thuyết trình.

.. toctree::
   :maxdepth: 2
   :caption: Mục Lục Kiến Trúc Hệ Thống:
   :numbered:

   chapter1
   chapter2
   chapter3
   chapter4
   chapter5
   chapter6
