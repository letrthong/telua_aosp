Status Codes & Error Definitions
--------------------------------

All API and IPC calls return standard status integers:

+-----------+----------------------+------------------------------------------------+
| Code      | Name                 | Description                                    |
+===========+======================+================================================+
| ``0``     | ``STATUS_OK``        | The operation completed successfully.          |
+-----------+----------------------+------------------------------------------------+
| ``-1``    | ``ERR_INVALID_PARAM``| One or more parameters were out of range.      |
+-----------+----------------------+------------------------------------------------+
| ``-2``    | ``ERR_DEVICE_BUSY``  | Hardware resource is locked by another process.|
+-----------+----------------------+------------------------------------------------+
| ``-3``    | ``ERR_PERMISSION``   | Caller lacks required SELinux permission.      |
+-----------+----------------------+------------------------------------------------+

.. tip::
   Always verify the return code before streaming data buffers to avoid kernel panics.
