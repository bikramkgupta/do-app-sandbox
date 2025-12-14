# Run Commands

Execute shell commands in your sandbox with full control over environment variables, working directories, and timeouts.

## Basic Command Execution

### Execute a Command

The `exec()` method runs a command and returns the result:

**Sync:**

```python
from app_platform_sandbox import Sandbox

sandbox = Sandbox.get_from_id(app_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

result = sandbox.exec("echo 'Hello, World!'")
print(result.stdout)  # Output: Hello, World!
```

**Async:**

```python
import asyncio
from app_platform_sandbox import AsyncSandbox

async def main():
    sandbox = await AsyncSandbox.get_from_id(app_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

    result = await sandbox.exec("echo 'Hello, World!'")
    print(result.stdout)

asyncio.run(main())
```

**CLI:**

```bash
sandbox exec --id a1b2c3d4-e5f6-7890-abcd-ef1234567890 "echo 'Hello, World!'"
```

**Output:**

```
Hello, World!
```

## Command Results

The `exec()` method returns a `CommandResult` object with these properties:

| Property | Type | Description |
|----------|------|-------------|
| `stdout` | str | Standard output from the command |
| `stderr` | str | Standard error output |
| `exit_code` | int | Exit code (0 = success) |
| `success` | bool | True if exit_code == 0 |

### Accessing Results

**Sync:**

```python
result = sandbox.exec("ls -la /tmp")

print(f"Output: {result.stdout}")
print(f"Errors: {result.stderr}")
print(f"Exit Code: {result.exit_code}")
print(f"Success: {result.success}")
```

### Checking for Errors

```python
result = sandbox.exec("cat /nonexistent/file")

if not result.success:
    print(f"Command failed with exit code {result.exit_code}")
    print(f"Error: {result.stderr}")
else:
    print(f"Output: {result.stdout}")
```

**Output:**

```
Command failed with exit code 1
Error: cat: /nonexistent/file: No such file or directory
```

## Environment Variables

Pass environment variables to your commands:

### SDK

**Sync:**

```python
result = sandbox.exec(
    "echo $MY_VAR",
    env={"MY_VAR": "Hello from env!"}
)
print(result.stdout)  # Output: Hello from env!

# Multiple environment variables
result = sandbox.exec(
    "echo $DB_HOST:$DB_PORT",
    env={
        "DB_HOST": "localhost",
        "DB_PORT": "5432"
    }
)
print(result.stdout)  # Output: localhost:5432
```

**Async:**

```python
result = await sandbox.exec(
    "python -c \"import os; print(os.environ.get('API_KEY'))\"",
    env={"API_KEY": "secret-key-123"}
)
print(result.stdout)  # Output: secret-key-123
```

### Example: AI/ML Configuration

```python
# Set up ML environment and run inference
result = sandbox.exec(
    "python inference.py",
    env={
        "MODEL_PATH": "/models/bert-base",
        "BATCH_SIZE": "32",
        "DEVICE": "cpu",
        "LOG_LEVEL": "INFO"
    }
)
```

## Working Directory

Change the working directory for command execution:

### SDK

**Sync:**

```python
# Create a directory and work within it
sandbox.exec("mkdir -p /app/project")

result = sandbox.exec(
    "pwd",
    cwd="/app/project"
)
print(result.stdout)  # Output: /app/project

# Run commands from project directory
result = sandbox.exec(
    "ls -la",
    cwd="/app/project"
)
```

**Async:**

```python
result = await sandbox.exec(
    "python main.py",
    cwd="/app/src"
)
```

### Example: Data Processing Pipeline

```python
# Set up project structure
sandbox.exec("mkdir -p /workspace/data /workspace/output")

# Process data in the workspace
result = sandbox.exec(
    "python process.py --input data/input.csv --output output/result.csv",
    cwd="/workspace",
    env={"PYTHONPATH": "/workspace/lib"}
)
```

## Timeouts

Set a maximum execution time for commands:

### SDK

**Sync:**

```python
from app_platform_sandbox.exceptions import CommandTimeoutError

try:
    # Command with 30 second timeout
    result = sandbox.exec(
        "sleep 60",
        timeout=30
    )
except CommandTimeoutError:
    print("Command timed out after 30 seconds")
```

**Async:**

```python
try:
    result = await sandbox.exec(
        "python long_running_script.py",
        timeout=120  # 2 minutes
    )
except CommandTimeoutError:
    print("Script exceeded timeout")
```

### Default Timeout

The default timeout is 120 seconds (2 minutes). For longer operations, specify a higher timeout:

```python
# Long-running data processing
result = sandbox.exec(
    "python train_model.py",
    timeout=600  # 10 minutes
)
```

## Error Handling

### Handle Execution Errors

