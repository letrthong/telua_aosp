3.3 Communication Protocols & Data Flow
------------------------------------------------------------------------------------------

This section describes inter-process communication (IPC) protocols and audio data streaming models (**Audio Data Flow**) implemented across the subsystem.

Inter-Process Communication (IPC) Mechanisms
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The system leverages three standard IPC transport channels based on bandwidth and latency requirements:

1. **Android Binder IPC / Stable AIDL**:
   - Used for control commands, volume level adjustments, and asynchronous event callbacks between Applications and ``CarAudioService``.
   - Highly reliable, supports caller UID/PID verification, and provides `linkToDeath` notifications for crash recovery.
2. **Shared Memory / FastMixer Ring Buffer**:
   - Used for high-throughput, raw PCM audio buffer transfers from user space directly to Audio HAL.
   - Operates with zero-copy shared memory semantics, achieving sub-millisecond audio delivery.
3. **Hardware Bus (I2S, TDM, CAN-FD)**:
   - Synchronizes audio clocking and multi-channel audio data between the primary SoC and peripheral DSP processors.

Audio Data Flow Diagram
~~~~~~~~~~~~~~~~~~~~~~~

.. mermaid::

   graph LR
       subgraph Source_Layer ["Audio Sources"]
           PCM_App["App PCM Audio<br/>(48kHz / 16-bit / Stereo)"]
           Tone_Gen["Vehicle Chimes<br/>(Seatbelt, Turn Signal)"]
       end

       subgraph Mixer_Layer ["Mixing & Routing Layer"]
           FastMixer["AudioFlinger FastMixer<br/>(Ring Buffer)"]
           ZoneRouter["CarAudio Zone Router<br/>(Zone 0 / Zone 1)"]
       end

       subgraph HAL_DSP_Layer ["Hardware & DSP Layer"]
           HAL_Bus["Audio HAL Bus Devices<br/>(bus00_media, bus01_nav)"]
           DSP_Engine["DSP Mixer & Crossover<br/>(Equalizer / Reverb / Gain)"]
           DAC_Amp["DAC & Power Amplifier"]
       end

       PCM_App --> FastMixer
       Tone_Gen --> ZoneRouter
       FastMixer --> ZoneRouter
       ZoneRouter --> HAL_Bus
       HAL_Bus -->|TDM Stream| DSP_Engine
       DSP_Engine --> DAC_Amp
       DAC_Amp --> Speakers["Vehicle Speaker System"]

Core AIDL Interface Contract Specification
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The sample interface definition below illustrates the Stable AIDL contract binding CarAudioService to the vendor HAL:

.. code-block:: java

   package android.hardware.automotive.audiocontrol;

   @VintfStability
   interface IAudioControl {
       /**
        * Configures volume gain index for an individual volume group within an audio zone.
        */
       void setVolumeGroupGain(in int zoneId, in int groupId, in int gainIndex);

       /**
        * Sets mute state independently for an individual audio zone.
        */
       void setAudioZoneMuted(in int zoneId, in boolean muted);

       /**
        * Registers an asynchronous callback for DSP hardware error and state notifications.
        */
       void registerAudioControlCallback(in IAudioControlCallback callback);
   }

.. note::
   **Official Reference**: For the complete interface definition and HAL version history, see `Google AOSP: Audio Control HAL <https://source.android.com/docs/automotive/audio/audio-control-hal>`_.
