6.3 Automated Test Pipeline & Quality Gates
------------------------------------------------------------------------------------------

This section describes automated CI/CD testing workflows (**Automated Test Pipeline**) and software release criteria (**Quality Gates**).

Continuous Integration (CI) Automated Testing Flow
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Every incoming Pull Request (PR) triggers automated quality pipelines before merge authorization:

.. mermaid::

   graph LR
       PR["New Pull Request"] --> Static["1. Static Analysis<br/>(Clang-Tidy / SonarQube)"]
       Static --> Unit["2. Run Unit Tests<br/>(atest / GTest)"]
       Unit --> Coverage["3. Coverage Check<br/>(JaCoCo / LCOV)"]
       Coverage --> VTS["4. Automated VTS / CTS<br/>(Android Cuttlefish AVD)"]
       VTS --> Gate{"Quality Gate Passed?"}
       Gate -- Yes --> Approve["Approve & Merge"]
       Gate -- No --> Reject["Block PR & Report Failure"]

       classDef success fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
       classDef fail fill:#ffebee,stroke:#c62828,stroke-width:2px;
       class Approve success;
       class Reject fail;

Android AOSP Automated Test Tooling
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **Automated Unit Testing with `atest`**:
   
   .. code-block:: bash

      # Execute automated unit test suite for CarAudioService
      atest CarAudioServiceUnitTest

      # Run unit tests and compute line-by-line code coverage
      atest CarAudioServiceUnitTest --collect-tests-only --coverage

2. **Vendor Interface Compliance Testing (VTS - Vendor Test Suite)**:
   
   .. code-block:: bash

      # Verify HAL interface contract conformance
      atest VtsHalAudioControlTargetTest

3. **Memory Safety Validation with AddressSanitizer (ASan)**:
   
   .. code-block:: bash

      # Compile Native C++ services with memory sanitizer enabled
      SANITIZE_TARGET=address m android.hardware.automotive.audiocontrol-service

Quality Gates & Release Metrics Matrix
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To achieve release readiness, code changes must satisfy the strict thresholds defined in the quality gate matrix:

.. list-table:: **Quality Gate Acceptance Criteria**
   :widths: 25 35 40
   :header-rows: 1

   * - Quality KPI
     - Acceptance Threshold
     - Action Upon Threshold Violation
   * - **Code Line Coverage**
     - Minimum **>= 80%** module-wide; **>= 95%** for core focus arbitration logic
     - Automatically block Pull Request merge in CI runner.
   * - **Security Vulnerabilities**
     - **0** Critical or High severity issues (SonarQube)
     - Engineer must patch vulnerability before requesting re-review.
   * - **Memory Leaks**
     - **0 bytes** leaked after a continuous 24-hour stress test
     - Analyze heap allocation dump via Android Studio Profiler.
   * - **Routing Latency**
     - 100% of audio focus transitions complete in **< 30ms**
     - Flag as performance regression and reject commit.

.. note::
   **Official Reference**: For official Android Automotive audio compliance suites, VTS targets, and CTS verification rules, see `Google AOSP Automotive Audio <https://source.android.com/docs/automotive/audio>`_ and `Google AOSP Vendor Test Suite (VTS) <https://source.android.com/docs/compatibility/vts>`_.
