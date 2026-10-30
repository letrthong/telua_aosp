3.4 Security Architecture, SELinux & Threat Model
------------------------------------------------------------------------------------------

This section specifies the defense-in-depth security architecture (**Security Architecture**), Mandatory Access Control (**SELinux Policies**), privileged permission whitelisting, and cybersecurity threat modeling (**ISO/SAE 21434 STRIDE**).

Defense-in-Depth Security Boundary Diagram
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In Android Automotive OS, untrusted third-party media apps are strictly isolated from privileged system services and vendor HAL domains through multi-stage enforcement gates:

.. mermaid::

   graph LR
       subgraph Untrusted_Zone ["Untrusted App Sandbox (u:r:untrusted_app:s0)"]
           ThirdPartyApp["3rd-Party Media App<br/>(UID >= 10000)"]
       end

       subgraph Priv_Zone ["Privileged System Sandbox (u:r:system_server:s0)"]
           PermCheck["Binder Permission Gate<br/>(checkCallingOrSelfPermission)"]
           CarAudioSvc["CarAudioService<br/>(Audio Policy Engine)"]
       end

       subgraph Vendor_Zone ["Vendor HAL Sandbox (u:r:hal_audiocontrol_default:s0)"]
           SELinuxGate["SELinux Binder Call Gate<br/>(binder_call macro)"]
           AudioHAL["AudioControl AIDL HAL<br/>(UID: audioserver / vendor)"]
       end

       subgraph Kernel_Zone ["Linux Kernel & Hardware Drivers"]
           AlsaDev["ALSA / DSP Device Nodes<br/>(/dev/snd/*, /dev/i2c-*)"]
       end

       ThirdPartyApp -->|1. Public SDK IPC| PermCheck
       PermCheck -->|2. Verified Caller UID| CarAudioSvc
       CarAudioSvc -->|3. VINTF Binder IPC| SELinuxGate
       SELinuxGate -->|4. Authorized Domain| AudioHAL
       AudioHAL -->|5. ioctl() / TDM| AlsaDev

SELinux Policy & Privileged Permission Enforcement
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **SELinux Type Enforcement Rules (``hal_audiocontrol.te``)**:
   Only ``car_service`` (running inside ``system_server``) and ``audioserver`` are permitted to invoke Binder transactions against ``hal_audiocontrol_hwservice`` / AIDL service:

   .. code-block:: text

      # Allow system_server (CarAudioService) to communicate with AudioControl HAL over Binder
      binder_call(system_server, hal_audiocontrol_server)
      binder_call(hal_audiocontrol_server, system_server)

      # Grant AudioControl HAL exclusive access to hardware DSP I2C/SPI control nodes
      allow hal_audiocontrol_default audio_device:chr_file rw_file_perms;

      # Neverallow rule: strictly forbid untrusted apps from directly accessing AudioControl HAL
      neverallow { appdomain -system_server } hal_audiocontrol_service:service_manager find;

2. **Privileged App Whitelisting (``/system/etc/permissions/privapp-permissions-car.xml``)**:
   System applications deployed to ``/system/priv-app/`` must explicitly declare signature-level permissions in the whitelist, otherwise the system refuses to boot (`ro.control_privapp_permissions=enforce`):

   .. code-block:: xml

      <permissions>
          <privapp-permissions package="com.android.car.oemservice">
              <permission name="android.car.permission.CAR_CONTROL_AUDIO_VOLUME"/>
              <permission name="android.car.permission.CAR_CONTROL_AUDIO_SETTINGS"/>
          </privapp-permissions>
      </permissions>

Cybersecurity Threat Model (ISO/SAE 21434 — STRIDE Matrix)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **STRIDE Threat Analysis & Architectural Mitigations**
   :widths: 16 24 30 30
   :header-rows: 1

   * - STRIDE Category
     - Threat Scenario
     - Impact / ASIL Risk
     - Architectural Mitigation Control
   * - **Spoofing**
     - Malicious media app spoofs ADAS navigation usage to mute other streams.
     - High (Driver distraction / blocked audio)
     - Enforce ``MODIFY_AUDIO_ROUTING`` signature permission for safety usages (``USAGE_EMERGENCY``).
   * - **Tampering**
     - Unauthorized modification of ``car_audio_configuration.xml`` on `/vendor`.
     - Critical (Broken routing of safety chimes)
     - Enforce **dm-verity** Verified Boot on `/system` and `/vendor` partitions (`ro.boot.verifiedbootstate=green`).
   * - **Repudiation**
     - Volume or mute state altered unexpectedly without audit trail.
     - Medium (Undiagnosable field incidents)
     - Log caller ``Binder.getCallingUid()`` and ``getCallingPid()`` in ``CarAudioService`` ring buffer for dumpsys audit.
   * - **Information Disclosure**
     - Background app eavesdrops on cabin microphone or active phone call PCM buffers.
     - High (Privacy violation)
     - Isolate microphone capture via Android ``AppOpsManager`` indicators and separate HAL input buses.
   * - **Denial of Service**
     - Rogue app floods ``requestAudioFocus()`` with 10,000 requests/sec.
     - High (Watchdog ANR in ``system_server``)
     - Enforce per-UID rate limiting and bounded focus stack depth inside ``AudioFocusManager``.
   * - **Elevation of Privilege**
     - Compromised app attempts direct ``ioctl()`` on ``/dev/snd/pcmC0D0p``.
     - Critical (Arbitrary speaker output)
     - SELinux ``neverallow`` blocks direct device node access; DAC permissions restricted to `audio` group (`0660`).

Security Verification Commands (``telua sec``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Engineers can audit live SELinux policies, AVC denials, and privileged permission whitelisting directly using the ``telua`` toolkit:

.. code-block:: bash

   # Inspect SELinux enforcement mode, dm-verity, and ro.debuggable / ro.secure state
   telua sec status

   # Scan logcat and kernel dmesg for SELinux AVC audit denials
   telua sec avc

   # Verify privileged app permission grants and detect missing whitelist entries
   telua sec privapp
