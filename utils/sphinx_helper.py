import subprocess
import os
import sys
import platform
import webbrowser
from pathlib import Path


# --- Path setup ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CORE_DIR = PROJECT_ROOT / "core"
DOCS_DIR = PROJECT_ROOT / "docs"
DIAGRAMS_DIR = DOCS_DIR / "_static" / "diagrams"


class SphinxHelper:
    def __init__(self):
        # Create folder structure
        DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)
        self.is_windows = platform.system() == "Windows"

    def generate_diagrams(self, project_name="PsychoLab"):
        """Runs pyreverse to generate UML diagrams."""
        print(f"🚀 [OS: {platform.system()}] Generating Diagrams for {project_name}...")

        # pyreverse prefix logic
        cmd = [
            "pyreverse",
            "-o", "png",
            "-p", project_name,
            str(CORE_DIR)
        ]

        try:
            # We run inside the target directory so output drops there
            subprocess.run(cmd, cwd=DIAGRAMS_DIR, check=True, shell=self.is_windows)
            print(f"✅ Diagrams saved to: {DIAGRAMS_DIR}")
        except subprocess.CalledProcessError:
            print("❌ Pyreverse failed. Check if Graphviz is installed and in your PATH.")
        except FileNotFoundError:
            print("❌ pyreverse command not found. Run: pip install pylint")

    def build_docs(self, builder="html"):
        """Unified builder for Windows and Linux/Ubuntu."""
        print(f"🏗️ Building {builder} documentation...")

        # OS-specific executable selection
        make_cmd = "make.bat" if self.is_windows else "make"

        # Double check if sphinx-quickstart was run
        if not (DOCS_DIR / make_cmd).exists() and not (DOCS_DIR / "Makefile").exists():
            print(f"❌ Build tool ({make_cmd}) not found in {DOCS_DIR}.")
            return

        try:
            # shell=True is mandatory for .bat on Windows, optional/safe on Linux
            subprocess.run([make_cmd, builder], cwd=DOCS_DIR, check=True, shell=self.is_windows)
            print(f"✅ Docs build complete.")
        except Exception as e:
            print(f"❌ Build failed: {e}")

    def open_docs(self):
        """Opens the generated index.html in the default browser."""
        index_file = DOCS_DIR / "_build" / "html" / "index.html"

        if index_file.exists():
            print(f"🌐 Opening: {index_file}")
            # Use as_uri() to handle spaces and special chars in Windows paths
            webbrowser.open(index_file.resolve().as_uri())
        else:
            print(f"❌ Cannot find {index_file}. Did you run build_docs()?")


if __name__ == "__main__":
    helper = SphinxHelper()
    helper.generate_diagrams()
    helper.build_docs()
    helper.open_docs()