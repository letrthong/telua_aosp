4.1 Class Modeling & Object Design
------------------------------------------------------------------------------------------

This section specifies the object-oriented design model (**Class Modeling**) of the core audio subsystem, detailing key class relationships, interfaces, and applied design patterns.

Architectural Class Diagram
~~~~~~~~~~~~~~~~~~~~~~~~~~~

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

Applied Design Patterns
~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Design Patterns Applied in Subsystem Architecture**
   :widths: 20 25 55
   :header-rows: 1

   * - Design Pattern
     - Primary Class
     - Architectural Purpose & Engineering Benefit
   * - **Facade Pattern**
     - ``CarAudioManager``
     - Shields application developers from the internal complexity of Android Automotive routing policies behind a clean, intuitive client API.
   * - **Strategy Pattern**
     - ``AudioRoutingPolicy``
     - Enables dynamic runtime switching of audio distribution strategies (e.g., Driver-Centric Mode, Rear-Seat Entertainment Mode, Conference Mode).
   * - **Observer Pattern**
     - ``CarVolumeCallback``
     - Emits asynchronous volume change notifications to user interfaces whenever steering wheel controls or physical rotary dials are turned.