```python
from app_platform_sandbox.exceptions import (
    CommandExecutionError,
    CommandTimeoutError
)

try:
    result = sandbox.exec("python script.py")

    if not result.success:
        print(f"Script exited with code {result.exit_code}")
        print(f"Error output: {result.stderr}")
    else:
        print(f"Success: {result.stdout}")

except CommandTimeoutError:
    print("Command timed out")

except CommandExecutionError as e:
    print(f"Execution failed: {e}")
```

### Validate Commands

```python
def run_safely(sandbox, command, **kwargs):
    """Run a command and handle common errors."""
    result = sandbox.exec(command, **kwargs)

    if not result.success:
        raise RuntimeError(
            f"Command failed: {command}\n"
            f"Exit code: {result.exit_code}\n"
            f"Error: {result.stderr}"
        )

    return result.stdout

# Usage
try:
    output = run_safely(sandbox, "python validate.py")
    print(output)
except RuntimeError as e:
    print(e)
```

## Examples

### AI/ML: Running Python Inference

```python
from app_platform_sandbox import Sandbox

# Connect to existing ML sandbox
sandbox = Sandbox.get_from_id(app_id="ml-sandbox-id")

# Install dependencies (if not already installed)
result = sandbox.exec("pip install torch transformers")
print(result.stdout)

# Upload model script
sandbox.filesystem.write_file("/app/inference.py", '''
import torch
from transformers import pipeline

classifier = pipeline("sentiment-analysis")
result = classifier("I love using this sandbox!")
print(f"Sentiment: {result[0]['label']}, Score: {result[0]['score']:.4f}")
''')

# Run inference
result = sandbox.exec(
    "python inference.py",
    cwd="/app",
    env={"TRANSFORMERS_CACHE": "/tmp/cache"},
    timeout=300
)
print(result.stdout)
```

**Output:**

```
Sentiment: POSITIVE, Score: 0.9998
```

### Data Processing: Transform CSV Data

```python
from app_platform_sandbox import Sandbox

sandbox = Sandbox.get_from_id(app_id="data-sandbox-id")

# Upload data
sandbox.filesystem.write_file("/data/input.csv", """name,age,city
Alice,30,NYC
Bob,25,LA
Charlie,35,Chicago
""")

# Process with Python
result = sandbox.exec('''
python -c "
import csv
with open('/data/input.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        print(f\"{row['name']} is {row['age']} years old\")
"
''')
print(result.stdout)
```

**Output:**

```
Alice is 30 years old
Bob is 25 years old
Charlie is 35 years old
```

### General: Installing Packages and Running Tests

```python
from app_platform_sandbox import Sandbox

sandbox = Sandbox.get_from_id(app_id="test-sandbox-id")

# Install test framework
result = sandbox.exec("pip install pytest")
print("Installed pytest")

# Create test file
sandbox.filesystem.write_file("/tests/test_math.py", '''
def test_addition():
    assert 1 + 1 == 2

def test_multiplication():
    assert 3 * 4 == 12

def test_division():
    assert 10 / 2 == 5
''')

# Run tests
result = sandbox.exec(
    "pytest -v",
    cwd="/tests"
)
print(result.stdout)
```

**Output:**

```
============================= test session starts ==============================
collected 3 items

test_math.py::test_addition PASSED
test_math.py::test_multiplication PASSED
test_math.py::test_division PASSED

============================== 3 passed in 0.01s ===============================
```

### Chaining Commands

Execute multiple commands in sequence:

```python
# Using shell operators
result = sandbox.exec("cd /app && pip install -r requirements.txt && python main.py")

# Or execute separately for better error handling
sandbox.exec("pip install -r /app/requirements.txt")
result = sandbox.exec("python main.py", cwd="/app")
```

### Capture Both stdout and stderr

```python
result = sandbox.exec("python -c \"import sys; print('out'); print('err', file=sys.stderr)\"")

print(f"stdout: {result.stdout}")  # Output: out
print(f"stderr: {result.stderr}")  # Output: err
```

## CLI Reference

### Basic Execution

```bash
# By sandbox name
sandbox exec my-sandbox "echo 'Hello'"

# By App ID
sandbox exec --id a1b2c3d4-... "python --version"
```

### Complex Commands

```bash
# Multi-line scripts (use quotes)
sandbox exec my-sandbox "
    pip install pandas
    python -c 'import pandas; print(pandas.__version__)'
"

# With special characters
sandbox exec my-sandbox "echo 'Hello, World!' | wc -c"
```

## Next Steps

- [File Operations](sandbox_fileops.md) - Upload, download, and manage files in your sandbox
- [Large File Transfers](sandbox_large_files.md) - Handle files larger than 5MB using Spaces
- [Background Processes](sandbox_processes.md) - Run long-running processes in the background
