# Background Processes

Run long-running processes in the background, monitor their status, and retrieve their output. Ideal for ML training jobs, data pipelines, and services.

## Overview

Background processes:
- Run with `nohup` to survive connection drops
- Output is redirected to log files in `/tmp`
- Can be monitored, killed, and have their output retrieved
- Persist until the sandbox is deleted or the process completes

## Launching Background Processes

### Basic Launch

**Sync:**

```python
from app_platform_sandbox import Sandbox

sandbox = Sandbox.get_from_id(app_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

# Launch a background process
pid = sandbox.launch_process("python long_script.py")
print(f"Process started with PID: {pid}")
```

**Async:**

```python
from app_platform_sandbox import AsyncSandbox

sandbox = await AsyncSandbox.get_from_id(app_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

pid = await sandbox.launch_process("python train.py --epochs 100")
print(f"Training started with PID: {pid}")
```

### Launch with Working Directory

```python
# Launch process in a specific directory
pid = sandbox.launch_process(
    command="python main.py",
    cwd="/app/project"
)
```

### Launch with Environment Variables

```python
# Set environment variables for the process
pid = sandbox.launch_process(
    command="python train.py",
    env={
        "CUDA_VISIBLE_DEVICES": "0",
        "BATCH_SIZE": "32",
        "LEARNING_RATE": "0.001"
    }
)
```

## Listing Running Processes

### List All Processes

**Sync:**

```python
processes = sandbox.list_processes()

for proc in processes:
    print(f"PID: {proc.pid}")
    print(f"  Command: {proc.command}")
    print(f"  Status: {proc.status}")
    print(f"  CPU: {proc.cpu}")
    print(f"  Memory: {proc.memory}")
    print()
```

**Async:**

```python
processes = await sandbox.list_processes()
for proc in processes:
    print(f"{proc.pid}: {proc.command}")
```

**Output:**

```
PID: 1234
  Command: python train.py --epochs 100
  Status: running
  CPU: 45.2%
  Memory: 1.2G

PID: 5678
  Command: python server.py
  Status: running
  CPU: 2.1%
  Memory: 128M
```

### Filter Processes by Pattern

```python
# Find all Python processes
python_procs = sandbox.list_processes(pattern="python")

for proc in python_procs:
    print(f"{proc.pid}: {proc.command}")

# Find specific script
training_procs = sandbox.list_processes(pattern="train.py")
```

## Getting Process Output

Retrieve the stdout/stderr from a launched process:

**Sync:**

```python
# Launch a process
pid = sandbox.launch_process("python train.py")

# Wait a bit for output
import time
time.sleep(10)

# Get the output so far
output = sandbox.process_manager.get_output(pid)
print(output)
```

**Async:**

```python
pid = await sandbox.launch_process("python script.py")
await asyncio.sleep(5)
output = await sandbox.process_manager.get_output(pid)
print(output)
```

### Polling for Output

```python
import time

pid = sandbox.launch_process("python long_job.py")

# Poll for updates
for _ in range(10):
    output = sandbox.process_manager.get_output(pid)
    print(f"Current output:\n{output}\n---")
    time.sleep(30)

    # Check if still running
    if not sandbox.process_manager.is_running(pid):
        print("Process completed!")
        break
```

## Checking Process Status

### Is Process Running

```python
pid = sandbox.launch_process("python server.py")

# Check later if it's still running
if sandbox.process_manager.is_running(pid):
    print(f"Process {pid} is still running")
else:
    print(f"Process {pid} has finished")
```

### Wait for Process Completion

```python
pid = sandbox.launch_process("python batch_job.py")

# Wait up to 5 minutes for completion
try:
    sandbox.process_manager.wait_for(pid, timeout=300)
    print("Process completed successfully")
except TimeoutError:
    print("Process still running after timeout")
```

## Killing Processes

### Kill by PID

**Sync:**

```python
# Kill a specific process
sandbox.kill_process(pid)
print(f"Process {pid} killed")
```

**Async:**

```python
await sandbox.kill_process(pid)
```

### Kill with Signal

```python
import signal

# Send SIGTERM (graceful shutdown)
sandbox.process_manager.kill(pid, signal=signal.SIGTERM)

# Force kill with SIGKILL
sandbox.process_manager.kill(pid, signal=signal.SIGKILL)
```

