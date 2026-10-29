6.3 Kiểm Thử Tự Động & Tiêu Chuẩn Chất Lượng (Automated Test Pipeline & Quality Gates)
------------------------------------------------------------------------------------------

Phần này mô tả hệ thống kiểm thử tự động hóa tích hợp trong đường ống CI/CD (**Automated Test Pipeline**) và các tiêu chuẩn kiểm soát chất lượng phần mềm (**Quality Gates**).

Quy Trình Kiểm Thử Tự Động Trong CI/CD Pipeline
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Mọi Pull Request (PR) gửi lên hệ thống quản lý mã nguồn (GitLab / GitHub) đều kích hoạt chuỗi kiểm tra tự động trước khi được phép merge vào nhánh chính:

.. mermaid::

   graph LR
       PR([Pull Request Mới]) --> Static["1. Static Analysis<br/>(Clang-Tidy / SonarQube)"]
       Static --> Unit["2. Run Unit Tests<br/>(atest / GTest)"]
       Unit --> Coverage["3. Coverage Check<br/>(JaCoCo / LCOV)"]
       Coverage --> VTS["4. Automated VTS / CTS<br/>(Android Cuttlefish AVD)"]
       VTS --> Gate{Quality Gate Passed?}
       Gate -- Yes --> Approve([Cho Phép Merge])
       Gate -- No --> Reject([Chặn Merge & Báo Lỗi])

       classDef success fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
       classDef fail fill:#ffebee,stroke:#c62828,stroke-width:2px;
       class Approve success;
       class Reject fail;

Bộ Công Cụ Kiểm Thử Tự Động Của Android (AOSP Test Suites)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **Kiểm thử tự động bằng lệnh `atest`**:
   
   .. code-block:: bash

      # Chạy kiểm thử đơn vị tự động cho CarAudioService
      atest CarAudioServiceUnitTest

      # Chạy kiểm thử kèm đo độ phủ dòng code (Code Coverage)
      atest CarAudioServiceUnitTest --collect-tests-only --coverage

2. **Kiểm thử tương thích phần cứng Vendor (VTS - Vendor Test Suite)**:
   
   .. code-block:: bash

      # Kiểm tra tuân thủ giao tiếp chuẩn của AudioControl HAL AIDL
      atest VtsHalAudioControlTargetTest

3. **Kiểm tra rò rỉ bộ nhớ với AddressSanitizer (ASan)**:
   
   .. code-block:: bash

      # Biên dịch Native C++ với cờ kiểm tra tràn bộ nhớ
      SANITYZE_TARGET=address m android.hardware.automotive.audiocontrol-service

Chỉ Số Độ Phủ & Tiêu Chuẩn Kiểm Soát Chất Lượng (Quality Gates)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Để được gắn nhãn sẵn sàng xuất bản (Release-Ready), toàn bộ mã nguồn phải vượt qua các ngưỡng chất lượng cam kết sau:

.. list-table:: **Bảng Tiêu Chuẩn Kiểm Soát Chất Lượng (Quality Gates Matrix)**
   :widths: 25 35 40
   :header-rows: 1

   * - Chỉ Số Chất Lượng (KPI)
     - Ngưỡng Yêu Cầu (Threshold)
     - Biện Pháp Xử Lý Khi Vi Phạm
   * - **Độ Phủ Dòng Code (Line Coverage)**
     - Tối thiểu **>= 80%** toàn bộ module; **>= 95%** cho module phân xử Audio Focus
     - Chặn Pull Request tự động trên CI/CD runner.
   * - **Lỗ Hổng Bảo Mật (Vulnerabilities)**
     - **0** lỗi mức Critical hoặc High (SonarQube)
     - Yêu cầu lập trình viên vá lỗi bảo mật trước khi review lại.
   * - **Rò Rỉ Bộ Nhớ (Memory Leaks)**
     - **0 byte** leak sau 24 giờ chạy kiểm thử tải căng thẳng (Stress Test)
     - Phân tích dump heap qua Android Studio Profiler để giải phóng con trỏ.
   * - **Độ Trễ Phản Hồi (Performance SLA)**
     - 100% các lệnh chuyển kênh âm thanh thực hiện trong **< 30ms**
     - Đánh dấu Regression và rollback commit gây suy giảm hiệu năng.
