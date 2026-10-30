2.4 Bidirectional Requirements Traceability Matrix (RTM)
------------------------------------------------------------------------------------------

This section establishes the **Bidirectional Requirements Traceability Matrix (RTM)** in compliance with **Automotive SPICE (ASPICE SWE.1 / SWE.2 / SWE.3)** and **ISO 26262**, ensuring every functional, non-functional, hardware, interface, and safety/security requirement maps forward to architectural components and verification tests, and backward to business use cases.

ASPICE End-to-End Traceability Model
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. mermaid::

   graph LR
       UC["System Use Cases<br/>(UC-01 .. UC-05)"] <-->|Derives| REQ["System Requirements<br/>(FR / NFR / HWR / IR / SAF / SEC)"]
       REQ <-->|Allocated to| ARCH["HLD / LLD Components<br/>(Chapter 3 & Chapter 4)"]
       ARCH <-->|Verified by| TEST["Automated Verification<br/>(Unit / VTS / CTS / HIL)"]

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
   * - **FR-06**
     - ``UC-02`` (Emergency Alert)
     - ``AudioFocusManager``, ``AudioControlHAL`` (Sec 3.2)
     - ``USAGE_EMERGENCY`` Priority Preemption
     - ``CarAudioFocusUnitTest#testEmergencyPreemptsMute``
   * - **FR-07**
     - ``UC-04`` (Rotary Control)
     - ``CarInputService``, ``CarAudioService`` (Sec 3.1)
     - VHAL ``HW_ROTARY_INPUT`` / ``inject-key``
     - ``CarAudioInputTest#testRotaryKnobAdjustsActiveGroup``
   * - **NFR-01**
     - ``UC-02``, ``UC-03`` (< 30ms Latency)
     - ``AudioFlinger FastMixer``, ``DSP_Engine`` (Sec 3.3)
     - Shared Memory Ring Buffer + TDM Bus
     - ``PerfettoLatencyBenchmark#testFocusSwitchUnder30ms``
   * - **NFR-02**
     - ``UC-01``..``UC-05`` (MTBF > 10k hrs)
     - ``CarAudioService``, ``AudioControlHAL`` (Sec 4.4, 6.3)
     - AddressSanitizer (ASan) + Lock Hierarchy
     - ``StressTest24h#testZeroMemoryLeakAndNoANR``
   * - **HWR-02**
     - ``UC-01``..``UC-03`` (Digital Audio)
     - ``AudioHAL``, ``DSP_Engine`` (Sec 3.1, 3.3)
     - TDM-16 / I2S 48kHz 24-bit Bus
     - ``HIL_AudioPrecisionTest#testTdmClockJitterAndTHD``
   * - **IR-02**
     - ``UC-03``, ``UC-04`` (HAL IPC)
     - ``CarAudioService``, ``IAudioControlHAL`` (Sec 3.3, 4.1)
     - ``@VintfStability IAudioControl.aidl``
     - ``VtsHalAudioControlTargetTest#AllInterfaceMethods``
   * - **SAF-01**
     - ``UC-02`` (ISO 26262 ASIL-B)
     - ``AudioFocusManager``, ``AudioControlHAL`` (Sec 3.2, 4.4)
     - Dedicated ``bus_adas_chime`` Hardware Pipe
     - ``HIL_SafetyTest#testAdasOverrideUnderCpuLoad``
   * - **SEC-01**
     - ``UC-04`` (ISO 21434 Security)
     - ``SELinuxGate``, ``hal_audiocontrol.te`` (Sec 3.4)
     - SELinux ``binder_call`` & ``neverallow``
     - ``CtsSecurityHostTestCases#testNeverallowRules``
   * - **SEC-02**
     - ``UC-04`` (Access Control)
     - ``CarAudioService`` Permission Gate (Sec 3.4)
     - ``CAR_CONTROL_AUDIO_VOLUME`` Whitelist
     - ``CtsCarSecurityTest#testUnauthorizedVolumeRejected``

Coverage & Audit Rules
~~~~~~~~~~~~~~~~~~~~~~

1. **Zero Orphan Requirements**: Every requirement (`FR-*`, `NFR-*`, `HWR-*`, `IR-*`, `SAF-*`, `SEC-*`) must map to at least one concrete LLD class/interface and at least one automated verification test.
2. **Zero Gold-Plating**: Any architectural component or public AIDL method not linked to a valid requirement in this matrix is flagged during design review.
3. **CI Gate Verification**: Pull requests modifying `IAudioControl.aidl` or `car_audio_configuration.xml` must update the corresponding test cases referenced in the RTM.