### Kill by Pattern

```python
# Kill all processes matching a pattern
sandbox.process_manager.kill_by_pattern("train.py")
```

### Kill All Launched Processes

```python
# Kill all processes launched by this sandbox instance
sandbox.kill_all_processes()
print("All sandbox processes killed")
```

## Examples

### Running Long-Running Data Processing Job

```python
from app_platform_sandbox import Sandbox
import time

sandbox = Sandbox.get_from_id(app_id="data-processing-id")

# Upload processing script
sandbox.filesystem.write_file("/app/process.py", '''
import time
for batch in range(100):
    print(f"Batch {batch+1}/100 - processed: {(batch+1)*1000} records")
    time.sleep(2)  # Simulate processing
print("Processing complete!")
''')

# Launch processing in background
print("Starting data processing...")
pid = sandbox.launch_process(
    command="python process.py",
    cwd="/app"
)
print(f"Processing running with PID: {pid}")

# Monitor progress
print("\nMonitoring progress...")
for i in range(5):
    time.sleep(10)

    output = sandbox.process_manager.get_output(pid)
    lines = output.strip().split('\n')
    if lines:
        print(f"Latest: {lines[-1]}")

    if not sandbox.process_manager.is_running(pid):
        print("\nProcessing finished!")
        break

# Get final output
final_output = sandbox.process_manager.get_output(pid)
print(f"\nFinal output:\n{final_output}")
```

**Output:**

```
Starting data processing...
Processing running with PID: 12345

Monitoring progress...
Latest: Batch 5/100 - processed: 5000 records
Latest: Batch 10/100 - processed: 10000 records
Latest: Batch 15/100 - processed: 15000 records
...
Processing finished!

Final output:
Batch 1/100 - processed: 1000 records
Batch 2/100 - processed: 2000 records
...
Processing complete!
```

### Running a Background Worker

```python
from app_platform_sandbox import Sandbox
import time

sandbox = Sandbox.get_from_id(app_id="worker-sandbox-id")

# Create a background worker that polls a queue
sandbox.filesystem.write_file("/app/worker.py", '''
import time
import json
import os

queue_file = "/tmp/task_queue.json"
results_file = "/tmp/results.json"

def process_task(task):
    """Simulate processing a task."""
    time.sleep(1)  # Simulate work
    return {"task_id": task["id"], "status": "completed", "result": task["data"] * 2}

print("Worker started, polling for tasks...")
processed = 0

while True:
    # Check for tasks
    if os.path.exists(queue_file):
        with open(queue_file) as f:
            tasks = json.load(f)

        if tasks:
            task = tasks.pop(0)
            print(f"Processing task {task['id']}...")
            result = process_task(task)

            # Save result
            results = []
            if os.path.exists(results_file):
                with open(results_file) as f:
                    results = json.load(f)
            results.append(result)
            with open(results_file, "w") as f:
                json.dump(results, f)

            # Update queue
            with open(queue_file, "w") as f:
                json.dump(tasks, f)

            processed += 1
            print(f"Task {task['id']} completed. Total processed: {processed}")

    time.sleep(2)  # Poll interval
''')

# Start worker in background
pid = sandbox.launch_process("python /app/worker.py")
print(f"Worker started with PID: {pid}")

# Wait for worker to initialize
time.sleep(3)

# Verify it's running
procs = sandbox.list_processes(pattern="worker.py")
if procs:
    print("Worker is running!")
```

### Data Processing Pipeline with Progress

```python
from app_platform_sandbox import Sandbox
import time

sandbox = Sandbox.get_from_id(app_id="data-pipeline-id")

# Create processing script
sandbox.filesystem.write_file("/app/process.py", '''
import time
import sys

total_records = 1000000

for i in range(0, total_records, 100000):
    # Simulate processing
    time.sleep(2)
    progress = (i + 100000) / total_records * 100
    print(f"Processed {i+100000:,} records ({progress:.0f}%)")
    sys.stdout.flush()

print("Processing complete!")
''')

# Launch processing
pid = sandbox.launch_process("python /app/process.py")
print(f"Processing started (PID: {pid})")

# Monitor until complete
while True:
    time.sleep(5)

    if not sandbox.process_manager.is_running(pid):
        break

    output = sandbox.process_manager.get_output(pid)
    lines = output.strip().split('\n')
    if lines:
        print(f"Status: {lines[-1]}")

print("\nFinal results:")
print(sandbox.process_manager.get_output(pid))
```

