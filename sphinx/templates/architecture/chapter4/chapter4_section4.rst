4.4 Concurrency, Lock Hierarchy & Power/Crash Recovery
------------------------------------------------------------------------------------------

This section specifies the concurrency threading model (**Threading & Lock Hierarchy**), vendor HAL crash resilience (**Binder DeathRecipient Recovery**), and automotive power state transitions (**Suspend-to-RAM / Fast Wakeup**).

Concurrency & Lock Ordering Rules
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To prevent deadlocks and ``system_server`` Watchdog ANRs (triggered if a lock is held > 30 seconds), ``CarAudioService`` strictly enforces a unidirectional lock hierarchy:

1. **Rule 1 — Never Hold ``mLock`` Across Outbound Binder IPC**:
   Snapshot state variables inside ``synchronized (mLock)``, release the lock, and only then invoke ``IAudioControl`` HAL methods or client callbacks.
2. **Rule 2 — Dedicated Handler Thread for Focus & Routing**:
   All asynchronous VHAL rotary volume events and focus transitions are serialized onto a dedicated ``CarAudioHandlerThread`` (`Process.THREAD_PRIORITY_AUDIO`).
3. **Rule 3 — Read-Mostly Zone Configurations**:
   ``CarAudioZone`` and ``CarVolumeGroup`` topology arrays are immutable after boot initialization; runtime gain indices use ``AtomicInteger`` to allow lock-free reads during dumpsys and UI queries.

HAL Crash Resilience (``IBinder.DeathRecipient`` Flow)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If the native ``android.hardware.automotive.audiocontrol-service`` process crashes due to a driver fault, ``CarAudioService`` automatically recovers state without restarting the Android framework:

.. mermaid::

   sequenceDiagram
       autonumber
       participant CarAudio as CarAudioService (Java)
       participant Binder as Android Binder Driver
       participant AudioHAL as AudioControl HAL (C++ Daemon)
       participant DSP as Hardware DSP

       Note over CarAudio, AudioHAL: Normal Operation: linkToDeath(DeathRecipient) registered
       AudioHAL-xBinder: Process crash (SIGSEGV / Bus Fault)
       Binder->>CarAudio: binderDied() callback invoked on Binder thread
       activate CarAudio
       CarAudio->>CarAudio: Mark HAL disconnected & clear stale IAudioControl proxy
       
       Note over AudioHAL: init daemon automatically respawns vendor HAL (< 150ms)
       AudioHAL->>Binder: Register IAudioControl with ServiceManager
       Binder->>CarAudio: onServiceRegistered(".../IAudioControl/default")
       
       CarAudio->>AudioHAL: re-register IAudioControlCallback & linkToDeath()
       CarAudio->>AudioHAL: Replay cached zone mute & volume group gains
       AudioHAL->>DSP: Restore hardware mixer registers
       deactivate CarAudio
       Note over CarAudio, DSP: Seamless recovery complete (< 200ms) without rebooting IVI

Automotive Power State Lifecycle (Suspend-to-RAM / STR)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unlike consumer mobile devices, automotive ECUs transition into **Suspend-to-RAM (STR / Deep Sleep)** upon vehicle Ignition Off and must resume safety chimes within **< 500ms** on door open or Ignition On:

.. mermaid::

   stateDiagram-v2
       [*] --> ON_FULL : Vehicle Ignition ON
       ON_FULL --> PREPARE_SHUTDOWN : Ignition OFF (CarPowerManagementService)
       PREPARE_SHUTDOWN --> GARAGE_MODE : Background OTA / Maintenance
       GARAGE_MODE --> SUSPEND_TO_RAM : Flush Volume State & Mute Amplifier
       PREPARE_SHUTDOWN --> SUSPEND_TO_RAM : Immediate Sleep (No OTA pending)
       SUSPEND_TO_RAM --> FAST_WAKEUP : CAN Wakeup / Door Open (< 500ms)
       FAST_WAKEUP --> ON_FULL : Unmute Amplifier & Restore Zone Gains

.. list-table:: **Power Lifecycle Stage Responsibilities**
   :widths: 22 38 40
   :header-rows: 1

   * - Power State
     - ``CarAudioService`` Action
     - Hardware / DSP Action
   * - **PREPARE_SHUTDOWN**
     - Ramp down active media streams over 50ms to prevent speaker pop noise; persist volume group indices to flash.
     - Assert hardware mute pin on external power amplifier before cutting rail voltage.
   * - **SUSPEND_TO_RAM (STR)**
     - Release transient focus locks; retain parsed ``CarAudioZone`` objects in DRAM.
     - Enter ultra-low-power standby (< 2mA quiescent current).
   * - **FAST_WAKEUP**
     - Prioritize ``bus_adas_chime`` readiness before full media app resume.
     - Re-lock TDM/I2S PLL clocks and unmute primary driver zone within 150ms.
