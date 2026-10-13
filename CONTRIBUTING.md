# Contributing to telua (AOSP & Automotive Toolkit)

Thank you for your interest in contributing to **telua**! 🎉

This project is an open, modular developer automation toolkit designed to solve common pain points in **AOSP & Android Automotive (AAOS)** development: streamlining compilation, partition remounts, APK deployment, diagnostic dumps, and developer cheatsheets into a single, cohesive CLI.

Whether you are fixing a bug, adding a new Automotive command, expanding a cheatsheet, or improving documentation, your contributions are warmly welcomed!

---

## 1. Code of Conduct & Core Philosophy

When contributing to this toolkit, please keep our core design principles in mind:

1. **Zero Cognitive Load:** "Make it simple to use, even if the underlying task is complex." Users should not need to memorize lengthy shell parameters—typing the root command (`telua`, `telua run`, `telua audio`, `telua dump`) should always display an interactive, self-explanatory cheatsheet.
2. **Defensive & Enterprise-Safe:** This tool is used in corporate and shared server environments. Never introduce automated destructive actions (such as git resets or container prunings) without an explicit, interactive confirmation prompt (`[y/N]`) and an optional `-y` bypass flag.
3. **Modular Separation of Concerns:**
   - Script orchestration logic belongs in `build_apk.sh`.
   - Domain-specific actions belong in their respective `const_*.config` files.
   - Project-specific parameters belong in `apk.config`.
4. **Clean Code & Universal English:** All code comments, CLI descriptions, and documentation must be written in clear, professional technical English.

---

## 2. Ways to Contribute

There are many ways you can help improve `telua`:

### A. Add New Automotive Commands (`const_audio.config` / `const_dumpsys.config`)
If you work with Android Automotive OS (AAOS) and have useful ADB shell shortcuts:
- Add volume controls, CarInputService inject keys, or audio focus tests to `const_audio.config`.
- Add new diagnostic targets (e.g., VHAL, CarPropertyService, SensorService) to `const_dumpsys.config` via `DUMP_CLI_LIST`.

### B. Add Multi-Command Pipelines (`const_multi_cli.config`)
Have a sequence of commands you run frequently together (e.g., restarting Bluetooth, clearing app cache and relaunching, or probing audio zones)?
- Register the group in `MULTI_GROUP_LIST`.
- Define the sequential step array `MULTI_CMD_<GROUP_NAME>`.

### C. Expand Developer Cheatsheets (`const_git.config`, `const_docker.config`, `const_network.config`)
If there are high-frequency Git, Google Repo, Docker, or Linux networking commands that developers constantly look up, suggest adding them to the relevant cheatsheet.

### D. Enhance Core Orchestration (`build_apk.sh`)
- Improve build time optimizations or lunch target detection.
- Add support for new Android build variants or hardware platforms.
- Improve ADB device detection and multi-device handling.

---

## 3. Coding Guidelines & Standards

To maintain high code quality across the codebase, please adhere to these rules:

### Linux (LF) Line Endings
> [!IMPORTANT]
> All shell scripts (`.sh`) and configuration files (`.config`) **must maintain Linux (LF) line endings**. Do not commit Windows CRLF endings.
> If editing on Windows, ensure your editor is configured for LF, or run:
> ```bash
> dos2unix build_apk.sh *.config requirements.txt
> ```

### Shell Scripting Standards (`build_apk.sh`)
- Target **Bash 4.0+** running on Linux (Ubuntu LTS).
- Use the built-in color logging helpers:
  - `log_info "..."` for informational messages.
  - `log_success "..."` for successful steps.
  - `log_warn "..."` for non-fatal warnings.
  - `log_error "..."` for fatal errors.
- Respect fail-fast safety: verify prerequisite binaries (`command -v <tool>`) before executing critical operations.
- Avoid external non-standard dependencies where native shell utilities suffice.

### Configuration File Standards (`const_*.config`)
- Follow the declarative array syntax:
  ```bash
  # Syntax: "action :: English description :: command"
  CONFIG_ARRAY=(
      "action-name :: Short description :: adb shell command"
  )
  ```
- Always include the standard Apache License 2.0 header at the top of new files:
  ```bash
  # ==============================================================================
  # Copyright (C) 2026 Thong Le <letrthong@gmail.com>
  # Author & Maintainer: Thong Le <letrthong@gmail.com>
  #
  # Contribution History:
  #   - 2026-10: Thong Le <letrthong@gmail.com> (Architecture & Domain Design)
  #   - 2026-10: Gemini 3.8 Pro - Google DeepMind (Implementation & Refactoring)
  #   - <YYYY-MM>: <Contributor Name> <<email>> (<Description of contribution>)
  #
  # Licensed under the Apache License, Version 2.0 (the "License");
  # you may not use this file except in compliance with the License.
  # You may obtain a copy of the License at
  #
  #     http://www.apache.org/licenses/LICENSE-2.0
  #
  # Unless required by applicable law or agreed to in writing, software
  # distributed under the License is distributed on an "AS IS" BASIS,
  # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  # See the License for the specific language governing permissions and
  # limitations under the License.
  # ==============================================================================
  ```

---

## 4. Development & Pull Request Workflow

1. **Fork the Repository:** Fork the project on GitHub to your personal account.
2. **Clone & Set Up Locally:**
   ```bash
   git clone https://github.com/<your-username>/telua_aosp.git
   cd telua_aosp
   chmod +x build_apk.sh config_crypto.py
   ```
3. **Create a Topic Branch:**
   ```bash
   git checkout -b feat/add-camera-dumpsys
   ```
4. **Implement Your Changes:** Make your modifications in the relevant file.
5. **Test Your Changes on a Real Linux/ADB Host:**
   - Verify script execution:
     ```bash
     ./build_apk.sh --info
     ./build_apk.sh --help
     ```
   - If adding a cheatsheet or pipeline group, run the command to verify output:
     ```bash
     ./build_apk.sh run
     ./build_apk.sh run <your_group>
     ```
6. **Commit with Conventional Commit Messages:**
   Use clear, conventional commit messages:
   - `feat: add camera service to dumpsys cheatsheet`
   - `fix: resolve overlayfs remount timeout on Android 14`
   - `docs: update README with new multi-cli options`
7. **Submit a Pull Request (PR):**
   - Open a PR against the `main` branch.
   - Provide a concise description of the motivation and testing performed.

---

## 5. Security & Responsible Disclosure

Never commit internal corporate details:
- Do not commit private server IP addresses, internal lunch targets, or proprietary package names.
- Keep `apk.config` populated with generic sample values (e.g., `oem_service`, `192.168.1.100`).
- Ensure sensitive files (`dec_apk.config`, `*.apk`, `*.log`) remain strictly ignored by `.gitignore`.

---

## 6. License

By contributing to this repository, you agree that your contributions will be licensed under the **Apache License 2.0**.
