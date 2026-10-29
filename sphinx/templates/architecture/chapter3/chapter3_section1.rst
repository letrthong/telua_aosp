3.1 Kiến Trúc Hệ Thống Tổng Thể (System Architecture)
----------------------------------------------------------------------------------

Phần này đặc tả kiến trúc phân tầng tổng thể (**Layered Architectural Model**) của hệ thống điều khiển âm thanh trên nền tảng ô tô thông minh.

Sơ Đồ Phân Tầng Kiến Trúc (Layered Architecture Diagram)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Hệ thống được thiết kế theo mô hình 4 tầng phân tách ranh giới rõ ràng:
1. **Application Layer (Tầng ứng dụng)**: Chứa các ứng dụng người dùng cuối và dịch vụ bên thứ ba.
2. **Framework Layer (Tầng khung dịch vụ Car Service)**: Nơi thực thi chính sách âm thanh, phân quyền và điều phối đa vùng.
3. **Native & HAL Layer (Tầng dịch vụ gốc & Trừu tượng phần cứng)**: Giao tiếp qua IPC Native và driver DSP.
4. **Hardware & Bus Layer (Tầng thiết bị vật lý & Mạng xe hơi)**: Phần cứng khuếch đại, bus I2S/TDM và loa.

.. mermaid::

   graph TB
       subgraph App_Layer ["1. Application Layer (Ứng Dụng)"]
           MediaApp["Media Player App<br/>(Spotify / Radio)"]
           NavApp["Navigation App<br/>(Google Maps / Waze)"]
           PhoneApp["Dialer / Telecom App"]
       end

       subgraph Framework_Layer ["2. Car Framework Layer (Android Automotive OS)"]
           CarAudioMgr["CarAudioManager<br/>(Public SDK Facade)"]
           CarAudioSvc["CarAudioService<br/>(Zone & Routing Policy Engine)"]
           AudioFocusMgr["AudioFocusManager<br/>(Arbitration Engine)"]
       end

       subgraph HAL_Layer ["3. Native & Hardware Abstraction Layer (HAL)"]
           AudioHAL["Audio HAL v7.0<br/>(PCM Stream Engine)"]
           AudioControlHAL["AudioControl HAL AIDL<br/>(Multi-bus DSP Mixer)"]
           VehicleHAL["Vehicle HAL (VHAL)<br/>(CAN / LIN / Ethernet Bus)"]
       end

       subgraph Hardware_Layer ["4. Hardware & Acoustic Layer (Phần Cứng Xe)"]
           DSP["Digital Signal Processor (DSP)<br/>(EQ, Delay, Crossover)"]
           Amp["Multi-Channel Power Amplifier"]
           Speakers["Car Speakers System<br/>(Front, Rear, Subwoofer)"]
       end

       MediaApp -->|IPC / AIDL| CarAudioMgr
       NavApp -->|IPC / AIDL| CarAudioMgr
       PhoneApp -->|IPC / AIDL| CarAudioMgr

       CarAudioMgr --> CarAudioSvc
       CarAudioSvc --> AudioFocusMgr

       CarAudioSvc -->|Binder IPC| AudioControlHAL
       CarAudioSvc -->|Native Stream| AudioHAL
       VehicleHAL -->|Volume Knob / Wheel Event| CarAudioSvc

       AudioControlHAL -->|SPI / I2C Control| DSP
       AudioHAL -->|I2S / TDM Audio Stream| DSP
       DSP --> Amp
       Amp --> Speakers

Bảng Phân Tích Công Nghệ Sử Dụng (Technology Stack)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Công Nghệ Cốt Lõi Của Hệ Thống**
   :widths: 25 35 40
   :header-rows: 1

   * - Tầng Kiến Trúc
     - Ngôn Ngữ & Framework
     - Giao Thức / Tiêu Chuẩn Áp Dụng
   * - **Application**
     - Kotlin, Java, Android Jetpack
     - MediaSession2, Android AudioFocus API
   * - **Framework**
     - Modern Java / C++ (Android Runtime)
     - Android Binder IPC, Stable AIDL
   * - **Native & HAL**
     - C++20, Rust, POSIX Threads
     - AIDL HAL, HIDL (Legacy), ALSA Driver
   * - **Hardware Bus**
     - C, DSP Assembly
     - I2S, TDM (Time-Division Multiplexing), CAN-FD
