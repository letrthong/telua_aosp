Audio & Device Management Service
------------------------------------------------------------------------------------------

This section details the primary service methods for device configuration, audio stream routing, and volume management.

Method: requestAudioFocus
~~~~~~~~~~~~~~~~~~~~~~~~~

Requests audio focus for a specified usage type and audio zone.

**Parameters:**

.. list-table::
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - usage
     - int
     - Stream usage (e.g., USAGE_MEDIA = 1).
   * - zoneId
     - int
     - Target audio zone (0 for Primary Zone).
   * - flags
     - int
     - Focus request flags (e.g., AUDIOFOCUS_FLAG_DELAY)

**Return Values:**

- AUDIOFOCUS_REQUEST_GRANTED (1): Focus successfully acquired.
- AUDIOFOCUS_REQUEST_FAILED (0): Focus request denied.
- AUDIOFOCUS_REQUEST_DELAYED (2): Focus request queued for later grant.

**Client Code Examples:**
