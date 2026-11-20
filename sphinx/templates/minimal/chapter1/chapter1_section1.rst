Overview & Quick Start
----------------------

Welcome to the project! This is a clean, minimal starter documentation template.

Features & Checklist
~~~~~~~~~~~~~~~~~~~~
- [x] Lightweight and easy to maintain.
- [x] Modular Doc-as-Code workflow with Sphinx.
- [x] Built-in search, dark mode, and mobile responsive design.

.. note::
   You can add more sections by updating ``metadata.json`` or running ``telua docs sync``.

.. mermaid::

   pie showData
       title Audio Usage by Context
       "media" : 12
       "navigation" : 8
       "call" : 5
       "tts" : 3
       "fm_tuner" : 7

.. mermaid::

   xychart-beta
       title "Media Volume Trend"
       x-axis ["08:00", "10:00", "12:00", "14:00", "16:00", "18:00"]
       y-axis "Value" 0 --> 15
       line [8, 12, 10, 14, 11, 15]

.. mermaid::

   xychart-beta
       title "Focus Enforcement Events / Week"
       x-axis ["mon", "tue", "wed", "thu", "fri"]
       y-axis "Value" 0 --> 31
       bar [12, 25, 8, 31, 19]