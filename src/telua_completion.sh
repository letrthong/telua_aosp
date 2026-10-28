#!/bin/bash
# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Author & Maintainer: Thong Le <letrthong@gmail.com>
#
# Contribution History:
#   - 2026-10: Thong Le <letrthong@gmail.com> (Bash & Zsh Auto-completion Engine)
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
#
# telua_completion.sh - Tab Auto-completion for 'telua' and 'tel' CLI commands.
# Supports Bash (>= 4.0) and Zsh (via bashcompinit).
#
# To activate manually:
#   source /path/to/telua_aosp/src/telua_completion.sh
# Or install automatically via:
#   telua install
# ==============================================================================

# Enable bash completion compatibility in Zsh if needed
if [ -n "${ZSH_VERSION:-}" ]; then
    autoload -U +X bashcompinit 2>/dev/null && bashcompinit 2>/dev/null || true
fi

_telua_completions() {
    local cur prev words cword
    if [ -n "${ZSH_VERSION:-}" ]; then
        # Zsh compatibility layer
        words=("${COMP_WORDS[@]}")
        cword=$COMP_CWORD
        cur="${words[cword]}"
        prev="${words[cword-1]}"
    else
        # Standard Bash
        cur="${COMP_WORDS[COMP_CWORD]}"
        prev="${COMP_WORDS[COMP_CWORD-1]}"
    fi

    # 1. Primary subcommands and global options
    local subcommands="build init install info update replace car dump sec security clean-java docs doc run multi my proj git docker network help version"
    local options="--no-reboot --start-deploy --platform --repo-sync --repo-reset -y --yes --config --softlink --test-mode --ram-monitor --find-file --find-dir --find-text --replace -h --help -v --version"

    # Context-aware completion based on the previous word
    case "$prev" in
        docs|doc)
            local docs_actions="init build clean serve check help"
            COMPREPLY=($(compgen -W "$docs_actions" -- "$cur"))
            return 0
            ;;
        sec|security)
            local sec_actions="host status perm enforce avc privapp appops keystore policy root unroot remount disable-verity help"
            local config_dir
            config_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../config" 2>/dev/null && pwd)"
            if [ -f "$config_dir/const_security.config" ]; then
                local dynamic_sec
                dynamic_sec=$(grep -E '^[[:space:]]*"[^:]+::' "$config_dir/const_security.config" 2>/dev/null | sed -E 's/^[[:space:]]*"([^[:space:]]+).*/\1/' | tr '\n' ' ')
                if [ -n "$dynamic_sec" ]; then
                    sec_actions="$dynamic_sec help"
                fi
            fi
            COMPREPLY=($(compgen -W "$sec_actions" -- "$cur"))
            return 0
            ;;
        car)
            local car_actions="vol-up vol-down vol-mute ks ks-stop status help"
            # Try to read dynamic actions from const_car.config if present
            local config_dir
            config_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../config" 2>/dev/null && pwd)"
            if [ -f "$config_dir/const_car.config" ]; then
                local dynamic_car
                dynamic_car=$(grep -E '^[[:space:]]*"[^:]+::' "$config_dir/const_car.config" 2>/dev/null | sed -E 's/^[[:space:]]*"([^[:space:]]+).*/\1/' | tr '\n' ' ')
                if [ -n "$dynamic_car" ]; then
                    car_actions="$dynamic_car help"
                fi
            fi
            COMPREPLY=($(compgen -W "$car_actions" -- "$cur"))
            return 0
            ;;
        dump)
            local dump_targets="audio car-service car-audio media battery activity help"
            local config_dir
            config_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../config" 2>/dev/null && pwd)"
            if [ -f "$config_dir/const_dumpsys.config" ]; then
                local dynamic_dumps
                dynamic_dumps=$(grep -E '^[[:space:]]*"[^:]+::' "$config_dir/const_dumpsys.config" 2>/dev/null | sed -E 's/^[[:space:]]*"([^[:space:]]+).*/\1/' | tr '\n' ' ')
                if [ -n "$dynamic_dumps" ]; then
                    dump_targets="$dynamic_dumps help"
                fi
            fi
            COMPREPLY=($(compgen -W "$dump_targets" -- "$cur"))
            return 0
            ;;
        run|multi)
            local run_groups="audio-cycle media-mute-cycle dev-prep remount-reboot audio-dump logcat-start logcat-stop net-up unittest help"
            local config_dir
            config_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../config" 2>/dev/null && pwd)"
            if [ -f "$config_dir/const_multi_cli.config" ]; then
                local dynamic_groups
                dynamic_groups=$(grep -E '^[[:space:]]*"[^:]+::' "$config_dir/const_multi_cli.config" 2>/dev/null | sed -E 's/^[[:space:]]*"([^[:space:]]+).*/\1/' | tr '\n' ' ')
                if [ -n "$dynamic_groups" ]; then
                    run_groups="$dynamic_groups help"
                fi
            fi
            COMPREPLY=($(compgen -W "$run_groups" -- "$cur"))
            return 0
            ;;
        clean-java)
            local clean_options="diff all help"
            COMPREPLY=($(compgen -W "$clean_options" -- "$cur"))
            return 0
            ;;
        my|proj)
            local my_actions="hello help"
            local config_dir
            config_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../config" 2>/dev/null && pwd)"
            local my_cfg="$config_dir/const_my_cli.config"
            [ ! -f "$my_cfg" ] && my_cfg="$config_dir/const_my_cli.config.example"
            if [ -f "$my_cfg" ]; then
                local dynamic_my
                dynamic_my=$(grep -E '^[[:space:]]*"[^:]+::' "$my_cfg" 2>/dev/null | sed -E 's/^[[:space:]]*"([^[:space:]]+).*/\1/' | tr '\n' ' ')
                if [ -n "$dynamic_my" ]; then
                    my_actions="$dynamic_my help"
                fi
            fi
            COMPREPLY=($(compgen -W "$my_actions" -- "$cur"))
            return 0
            ;;
        --platform)
            COMPREPLY=($(compgen -W "android qnx" -- "$cur"))
            return 0
            ;;
        --start-deploy|--test-mode|--ram-monitor)
            COMPREPLY=($(compgen -W "true false" -- "$cur"))
            return 0
            ;;
        --config|--softlink)
            # Default filesystem completion for paths
            COMPREPLY=($(compgen -f -- "$cur"))
            return 0
            ;;
    esac

    # Top-level completion (if typing options starting with '-', complete options, else subcommands + options)
    if [[ "$cur" == -* ]]; then
        COMPREPLY=($(compgen -W "$options" -- "$cur"))
    else
        COMPREPLY=($(compgen -W "$subcommands $options" -- "$cur"))
    fi
    return 0
}

# Register completion function for telua, tel, and direct script executions
complete -F _telua_completions telua tel build_apk.sh ./build_apk.sh 2>/dev/null || true
