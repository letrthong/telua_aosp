3.2 Component Interactions & Sequence Flows
------------------------------------------------------------------------------------------

This section details the real-time execution sequences (**Sequence Flows**) between applications, framework services, and hardware layers during audio playback and focus arbitration.

Sequence Diagram: Audio Focus Request Flow
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When a navigation app issues turn-by-turn guidance while media is currently playing, the system coordinates audio ducking through the sequence below:

.. mermaid::

   sequenceDiagram
       autonumber
       actor Driver as Vehicle Driver
       participant NavApp as Navigation App
       participant MediaApp as Media Player App
       participant CarAudio as CarAudioService
       participant FocusMgr as AudioFocusManager
       participant AudioHAL as Audio Control HAL (DSP)

       Note over Driver, MediaApp: Initial State: MediaApp is playing music in Zone 0 (Primary)
       Driver->>NavApp: Enter destination & start navigation
       activate NavApp
       
       NavApp->>CarAudio: requestAudioFocus(USAGE_ASSISTANCE_NAVIGATION_GUIDANCE)
       activate CarAudio

       CarAudio->>FocusMgr: evaluateFocusChange(USAGE_MEDIA vs USAGE_NAV)
       activate FocusMgr
       FocusMgr-->>CarAudio: DUCK_LOWER_PRIORITY (Attenuate media volume)
       deactivate FocusMgr

       CarAudio->>AudioHAL: setVolumeGroupGain(GROUP_MEDIA, -15dB)
       activate AudioHAL
       AudioHAL-->>CarAudio: OK (Gain Applied)
       deactivate AudioHAL

       CarAudio-->>MediaApp: onAudioFocusChange(AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK)
       CarAudio-->>NavApp: AUDIOFOCUS_REQUEST_GRANTED
       deactivate CarAudio

       NavApp->>AudioHAL: streamAudio("Turn right in 100 meters")
       AudioHAL-->>Driver: Broadcast crisp voice guidance, media volume ducked

       Note over NavApp, AudioHAL: Once navigation prompt finishes
       NavApp->>CarAudio: abandonAudioFocus()
       activate CarAudio
       deactivate NavApp

       CarAudio->>AudioHAL: setVolumeGroupGain(GROUP_MEDIA, 0dB)
       CarAudio-->>MediaApp: onAudioFocusChange(AUDIOFOCUS_GAIN)
       deactivate CarAudio
       Note over MediaApp, Driver: Media volume restores smoothly to original gain
