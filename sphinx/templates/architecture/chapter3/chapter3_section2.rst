3.2 Luồng Tương Tác Giữa Các Thành Phần (Component Interactions)
----------------------------------------------------------------------------------

Phần này mô tả chi tiết các luồng tương tác thời gian thực (**Sequence Flows**) giữa ứng dụng, framework và phần cứng khi thực hiện phát âm thanh và phân xử quyền phát.

Sơ Đồ Tuần Tự: Luồng Yêu Cầu Quyền Phát (Audio Focus Request Flow)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Khi người dùng bật nhạc hoặc có cảnh báo dẫn đường từ ứng dụng bản đồ, hệ thống thực hiện phân xử theo sơ đồ tuần tự dưới đây:

.. mermaid::

   sequenceDiagram
       autonumber
       actor Driver as Người Lái Xe
       participant NavApp as Navigation App
       participant MediaApp as Media Player (Nhạc)
       participant CarAudio as CarAudioService
       participant FocusMgr as AudioFocusManager
       participant AudioHAL as Audio Control HAL (DSP)

       Note over Driver, MediaApp: Trạng thái ban đầu: MediaApp đang phát nhạc ở Zone 0 (Primary)
       Driver->>NavApp: Nhập điểm đến & bắt đầu dẫn đường
       activate NavApp
       
       NavApp->>CarAudio: requestAudioFocus(USAGE_ASSISTANCE_NAVIGATION_GUIDANCE)
       activate CarAudio

       CarAudio->>FocusMgr: evaluateFocusChange(USAGE_MEDIA vs USAGE_NAV)
       activate FocusMgr
       FocusMgr-->>CarAudio: DUCK_LOWER_PRIORITY (Hạ âm lượng nhạc)
       deactivate FocusMgr

       CarAudio->>AudioHAL: setVolumeGroupGain(GROUP_MEDIA, -15dB)
       activate AudioHAL
       AudioHAL-->>CarAudio: OK (Gain Applied)
       deactivate AudioHAL

       CarAudio-->>MediaApp: onAudioFocusChange(AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK)
       CarAudio-->>NavApp: AUDIOFOCUS_REQUEST_GRANTED
       deactivate CarAudio

       NavApp->>AudioHAL: streamAudio("Rẽ phải sau 100 mét")
       AudioHAL-->>Driver: Phát giọng nói dẫn đường to rõ, nhạc nền êm dịu

       Note over NavApp, AudioHAL: Sau khi đọc xong câu hướng dẫn
       NavApp->>CarAudio: abandonAudioFocus()
       activate CarAudio
       deactivate NavApp

       CarAudio->>AudioHAL: setVolumeGroupGain(GROUP_MEDIA, 0dB)
       CarAudio-->>MediaApp: onAudioFocusChange(AUDIOFOCUS_GAIN)
       deactivate CarAudio
       Note over MediaApp, Driver: Âm lượng nhạc tự động trở lại mức ban đầu
