2.1 Tác Nhân & Sơ Đồ Ca Sử Dụng (Actors & Use Case Diagrams)
----------------------------------------------------------------------------------

Phần này phân tích các tác nhân tham gia tương tác với hệ thống (Actors) cùng sơ đồ ca sử dụng nghiệp vụ (Use Cases).

Danh Sách Tác Nhân (System Actors)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Bảng Phân Tích Tác Nhân (Actor Matrix)**
   :widths: 20 25 55
   :header-rows: 1

   * - Tác Nhân (Actor)
     - Loại Tác Nhân
     - Trách Nhiệm & Hành Vi Chính
   * - **Driver / Passenger**
     - Human Actor
     - Tương tác qua màn hình cảm ứng, vô lăng hoặc giọng nói để phát nhạc, nhận cuộc gọi, chỉnh âm lượng.
   * - **Navigation / ADAS App**
     - Software Actor
     - Phát cảnh báo khẩn cấp (Lane departure, Speed warning, Turn-by-turn guidance) với quyền ưu tiên cao nhất.
   * - **Vehicle Audio HAL**
     - Hardware/System Actor
     - Tiếp nhận tín hiệu từ framework, điều khiển mixer phần cứng, DSP và các cổng vật lý của loa xe.
   * - **Telematics Service**
     - System Actor
     - Thu thập thông số vận hành và gửi log chẩn đoán từ xa lên máy chủ đám mây.

Sơ Đồ Ca Sử Dụng Tổng Quát (Use Case Diagram)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Dưới đây là sơ đồ tương tác ca sử dụng giữa các tác nhân và hệ thống điều khiển âm thanh:

.. mermaid::

   graph TD
       User([Driver / Passenger])
       ADAS([ADAS Safety System])
       HAL([Audio Control HAL])
       Cloud([Telematics Cloud])

       subgraph Audio_Management_System [Hệ Thống Điều Khiển Âm Thanh Trung Tâm]
           UC1((Phát Nhạc & Media))
           UC2((Phân Xử Quyền Phát - Audio Focus))
           UC3((Hạ Âm Lượng Tạm Thời - Ducking))
           UC4((Điều Chỉnh Âm Lượng Nhóm - Volume Group))
           UC5((Thu Thập Metrics Chẩn Đoán))
       end

       User --> UC1
       User --> UC4
       ADAS --> UC2
       UC1 ..> UC2 : <<include>>
       UC2 ..> UC3 : <<trigger khi có ADAS>>
       UC4 --> HAL
       UC3 --> HAL
       UC5 --> Cloud

Đặc Tả Chi Tiết Ca Sử Dụng Chính (Use Case Specification)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Ca Sử Dụng: UC-02 - Phân Xử Quyền Phát Âm Thanh (Audio Focus Arbitration)**

1. **Điều kiện tiên quyết (Preconditions)**: Hệ thống âm thanh đã khởi động thành công, các Audio Zone đã được định danh.
2. **Kích hoạt (Trigger)**: Một ứng dụng (ví dụ Media Player hoặc Navigation) gửi yêu cầu ``requestAudioFocus()``.
3. **Luồng sự kiện chính (Main Flow)**:

   - Framework kiểm tra quyền ưu tiên của ứng dụng yêu cầu so với các luồng âm thanh hiện tại.
   - Nếu luồng yêu cầu có độ ưu tiên cao hơn (ví dụ Navigation Alert > Nhạc nền):

     * Framework ra lệnh cho ứng dụng nhạc nền giảm âm lượng (Ducking) hoặc tạm dừng (Pause).
     * Gửi tín hiệu thông báo cấp quyền phát ``AUDIOFOCUS_REQUEST_GRANTED`` cho Navigation.
     * Cấu hình lại ma trận mixer ở tầng HAL DSP.

4. **Hậu điều kiện (Postconditions)**: Ứng dụng Navigation phát thông điệp rõ ràng tới loa của người lái, ứng dụng nhạc nền tiếp tục phát bình thường sau khi thông điệp kết thúc.
