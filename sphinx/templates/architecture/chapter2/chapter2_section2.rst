2.2 Functional & Non-Functional Requirements (SRS)
------------------------------------------------------------------------------------------

This section provides the formal **Software Requirements Specification (SRS)** following **ISO/IEC/IEEE 29148** and **ASPICE SWE.1**, detailing the requirements taxonomy, prioritized Functional Requirements (**FR**), and Non-Functional Requirements (**NFR**) with measurable acceptance criteria.

Requirements Taxonomy & Decomposition
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. mermaid::

   graph TD
       SYS["System Stakeholder Needs<br/>(Connected Vehicle Infotainment)"]
       
       SYS --> FR["Functional Requirements (FR)<br/>(Routing, Focus, Ducking, Volume)"]
       SYS --> NFR["Non-Functional Requirements (NFR)<br/>(Latency, MTBF, CPU/RAM Budget)"]
       SYS --> HIR["Hardware & Interface Requirements (HWR / IR)<br/>(DSP, TDM/I2S, AIDL, VHAL)"]
       SYS --> SSR["Safety & Security Requirements (SAF / SEC)<br/>(ISO 26262 ASIL-B, SELinux, dm-verity)"]

Functional Requirements Matrix (FR)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Functional Requirements Specification Matrix (FR)**
   :widths: 10 20 38 18 14
   :header-rows: 1

   * - Req ID
     - Capability Domain
     - Technical Requirement Specification
     - Acceptance Criteria
     - Priority
   * - **FR-01**
     - Multi-Zone Audio Routing
     - The system shall support independent audio playback across at least 3 isolated acoustic zones (Zone 0: Primary Driver, Zone 1: Front Passenger, Zone 2: Rear Seats).
     - Streams routed to Zone 2 produce 0 dB crosstalk on Zone 0 buses.
     - **P0 (Mandatory)**
   * - **FR-02**
     - Volume Group Management
     - The system shall bundle related ``AudioAttributes`` usages (Media, Navigation, Voice, Call, Alarm) into independently controllable Volume Groups per zone.
     - Adjusting Group 0 (Media) gain does not alter Group 1 (Navigation) gain.
     - **P0 (Mandatory)**
   * - **FR-03**
     - Dynamic Audio Ducking
     - The system shall automatically attenuate lower-priority streams (minimum -15 dB ducking) within the active zone when navigation guidance or ADAS alerts are active.
     - Gain transition completes within 30ms with smooth ramp (no audible click).
     - **P0 (Mandatory)**
   * - **FR-04**
     - Persistent Volume & Mute State
     - Upon vehicle ignition cut-off (IGNITION OFF / STR), the system shall serialize per-user volume group indices and zone mute states to non-volatile storage.
     - 100% of user volume settings restore accurately on next Ignition ON.
     - **P1 (High)**
   * - **FR-05**
     - Hardware Fault Diagnostics
     - The subsystem shall detect and report missing DAC/DSP amplifier nodes across I2C/SPI buses to ``CarAudioService`` via ``IAudioControlCallback`` within 100ms.
     - Fault code logged to logcat & telemetry within 100ms of bus disconnect.
     - **P1 (High)**
   * - **FR-06**
     - Emergency Alert Override
     - Safety-critical usages (``USAGE_EMERGENCY``, ``USAGE_SAFETY``) shall preempt all active focus holders and bypass user mute settings in the primary driver zone.
     - Chime plays at calibrated safety gain even if Zone 0 is muted by user.
     - **P0 (Mandatory)**
   * - **FR-07**
     - Rotary Knob & Steering Control
     - The system shall consume ``HW_ROTARY_INPUT`` and ``HW_KEY_INPUT`` events from Vehicle HAL (VHAL) and adjust the currently active volume group context.
     - Each rotary detent step increments/decrements target group by 1 step index.
     - **P1 (High)**
   * - **FR-08**
     - Per-Zone Individual Mute
     - Authorized client apps shall be able to mute or unmute individual audio zones or volume groups via ``CarAudioManager`` without affecting other zones.
     - ``isVolumeGroupMuted()`` reflects updated state across all registered listeners.
     - **P2 (Medium)**

Non-Functional Requirements Matrix (NFR)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Non-Functional Requirements Specification Matrix (NFR)**
   :widths: 12 22 38 28
   :header-rows: 1

   * - Req ID
     - Quality Dimension
     - Target Engineering Constraint
     - Verification Method
   * - **NFR-01**
     - **End-to-End Latency**
     - Audio focus arbitration and hardware DSP gain transition latency shall be **< 30ms** (P99).
     - Perfetto trace timestamp delta from ``requestAudioFocus()`` to HAL ACK.
   * - **NFR-02**
     - **System Reliability (MTBF)**
     - **> 10,000 hours** of continuous operation without native memory leaks, fd exhaustion, or Watchdog ANR hangs.
     - 24-hour automated monkey/stress test with AddressSanitizer (ASan) enabled.
   * - **NFR-03**
     - **CPU & Memory Budget**
     - Steady-state CPU utilization **< 3%** of one core; resident heap footprint **< 40 MB** inside ``system_server``.
     - ``dumpsys meminfo`` and ``top`` profiling under 8 concurrent PCM streams.
   * - **NFR-04**
     - **Cold Boot & STR Wakeup**
     - Early safety chime readiness in **< 1.5s** on cold boot and **< 500ms** when resuming from Suspend-to-RAM (STR).
     - Bootchart / Kernel dmesg & GPIO oscilloscope measurement on HIL bench.
   * - **NFR-05**
     - **Crash Recovery Time**
     - Automated reconnection and gain state replay within **< 200ms** following an unexpected vendor AudioControl HAL crash.
     - Fault injection via ``kill -9 <hal_pid>`` during active playback.
   * - **NFR-06**
     - **API & Treble Stability**
     - 100% backwards compatibility across Android OS upgrades via frozen ``@VintfStability`` AIDL interfaces.
     - ``m-aidl-freeze-api`` check and Google VTS compliance suite.
