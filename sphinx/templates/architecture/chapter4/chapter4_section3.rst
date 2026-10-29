4.3 Data Models & Configuration Schemas
------------------------------------------------------------------------------------------

This section describes the configuration data schema (**Car Audio Configuration Schema**) used to initialize physical buses and initialize zone routing upon system startup.

Entity-Relationship Diagram (ERD)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. mermaid::

   erDiagram
       AUDIO_ZONE ||--o{ VOLUME_GROUP : contains
       VOLUME_GROUP ||--o{ AUDIO_CONTEXT : maps
       AUDIO_CONTEXT ||--|| BUS_DEVICE : routes_to

       AUDIO_ZONE {
           int zone_id PK
           string zone_name
           boolean is_primary
       }
       VOLUME_GROUP {
           int group_id PK
           int zone_id FK
           int default_gain
           int min_gain
           int max_gain
           int step_size
       }
       AUDIO_CONTEXT {
           int context_id PK
           string context_name
           int priority_level
       }
       BUS_DEVICE {
           string bus_address PK
           string hal_device_port
           int sample_rate
       }

Sample Configuration Schema (car_audio_configuration.xml)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: xml

   <?xml version="1.0" encoding="utf-8"?>
   <carAudioConfiguration version="2.0">
       <zones>
           <!-- Primary Audio Zone for Driver -->
           <zone name="Primary Zone" isPrimary="true" id="0">
               <volumeGroups>
                   <!-- Volume Group 0: Media & Radio -->
                   <group id="0">
                       <context context="music"/>
                       <context context="radio"/>
                       <device address="bus00_media_out"/>
                   </group>
                   <!-- Volume Group 1: Navigation Guidance & Warnings -->
                   <group id="1">
                       <context context="navigation"/>
                       <context context="voice_command"/>
                       <device address="bus01_nav_out"/>
                   </group>
                   <!-- Volume Group 2: Telephony & Cellular Calls -->
                   <group id="2">
                       <context context="call"/>
                       <context context="call_ring"/>
                       <device address="bus02_call_out"/>
                   </group>
               </volumeGroups>
           </zone>
       </zones>
   </carAudioConfiguration>

Data Dictionary
~~~~~~~~~~~~~~~

.. list-table:: **Core Data Attribute Definitions**
   :widths: 20 20 60
   :header-rows: 1

   * - Field Name
     - Data Type
     - Detailed Engineering Definition
   * - ``zone_id``
     - Integer (0..3)
     - Unique hardware index representing an acoustic zone in the vehicle (0: Primary Driver, 1: Passenger, 2: Rear Left, 3: Rear Right).
   * - ``group_id``
     - Integer (0..7)
     - Identifier of a unified volume group controlling related audio usages (Media, Nav, Phone, Notification).
   * - ``bus_address``
     - String
     - Address identifier corresponding to ALSA hardware ports registered in vendor HAL configurations (e.g., ``bus00_media_out``).
   * - ``default_gain``
     - Integer (dB)
     - Default gain level index applied upon factory reset or initial system installation.
