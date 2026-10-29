6.1 Chiến Lược Kiểm Thử & Mô Hình Kim Tự Tháp (Testing Strategy & Test Pyramid)
------------------------------------------------------------------------------------------

Phần này đặc tả chiến lược kiểm thử tổng thể (**Software Quality & Testing Strategy**) nhằm đảm bảo độ tin cậy, an toàn và tính sẵn sàng cao của hệ thống phần mềm.

Mô Hình Kim Tự Tháp Kiểm Thử (Testing Pyramid)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Hệ thống áp dụng mô hình kim tự tháp kiểm thử chuẩn công nghiệp, ưu tiên số lượng lớn kiểm thử đơn vị chạy nhanh, độc lập ở tầng dưới và thu hẹp dần lên các tầng tích hợp:

.. mermaid::

   graph TB
       Manual["4. Manual / Drive Test (Thử Nghiệm Thực Địa Trên Xe)<br/>(Kiểm tra độ hài lòng trải nghiệm âm học thực tế)"]
       HIL["3. System & HIL Automated Testing (Băng Thử Phần Cứng)<br/>(Kiểm tra phối hợp loa thật, DSP, CAN bus, đo sóng âm)"]
       Integration["2. Integration & Contract Testing (Kiểm Thử Tích Hợp)<br/>(Kiểm tra IPC AIDL, Robolectric, VTS/CTS Test Suites)"]
       Unit["1. Unit Testing & Mocking (Kiểm Thử Đơn Vị)<br/>(JUnit 5, Mockito, Google Test - 70% toàn bộ kịch bản test)"]

       Manual --- HIL
       HIL --- Integration
       Integration --- Unit

       classDef pyramid fill:#e0f2fe,stroke:#0284c7,stroke-width:2px;
       class Manual,HIL,Integration,Unit pyramid;

Bảng Phân Tầng Cấp Độ Kiểm Thử (Test Levels & Objectives)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Các Cấp Độ Kiểm Thử Trong Hệ Thống**
   :widths: 20 25 35 20
   :header-rows: 1

   * - Cấp Độ Kiểm Thử
     - Đối Tượng Kiểm Thử
     - Công Cụ / Framework
     - Môi Trường Thực Thi
   * - **Unit Testing**
     - Từng hàm, class logic độc lập (Audio Focus rules, Volume calc)
     - JUnit 5, Mockito, Google Test (GTest)
     - Máy tính lập trình viên / CI Local
   * - **Integration Testing**
     - Giao tiếp liên tiến trình Binder IPC giữa Service và HAL
     - Android Test Framework, VTS, AIDL Stubs
     - Android Virtual Device (AVD / Cuttlefish)
   * - **System & HIL Testing**
     - Toàn bộ chu trình âm thanh từ micro/màn hình đến DSP và loa xe
     - Python Automation, Audio Precision, CANoe
     - Băng thử Hardware-In-the-Loop (HIL)
   * - **Static Analysis & Security**
     - Phân tích tĩnh cú pháp, lỗ hổng bảo mật, rò rỉ bộ nhớ
     - SonarQube, Clang-Tidy, AddressSanitizer (ASan)
     - Pre-commit Hook & CI Pull Request

Nguyên Tắc Kiểm Thử Độc Lập (Test Isolation Principles)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **Không phụ thuộc phần cứng (Hardware-Independent)**: Toàn bộ Unit Test ở tầng Framework phải chạy được trên máy tính cá nhân hoặc CI Runner mà không cần cắm bo mạch xe hơi thật.
2. **Deterministic & Fast (Xác định & Tốc độ cao)**: Mỗi Unit Test phải thực thi trong < 10ms. Không sử dụng `Thread.sleep()`; thay vào đó sử dụng `TestLooper` hoặc `VirtualClock`.
3. **Given-When-Then BDD Style**: Mọi kịch bản kiểm thử phải tuân thủ cấu trúc 3 pha chuẩn mực: Thiết lập tiền đề (Given), Thực thi hành động (When), Kiểm tra kết quả (Then/Assert).
