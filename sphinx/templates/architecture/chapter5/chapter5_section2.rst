5.2 Deployment Topology & Environments
------------------------------------------------------------------------------------------

This section outlines system deployment topology (**Deployment Topology**), environment tier distinctions (Dev, Staging, Production), and the Over-The-Air (**OTA**) update mechanism.

Deployment Topology Diagram
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. mermaid::

   graph TB
       subgraph Cloud_Infra ["Cloud Infrastructure & Management Services"]
           OTA_Server["OTA Release Server<br/>(Signed Image Payloads)"]
           Telemetry_Collector["Logging & Telemetry Server<br/>(Elastic / Grafana)"]
       end

       subgraph Target_Environments ["Target Execution Environments"]
           subgraph Env_Dev ["Development Environment (Dev)"]
               AVD_Emulator["Android Virtual Device (AVD)<br/>(Cuttlefish / QEMU x86_64)"]
           end

           subgraph Env_Staging ["Staging & Verification Environment"]
               HIL_Rig["Hardware-In-the-Loop (HIL) Rig<br/>(Physical Test Benches & Real DSP)"]
           end

           subgraph Env_Prod ["Production Vehicle Environment"]
               IVI_ECU["In-Vehicle Infotainment ECU<br/>(Qualcomm / NXP SoC)"]
               Audio_DSP["Dedicated Audio DSP"]
               IVI_ECU -->|TDM / I2S Bus| Audio_DSP
           end
       end

       OTA_Server -->|Deploy Nightly Builds| HIL_Rig
       OTA_Server -->|Seamless A/B OTA Updates| IVI_ECU
       IVI_ECU -->|Transmit Fleet Telemetry| Telemetry_Collector

Environment Comparison Matrix
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Environment Characteristic Comparison**
   :widths: 20 25 30 25
   :header-rows: 1

   * - Environment Tier
     - Primary Purpose
     - Hardware Configuration
     - Deployment Frequency
   * - **Dev (Development)**
     - Fast feature validation and debugging
     - Workstation QEMU / Cuttlefish emulator
     - Per commit / pull request
   * - **Staging (HIL Bench)**
     - Acoustic tuning, latency measurements, and DSP tests
     - Automated test rigs with microphones and load boxes
     - Nightly release builds
   * - **Production (Vehicle)**
     - In-vehicle customer operation
     - Automotive-grade Cockpit ECU (High Reliability)
     - Scheduled OTA releases (every 1-3 months)

A/B Seamless Partition Update Strategy
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To prevent bricking vehicle hardware during unexpected power losses while upgrading firmware, the architecture enforces **A/B Seamless Partition Updates**:

1. **Active Partition (Slot A)**: Executes live operating system tasks, maintaining uninterrupted audio and navigation for passengers.
2. **Background Download (Slot B)**: The update payload downloads silently in the background and writes sequentially to Slot B.
3. **Payload Verification**: Computes SHA-256 checksums and decrypts firmware using the Hardware Security Module (HSM).
4. **Slot Swap & Rollback**: Upon next engine reboot, the bootloader switches execution to Slot B. If boot fails within 15 seconds, the bootloader automatically rolls back to Slot A.
