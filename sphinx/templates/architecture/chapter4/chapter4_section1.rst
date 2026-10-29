4.1 Thiết Kế Lớp Đối Tượng (Class Modeling & Object Design)
----------------------------------------------------------------------------------

Phần này đặc tả thiết kế hướng đối tượng chi tiết (**Class Modeling**) của hệ thống điều khiển âm thanh bao gồm các thực thể cốt lõi, quan hệ kế thừa, quan hệ kết tập và các mẫu thiết kế (Design Patterns) áp dụng.

Sơ Đồ Lớp Kiến Trúc (Architectural Class Diagram)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. mermaid::

   classDiagram
       class CarAudioManager {
           +int getVolumeGroupCount()
           +int getGroupVolume(int groupId)
           +void setGroupVolume(int groupId, int index, int flags)
           +int requestAudioFocus(AudioFocusRequest req)
           +int abandonAudioFocus(AudioFocusRequest req)
           +registerVolumeCallback(CarVolumeCallback cb)
       }

       class CarAudioService {
           -List~CarAudioZone~ mZones
           -CarVolumeGroup mVolumeGroup
           -AudioControlWrapper mHalWrapper
           +initialize()
           +handleVolumeChange(int volume)
           +routeAudioBus(int usage, int zoneId)
           +resetConfiguration()
       }

       class CarAudioZone {
           -int mZoneId
           -String mZoneName
           -List~CarVolumeGroup~ mVolumeGroups
           +getVolumeGroups()
           +isMuted()
           +setMuted(boolean mute)
       }

       class CarVolumeGroup {
           -int mId
           -int mCurrentGain
           -int mMaxGain
           -int mMinGain
           +setGain(int gain)
           +getGain()
           +calculateDuckingGain()
       }

       class IAudioControlHAL {
           <<interface>>
           +setAudioPortConfig()
           +onVolumeChange(int bus, float gain)
           +registerCallback(IAudioControlCallback cb)
       }

       CarAudioManager --> CarAudioService : Binds via IPC / AIDL
       CarAudioService *-- CarAudioZone : Aggregates Multiple Zones
       CarAudioZone *-- CarVolumeGroup : Contains Volume Groups
       CarAudioService ..|> IAudioControlHAL : Controls Hardware via HAL

Các Mẫu Thiết Kế Áp Dụng (Design Patterns)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Mẫu Thiết Kế Được Ứng Dụng Trong Hệ Thống**
   :widths: 20 25 55
   :header-rows: 1

   * - Mẫu Thiết Kế
     - Lớp Áp Dụng
     - Mục Đích & Lợi Ích Kỹ Thuật
   * - **Facade Pattern**
     - ``CarAudioManager``
     - Đơn giản hóa toàn bộ sự phức tạp của hệ thống âm thanh ô tô thành một giao diện lập trình đơn giản cho các nhà phát triển ứng dụng bên trên.
   * - **Strategy Pattern**
     - ``AudioRoutingPolicy``
     - Cho phép hoán đổi linh hoạt chiến lược định tuyến âm thanh (ví dụ: Chế độ hội họp Conference, Chế độ xem phim Cinema, Chế độ cá nhân Driver-only).
   * - **Observer Pattern**
     - ``CarVolumeCallback``
     - Phát thông báo cập nhật bất đồng bộ cho các thành phần giao diện (UI) khi người dùng vặn núm âm lượng vật lý trên xe hơi.
