2.2 Đặc Tả Yêu Cầu Chức Năng & Phi Chức Năng (Functional & Non-Functional Requirements)
------------------------------------------------------------------------------------------

Phần này cung cấp ma trận chi tiết các yêu cầu chức năng (Functional Requirements - FR) và phi chức năng (Non-Functional Requirements - NFR) làm căn cứ kiểm định hệ thống.

Ma Trận Yêu Cầu Chức Năng (Functional Requirements)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Bảng Yêu Cầu Chức Năng (FR Matrix)**
   :widths: 15 25 45 15
   :header-rows: 1

   * - Mã Yêu Cầu
     - Tên Chức Năng
     - Mô Tả Chi Tiết Yêu Cầu Kỹ Thuật
     - Mức Ưu Tiên
   * - **FR-01**
     - Độc lập Zone Âm Thanh
     - Hệ thống phải hỗ trợ phân chia tối thiểu 3 vùng độc lập (Zone 0: Primary Driver, Zone 1: Passenger, Zone 2: Rear Seats).
     - **P0 (Bắt buộc)**
   * - **FR-02**
     - Quản lý Volume Groups
     - Phải nhóm các loại âm thanh cùng tính chất (Media, Navigation, Voice Call, Notification) vào các Volume Group riêng biệt.
     - **P0 (Bắt buộc)**
   * - **FR-03**
     - Audio Ducking tự động
     - Tự động hạ âm lượng nhạc nền (tối thiểu giảm 12dB) khi có âm thanh hướng dẫn đường đi hoặc cảnh báo va chạm.
     - **P1 (Quan trọng)**
   * - **FR-04**
     - Lưu trữ trạng thái tắt máy
     - Khi tắt máy xe (IGNITION OFF), hệ thống phải lưu trữ mức âm lượng hiện tại vào flash memory và phục hồi khi khởi động lại.
     - **P1 (Quan trọng)**
   * - **FR-05**
     - Chẩn đoán phần cứng HAL
     - Tự động phát hiện và gửi thông báo lỗi nếu chip khuếch đại hoặc DSP bị mất kết nối trên bus I2C/SPI.
     - **P2 (Tùy chọn)**

Ma Trận Yêu Cầu Phi Chức Năng (Non-Functional Requirements)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Bảng Yêu Cầu Phi Chức Năng (NFR Matrix)**
   :widths: 20 30 50
   :header-rows: 1

   * - Tiêu Chí NFR
     - Chỉ Số Đo Lường
     - Ràng Buộc & Tiêu Chuẩn Áp Dụng
   * - **Thời gian đáp ứng (Latency)**
     - Audio routing latency
     - Thời gian chuyển đổi giữa các nguồn âm thanh phải < 30ms.
   * - **Độ tin cậy (Reliability)**
     - Mean Time Between Failures (MTBF)
     - > 10,000 giờ hoạt động liên tục không xảy ra hiện tượng tràn bộ nhớ (Memory Leak) hoặc ANR.
   * - **An toàn phần mềm (Safety)**
     - Tiêu chuẩn an toàn chức năng ô tô
     - Phù hợp với tiêu chuẩn **ISO 26262 ASIL-B** đối với luồng âm cảnh báo nguy hiểm.
   * - **Bảo mật truy cập (Security)**
     - Phân quyền & Sandbox
     - Chỉ ứng dụng hệ thống ký bằng Platform Key mới được cấp quyền thay đổi cấu hình Audio Zone.
