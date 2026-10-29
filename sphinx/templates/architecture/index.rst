Software Architecture & System Design Document
===============================================

Welcome to the **Software Architecture & System Design Specification Document**.

This document is structured following international software architecture engineering methodologies (ISO/IEC/IEEE 42010), clearly partitioned from business context to low-level implementation details, operations, and quality engineering:

.. list-table:: **Software Architecture Framework**
   :widths: 18 37 45
   :header-rows: 1

   * - Part
     - Chapter Title
     - Scope & Engineering Focus
   * - **Chapter 1**
     - **System Overview**
     - Business context, problem statement, project scope (In-Scope / Out-of-Scope), and quality attributes (SLA/SLO).
   * - **Chapter 2**
     - **Requirements & Use Cases**
     - System actors, use case diagrams, functional requirements (FR matrix), and non-functional requirements (NFR matrix).
   * - **Chapter 3**
     - **High-Level Design (HLD)**
     - Layered C4 system architecture, inter-service interactions, IPC protocols, and audio data flow models.
   * - **Chapter 4**
     - **Low-Level Design (LLD)**
     - Object-oriented class modeling, finite state machines (FSM), data models, and XML/JSON configuration schemas.
   * - **Chapter 5**
     - **Build & Deployment**
     - Automated compilation, CI/CD pipeline workflows, deployment topology (Dev / Staging / Prod), and runbooks.
   * - **Chapter 6**
     - **Quality & Automated Testing**
     - Test pyramid model, unit testing & mocking (JUnit 5 / GTest), Android CTS/VTS, and quality gate metrics.

Interactive Features
--------------------
- **Rich Mermaid Diagrams**: Native support for Class Diagrams, Sequence Flows, State Machines, Flowcharts, and C4 Blocks.
- **Interactive Fullscreen Zoom**: Fullscreen lightbox viewer with free mouse-wheel scaling, drag-to-pan, and convenient controls.
- **Vector SVG Export**: Instant one-click vector `.svg` download for crystal-clear inclusion in presentations and reports.

References & Official Google AOSP Documentation
------------------------------------------------
This architecture specification is based on public open-source standards published by Google under the Apache 2.0 license:

- **AOSP Automotive Audio Overview**: `Google AOSP Automotive Audio <https://source.android.com/docs/automotive/audio>`_
- **AOSP AudioControl HAL AIDL Interface**: `AudioControl HAL Specification <https://source.android.com/docs/automotive/audio/audio-control-hal>`_
- **AOSP Multi-Zone Audio Routing & Volume Groups**: `Multi-Zone Audio Documentation <https://source.android.com/docs/automotive/audio/multi-zone-audio>`_
- **Android Developer Audio Focus Guidelines**: `Managing Audio Focus API <https://developer.android.com/guide/topics/media-apps/audio-focus>`_
- **AOSP Automotive Testing & Compliance**: `Audio Compliance & VTS <https://source.android.com/docs/automotive/audio/audio-compliance>`_
- **AOSP Build System & Environment Setup**: `Building Android AOSP <https://source.android.com/docs/setup/build/building>`_


.. toctree::
   :maxdepth: 2
   :caption: Architecture Table of Contents:
   :numbered:

   chapter1
   chapter2
   chapter3
   chapter4
   chapter5
   chapter6
