2.2 Functional & Non-Functional Requirements
------------------------------------------------------------------------------------------

This section provides a rigorous matrix of functional requirements (FR) and non-functional requirements (NFR) serving as the baseline for system verification.

Functional Requirements Matrix
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Functional Requirements Matrix (FR)**
   :widths: 15 25 45 15
   :header-rows: 1

   * - Requirement ID
     - Capability Domain
     - Technical Requirement Specification
     - Priority Level
   * - **FR-01**
     - Multi-Zone Audio Routing
     - The system must support at least 3 isolated acoustic zones (Zone 0: Primary Driver, Zone 1: Passenger, Zone 2: Rear Seats).
     - **P0 (Mandatory)**
   * - **FR-02**
     - Volume Group Management
     - Related audio usages (Media, Navigation, Phone, Notifications) must be bundled into independently adjustable Volume Groups.
     - **P0 (Mandatory)**
   * - **FR-03**
     - Dynamic Audio Ducking
     - The system must automatically duck background media streams (minimum -12dB reduction) upon incoming navigation guidance or collision warnings.
     - **P1 (High)**
   * - **FR-04**
     - Persistent Power State
     - Upon vehicle ignition cut-off (IGNITION OFF), volume settings and zone states must be serialized to non-volatile flash storage.
     - **P1 (High)**
   * - **FR-05**
     - Hardware Fault Diagnostics
     - The subsystem must detect and report missing DAC amplifier nodes across I2C/SPI buses to system error logs within 100ms.
     - **P2 (Medium)**

Non-Functional Requirements Matrix
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Non-Functional Requirements Matrix (NFR)**
   :widths: 20 30 50
   :header-rows: 1

   * - NFR Dimension
     - Measurement Criteria
     - Target Constraint & Engineering Standard
   * - **Response Latency**
     - Stream routing & focus handover
     - Audio routing transition latency must be **< 30ms**.
   * - **System Reliability**
     - Mean Time Between Failures (MTBF)
     - **> 10,000 hours** of continuous execution without memory leaks or Application Not Responding (ANR) hangs.
   * - **Automotive Safety**
     - Functional Safety Classification
     - Must comply with **ISO 26262 ASIL-B** requirements for emergency sound alert delivery pathways.
   * - **Access Security**
     - Privilege Isolation & Sandboxing
     - Only system-privileged applications signed with OEM platform keys may modify core audio zone routing configurations.
