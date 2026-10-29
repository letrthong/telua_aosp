5.2 Mô Hình & Hạ Tầng Triển Khai (Deployment Topology & Environments)
----------------------------------------------------------------------------------

Phần này mô tả cấu trúc hạ tầng triển khai (**Deployment Topology**), sự khác biệt giữa các môi trường (Dev, Staging, Production) và cơ chế nâng cấp từ xa qua sóng OTA (**Over-The-Air Update**).

Sơ Đồ Cấu Trúc Môi Trường Triển Khai (Deployment Topology)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. mermaid::

   graph TB
       subgraph Cloud_Infra [Hạ Tầng Đám Mây & Máy Chủ Quản Trị]
           OTA_Server["OTA Release Server<br/>(Signed Image Payloads)"]
           Telemetry_Collector["Logging & Telemetry Server<br/>(Elastic / Grafana)"]
       end

       subgraph Target_Environments [Các Môi Trường Thực Thi]
           subgraph Env_Dev ["Môi Trường Phát Triển (Dev)"]
               AVD_Emulator["Android Virtual Device (AVD)<br/>(Cuttlefish / QEMU x86_64)"]
           end

           subgraph Env_Staging ["Môi Trường Thử Nghiệm (Staging)"]
               HIL_Rig["Hardware-In-the-Loop (HIL)<br/>(Băng thử phần cứng + DSP thật)"]
           end

           subgraph Env_Prod ["Môi Trường Thực Tế (Production Vehicle)"]
               IVI_ECU["In-Vehicle Infotainment ECU<br/>(Qualcomm / NXP SoC)"]
               Audio_DSP["Dedicated Audio DSP"]
               IVI_ECU -->|TDM / I2S Bus| Audio_DSP
           end
       end

       OTA_Server -->|Phân phối bản build thử nghiệm| HIL_Rig
       OTA_Server -->|Nâng cấp A/B OTA bảo mật| IVI_ECU
       IVI_ECU -->|Gửi metrics chẩn đoán định kỳ| Telemetry_Collector

Ma Trận Môi Trường Triển Khai (Environment Matrix)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **So Sánh Đặc Tính Các Môi Trường Triển Khai**
   :widths: 20 25 30 25
   :header-rows: 1

   * - Môi Trường
     - Mục Đích Sử Dụng
     - Cấu Hình Phần Cứng
     - Tần Suất Triển Khai
   * - **Dev (Development)**
     - Lập trình viên kiểm tra tính năng nhanh
     - QEMU Emulator trên máy workstation
     - Theo từng commit / pull request
   * - **Staging (HIL Bench)**
     - Đánh giá chất lượng âm thanh, độ trễ và tải DSP thật
     - Bàn test chuyên dụng gắn loa và microphone đo xung
     - Hàng đêm (Nightly Build)
   * - **Production (Vehicle)**
     - Xe hơi thương mại vận hành thực tế
     - Bộ điều khiển trung tâm Head Unit đạt chuẩn Automotive
     - Theo chu kỳ release OTA (mỗi 1-3 tháng)

Cơ Chế Cập Nhật An Toàn A/B System Partition
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Để đảm bảo xe hơi không bao giờ bị biến thành "cục gạch" (Bricked) khi gặp sự cố cúp nguồn đột ngột trong lúc nâng cấp, hệ thống áp dụng cơ chế phân vùng kép **A/B Seamless Update**:

1. **Active Partition (Slot A)**: Hệ thống đang chạy bình thường, người lái vẫn điều khiển âm thanh và nghe nhạc không bị gián đoạn.
2. **Background Download (Slot B)**: File payload cập nhật được tải xuống ngầm và ghi đè tuần tự vào Slot B.
3. **Verification**: Kiểm tra chữ ký số SHA-256 và giải mã an toàn qua Hardware Security Module (HSM).
4. **Slot Swap & Reboot**: Lần khởi động xe tiếp theo, bootloader tự động chuyển quyền kiểm soát sang Slot B. Nếu boot thất bại, bootloader tự động quay lui (Rollback) về Slot A trong vòng 15 giây.
