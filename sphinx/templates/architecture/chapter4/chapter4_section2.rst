4.2 Máy Trạng Thái & Vòng Đời Hoạt Động (State Machine & Lifecycle Transitions)
----------------------------------------------------------------------------------

Phần này đặc tả máy trạng thái hữu hạn (**Finite State Machine - FSM**) điều khiển vòng đời yêu cầu và giải phóng quyền phát âm thanh (**Audio Focus Lifecycle**).

Sơ Đồ Máy Trạng Thái (Audio Focus State Machine Diagram)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Vòng đời của một đối tượng yêu cầu quyền phát âm thanh được biểu diễn qua các trạng thái chuẩn sau:

.. mermaid::

   stateDiagram-v2
       [*] --> IDLE : Khởi tạo AudioFocusRequest

       IDLE --> REQUESTING : Gọi requestAudioFocus()
       REQUESTING --> ACTIVE_FOCUS : Được cấp quyền (GAIN)
       REQUESTING --> FAILED_REJECTED : Bị từ chối do ưu tiên thấp

       ACTIVE_FOCUS --> DUCKED : Ứng dụng ưu tiên cao hơn xuất hiện (LOSS_TRANSIENT_CAN_DUCK)
       DUCKED --> ACTIVE_FOCUS : Ứng dụng ưu tiên cao kết thúc (GAIN)

       ACTIVE_FOCUS --> PAUSED_TRANSIENT : Tạm dừng do cuộc gọi thoại (LOSS_TRANSIENT)
       PAUSED_TRANSIENT --> ACTIVE_FOCUS : Cuộc gọi thoại kết thúc (GAIN)

       ACTIVE_FOCUS --> PERMANENT_LOSS : Bị ứng dụng khác thay thế hoàn toàn (LOSS)
       PERMANENT_LOSS --> RELEASED : Giải phóng tài nguyên
       
       ACTIVE_FOCUS --> RELEASED : Ứng dụng chủ động gọi abandonAudioFocus()
       FAILED_REJECTED --> IDLE : Reset trạng thái
       RELEASED --> [*]

Bảng Ma Trận Chuyển Trạng Thái (State Transition Table)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Quy Tắc Chuyển Đổi Trạng Thái**
   :widths: 20 25 30 25
   :header-rows: 1

   * - Trạng Thái Hiện Tại
     - Sự Kiện Kích Hoạt
     - Điều Kiện Ràng Buộc (Guard)
     - Trạng Thái Đích
   * - **IDLE**
     - ``requestAudioFocus()``
     - Request hợp lệ
     - **REQUESTING**
   * - **REQUESTING**
     - Phân xử chính sách
     - Priority >= Current Owner
     - **ACTIVE_FOCUS**
   * - **ACTIVE_FOCUS**
     - Nav alert xuất hiện
     - Hỗ trợ can_duck == true
     - **DUCKED**
   * - **ACTIVE_FOCUS**
     - Cuộc gọi thoại đến
     - Hỗ trợ can_duck == false
     - **PAUSED_TRANSIENT**
   * - **DUCKED / PAUSED**
     - Nguồn âm thanh cao hơn kết thúc
     - Không còn luồng ưu tiên nào
     - **ACTIVE_FOCUS**
   * - **Bất kỳ trạng thái**
     - ``abandonAudioFocus()``
     - Caller hợp lệ
     - **RELEASED**
