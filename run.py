#!/usr/bin/env python3
"""
CV Attendance System - Cross-Platform Launcher
Works on Windows, Linux, and macOS.

Usage:
    python run.py              # Auto-detect and run
    python run.py --dev        # Development mode with hot reload
    python run.py --docker     # Run with Docker Compose
    python run.py --install    # Install dependencies only
    python run.py --help       # Show help
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path


class Launcher:
    def __init__(self):
        self.project_root = Path(__file__).parent.absolute()
        self.venv_dir = self.project_root / ".venv"
        self.is_windows = platform.system() == "Windows"
        self.python_exe = self._get_python_executable()
        self.pip_exe = self._get_pip_executable()

    def _get_python_executable(self) -> str:
        """Get the python executable path for the virtual environment."""
        if self.is_windows:
            return str(self.venv_dir / "Scripts" / "python.exe")
        return str(self.venv_dir / "bin" / "python")

    def _get_pip_executable(self) -> str:
        """Get the pip executable path for the virtual environment."""
        if self.is_windows:
            return str(self.venv_dir / "Scripts" / "pip.exe")
        return str(self.venv_dir / "bin" / "pip")

    def _get_system_python(self) -> str:
        """Get system python command."""
        return "python" if self.is_windows else "python3"

    def run_command(self, cmd: list[str], cwd: Path | None = None, env: dict | None = None, shell: bool = False) -> int:
        """Run a command and return exit code."""
        full_env = os.environ.copy()
        if env:
            full_env.update(env)
        if cwd is None:
            cwd = self.project_root

        print(f"\n🔧 Running: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
        try:
            result = subprocess.run(cmd, cwd=cwd, env=full_env, shell=shell)
            return result.returncode
        except FileNotFoundError:
            print(f"❌ Command not found: {cmd[0]}")
            return 1
        except KeyboardInterrupt:
            print("\n⚠️ Interrupted by user")
            return 130

    def check_docker(self) -> bool:
        """Check if Docker is available."""
        return shutil.which("docker") is not None and shutil.which("docker-compose") is not None

    def check_system_deps(self) -> bool:
        """Check if system dependencies are installed (Linux only)."""
        if self.is_windows:
            return True

        # Check for apt-get and required packages
        if shutil.which("apt-get"):
            try:
                result = subprocess.run(
                    ["dpkg", "-l", "build-essential", "cmake", "libgl1", "libglib2.0-0", "libsm6", "libxext6", "libxrender-dev", "libgomp1"],
                    capture_output=True,
                    text=True,
                )
                return result.returncode == 0
            except Exception:
                return False
        return True  # Assume other distros have deps handled

    def install_system_deps(self) -> bool:
        """Install system dependencies (Linux with apt)."""
        if self.is_windows:
            print("ℹ️  Windows: System dependencies handled by wheels (no apt needed)")
            return True

        if not shutil.which("apt-get"):
            print("⚠️  Non-Debian distro detected. Please install manually:")
            print("   build-essential cmake libgl1 libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1")
            return True

        print("📦 Installing system dependencies (requires sudo)...")
        cmd = [
            "sudo", "apt-get", "update", "&&",
            "sudo", "apt-get", "install", "-y", "--no-install-recommends",
            "build-essential", "cmake",
            "libgl1", "libglib2.0-0", "libsm6", "libxext6", "libxrender-dev", "libgomp1",
            "libgtk-3-0", "libcanberra-gtk3-module",
            "python3-venv", "python3-pip"
        ]
        return self.run_command(cmd, shell=True) == 0

    def create_venv(self) -> bool:
        """Create virtual environment if it doesn't exist."""
        if self.venv_dir.exists():
            print(f"✅ Virtual environment already exists at {self.venv_dir}")
            return True

        print(f"📦 Creating virtual environment at {self.venv_dir}...")
        try:
            venv.create(self.venv_dir, with_pip=True)
            print("✅ Virtual environment created")
            return True
        except Exception as e:
            print(f"❌ Failed to create virtual environment: {e}")
            return False

    def upgrade_pip(self) -> bool:
        """Upgrade pip in the virtual environment."""
        print("⬆️  Upgrading pip...")
        return self.run_command([self.pip_exe, "install", "--upgrade", "pip"]) == 0

    def install_python_deps(self, dev: bool = False) -> bool:
        """Install Python dependencies from requirements.txt."""
        req_file = self.project_root / "requirements.txt"
        if not req_file.exists():
            print(f"❌ Requirements file not found: {req_file}")
            return False

        print("📦 Installing Python dependencies...")
        cmd = [self.pip_exe, "install", "-r", str(req_file)]
        
        # Windows-specific dependencies
        if self.is_windows:
            win_req = self.project_root / "requirements-windows.txt"
            if win_req.exists():
                cmd.extend(["-r", str(win_req)])

        if dev:
            # Also install test dependencies
            test_req = self.project_root / "requirements-test.txt"
            if test_req.exists():
                cmd.extend(["-r", str(test_req)])

        return self.run_command(cmd) == 0

    def install_dlib(self) -> bool:
        """Install dlib (may need source build on some platforms).
        On Windows, dlib is handled via requirements-windows.txt (pre-built wheel).
        """
        if self.is_windows:
            print("ℹ️  Windows: dlib handled via requirements-windows.txt")
            return True

        print("🔧 Checking dlib installation...")
        check_cmd = [self.python_exe, "-c", "import dlib; print('dlib OK')"]
        if self.run_command(check_cmd) == 0:
            print("✅ dlib already available")
            return True

        print("📦 Installing dlib (this may take a few minutes)...")
        return self.run_command([self.pip_exe, "install", "dlib==19.24.1"]) == 0

    def setup_env_file(self) -> bool:
        """Create .env from .env.example if it doesn't exist."""
        env_file = self.project_root / ".env"
        example_file = self.project_root / ".env.example"

        if env_file.exists():
            print("✅ .env file already exists")
            return True

        if not example_file.exists():
            print("❌ .env.example not found")
            return False

        print("📝 Creating .env from .env.example...")
        shutil.copy(example_file, env_file)
        print("⚠️  Please edit .env with your settings before production use!")
        return True

    def run_server(self, dev: bool = False) -> int:
        """Run the FastAPI server."""
        print("\n🚀 Starting CV Attendance System...")
        print(f"   Mode: {'Development (hot reload)' if dev else 'Production'}")
        print(f"   URL:  http://localhost:8000")
        print(f"   Docs: http://localhost:8000/docs")
        print(f"   Admin: http://localhost:8000/admin")
        print("\n   Press Ctrl+C to stop\n")

        cmd = [
            self.python_exe, "-m", "uvicorn",
            "main_fastapi:app",
            "--host", "0.0.0.0",
            "--port", "8000",
        ]
        if dev:
            cmd.append("--reload")

        return self.run_command(cmd)

    def run_docker(self, dev: bool = False) -> int:
        """Run with Docker Compose."""
        if not self.check_docker():
            print("❌ Docker or Docker Compose not found. Please install Docker Desktop.")
            return 1

        compose_file = self.project_root / "docker-compose.yml"
        if not compose_file.exists():
            print("❌ docker-compose.yml not found")
            return 1

        print("🐳 Starting with Docker Compose...")
        cmd = ["docker-compose", "up", "--build"]
        if dev:
            cmd.append("-d")  # Detached for dev
        return self.run_command(cmd, shell=True)

    def run_tests(self) -> int:
        """Run test suite."""
        print("🧪 Running tests...")
        return self.run_command([self.python_exe, "-m", "pytest", "tests/", "-v"])

    def print_help(self):
        """Print help message."""
        print("""
╔══════════════════════════════════════════════════════════════╗
║        CV Attendance System - Cross-Platform Launcher        ║
╚══════════════════════════════════════════════════════════════╝

Usage: python run.py [COMMAND] [OPTIONS]

Commands:
  (none)          Auto-detect environment and run server
  --dev           Run in development mode (hot reload)
  --docker        Run with Docker Compose
  --install       Install dependencies only (create venv, install packages)
  --test          Run test suite
  --help          Show this help message

Options:
  --skip-deps     Skip dependency installation (use existing venv)
  --skip-system   Skip system dependency check (Linux)

Examples:
  python run.py                    # Quick start (auto-install if needed)
  python run.py --dev              # Development with hot reload
  python run.py --docker           # Production with Docker
  python run.py --install          # Setup only
  python run.py --install --dev    # Setup + dev dependencies

Platform: """ + platform.system() + " " + platform.release() + f"""
Python: {sys.version.split()[0]}
Project: {self.project_root}
        """)


