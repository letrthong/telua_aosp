3.3 Giao Thức Giao Tiếp & Luồng Dữ Liệu (Communication Protocols & Data Flow)
----------------------------------------------------------------------------------

Phần này mô tả các giao thức truyền thông liên tiến trình (IPC) và mô hình dòng dữ liệu âm thanh (**Audio Data Flow**) trong hệ thống.

Cơ Chế Giao Tiếp Liên Tiến Trình (IPC Mechanisms)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Hệ thống kết hợp ba cơ chế IPC tiêu chuẩn tùy theo yêu cầu về băng thông và độ trễ:

1. **Android Binder IPC / Stable AIDL**:
   - Dùng để truyền lệnh điều khiển, thiết lập cấu hình và đăng ký listener giữa App và ``CarAudioService``.
   - Độ tin cậy cao, hỗ trợ kiểm tra định danh caller UID/PID và cơ chế `linkToDeath` tự động giải phóng tài nguyên khi caller bị crash.
2. **Shared Memory / FastMixer Ring Buffer**:
   - Dùng để truyền dòng dữ liệu âm thanh PCM thô trực tiếp từ App xuống Audio HAL.
   - Tránh việc sao chép bộ nhớ (Zero-copy), đảm bảo độ trễ ở mức sub-millisecond.
3. **Hardware Bus (I2S, TDM, CAN-FD)**:
   - Dùng để giao tiếp giữa vi xử lý chính (SoC) và chip xử lý tín hiệu DSP bên ngoài.

Sơ Đồ Dòng Dữ Liệu Âm Thanh (Audio Data Flow Diagram)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. mermaid::

   graph LR
       subgraph Source_Layer [Nguồn Phát Âm Thanh]
           PCM_App["App PCM Audio<br/>(48kHz / 16-bit / Stereo)"]
           Tone_Gen["Vehicle Chimes<br/>(Seatbelt, Turn Signal)"]
       end

       subgraph Mixer_Layer [Tầng Trộn & Định Tuyến]
           FastMixer["AudioFlinger FastMixer<br/>(Ring Buffer)"]
           ZoneRouter["CarAudio Zone Router<br/>(Zone 0 / Zone 1)"]
       end

       subgraph HAL_DSP_Layer [Tầng Phần Cứng & DSP]
           HAL_Bus["Audio HAL Bus Devices<br/>(bus00_media, bus01_nav)"]
           DSP_Engine["DSP Mixer & Crossover<br/>(Equalizer / Reverb / Gain)"]
           DAC_Amp["DAC & Power Amplifier"]
       end

       PCM_App --> FastMixer
       Tone_Gen --> ZoneRouter
       FastMixer --> ZoneRouter
       ZoneRouter --> HAL_Bus
       HAL_Bus -->|TDM Stream| DSP_Engine
       DSP_Engine --> DAC_Amp
       DAC_Amp --> Speakers([Hệ Thống Loa Trên Xe])

Đặc Tả Interface AIDL Cốt Lõi
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Dưới đây là định nghĩa giao diện AIDL chuẩn mẫu được sử dụng giữa CarAudioService và HAL:

.. code-block:: aidl

   package android.hardware.automotive.audiocontrol;

   @VintfStability
   interface IAudioControl {
       /**
        * Thiết lập gain cho nhóm âm lượng theo bus vật lý
        */
       void setVolumeGroupGain(in int zoneId, in int groupId, in int gainIndex);

       /**
        * Bật/tắt chế độ Mute cho từng vùng âm thanh riêng biệt
        */
       void setAudioZoneMuted(in int zoneId, in boolean muted);

       /**
        * Đăng ký callback nhận sự kiện thay đổi từ phần cứng DSP
        */
       void registerAudioControlCallback(in IAudioControlCallback callback);
   }
