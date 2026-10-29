4.2 State Machine & Lifecycle Transitions
------------------------------------------------------------------------------------------

This section specifies the finite state machine (**Finite State Machine - FSM**) governing the operational lifecycle of audio focus arbitration (**Audio Focus Lifecycle**).

Audio Focus State Machine Diagram
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The lifecycle of an active audio focus request transitions through well-defined deterministic states:

.. mermaid::

   stateDiagram-v2
       [*] --> IDLE : Initialize AudioFocusRequest

       IDLE --> REQUESTING : Invoke requestAudioFocus()
       REQUESTING --> ACTIVE_FOCUS : Focus Granted (GAIN)
       REQUESTING --> FAILED_REJECTED : Focus Denied (REJECTED)

       ACTIVE_FOCUS --> DUCKED : Higher priority alert begins (LOSS_TRANSIENT_CAN_DUCK)
       DUCKED --> ACTIVE_FOCUS : High priority alert ends (GAIN)

       ACTIVE_FOCUS --> PAUSED_TRANSIENT : Voice call received (LOSS_TRANSIENT)
       PAUSED_TRANSIENT --> ACTIVE_FOCUS : Voice call ends (GAIN)

       ACTIVE_FOCUS --> PERMANENT_LOSS : Replaced by competing primary stream (LOSS)
       PERMANENT_LOSS --> RELEASED : Tear down resources
       
       ACTIVE_FOCUS --> RELEASED : Application invokes abandonAudioFocus()
       FAILED_REJECTED --> IDLE : Reset state
       RELEASED --> [*]

State Transition Matrix
~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: **State Transition Rules & Guard Conditions**
   :widths: 20 25 30 25
   :header-rows: 1

   * - Current State
     - Triggering Event
     - Guard Condition
     - Target State
   * - **IDLE**
     - ``requestAudioFocus()``
     - Valid request bundle
     - **REQUESTING**
   * - **REQUESTING**
     - Focus policy evaluation
     - Request Priority >= Current Owner
     - **ACTIVE_FOCUS**
   * - **ACTIVE_FOCUS**
     - Navigation prompt begins
     - ``can_duck == true``
     - **DUCKED**
   * - **ACTIVE_FOCUS**
     - Incoming phone call begins
     - ``can_duck == false``
     - **PAUSED_TRANSIENT**
   * - **DUCKED / PAUSED**
     - Higher priority stream ends
     - No remaining higher priority owners
     - **ACTIVE_FOCUS**
   * - **Any State**
     - ``abandonAudioFocus()``
     - Valid caller PID
     - **RELEASED**
