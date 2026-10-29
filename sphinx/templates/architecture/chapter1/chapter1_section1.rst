1.1 Bối Cảnh Nghiệp Vụ & Mục Tiêu Dự Án (Project Context & Business Objectives)
----------------------------------------------------------------------------------

Phần này đặc tả bối cảnh kinh doanh, bài toán cần giải quyết và các mục tiêu chiến lược của hệ thống kiến trúc phần mềm.

Bối Cảnh & Bài Toán Đặt Ra (Problem Statement)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Trong các hệ thống nhúng thông minh và nền tảng ô tô kết nối (**Connected Vehicles / AAOS**), yêu cầu về khả năng mở rộng, độ trễ cực thấp và tính độc lập module ngày càng trở nên cấp thiết:

- **Độ phức tạp tăng cao**: Hệ thống tích hợp nhiều subsystem (Audio, Telematics, Sensor, Power HAL, UI Service) cần cơ chế điều phối tập trung.
- **Yêu cầu an toàn & thời gian thực**: Xử lý tín hiệu khẩn cấp (cảnh báo ADAS, chuông báo động, cuộc gọi eCall) phải ưu tiên tuyệt đối so với các tác vụ giải trí đa phương tiện (Media Player).
- **Tính bảo trì dài hạn**: Kiến trúc phải tuân thủ chuẩn mở (Open Architecture), cho phép thay thế hoặc nâng cấp phần cứng/HAL mà không ảnh hưởng tới tầng ứng dụng.

Mục Tiêu Chiến Lược Của Hệ Thống (Architecture Goals)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Mục Tiêu Thiết Kế Hệ Thống**
   :widths: 25 35 40
   :header-rows: 1

   * - Mục Tiêu
     - Chỉ Số Đo Lường (Metrics)
     - Giá Trị Cam Kết
   * - **Độ Trễ Thấp (Low Latency)**
     - Audio routing & focus latency
     - < 50ms từ lúc phát sự kiện đến DSP output.
   * - **Tính Sẵn Sàng (High Availability)**
     - System uptime & crash recovery
     - 99.99% uptime, tự động phục hồi trong < 200ms khi crash.
   * - **Độc Lập Nền Tảng (Portability)**
     - HAL / Driver abstraction layer
     - Đổi chipset/DSP không cần viết lại Car Framework Service.
   * - **Tài Liệu Hóa Tự Động (Doc-as-Code)**
     - Sphinx + Mermaid + Git isolation
     - 100% tài liệu được build CI/CD không làm dơ git workspace.

Đối Tượng & Vai Trò Các Bên Liên Quan (Key Stakeholders)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **System Architects**: Định hình ranh giới module, phê duyệt giao diện IPC và luồng dữ liệu liên service.
2. **Framework & HAL Engineers**: Hiện thực hóa các interface AIDL, Service logic và driver tương thích.
3. **QA & Validation Team**: Kiểm thử tự động hóa theo ma trận Use Cases và các kịch bản kiểm thử ngoại lệ.
4. **DevOps & Release Team**: Quản lý pipeline CI/CD, đóng gói image và quy trình cập nhật OTA.
