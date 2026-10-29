5.3 Vận Hành, Giám Sát & Xử Lý Sự Cố (Observability & Runbook)
----------------------------------------------------------------------------------

Phần này cung cấp các công cụ giám sát hiệu năng (**Observability**) và sổ tay vận hành (**Operations Runbook**) phục vụ việc chẩn đoán và khắc phục sự cố nhanh chóng.

Công Cụ Giám Sát & Thu Thập Log (Monitoring & Tracing)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Android Logcat Filtering**: Lọc các bản tin nhật ký với tiền tố quy chuẩn:
  
  .. code-block:: bash

     adb logcat -s CarAudioService:V CarAudioZone:D AudioControlHAL:I

- **Dumpsys Car Audio Diagnostics**: Xuất toàn bộ trạng thái cấu hình runtime của Audio Zones và Volume Groups:

  .. code-block:: bash

     adb shell dumpsys car_service --services CarAudioService

- **Perfetto Performance Tracing**: Đo độ trễ từ lúc ứng dụng gửi Audio Focus đến khi loa nhận được tín hiệu:

  .. code-block:: bash

     perfetto --txt -c /data/misc/perfetto-configs/audio_trace.pbtx -o /data/misc/perfetto-traces/trace.perfetto-trace

Sổ Tay Xử Lý Sự Cố Tiêu Chuẩn (Troubleshooting Runbook)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Ma Trận Khắc Phục Sự Cố Hệ Thống (Diagnostic Runbook)**
   :widths: 20 25 30 25
   :header-rows: 1

   * - Triệu Chứng Lỗi
     - Nguyên Nhân Tiềm Ẩn
     - Lệnh Kiểm Tra / Chẩn Đoán
     - Biện Pháp Khắc Phục
   * - **Không có âm thanh phát ra loa**
     - Bus HAL bị Mute hoặc DSP chưa nhận được lệnh khởi tạo nguồn cấp điện
     - ``adb shell dumpsys car_service --services CarAudioService | grep isMuted``
     - Khởi động lại Audio HAL: ``adb shell setprop ctl.restart vendor.audiocontrol-default``
   * - **Nhạc không tự hạ âm lượng khi có dẫn đường**
     - Thuộc tính ``can_duck`` bị vô hiệu hóa hoặc Context Mapping trong XML bị sai ID
     - Kiểm tra file ``/vendor/etc/car_audio_configuration.xml`` trên thiết bị
     - Đồng bộ lại ma trận Volume Groups và gán đúng quyền ưu tiên trong file XML.
   * - **Lỗi cấp quyền (Security Exception)**
     - Ứng dụng gọi API điều chỉnh âm lượng thiếu permission hệ thống
     - Xem log: ``adb logcat | grep "requires CAR_CONTROL_AUDIO_VOLUME"``
     - Cấp quyền tương ứng trong file ``AndroidManifest.xml`` của ứng dụng hoặc cấp thủ công qua ``adb shell pm grant``.
   * - **Dịch vụ Car Service bị Crash khi khởi động**
     - File cấu hình XML có cú pháp không hợp lệ (Invalid XML schema)
     - Xem log khởi động: ``adb logcat -b crash``
     - Chạy công cụ kiểm tra cú pháp: ``xmllint --noout /vendor/etc/car_audio_configuration.xml``