def main():
    parser = argparse.ArgumentParser(
        description="CV Attendance System Launcher",
        add_help=False,  # We'll handle --help ourselves
    )
    parser.add_argument("--dev", action="store_true", help="Development mode with hot reload")
    parser.add_argument("--docker", action="store_true", help="Run with Docker Compose")
    parser.add_argument("--install", action="store_true", help="Install dependencies only")
    parser.add_argument("--test", action="store_true", help="Run test suite")
    parser.add_argument("--help", action="store_true", help="Show help")
    parser.add_argument("--skip-deps", action="store_true", help="Skip Python dependency installation")
    parser.add_argument("--skip-system", action="store_true", help="Skip system dependency check")

    args = parser.parse_args()

    launcher = Launcher()

    if args.help:
        launcher.print_help()
        return 0

    # Docker mode
    if args.docker:
        return launcher.run_docker(dev=args.dev)

    # Test mode
    if args.test:
        if not launcher.venv_dir.exists():
            print("❌ Virtual environment not found. Run with --install first.")
            return 1
        return launcher.run_tests()

    # Install mode (or auto-install if needed)
    if args.install or not launcher.venv_dir.exists():
        print("🔧 Setting up environment...")

        if not args.skip_system:
            if not launcher.check_system_deps():
                print("⚠️  Some system dependencies may be missing.")
                if not args.skip_system:
                    launcher.install_system_deps()

        if not launcher.create_venv():
            return 1

        if not launcher.upgrade_pip():
            return 1

        if not launcher.install_python_deps(dev=args.dev):
            return 1

        if not launcher.install_dlib():
            print("⚠️  dlib installation failed. Face recognition may use fallback only.")

        launcher.setup_env_file()

        if args.install:
            print("\n✅ Installation complete!")
            print("   Run 'python run.py' to start the server")
            print("   Run 'python run.py --dev' for development mode")
            return 0

    # Normal server run
    if not args.skip_deps:
        # Quick check if deps are installed
        check = launcher.run_command([launcher.python_exe, "-c", "import fastapi, cv2, insightface; print('OK')"])
        if check != 0:
            print("⚠️  Dependencies missing, installing...")
            if not launcher.install_python_deps(dev=args.dev):
                return 1
            if not launcher.install_dlib():
                print("⚠️  dlib installation failed.")

    return launcher.run_server(dev=args.dev)


if __name__ == "__main__":
    sys.exit(main())