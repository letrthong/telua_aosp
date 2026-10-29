4.3 Cấu Trúc Dữ Liệu & Data Schema (Data Models & Configuration)
----------------------------------------------------------------------------------

Phần này mô tả cấu trúc dữ liệu cấu hình âm thanh (**Car Audio Configuration Schema**) dùng để khởi tạo và ánh xạ phần cứng khi hệ thống boot.

Lược Đồ Cấu Trúc Thực Thể Dữ Liệu (ER Diagram)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. mermaid::

   erDiagram
       AUDIO_ZONE ||--o{ VOLUME_GROUP : contains
       VOLUME_GROUP ||--o{ AUDIO_CONTEXT : maps
       AUDIO_CONTEXT ||--|| BUS_DEVICE : routes_to

       AUDIO_ZONE {
           int zone_id PK
           string zone_name
           boolean is_primary
       }
       VOLUME_GROUP {
           int group_id PK
           int zone_id FK
           int default_gain
           int min_gain
           int max_gain
           int step_size
       }
       AUDIO_CONTEXT {
           int context_id PK
           string context_name
           int priority_level
       }
       BUS_DEVICE {
           string bus_address PK
           string hal_device_port
           int sample_rate
       }

Đặc Tả File Cấu Hình Mẫu (car_audio_configuration.xml)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: xml

   <?xml version="1.0" encoding="utf-8"?>
   <carAudioConfiguration version="2.0">
       <zones>
           <!-- Vùng âm thanh chính cho người lái (Primary Zone) -->
           <zone name="Primary Zone" isPrimary="true" id="0">
               <volumeGroups>
                   <!-- Nhóm âm lượng 0: Media & Radio -->
                   <group id="0">
                       <context context="music"/>
                       <context context="radio"/>
                       <device address="bus00_media_out"/>
                   </group>
                   <!-- Nhóm âm lượng 1: Dẫn đường & Cảnh báo -->
                   <group id="1">
                       <context context="navigation"/>
                       <context context="voice_command"/>
                       <device address="bus01_nav_out"/>
                   </group>
                   <!-- Nhóm âm lượng 2: Cuộc gọi điện thoại -->
                   <group id="2">
                       <context context="call"/>
                       <context context="call_ring"/>
                       <device address="bus02_call_out"/>
                   </group>
               </volumeGroups>
           </zone>
       </zones>
   </carAudioConfiguration>

Từ Điển Dữ Liệu Các Trường Cốt Lõi (Data Dictionary)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Bảng Định Nghĩa Thuộc Tính Dữ Liệu**
   :widths: 20 20 60
   :header-rows: 1

   * - Thuộc Tính
     - Kiểu Dữ Liệu
     - Giải Thích Chi Tiết
   * - ``zone_id``
     - Integer (0..3)
     - Định danh duy nhất của vùng âm thanh trên xe (0: Driver, 1: Front Passenger, 2: Rear Left, 3: Rear Right).
   * - ``group_id``
     - Integer (0..7)
     - Định danh nhóm âm lượng điều khiển chung (Media, Nav, Phone, Notification, System).
   * - ``bus_address``
     - String
     - Tên cổng bus vật lý tương ứng đăng ký trong file cấu hình ALSA/HAL (ví dụ: ``bus00_media_out``).
   * - ``default_gain``
     - Integer (dB)
     - Mức âm lượng mặc định tính bằng chỉ số index gain khi người dùng reset cài đặt gốc.
