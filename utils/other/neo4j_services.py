import subprocess
import os
import platform
import shutil

def neo4j_running():
    """
    Check if a Neo4j process is already running.
    - On Windows: scans tasklist for 'neo4j' or 'java.exe'.
    - On Linux/Ubuntu: scans process list for 'neo4j'.
    Returns True if running, False otherwise.
    """
    if platform.system() == "Windows":
        result = subprocess.run(["tasklist"], capture_output=True, text=True)
        return "neo4j" in result.stdout.lower() or "java.exe" in result.stdout.lower()
    else:  # Linux/Ubuntu
        # First check systemd service status
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "neo4j"],
                capture_output=True, text=True
            )
            if "active" in result.stdout.lower():
                return True
        except FileNotFoundError:
            # systemctl not available, fallback to ps
            pass

        result = subprocess.run(["ps", "-ef"], capture_output=True, text=True)
        return "neo4j" in result.stdout.lower()

def find_neo4j_bin():
    """
    Locate the Neo4j binary folder.
    - First tries NEO4J_HOME environment variable.
    - Then searches PATH for 'neo4j' executable.
    Returns the path to the bin directory.
    Raises RuntimeError if not found.
    """
    neo4j_home = os.environ.get("NEO4J_HOME")
    if neo4j_home:
        return os.path.join(neo4j_home, "bin")

    exe = shutil.which("neo4j")
    if exe:
        return os.path.dirname(exe)

    raise RuntimeError("Neo4j binary path not found. Set NEO4J_HOME or add to PATH.")

def start_neo4j():
    """
    Start Neo4j console mode if not already running.
    - On Windows: runs 'neo4j.bat console'.
    - On Linux/Ubuntu: runs './neo4j console'.
    Skips startup if an instance is already active.
    """
    if neo4j_running():
        print("Neo4j is already running. Skipping startup.")
        return

    neo4j_bin = find_neo4j_bin()

    if platform.system() == "Windows":
        cmd = [os.path.join(neo4j_bin, "neo4j.bat"), "console"]
    else:  # Linux/Ubuntu
        cmd = [os.path.join(neo4j_bin, "neo4j"), "console"]

    print(f"Starting Neo4j: {' '.join(cmd)}")
    subprocess.Popen(cmd, cwd=neo4j_bin)
