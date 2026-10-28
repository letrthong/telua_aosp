build_apk.sh — AOSP System APK Build & Deployment Toolkit
==========================================================

An automated developer workflow script for building and deploying privileged system
applications (``priv-app``) in **AOSP / Android Automotive** environments
(Qualcomm QSSI architecture):

**lunch → build module → root & remount → push APK → reboot / fast restart → capture logcat**

Contents
--------

.. toctree::
   :maxdepth: 2
   :caption: Documentation

Quick Start
-----------

.. code-block:: bash

   # 1. Grant execution permissions
   chmod +x build_apk.sh config_crypto.py config_overlay.py

   # 2. Install 'telua' & 'tel' commands and Tab Auto-completion into ~/.bashrc
   ./build_apk.sh --install

   # 3. Reload shell
   source ~/.bashrc

CLI Overview
------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Command
     - Purpose
   * - ``telua build``
     - Build & deploy APK to AOSP target
   * - ``telua car <action>``
     - AAOS control via ADB (volume, keys, status)
   * - ``telua dump <target>``
     - Dumpsys diagnostics
   * - ``telua sec <action>``
     - Security & SELinux diagnostics
   * - ``telua git`` / ``telua docker`` / ``telua network``
     - Cheatsheets
   * - ``telua my <action>``
     - Personal pipelines
   * - ``telua run <group>``
     - Multi-command pipelines
   * - ``telua clean-java``
     - Java source hygiene
