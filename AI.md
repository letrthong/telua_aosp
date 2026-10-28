
# AI & LLM Agent Quick Reference (`AI.md`)

This document is specifically crafted for **AI Assistants, Autonomous Coding Agents, and LLMs** (e.g., Gemini, Claude, Cursor, Copilot, Antigravity) operating in this repository or in client AOSP workspaces.

When assisting a developer, **ALWAYS prefer using `telua` (or `./build_apk.sh`) commands** instead of manually typing long ADB or AOSP compilation commands.

---

## 1. System Overview & Golden Rules

- **Root Script**: `build_apk.sh` (aliased globally to `telua` via `./build_apk.sh --install`).
- **Target OS**: Linux (Ubuntu 20.04/22.04 LTS).
- **Domain**: AOSP & Android Automotive OS (AAOS) build orchestration, device deployment, and hardware diagnostics.

> [!IMPORTANT]
> **Defensive Rules for AI Agents:**
> 1. **Non-Interactive CI/Agent Execution**: When executing `--repo-reset`, ALWAYS pass the `-y` or `--yes` flag to bypass the interactive `[y/N]` prompt (e.g., `telua --repo-sync --repo-reset -y`).
> 2. **Config Protection**: Never commit or display sensitive decrypted config files (`dec_apk.config`, `dec_*.config`).
> 3. **Line Endings**: Always maintain Linux `LF` line endings for all script and config files.
> 4. **Executable Permissions (Git Mode 100755)**: When modifying or adding scripts from Windows/cross-platform hosts, ALWAYS enforce executable permissions in Git using `git update-index --chmod=+x build_apk.sh config_crypto.py config_overlay.py` so the files run immediately upon checkout on Linux without requiring manual `chmod`.

---

## 2. Directory & Configuration Structure

```
.
├── build_apk.sh              # Core orchestration engine & CLI entrypoint
├── apk.config                # Project-specific active profile & lunch target
├── apk_overlays.config.example # Personal/private override template
├── config_overlay.py         # Smart overlay merger (merges apk_overlays.config)
├── config_crypto.py          # Configuration encryption/decryption (Fernet AES)
├── requirements.txt          # Python dependencies (cryptography)
├── sphinx/                   # Sphinx Doc-as-Code modular template & build scripts
├── config/                   # Declarative global constant cheatsheets & commands
│   ├── const_car.config      # AAOS car & audio key injection & test harness
│   ├── const_dumpsys.config  # System diagnostics & AAOS dumpsys targets
│   ├── const_security.config # Security, SELinux & permission diagnostics
│   ├── const_multi_cli.config# Multi-command sequential pipelines / macros
│   ├── const_my_cli.config.example # Personal pipeline template (telua my <action>)
│   ├── const_docker.config   # Docker & systemd service cheatsheet
│   ├── const_git.config      # Git & Google Repo cheatsheet
│   └── const_network.config  # Linux ports & socket inspection cheatsheet
└── AI.md                     # This file (AI reference)
```

---

## 3. Intent-to-Command Mapping for AI Agents

When the user asks you to perform a task, map their intent to the corresponding `telua` command:

| User Intent | Recommended Command | Notes |
|---|---|---|
| **View General Help & Commands** | `telua` or `telua -h` | Displays primary subcommands, build options, and config paths |
| **Build & Deploy APK (Full Reboot)** | `telua build` (or `telua b`) | Builds module, pushes APK, reboots device, captures logcat |
| **Fast Build & Deploy (No Reboot)** | `telua build --no-reboot` | Uses `stop && start` runtime framework restart |
| **Compile APK Only (No Push)** | `telua build --start-deploy false` | Skips ADB remount and device transfer |
| **Check Environment & Device Status** | `telua info` (or `telua --info`) | Verifies lunch target, module name, paths, and connected DUT |
| **Sync Source Code via Repo** | `telua --repo-sync` | Runs `repo sync` + executes post-sync hook |
| **Sync with Clean Reset** | `telua --repo-sync --repo-reset -y` | Hard resets dirty repos before sync (AI must pass `-y`) |
| **Run Unit Tests** | `telua --test-mode true` | Runs project test script configured in `apk.config` |
| **Find & Replace Text Across Files** | `telua replace <old> <new> [path]` | Fast literal string replacement across directory or single file |
| **Clean Java Trailing Whitespace** | `telua clean-java [diff\|all\|path]` | Strips trailing whitespace & enforces LF on Java source files |
| **Sphinx Doc-as-Code Manager** | `telua docs [init\|build\|clean\|serve\|check]` | Initializes template, validates images/sections & builds HTML |
| **Security & SELinux Diagnostics** | `telua sec [action]` | Controls SELinux (status, perm, enforce), dumps AVC denials & privapp |
| **Install Global CLI Alias & Completion** | `./build_apk.sh --install` | Adds `alias telua=...`, `alias tel=...`, and Tab Auto-completion into `~/.bashrc` |
| **Update Toolkit to Latest Main** | `telua update` | Pulls latest main commit with auto-recovery |

