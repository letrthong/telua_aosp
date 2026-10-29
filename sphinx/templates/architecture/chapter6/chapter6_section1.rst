6.1 Testing Strategy & Test Pyramid
------------------------------------------------------------------------------------------

This section defines the comprehensive software testing strategy (**Software Quality & Testing Strategy**) ensuring maximum reliability, functional safety, and high test velocity.

Testing Pyramid Model
~~~~~~~~~~~~~~~~~~~~~

The system adopts the industry-standard test pyramid model, prioritizing high-volume, fast, isolated unit tests at the base while tapering upward to full integration tests:

.. mermaid::

   graph TB
       Manual["4. Manual & Drive Testing (In-Vehicle)<br/>(Evaluate subjective acoustic perception and road noise)"]
       HIL["3. System & HIL Automated Testing (Hardware Benches)<br/>(Validate hardware amplifiers, DSP buses, CAN signals)"]
       Integration["2. Integration & Contract Testing<br/>(Validate Binder IPC AIDL, Robolectric, VTS/CTS Test Suites)"]
       Unit["1. Unit Testing & Mocking (Fast & Isolated)<br/>(JUnit 5, Mockito, Google Test - 70% of total test suites)"]

       Manual --- HIL
       HIL --- Integration
       Integration --- Unit

       classDef pyramid fill:#e0f2fe,stroke:#0284c7,stroke-width:2px;
       class Manual,HIL,Integration,Unit pyramid;

Test Levels & Objectives Matrix
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Testing Levels Breakdown**
   :widths: 20 25 35 20
   :header-rows: 1

   * - Testing Tier
     - Primary Target Scope
     - Tooling & Framework
     - Execution Target
   * - **Unit Testing**
     - Isolated business logic (Audio focus rules, gain conversions)
     - JUnit 5, Mockito, Google Test (GTest)
     - Developer Workstation / Fast CI
   * - **Integration Testing**
     - Cross-process Binder IPC communication between Service and HAL
     - Android Test Framework, VTS, AIDL Stubs
     - Android Virtual Device (AVD / Cuttlefish)
   * - **System & HIL Testing**
     - Full audio signal path from microphone/touchscreen to DSP and speakers
     - Python Test Automation, Audio Precision, CANoe
     - Hardware-In-the-Loop (HIL) Test Rig
   * - **Static Analysis & Security**
     - Syntax rules, memory safety, code smell detection
     - SonarQube, Clang-Tidy, AddressSanitizer (ASan)
     - Pre-commit Hooks & CI Pull Requests

Test Isolation Principles
~~~~~~~~~~~~~~~~~~~~~~~~~

1. **Hardware Independence**: 100% of Framework unit tests must execute in standard CI/CD virtualized runners without requiring physical vehicle ECUs.
2. **Deterministic & Fast Execution**: Individual unit test cases must finish in < 10ms. Usage of `Thread.sleep()` is prohibited; engineers must use `TestLooper` or virtual clock abstractions.
3. **Given-When-Then BDD Structure**: Test methods must follow the 3-phase Given-When-Then design pattern: establish preconditions (Given), execute target method (When), verify state transitions (Then/Assert).
