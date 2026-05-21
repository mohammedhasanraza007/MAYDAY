import os
import sys
import subprocess
import urllib.request
import zipfile
import shutil
from pathlib import Path

def bootstrap():
    root = Path(__file__).parent.parent
    runtime_dir = root / "runtime" / "python"
    
    if (runtime_dir / "python.exe").exists():
        print(f"[*] Runtime already exists at {runtime_dir}")
        return

    runtime_dir.mkdir(parents=True, exist_ok=True)
    
    # Python 3.10.6 embedded for Windows
    url = "https://www.python.org/ftp/python/3.10.6/python-3.10.6-embed-amd64.zip"
    zip_path = runtime_dir / "python_embed.zip"
    
    print(f"[*] Downloading embedded Python from {url}...")
    try:
        urllib.request.urlretrieve(url, zip_path)
    except Exception as e:
        print(f"[ERROR] Download failed: {e}")
        # Try alternate method via powershell if urllib fails
        subprocess.run(["powershell", "-Command", f"Invoke-WebRequest -Uri {url} -OutFile {zip_path}"], check=True)
    
    print("[*] Extracting...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(runtime_dir)
    
    zip_path.unlink()
    
    # Enable site-packages
    pth_files = list(runtime_dir.glob("python*._pth"))
    if not pth_files:
        print("[ERROR] Could not find .pth file")
        return
        
    pth_file = pth_files[0]
    print(f"[*] Modifying {pth_file.name} to enable site-packages...")
    with open(pth_file, "w") as f:
        f.write(".\n")
        f.write("python310.zip\n")
        f.write("import site\n")
        
    # Get get-pip.py
    print("[*] Installing pip...")
    pip_script = runtime_dir / "get-pip.py"
    urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", pip_script)
    
    # Run pip install with embedded python
    # We use -I to ignore existing packages and --no-warn-script-location
    subprocess.run([str(runtime_dir / "python.exe"), str(pip_script), "--no-warn-script-location"], check=True)
    pip_script.unlink()
    
    print("[*] Bootstrap complete.")

if __name__ == "__main__":
    try:
        bootstrap()
    except Exception as e:
        print(f"[ERROR] Bootstrap failed: {e}")
        sys.exit(1)