---

## 4. Android Automotive (AAOS) Car & Diagnostics
 
All commands execute directly on the target device via ADB shell (auto-checks device connectivity; immediately halts with `[ERROR] device offline: ...` if device is disconnected or offline):

### 4.1 AAOS Car & Audio Control (`telua car <action>` / `telua audio <action>`)
```bash
telua car                 # View interactive car & audio command list (alias: telua audio)
telua car vol-up          # Increase volume (AAOS CarInputService inject-key 24)
telua car vol-down        # Decrease volume (AAOS CarInputService inject-key 25)
telua car vol-mute        # Mute volume (AAOS CarInputService inject-key 164)
telua car ks              # Launch KitchenSink test application (device-offline verified)
telua car ks-stop         # Force-stop KitchenSink test application
telua car status          # List all registered CarService services (dumpsys car_service --list)
```

### 4.2 Dumpsys Diagnostics (`telua dump <target>`)
```bash
telua dump                # View interactive diagnostic target list
telua dump audio          # Dump standard Android AudioService
telua dump car-service    # Dump AAOS CarService state
telua dump car-audio      # Dump AAOS CarAudioService zones & context state
telua dump media          # Dump active MediaSession playback state
telua dump battery        # Dump battery charging status
telua dump activity       # Dump foreground Activity & window stack
```

### 4.3 Security & SELinux Diagnostics (`telua sec <action>` / `telua security <action>`)
```bash
telua sec                 # View interactive security command list (alias: telua security)
telua sec host            # Audit Linux host security, OS, limits, /tmp & developer hygiene
telua sec status          # Inspect target device SELinux mode, build type, secure & verity props
telua sec perm            # Set SELinux to Permissive mode (setenforce 0)
telua sec enforce         # Set SELinux to Enforcing mode (setenforce 1)
telua sec avc             # Dump SELinux AVC audit denials from logcat & dmesg
telua sec privapp         # Dump priv-app permissions & whitelist violations
telua sec appops          # Query AppOps restrictions and granted operations
telua sec keystore        # Dump Android Keystore service status
telua sec policy          # Dump DevicePolicyManager (DPM) state
telua sec root            # Restart adbd daemon with root privileges
telua sec remount         # Remount system partition as read-write
telua sec disable-verity  # Disable dm-verity partition verification
```

### 4.4 Java Code Hygiene (`telua clean-java`)
AI agents refactoring Java code should use this command to sanitize whitespace before committing:
```bash
telua clean-java          # Default: Cleans only Git modified/added .java files
telua clean-java all      # Recursively cleans all .java files across workspace
telua clean-java <path>   # Cleans a specific .java file or target directory
```

### 4.5 Tab Auto-completion Engine (`src/telua_completion.sh`)
Supports both `telua` and short alias `tel` on Bash & Zsh:
```bash
./build_apk.sh --install  # Automatically installs both aliases & completion into ~/.bashrc
tel <Tab><Tab>            # Subcommands: build, car, dump, clean-java, docs, run, replace...
tel car <Tab><Tab>        # Car actions: vol-up, vol-down, vol-mute, ks, ks-stop, status
tel dump <Tab><Tab>       # Dumpsys targets: audio, car-service, car-audio, media, battery...
tel docs <Tab><Tab>       # Docs actions: start, serve, build, check, clean, init
tel run <Tab><Tab>        # Pipelines: audio-cycle, dev-prep, remount-reboot...
```

