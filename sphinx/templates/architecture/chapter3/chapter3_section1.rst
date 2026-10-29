3.1 System Architecture
------------------------------------------------------------------------------------------

This section specifies the high-level layered architecture model (**Layered Architectural Model**) of the intelligent automotive audio management system.

Layered Architecture Diagram
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The system architecture is structured across four decoupled architectural layers:
1. **Application Layer**: Contains user-facing infotainment applications and third-party media clients.
2. **Car Framework Layer (Android Automotive OS)**: Houses core routing policy engines, multi-zone volume grouping, and arbitration logic.
3. **Native & HAL Layer**: Provides real-time native audio engines, IPC stubs, and hardware abstraction interfaces.
4. **Hardware & Acoustic Layer**: Comprises physical DSP hardware, multi-channel amplifiers, and vehicle speaker arrays.

.. mermaid::

   graph TB
       subgraph App_Layer ["1. Application Layer"]
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

       subgraph Hardware_Layer ["4. Hardware & Acoustic Layer"]
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

Technology Stack Breakdown
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Core Technology Stack Breakdown**
   :widths: 25 35 40
   :header-rows: 1

   * - Architecture Layer
     - Languages & Frameworks
     - Communication Protocols & Standards
   * - **Application Layer**
     - Kotlin, Java, Android Jetpack
     - MediaSession2, Android AudioFocus API
   * - **Framework Layer**
     - Modern Java / C++ (Android Runtime)
     - Android Binder IPC, Stable AIDL
   * - **Native & HAL Layer**
     - C++20, Rust, POSIX Threads
     - AIDL HAL, HIDL (Legacy), ALSA Drivers
   * - **Hardware Bus Layer**
     - C, DSP Assembly
     - I2S, TDM (Time-Division Multiplexing), CAN-FD