### Multiple Background Jobs

```python
from app_platform_sandbox import Sandbox
import time

sandbox = Sandbox.get_from_id(app_id="multi-job-id")

# Launch multiple jobs
jobs = []

# Job 1: Data preprocessing
pid1 = sandbox.launch_process("python preprocess.py", cwd="/app")
jobs.append(("Preprocessing", pid1))

# Job 2: Data transformation
pid2 = sandbox.launch_process("python transform.py", cwd="/app")
jobs.append(("Transformation", pid2))

# Job 3: Data validation
pid3 = sandbox.launch_process("python validate.py", cwd="/app")
jobs.append(("Validation", pid3))

print("Launched jobs:")
for name, pid in jobs:
    print(f"  {name}: PID {pid}")

# Monitor all jobs
while jobs:
    time.sleep(10)

    for name, pid in jobs[:]:  # Copy list to allow modification
        if not sandbox.process_manager.is_running(pid):
            output = sandbox.process_manager.get_output(pid)
            print(f"\n{name} (PID {pid}) completed:")
            print(output[-500:] if len(output) > 500 else output)  # Last 500 chars
            jobs.remove((name, pid))

    remaining = [name for name, _ in jobs]
    if remaining:
        print(f"Still running: {', '.join(remaining)}")

print("\nAll jobs complete!")
```

### Graceful Shutdown

```python
from app_platform_sandbox import Sandbox
import signal
import time

sandbox = Sandbox.get_from_id(app_id="server-id")

# Start a process that handles SIGTERM gracefully
sandbox.filesystem.write_file("/app/worker.py", '''
import signal
import time
import sys

running = True

def handle_shutdown(signum, frame):
    global running
    print("Received shutdown signal, cleaning up...")
    running = False

signal.signal(signal.SIGTERM, handle_shutdown)

print("Worker started")
while running:
    print("Working...")
    time.sleep(2)

print("Worker shut down gracefully")
''')

# Start worker
pid = sandbox.launch_process("python /app/worker.py")
print(f"Worker started: {pid}")

time.sleep(10)

# Graceful shutdown
print("Sending SIGTERM...")
sandbox.process_manager.kill(pid, signal=signal.SIGTERM)

time.sleep(3)

# Get final output
output = sandbox.process_manager.get_output(pid)
print(f"Output:\n{output}")
```

## CLI Usage

The CLI doesn't have direct background process commands, but you can use exec:

```bash
# Start a background process using nohup
sandbox exec my-sandbox "nohup python train.py > /tmp/train.log 2>&1 &"

# Check running processes
sandbox exec my-sandbox "ps aux | grep python"

# View logs
sandbox exec my-sandbox "tail -f /tmp/train.log"

# Kill a process
sandbox exec my-sandbox "kill 12345"
```

## Best Practices

1. **Use meaningful log files**: Redirect output to named log files for easier debugging
2. **Handle signals**: Implement SIGTERM handlers for graceful shutdown
3. **Monitor regularly**: Poll process status for long-running jobs
4. **Clean up**: Kill orphaned processes when done
5. **Set timeouts**: Use `wait_for()` with reasonable timeouts

## Error Handling

```python
from app_platform_sandbox.exceptions import CommandExecutionError

try:
    pid = sandbox.launch_process("python nonexistent.py")
except CommandExecutionError as e:
    print(f"Failed to launch: {e}")

# Check if process exists before operations
processes = sandbox.list_processes()
pids = [p.pid for p in processes]

if target_pid in pids:
    sandbox.kill_process(target_pid)
else:
    print(f"Process {target_pid} not found")
```

## Next Steps

- [Run Commands](sandbox_runcommands.md) - Execute one-off commands
- [File Operations](sandbox_fileops.md) - Upload scripts and download results
- [Large File Transfers](sandbox_large_files.md) - Handle large model files and datasets
