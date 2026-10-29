2.1 Actors & Use Case Modeling
------------------------------------------------------------------------------------------

This section analyzes the primary actors interacting with the system and illustrates the core use case interaction models.

System Actors
~~~~~~~~~~~~~

.. list-table:: **Actor Identification Matrix**
   :widths: 22 25 53
   :header-rows: 1

   * - Actor Name
     - Actor Classification
     - Primary Responsibilities & Interaction Behaviors
   * - **Driver / Passenger**
     - Human Actor
     - Interacts via infotainment touchscreens, steering wheel buttons, or voice assistants to play media, adjust volume, and make calls.
   * - **Navigation / ADAS App**
     - Software Actor
     - Generates safety-critical alerts (Lane Departure, Speed Warnings, Turn-by-Turn guidance) with highest routing priority.
   * - **Vehicle Audio HAL**
     - Hardware/System Actor
     - Consumes audio stream controls from the framework, manipulates physical DAC mixers, and directs outputs to vehicle speakers.
   * - **Telematics Service**
     - System Actor
     - Collects operational telemetry and transmits diagnostic crash reports to cloud infrastructure.

General Use Case Diagram
~~~~~~~~~~~~~~~~~~~~~~~~

The diagram below illustrates use case interactions between external actors and the core Audio Management System:

.. mermaid::

   graph TD
       User["Driver / Passenger"]
       ADAS["ADAS Safety System"]
       HAL["Audio Control HAL"]
       Cloud["Telematics Cloud"]

       subgraph Audio_Management_System ["Central Audio Management System"]
           UC1(["Media & Radio Playback"])
           UC2(["Arbitrate Audio Focus"])
           UC3(["Dynamic Audio Ducking"])
           UC4(["Manage Volume Groups"])
           UC5(["Collect Diagnostic Metrics"])
       end

       User --> UC1
       User --> UC4
       ADAS --> UC2
       UC1 -.->|include| UC2
       UC2 -.->|Trigger upon ADAS alert| UC3
       UC4 --> HAL
       UC3 --> HAL
       UC5 --> Cloud

Core Use Case Specification
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Use Case: UC-02 - Audio Focus Arbitration**

1. **Preconditions**: The audio subsystem is initialized, and all physical audio zones (Primary, Rear) are registered.
2. **Trigger**: An active media or navigation application invokes ``requestAudioFocus()``.
3. **Main Event Flow**:

   - The framework evaluates the incoming request priority against current focus owners in the target audio zone.
   - If the requesting stream possesses higher operational priority (e.g. Navigation Alert > Background Music):

     * The framework instructs the background media player to attenuate output volume (Ducking) or pause playback.
     * The framework issues an ``AUDIOFOCUS_REQUEST_GRANTED`` notification callback to the Navigation application.
     * The framework updates mixer gain matrices across the hardware DSP via Audio HAL.

4. **Postconditions**: The higher-priority alert is broadcast clearly to driver speakers, and background media volume seamlessly restores upon alert completion.

.. note::
   **Official Reference**: For official Android Audio Focus API guidelines and interaction contracts, refer to `Android Developers: Managing Audio Focus <https://developer.android.com/guide/topics/media-apps/audio-focus>`_.
