5.1 Quy Trình Đóng Gói & Tích Hợp Liên Tục (Build System & CI/CD Pipeline)
----------------------------------------------------------------------------------

Phần này mô tả công cụ biên dịch (**Build System**), quy trình kiểm thử tự động hóa và đường ống phân phối liên tục (**CI/CD Pipeline**).

Sơ Đồ Đường Ống CI/CD (CI/CD Pipeline Workflow)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Toàn bộ mã nguồn và tài liệu kiến trúc được tích hợp tự động qua hệ thống Git server và runner theo sơ đồ sau:

.. mermaid::

   graph LR
       Commit["Git Commit & Push"] --> Lint["1. Lint & Format Check"]
       Lint --> Test["2. Unit & Mock Tests"]
       Test --> Build["3. AOSP Soong & C++ Build"]
       Build --> DocBuild["4. Sphinx Docs-as-Code Build"]
       DocBuild --> Artifact["5. Generate OTA Payload & HTML Docs"]
       Artifact --> Deploy["Deploy to Staging / HIL Test Rig"]

       classDef success fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
       class Commit,Deploy success;

Các Lệnh Biên Dịch Tiêu Chuẩn (Build Commands)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **Biên Dịch Tài Liệu Sphinx Docs-as-Code (Telua Docs Pipeline)**:

   .. code-block:: bash

      # Khởi tạo dự án theo mẫu kiến trúc chuẩn
      telua docs init -t architecture

      # Biên dịch tài liệu HTML thông qua staging an toàn (giữ sạch git workspace)
      telua docs build

      # Khởi chạy preview server cục bộ tại http://localhost:8080
      telua docs start 8080

2. **Biên Dịch Subsystem Native C++ / Android Service**:

   .. code-block:: bash

      # Thiết lập môi trường Android AOSP
      source build/envsetup.sh
      lunch aosp_car_x86_64-userdebug

      # Biên dịch module CarAudioService và AudioControl AIDL HAL
      m android.hardware.automotive.audiocontrol-service
      m CarAudioService

3. **Chạy Bộ Kiểm Thử Đơn Vị Tự Động (Unit Testing)**:

   .. code-block:: bash

      # Chạy kiểm thử tự động với atest
      atest CarAudioServiceUnitTest
      atest VtsHalAudioControlTargetTest
