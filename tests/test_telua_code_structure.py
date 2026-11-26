# ==============================================================================
# Copyright (C) 2026 Thong Le <letrthong@gmail.com>
# Author & Maintainer: Thong Le <letrthong@gmail.com>
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
"""
test_telua_code_structure.py — Unit tests for CodeStructureEngine and structure-aware code reading.
"""

import unittest
from pathlib import Path

from web.ai.code_structure_engine import CodeStructureEngine
from web.ai.telua_web_ai import _tool_read_file


JAVA_SAMPLE = """package com.example.car.audio;

import android.util.Log;
import java.util.List;

/**
 * Audio Zone Controller for Automotive OS.
 */
public class CarAudioZoneController {
    private static final String TAG = "CarAudioZone";
    private int mZoneId;

    /**
     * Initializes the audio zone with specified ID.
     */
    public synchronized void init(int zoneId) {
        this.mZoneId = zoneId;
        Log.i(TAG, "Initialized zone: " + zoneId);
    }

    public int getZoneId() {
        return this.mZoneId;
    }

    /**
     * Sets volume group index safely.
     */
    public void setVolumeGroupIndex(int groupId, int index) {
        if (groupId < 0) {
            throw new IllegalArgumentException("Invalid group id");
        }
        Log.d(TAG, "Setting group " + groupId + " to " + index);
    }
}
"""

PYTHON_SAMPLE = '''"""Module docstring."""
import os
import sys

class AudioEngine:
    """Manages audio routing."""
    def __init__(self, sample_rate: int = 48000):
        self.sample_rate = sample_rate

    def route_audio(self, source: str, sink: str) -> bool:
        """Route audio stream from source to sink."""
        if not source or not sink:
            return False
        return True

def standalone_helper():
    return 42
'''


class TestCodeStructureEngine(unittest.TestCase):
    """Test suite for AST parsing, outline generation, and boundary snapping."""

    def test_detect_language(self):
        self.assertEqual(CodeStructureEngine.detect_language("CarAudio.java"), "java")
        self.assertEqual(CodeStructureEngine.detect_language("engine.cpp"), "cpp")
        self.assertEqual(CodeStructureEngine.detect_language("audio.py"), "python")
        self.assertEqual(CodeStructureEngine.detect_language("service.kt"), "kotlin")
        self.assertEqual(CodeStructureEngine.detect_language("build.bp"), "blueprint")
        self.assertEqual(CodeStructureEngine.detect_language("readme.txt"), "text")

    def test_parse_java_sample(self):
        struct = CodeStructureEngine.parse_text(JAVA_SAMPLE, "CarAudioZoneController.java")
        self.assertEqual(struct.language, "java")
        self.assertEqual(struct.package, "com.example.car.audio")
        self.assertEqual(len(struct.classes), 1)
        self.assertEqual(struct.classes[0].name, "CarAudioZoneController")

        method_names = [m.name for m in struct.methods]
        self.assertIn("init", method_names)
        self.assertIn("getZoneId", method_names)
        self.assertIn("setVolumeGroupIndex", method_names)

        # Check enclosing class
        for m in struct.methods:
            self.assertEqual(m.enclosing_class, "CarAudioZoneController")

    def test_parse_python_sample(self):
        struct = CodeStructureEngine.parse_text(PYTHON_SAMPLE, "engine.py")
        self.assertEqual(struct.language, "python")
        self.assertEqual(len(struct.classes), 1)
        self.assertEqual(struct.classes[0].name, "AudioEngine")

        method_names = [m.name for m in struct.methods]
        self.assertIn("__init__", method_names)
        self.assertIn("route_audio", method_names)
        self.assertIn("standalone_helper", method_names)

    def test_get_outline(self):
        outline = CodeStructureEngine.get_outline(JAVA_SAMPLE, "CarAudioZoneController.java")
        self.assertIn("=== OUTLINE: CarAudioZoneController.java", outline)
        self.assertIn("Package: com.example.car.audio", outline)
        self.assertIn("CarAudioZoneController", outline)
        self.assertIn("init()", outline)
        self.assertIn("setVolumeGroupIndex()", outline)

    def test_extract_symbol(self):
        res = CodeStructureEngine.extract_symbol(JAVA_SAMPLE, "CarAudioZoneController.java", "setVolumeGroupIndex")
        self.assertIsNotNone(res)
        self.assertEqual(res["symbol"], "setVolumeGroupIndex")
        self.assertIn("public void setVolumeGroupIndex", res["output"])
        self.assertIn("CarAudioZoneController", res["output"])

    def test_extract_symbol_not_found(self):
        res = CodeStructureEngine.extract_symbol(JAVA_SAMPLE, "CarAudioZoneController.java", "nonExistentMethod")
        self.assertIsNone(res)

    def test_snap_boundaries(self):
        # In JAVA_SAMPLE, init() starts around line 15 and ends around line 21
        # If user asks for lines 10 to 18, it should snap end_line to line 21
        struct = CodeStructureEngine.parse_text(JAVA_SAMPLE, "CarAudioZoneController.java")
        init_m = next(m for m in struct.methods if m.name == "init")

        s, e, note = CodeStructureEngine.snap_boundaries(
            JAVA_SAMPLE, "CarAudioZoneController.java", 1, init_m.start_line + 2, max_snap=50
        )
        self.assertEqual(e, init_m.end_line)
        self.assertIsNotNone(note)
        self.assertIn("Smart Snap", note)

    def test_chunk_code_for_vector_db(self):
        meta = {
            "source_id": "test_src",
            "source_name": "Test Source",
            "rel_path": "audio/CarAudioZoneController.java",
            "category": "audio",
        }
        chunks = CodeStructureEngine.chunk_code_for_vector_db(
            JAVA_SAMPLE, "CarAudioZoneController.java", meta
        )
        # Should have 1 context chunk + 3 method chunks = 4 chunks
        self.assertEqual(len(chunks), 4)

        ctx_chunk = chunks[0]
        self.assertEqual(ctx_chunk["metadata"]["chunk_type"], "class_context")
        self.assertIn("CarAudioZoneController", ctx_chunk["document"])

        method_chunks = chunks[1:]
        symbols = [c["metadata"]["symbol_name"] for c in method_chunks]
        self.assertIn("init", symbols)
        self.assertIn("getZoneId", symbols)
        self.assertIn("setVolumeGroupIndex", symbols)

    def test_tool_read_file_outline_and_method(self):
        # Test real workspace file
        real_java = "repos/telua_skill/Java_Android/examples/ApiTimeoutResilienceTemplate.java"
        if Path(real_java).is_file():
            # 1. Outline mode
            outline_out = _tool_read_file({"path": real_java, "outline": True})
            self.assertIn("=== OUTLINE:", outline_out)
            self.assertIn("ApiTimeoutResilienceTemplate", outline_out)
            self.assertIn("init()", outline_out)
            self.assertIn("executeWithTimeout()", outline_out)

            # 2. Method mode
            method_out = _tool_read_file({"path": real_java, "method": "executeWithTimeout"})
            self.assertIn("executeWithTimeout", method_out)
            self.assertIn("Future<T> future", method_out)

            # 3. Smart snap mode
            snap_out = _tool_read_file({"path": real_java, "start_line": 54, "end_line": 65})
            # init() ends at line 70, so end_line should snap to 70
            self.assertIn("70 |     }", snap_out)


if __name__ == "__main__":
    unittest.main()
