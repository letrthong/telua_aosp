2.3 System, Hardware, Interface & Safety Requirements
------------------------------------------------------------------------------------------

This section specifies the **Hardware Resource Requirements (HWR)**, **External Interface Requirements (IR)**, **Functional Safety & Cybersecurity Requirements (SAF / SEC)**, and **Engineering Constraints (CON)** governing the target automotive platform.

Hardware & Acoustic Resource Requirements (HWR)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Hardware & Acoustic Resource Requirements (HWR)**
   :widths: 12 23 40 25
   :header-rows: 1

   * - Req ID
     - Hardware Subsystem
     - Technical Specification
     - Target Tolerance / Limit
   * - **HWR-01**
     - **Audio DSP Co-Processor**
     - Dedicated hardware DSP supporting at least 16 concurrent input buses and 12 output speaker channels with hardware parametric EQ.
     - >= 800 MHz clock, < 2ms internal pipeline delay.
   * - **HWR-02**
     - **TDM / I2S Serial Link**
     - Full-duplex Time-Division Multiplexing (TDM-16) digital audio bus between Cockpit SoC and external DSP/Amplifier.
     - 48 kHz sample rate, 24-bit depth, clock jitter < 50 ppm.
   * - **HWR-03**
     - **Amplifier Hardware Mute**
     - Dedicated GPIO hardware mute line controlled during SoC power rail sequencing to eliminate pop/click transients.
     - Assert mute >= 20ms prior to power rail drop.
   * - **HWR-04**
     - **Non-Volatile Storage**
     - Wear-leveled eMMC / UFS partition (`/data/system/car`) for persisting per-zone volume tables and user profiles.
     - Minimum 100,000 write/erase cycles endurance.

External Interface & Protocol Requirements (IR)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **External Interface & Protocol Requirements (IR)**
   :widths: 12 23 40 25
   :header-rows: 1

   * - Req ID
     - Interface Boundary
     - Protocol & Contract Specification
     - Data Format / SLA
   * - **IR-01**
     - **App <-> CarAudioService**
     - Android Binder IPC via ``android.car.media.ICarAudio`` (exposed through ``CarAudioManager`` SDK).
     - Parcelable bundles, caller UID/PID verified on every call.
   * - **IR-02**
     - **CarAudioService <-> HAL**
     - VINTF Stable AIDL interface ``android.hardware.automotive.audiocontrol.IAudioControl``.
     - Asynchronous oneway callbacks + synchronous gain setters.
   * - **IR-03**
     - **AudioFlinger <-> Audio HAL**
     - FastMixer POSIX shared memory ring buffer (`ashmem` / `memfd`) mapped to HAL bus ports (`bus00_media_out` .. `bus07_adas_out`).
     - Zero-copy 48 kHz / 16-bit or 24-bit PCM frames (5ms period).
   * - **IR-04**
     - **Vehicle HAL (VHAL) <-> Car**
     - Subscription to VHAL properties (`HW_ROTARY_INPUT`, `HW_KEY_INPUT`, `AP_POWER_STATE_REQ`).
     - Event delivery latency < 15ms from CAN-FD frame arrival.

Functional Safety (ISO 26262) & Cybersecurity (ISO 21434) Requirements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Safety (SAF) & Cybersecurity (SEC) Requirements Matrix**
   :widths: 12 23 42 23
   :header-rows: 1

   * - Req ID
     - Standard / Classification
     - Requirement Description
     - Verification Mechanism
   * - **SAF-01**
     - **ISO 26262 ASIL-B** (Freedom from Interference)
     - A crash or hang in non-critical infotainment apps (Media, Browser) shall never block or delay ADAS acoustic warnings (`bus_adas_chime`).
     - Fault injection & CPU starvation test on HIL rig.
   * - **SAF-02**
     - **ISO 26262 ASIL-B** (Plausibility Check)
     - ``AudioControlHAL`` shall clamp all incoming gain indices to calibrated safe hardware bounds (`min_gain` .. `max_gain`) to prevent speaker blowout or hearing damage.
     - Boundary value unit tests (`GTest`) & VTS fuzzing.
   * - **SAF-03**
     - **ISO 26262** (Degraded Safe Mode)
     - If ``CarAudioService`` becomes unresponsive, the DSP shall automatically fallback to direct CAN-triggered hardware chime generation.
     - Watchdog timeout simulation on physical ECU bench.
   * - **SEC-01**
     - **ISO/SAE 21434** (Least Privilege)
     - Only processes in the `system_server` SELinux domain shall be permitted to bind to `IAudioControl` HAL (`neverallow` enforced).
     - `sepolicy-analyze` & CTS `SELinuxHostTest`.
   * - **SEC-02**
     - **ISO/SAE 21434** (Permission Gate)
     - All volume and routing mutation APIs shall enforce `CAR_CONTROL_AUDIO_VOLUME` or `CAR_CONTROL_AUDIO_SETTINGS` privileged permissions.
     - `CtsCarTestCases` & `telua sec privapp` audit.
   * - **SEC-03**
     - **ISO/SAE 21434** (Config Integrity)
     - Acoustic routing tables (`car_audio_configuration.xml`) shall reside on a `dm-verity` cryptographically signed read-only partition (`/vendor/etc`).
     - Verified Boot attestation check (`telua sec status`).

Design & Compliance Constraints (CON)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **CON-01 (Project Treble Compliance)**: Framework code (`packages/services/Car/`) must not link against vendor-proprietary C/C++ shared libraries (`libvendor_*.so`); all communication must traverse VINTF AIDL.
- **CON-02 (Open-Source Licensing)**: User-space HAL and framework components must strictly comply with **Apache License 2.0**; GPLv3 copyleft dependencies are prohibited in `/system` and `/vendor` binaries.
- **CON-03 (CTS / VTS Certification)**: Any custom OEM extension must pass 100% of Google's Android Automotive CTS (`CtsCarAudioTestCases`) and VTS (`VtsHalAudioControlTargetTest`) suites without modification to AOSP public SDK signatures.
