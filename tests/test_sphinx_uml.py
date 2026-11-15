import os
import subprocess
import sys
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as td:
    src = Path(td) / "src"
    out = Path(td) / "out"
    src.mkdir()
    
    wrapper = Path(r"d:\wmshare\telua_aosp\sphinx\scripts\plantuml_wrapper.py").resolve()
    
    conf = f"""
import sys
project = 'Test'
extensions = ['sphinxcontrib.plantuml']
plantuml = [sys.executable, r'{wrapper}']
plantuml_output_format = 'svg'
"""
    (src / "conf.py").write_text(conf, encoding="utf-8")
    
    rst = """Test PlantUML
============

.. uml::

   @startuml
   actor User
   participant "Frontend" as UI
   participant "Backend" as API
   database "Database" as DB

   @enduml
"""
    (src / "index.rst").write_text(rst, encoding="utf-8")
    
    res = subprocess.run([sys.executable, "-m", "sphinx", "-b", "html", str(src), str(out)], capture_output=True, text=True)
    print("STDOUT:", res.stdout)
    print("STDERR:", res.stderr)
    print("Return code:", res.returncode)
    images = list((out / "_images").glob("*")) if (out / "_images").exists() else []
    print("Images:", images)
    if images:
        print("Image content preview:", images[0].read_text(encoding="utf-8")[:200])
