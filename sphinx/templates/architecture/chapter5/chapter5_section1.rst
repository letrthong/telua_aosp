5.1 Build System & CI/CD Pipeline
------------------------------------------------------------------------------------------

This section describes build system configurations (**Build System**), automated testing workflows, and continuous delivery pipelines (**CI/CD Pipeline**).

CI/CD Pipeline Workflow Diagram
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

All software commits and architecture documentation are built automatically via the continuous integration pipeline:

.. mermaid::

   graph LR
       Commit["Git Commit & Push"] --> Lint["1. Lint & Format Check"]
       Lint --> Test["2. Unit & Mock Tests"]
       Test --> Build["3. AOSP Soong & C++ Build"]
       Build --> DocBuild["4. Sphinx Docs-as-Code Build"]
       DocBuild --> Artifact["5. Generate OTA Payload & HTML Docs"]
       Artifact --> Deploy["Deploy to Staging / HIL Test Rig"]

       classDef success fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
       class Commit,Deploy success;

Standard Build Commands
~~~~~~~~~~~~~~~~~~~~~~~

1. **Building Sphinx Documentation (Telua Docs Pipeline)**:

   .. code-block:: bash

      # Initialize documentation project using standard architecture template
      telua docs init -t architecture

      # Compile HTML documentation through safe isolated staging (clean git status)
      telua docs build

      # Launch local preview server at http://localhost:8080
      telua docs start 8080

2. **Compiling Android AOSP & Native HAL Services**:

   .. code-block:: bash

      # Initialize Android build environment
      source build/envsetup.sh
      lunch aosp_car_x86_64-userdebug

      # Build CarAudioService and AudioControl AIDL HAL module
      m android.hardware.automotive.audiocontrol-service
      m CarAudioService

3. **Running Automated Test Suites**:

   .. code-block:: bash

      # Execute automated unit test suites with atest
      atest CarAudioServiceUnitTest
      atest VtsHalAudioControlTargetTest
