Section 3 of Chapter 3: System Architecture Diagrams
----------------------------------------------------

Phần này minh họa cách vẽ **Class Diagram** (sơ đồ lớp) và **Sequence Diagram** (sơ đồ tuần tự) trực tiếp bên trong tài liệu Sphinx Doc-as-Code sử dụng directive ``.. mermaid::``.

Class Diagram: Car Audio Architecture
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Dưới đây là sơ đồ lớp kiến trúc điều khiển âm thanh trên Android Automotive (AAOS):

.. mermaid::

   classDiagram
       class CarAudioManager {
           +int getVolumeGroupCount()
           +int getGroupVolume(int groupId)
           +void setGroupVolume(int groupId, int index, int flags)
           +requestAudioFocus(AudioFocusRequest req)
       }

       class CarAudioService {
           -List~CarAudioZone~ mZones
           -CarVolumeGroup mVolumeGroup
           +initialize()
           +handleVolumeChange(int volume)
           +routeAudioBus()
       }

       class CarAudioZone {
           -int mZoneId
           -String mZoneName
           +getVolumeGroups()
           +isMuted()
       }

       class IAudioControlHAL {
           <<interface>>
           +setAudioPortConfig()
           +onVolumeChange(int bus, float gain)
       }

       CarAudioManager --> CarAudioService : Binds via IPC / AIDL
       CarAudioService *-- CarAudioZone : Aggregates Zones
       CarAudioService ..|> IAudioControlHAL : Controls Hardware


Sequence Diagram: Audio Focus Request Flow
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Dưới đây là sơ đồ tuần tự biểu diễn luồng yêu cầu quyền phát âm thanh (**Audio Focus Request**) từ ứng dụng Media đến phần cứng âm thanh:

.. mermaid::

   sequenceDiagram
       autonumber
       actor User
       participant MediaApp as Media Player App
       participant CarAudio as CarAudioService
       participant FocusMgr as AudioFocusManager
       participant AudioHAL as Audio HAL (DSP)

       User->>MediaApp: Tap Play Button
       activate MediaApp
       MediaApp->>CarAudio: requestAudioFocus(USAGE_MEDIA)
       activate CarAudio

       CarAudio->>FocusMgr: evaluateFocusChange(CAR_ZONE_PRIMARY)
       activate FocusMgr
       FocusMgr-->>CarAudio: AUDIOFOCUS_REQUEST_GRANTED
       deactivate FocusMgr

       CarAudio->>AudioHAL: setAudioPortVolume(BUS_MEDIA, 0dB)
       activate AudioHAL
       AudioHAL-->>CarAudio: OK (DSP Ready)
       deactivate AudioHAL

       CarAudio-->>MediaApp: onAudioFocusChange(GAIN)
       deactivate CarAudio

       MediaApp->>AudioHAL: streamAudioPCM(48kHz, 2ch)
       AudioHAL-->>User: Output Sound via Car Speakers
       deactivate MediaApp


PlantUML Diagram: Full-Stack Request Flow
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Dưới đây là sơ đồ tương tác biểu diễn bằng directive ``.. uml::`` (PlantUML) được biên dịch tự động thành vector SVG:

.. uml::

   @startuml
   autonumber
   actor User
   participant "Frontend" as UI
   participant "Backend" as API
   database "Database" as DB

   User -> UI : Submit Action / Request
   activate UI
   UI -> API : REST / GraphQL API Call
   activate API
   API -> DB : SQL Query / Transaction
   activate DB
   DB --> API : Result Set
   deactivate DB
   API --> UI : JSON Response (HTTP 200)
   deactivate API
   UI --> User : Render Success View
   deactivate UI
   @enduml