### 4.6 Sphinx Doc-as-Code Manager (`telua docs <action>` / `telua doc`)
```bash
telua docs init           # Initialize documentation project from template into ./docs (idempotent)
telua docs check          # Validate section file paths & image directives
telua docs build          # Merge sections & compile HTML into _build/html
telua docs start [8080]   # Auto-build (if needed), open default browser & start HTTP server
telua docs serve [8080]   # Alias for 'start'
telua docs clean          # Remove _build directory
```

---

## 5. Sequential Macro Pipelines (`telua run <group>`)

Execute multi-command sequences with automatic fail-fast safety (stops immediately if any step returns non-zero):

```bash
telua run                 # List all registered pipeline groups and their steps
telua run dev-prep        # Sequence: adb root -> adb remount -> enable debug log tags
telua run audio-cycle     # Sequence: stop KS -> sleep -> start KS -> test vol up/down
telua run remount-reboot  # Sequence: adb root -> adb remount -> adb reboot
telua run audio-dump      # Sequence: dumpsys audio -> car_audio -> media_session
```

*Note: `telua multi <group>` is an alias for `telua run <group>`.*

---

## 6. Developer Cheatsheets

Quick lookup commands for common developer questions:
```bash
telua docker              # Display Docker container & systemd management commands
telua git                 # Display Git status, commit, branch & log cheatsheet
telua network             # Display Linux open ports, ss, netstat & lsof commands
```

---

## 7. Fast Search & Replace Utilities

AI agents should use these built-in helpers when investigating or refactoring codebases:
```bash
./build_apk.sh --find-file "<pattern>" [path]   # Find files matching pattern (e.g. "*.bp")
./build_apk.sh --find-dir "<pattern>" [path]    # Find directories matching pattern
./build_apk.sh --find-text "<text>" [path]      # Grep text string inside files
telua replace "<old_text>" "<new_text>" [path]  # Fast literal text replacement across files/dir
./build_apk.sh --git-diff                       # Show diff of the last git commit
./build_apk.sh --git-amend                      # Amend staged changes to the last commit
```

---

## 8. Configuration File Handling

1. **Active Configuration (`apk.config`)**:
   - `ACTIVE_PROJECT`: Project profile identifier (e.g., `"oem_service"`, `"car_audio"`).
   - `MODULE_NAME`: Module identifier compiled by `m <MODULE_NAME>`.
   - `CONFIG_TARGET_PRODUCT` & `CONFIG_TARGET_BUILD_VARIANT`: Target lunch combination.
   - `APK_DEPLOY_PATH`: Target destination on device (e.g., `/system/priv-app/OemService`).
   - `DEBUG_LOG_TAGS`: List of tags enabled with `persist.log.tag.<TAG>=DEBUG`.

2. **Secrets Protection (`config_crypto.py`)**:
   - Encrypt: `python3 config_crypto.py encrypt <password>` -> `enc_apk.config`
   - Decrypt: `python3 config_crypto.py decrypt <password> --force` -> `dec_apk.config`

---

## 9. Error Troubleshooting for AI Agents

| Error / Exit Code | Cause | Recommended AI Action |
|---|---|---|
| `Could not find the 'android' root directory` | Working directory is outside AOSP tree | Check ancestor directories; ensure script/link is inside an `android/` tree |
| `Cannot find 'build/envsetup.sh'` | CWD does not match Qualcomm `android/qssi` tree | Check `$AOSP_TOP_REL_PATH` in `apk.config` |
| `Device is running a 'user' build` | Target device has secure production build | Inform the user that `userdebug` or `eng` image is required |
| `Fast restart failed ... did not come back` | System crash during `stop && start` | Fall back to full device reboot: run without `--no-reboot` |
| `Exit code 1` in pipeline | A step in `telua run` failed | Inspect failing step output; verify ADB connectivity |
