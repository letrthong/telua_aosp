1.3 Architecture Decision Records (ADR) & Glossary
------------------------------------------------------------------------------------------

This section documents the key **Architecture Decision Records (ADRs)** capturing architectural trade-offs and design rationale, followed by the standard **Domain Glossary & Acronyms**.

Architecture Decision Records (ADR) Matrix
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In accordance with **ISO/IEC/IEEE 42010**, significant architectural decisions, evaluated alternatives, and engineering trade-offs are recorded below:

.. list-table:: **Key Architecture Decision Records (ADRs)**
   :widths: 12 23 25 22 18
   :header-rows: 1

   * - ADR ID
     - Architectural Decision
     - Selected Solution
     - Rejected Alternatives
     - Rationale & Trade-Offs
   * - **ADR-01**
     - Framework-to-HAL IPC Contract
     - **Stable AIDL** (``@VintfStability``)
     - Legacy HIDL 2.0, Raw Unix Domain Sockets
     - Unifies framework and vendor IPC under a single IDL, enforces VINTF backwards compatibility, and eliminates HIDL thread-pool overhead.
   * - **ADR-02**
     - Audio Ducking Execution Tier
     - **Hardware DSP Gain Attenuation** via ``AudioControlHAL``
     - Software PCM sample scaling inside ``AudioFlinger``
     - Offloads floating-point attenuation to the dedicated DSP, preserving 24-bit dynamic range and keeping main CPU utilization < 1%.
   * - **ADR-03**
     - Multi-Zone Focus Arbitration Scope
     - **Per-Zone Independent Focus Stack**
     - Single global vehicle-wide focus lock
     - Allows rear-seat passengers to enjoy uninterrupted media on Zone 2 while the driver receives turn-by-turn navigation alerts in Zone 0.
   * - **ADR-04**
     - Concurrency & HAL Invocation Model
     - **Lock-Free Outbound IPC** with asynchronous callbacks
     - Holding ``synchronized(mLock)`` across synchronous HAL calls
     - Prevents ``system_server`` Watchdog ANR hangs if the vendor HAL process stalls or restarts during an I2C/SPI bus fault.

ADR Evaluation & Lifecycle Flow
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. mermaid::

   graph LR
       Problem["Architectural Driver<br/>(Latency / Safety / Treble)"] --> Options["Evaluate Alternatives<br/>(PoC & Benchmarks)"]
       Options --> Decision["Approve ADR<br/>(Architecture Board)"]
       Decision --> Enforce["Enforce via VTS & Lint<br/>(CI Quality Gates)"]

Domain Glossary & Acronyms
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Automotive & AOSP Architecture Glossary**
   :widths: 18 32 50
   :header-rows: 1

   * - Acronym / Term
     - Full Expansion
     - Engineering Definition in System Context
   * - **AAOS**
     - Android Automotive Operating System
     - Google's open-source infotainment operating system running natively on vehicle cockpit ECUs.
   * - **AIDL**
     - Android Interface Definition Language
     - Strongly-typed IPC contract language defining Binder interfaces between ``CarAudioService`` and vendor HALs.
   * - **ASIL-B**
     - Automotive Safety Integrity Level B
     - **ISO 26262** functional safety classification governing acoustic warning delivery pathways (ADAS chimes).
   * - **ASPICE**
     - Automotive SPICE (SWE.2 / SWE.3)
     - Process assessment model requiring bidirectional traceability between requirements, architecture, and tests.
   * - **DSP**
     - Digital Signal Processor
     - Dedicated co-processor executing real-time audio mixing, parametric equalization, crossover, and gain ducking.
   * - **HIL**
     - Hardware-In-the-Loop
     - Automated physical test bench integrating real ECU boards, DSP amplifiers, and acoustic measurement rigs.
   * - **STR**
     - Suspend-to-RAM (Deep Sleep)
     - Low-power vehicle state on Ignition Off that preserves DRAM state for sub-second cold wakeup.
   * - **TDM / I2S**
     - Time-Division Multiplexing / Inter-IC Sound
     - Synchronous serial hardware buses transporting multi-channel digital PCM audio from SoC to DSP.
   * - **VHAL**
     - Vehicle Hardware Abstraction Layer
     - Android HAL bridging CAN/LIN/Ethernet vehicle network properties (gear state, ignition, rotary knob) to CarService.
   * - **VTS**
     - Vendor Test Suite
     - Automated compliance test suite validating vendor HAL implementations against Stable AIDL contracts.

