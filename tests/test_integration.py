"""Integration tests for the App Platform Sandbox SDK."""

import os
import sys
import shutil
import subprocess

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from do_app_sandbox import Sandbox, CommandResult


def test_full_workflow():
    """Test the complete sandbox workflow."""
    print("=" * 60)
    print("App Platform Sandbox SDK - Integration Test")
    print("=" * 60)

    sandbox = None
    try:
        # 1. Create sandbox
        print("\n[1/6] Creating sandbox...")
        sandbox = Sandbox.create(image="python", name="test-sandbox-sdk")
        print(f"  App ID: {sandbox.app_id}")
        print(f"  Status: {sandbox.status}")

        # 2. Get URL
        print("\n[2/6] Getting public URL...")
        url = sandbox.get_url()
        print(f"  URL: {url}")

        # 3. Test command execution
        print("\n[3/6] Testing command execution...")
        result = sandbox.exec("python3 --version")
        print(f"  stdout: {result.stdout}")
        print(f"  stderr: {result.stderr}")
        print(f"  exit_code: {result.exit_code}")
        assert result.success, f"Python version command failed: {result.stderr}"

        # 4. Test exit code capture
        print("\n[4/6] Testing exit code capture...")
        result = sandbox.exec("ls /nonexistent_path_12345")
        print(f"  exit_code for non-existent path: {result.exit_code}")
        assert result.exit_code != 0, "Should have non-zero exit code for missing path"
        print("  Exit code capture working!")

        # 5. Test file operations
        print("\n[5/6] Testing file operations...")
        test_content = "print('Hello from Sandbox SDK!')"
        sandbox.filesystem.write_file("/tmp/test_script.py", test_content)
        print("  Wrote test script")

        read_content = sandbox.filesystem.read_file("/tmp/test_script.py")
        print(f"  Read back: {read_content[:50]}...")
        assert "Hello from Sandbox SDK" in read_content, "Content mismatch"

        # Run the script
        result = sandbox.exec("python3 /tmp/test_script.py")
        print(f"  Script output: {result.stdout}")
        assert "Hello from Sandbox SDK" in result.stdout, "Script output mismatch"

        # 6. Test directory operations
        print("\n[6/6] Testing directory operations...")
        sandbox.filesystem.mkdir("/tmp/test_dir/subdir", recursive=True)
        assert sandbox.filesystem.is_dir("/tmp/test_dir"), "Directory not created"
        print("  Directory created and verified")

        files = sandbox.filesystem.list_dir("/tmp")
        print(f"  Found {len(files)} items in /tmp")

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED!")
        print("=" * 60)

    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        raise

    finally:
        if sandbox:
            print("\nCleaning up - deleting sandbox...")
            sandbox.delete()
            print("Sandbox deleted")


if __name__ == "__main__":
    # Check doctl availability/auth instead of raw token
    if shutil.which("doctl") is None:
        print("ERROR: doctl not found. Install doctl and run 'doctl auth init'.")
        sys.exit(1)

    auth_check = subprocess.run(
        ["doctl", "auth", "list", "--output", "json"],
        capture_output=True,
        text=True,
    )
    if auth_check.returncode != 0 or not auth_check.stdout.strip():
        print("ERROR: doctl is not authenticated. Run 'doctl auth init'.")
        sys.exit(1)

    test_full_workflow()
