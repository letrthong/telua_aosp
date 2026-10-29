1.2 Scope & Architectural Quality Attributes
------------------------------------------------------------------------------------------

This section clearly defines the operational boundaries of the system (In-Scope vs. Out-of-Scope) and establishes the core architectural principles governing design decisions.

System Boundary & Scope Matrix
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Project Scope Matrix**
   :widths: 22 39 39
   :header-rows: 1

   * - Domain
     - In-Scope Capabilities
     - Out-of-Scope Responsibilities
   * - **Audio Management**
     - Multi-zone routing, Audio Focus arbitration engine, volume group policies, dynamic ducking.
     - Proprietary third-party audio codec DSP algorithms (delegated to DSP firmware).
   * - **IPC Communication**
     - AIDL interface definitions, parcel serialization, thread pool management, death recipient handlers.
     - Physical transceivers and electrical routing of CAN/Ethernet automotive bus networks.
   * - **Security & Access Control**
     - SELinux policy enforcement, Android permissions (``android.car.permission.CAR_CONTROL_AUDIO_VOLUME``).
     - System-wide hardware root of trust (HSM / Hardware Security Module key generation).

Core Architectural Principles
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Core Architectural Design Principles**
   :widths: 25 75
   :header-rows: 1

   * - Principle
     - Architectural Guidance & Implementation Rules
   * - **Loose Coupling**
     - Subsystems interact strictly through explicit contracts (Stable AIDL / Interfaces). Direct memory access or global variables between services are prohibited.
   * - **Single Responsibility**
     - Distinct separation of concerns: ``CarAudioService`` is dedicated purely to policy management, whereas ``AudioControlHAL`` is solely responsible for hardware registers.
   * - **Fail-Safe & Graceful Degradation**
     - Should an auxiliary service crash, the system automatically falls back to safe default presets rather than causing an operating system kernel panic.
   * - **Observability by Design**
     - Structured logging, Perfetto instrumentation markers, and dumpsys diagnostics are embedded from the initial prototype.

Non-Functional Quality Attributes & SLAs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Performance**: Background daemon CPU consumption must remain < 3% of total core utilization under standard operational loads.
- **Memory Footprint**: Static resident memory consumption is strictly capped at < 40MB heap footprint.
- **Security**: 100% of incoming IPC requests must validate caller UID/PID identity and verify granted Android platform permissions.
