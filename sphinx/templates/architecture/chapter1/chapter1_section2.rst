1.2 Phạm Vi & Thuộc Tính Chất Lượng (Scope & Architecture Principles)
----------------------------------------------------------------------------------

Phần này phân định rõ ranh giới trách nhiệm của hệ thống (In-Scope vs. Out-of-Scope) cùng các nguyên tắc kiến trúc cốt lõi chi phối mọi quyết định kỹ thuật.

Phân Định Phạm Vi Dự Án (System Boundary & Scope)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Phân Định Phạm Vi Dự Án (Scope Matrix)**
   :widths: 20 40 40
   :header-rows: 1

   * - Hạng Mục
     - Trong Phạm Vi (In-Scope)
     - Ngoài Phạm Vi (Out-of-Scope)
   * - **Audio Management**
     - Quản lý định tuyến đa vùng (Multi-zone routing), phân xử Audio Focus, quản lý âm lượng nhóm (Volume Groups).
     - Thuật toán giải mã codec độc quyền của bên thứ 3 (phụ trách bởi DSP Firmware).
   * - **Giao Tiếp IPC**
     - Định nghĩa AIDL interfaces, IPC serialization, xử lý timeout và thread pooling.
     - Triển khai lớp vật lý của bus CAN/Ethernet trên ô tô.
   * - **Bảo Mật & Phân Quyền**
     - Áp dụng SELinux policies, kiểm tra quyền Android Permission (``android.car.permission.CAR_CONTROL_AUDIO_VOLUME``).
     - Quản lý chứng chỉ số PKI gốc của phương tiện (Hardware Security Module HSM cấp hệ thống).

Nguyên Tắc Kiến Trúc Cốt Lõi (Architectural Principles)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Nguyên Tắc Thiết Kế Cốt Lõi**
   :widths: 25 75
   :header-rows: 1

   * - Nguyên Tắc
     - Ý Nghĩa & Hướng Dẫn Thực Thi
   * - **Loose Coupling (Kết Hợp Lỏng)**
     - Các subsystem chỉ giao tiếp qua contract rõ ràng (AIDL / Interface). Không truy cập trực tiếp biến toàn cục hoặc memory nội bộ của nhau.
   * - **Single Responsibility (Đơn Trách Nhiệm)**
     - Mỗi service chịu trách nhiệm duy nhất: ``CarAudioService`` quản lý chính sách âm thanh, trong khi ``AudioControlHAL`` thuần túy điều khiển phần cứng.
   * - **Fail-Safe & Graceful Degradation**
     - Khi một service phụ crash, hệ thống tự động fallback về cấu hình an toàn mặc định thay vì làm sập toàn bộ hệ điều hành.
   * - **Observability by Design**
     - Tích hợp sẵn logs có cấu trúc, Perfetto tracing và dumpsys diagnostics ngay từ dòng code đầu tiên.

Chỉ Số Chất Lượng Phi Chức Năng (Quality Attributes & SLAs)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Hiệu Năng (Performance)**: CPU footprint của background service không vượt quá 3% core tổng thể trong điều kiện tải cao.
- **Tiêu Thụ Bộ Nhớ (Memory Footprint)**: Giới hạn heap memory tĩnh < 40MB.
- **Bảo Mật (Security)**: Toàn bộ IPC calls phải được xác thực danh tính caller PID/UID và phân quyền chi tiết.
