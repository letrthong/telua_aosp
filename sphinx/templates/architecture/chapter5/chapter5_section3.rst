5.3 Observability & Troubleshooting Runbook
------------------------------------------------------------------------------------------

This section provides observability instrumentation (**Observability**) and operational runbooks (**Troubleshooting Runbook**) to expedite diagnostic investigation and incident mitigation.

Diagnostic Tooling & Logging Instrumentation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Android Logcat Filtering**: Filter structured audio logs using standard subsystem tags:
  
  .. code-block:: bash

     adb logcat -s CarAudioService:V CarAudioZone:D AudioControlHAL:I

- **Dumpsys Car Audio Diagnostics**: Inspect live runtime configurations of all audio zones and volume groups:

  .. code-block:: bash

     adb shell dumpsys car_service --services CarAudioService

- **Perfetto Performance Tracing**: Measure end-to-end latency from audio focus invocation to speaker output:

  .. code-block:: bash

     perfetto --txt -c /data/misc/perfetto-configs/audio_trace.pbtx -o /data/misc/perfetto-traces/trace.perfetto-trace

Standard Troubleshooting Runbook
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **Diagnostic Runbook Matrix**
   :widths: 20 25 30 25
   :header-rows: 1

   * - Error Symptom
     - Potential Root Cause
     - Diagnostic Verification Command
     - Remediation Procedure
   * - **No sound from speakers**
     - Hardware bus muted or DSP power amplifier in sleep mode
     - ``adb shell dumpsys car_service --services CarAudioService | grep isMuted``
     - Restart vendor audio HAL: ``adb shell setprop ctl.restart vendor.audiocontrol-default``
   * - **Media does not duck upon navigation prompt**
     - ``can_duck`` attribute disabled or invalid context mapping ID
     - Inspect target ``/vendor/etc/car_audio_configuration.xml``
     - Resynchronize volume groups and verify audio context mappings in XML.
   * - **Security exception thrown**
     - Application lacks required system permissions
     - Review logcat: ``adb logcat | grep "requires CAR_CONTROL_AUDIO_VOLUME"``
     - Grant permission in application manifest or via ``adb shell pm grant``.
   * - **Car service crashes during boot**
     - Malformed XML configuration file on vendor partition
     - View boot crash dump: ``adb logcat -b crash``
     - Validate syntax using: ``xmllint --noout /vendor/etc/car_audio_configuration.xml``
