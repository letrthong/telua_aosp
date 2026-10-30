2.3 Bidirectional Requirements Traceability Matrix (RTM)
------------------------------------------------------------------------------------------

This section establishes the **Bidirectional Requirements Traceability Matrix (RTM)** in compliance with **Automotive SPICE (ASPICE SWE.2 & SWE.3)** and **ISO 26262**, ensuring every requirement maps forward to architectural components and verification tests, and backward to business use cases.

ASPICE Traceability Model
~~~~~~~~~~~~~~~~~~~~~~~~~

.. mermaid::

   graph LR
       UC["System Use Cases<br/>(UC-01 .. UC-05)"] <-->|Derives| FR["Functional & NFR Specs<br/>(FR-01 .. NFR-04)"]
       FR <-->|Allocated to| ARCH["HLD / LLD Components<br/>(Chapter 3 & Chapter 4)"]
       ARCH <-->|Verified by| TEST["Automated Test Suites<br/>(Unit / VTS / HIL)"]

Bidirectional Traceability Matrix
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **End-to-End Requirements Traceability Matrix (RTM)**
   :widths: 12 14 26 24 24
   :header-rows: 1

   * - Req ID
     - Source Use Case
     - Allocated HLD / LLD Component
     - Interface / Schema Contract
     - Verification Test Case ID
   * - **FR-01**
     - ``UC-01`` (Media Playback)
     - ``CarAudioService``, ``CarAudioZone`` (Sec 3.1, 4.1)
     - ``car_audio_configuration.xml`` (``<zone id="0..2">``)
     - ``CarAudioZoneUnitTest#testMultiZoneRouting``
   * - **FR-02**
     - ``UC-04`` (Volume Groups)
     - ``CarVolumeGroup``, ``CarAudioManager`` (Sec 4.1)
     - ``IAudioControl.setVolumeGroupGain()``
     - ``CarVolumeGroupUnitTest#testSetGroupVolume``
   * - **FR-03**
     - ``UC-02``, ``UC-03`` (Focus & Ducking)
     - ``AudioFocusManager``, ``AudioControlHAL`` (Sec 3.2, 4.2)
     - ``AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK``
     - ``CarAudioServiceUnitTest#testNavAlertTriggersDucking``
   * - **FR-04**
     - ``UC-04`` (Persistent State)
     - ``CarAudioSettings``, ``CarPowerPolicy`` (Sec 4.3, 4.4)
     - ``Settings.Secure.VOLUME_GROUP_STATE``
     - ``HIL_PowerCycleTest#testVolumePersistsAcrossSTR``
   * - **FR-05**
     - ``UC-05`` (Fault Diagnostics)
     - ``AudioControlWrapper``, ``DeathRecipient`` (Sec 4.4, 5.3)
     - ``IAudioControlCallback.onHalError()``
     - ``VtsHalAudioControlTargetTest#FaultInjection``
   * - **NFR-01**
     - ``UC-02``, ``UC-03`` (< 30ms Latency)
     - ``AudioFlinger FastMixer``, ``DSP_Engine`` (Sec 3.3)
     - Shared Memory Ring Buffer + TDM Bus
     - ``PerfettoLatencyBenchmark#testFocusSwitchUnder30ms``
   * - **NFR-02**
     - ``UC-01``..``UC-05`` (MTBF > 10k hrs)
     - ``CarAudioService``, ``AudioControlHAL`` (Sec 6.3)
     - AddressSanitizer (ASan) + Lock Hierarchy
     - ``StressTest24h#testZeroMemoryLeakAndNoANR``
   * - **NFR-03**
     - ``UC-02`` (ISO 26262 ASIL-B)
     - ``AudioFocusManager``, ``AudioControlHAL`` (Sec 3.2)
     - Direct Emergency Bus Bypass (``bus_adas_chime``)
     - ``HIL_SafetyTest#testAdasOverrideUnderCpuLoad``
   * - **NFR-04**
     - ``UC-04`` (Access Security)
     - ``CarAudioService``, SELinux Domain (Sec 3.4)
     - ``CAR_CONTROL_AUDIO_VOLUME`` + SELinux ``.te``
     - ``CtsCarSecurityTest#testUnauthorizedVolumeRejected``

Coverage & Audit Rules
~~~~~~~~~~~~~~~~~~~~~~

1. **Zero Orphan Requirements**: Every requirement (`FR-*`, `NFR-*`) must map to at least one concrete LLD class/interface and at least one automated verification test.
2. **Zero Gold-Plating**: Any architectural component or public AIDL method not linked to a valid requirement in this matrix is flagged during design review.
3. **CI Gate Verification**: Pull requests modifying `IAudioControl.aidl` or `car_audio_configuration.xml` must update the corresponding test cases referenced in the RTM.

