# File Operations

Upload, download, and manage files in your sandbox. The filesystem API provides a familiar interface for all file operations.

## Accessing the Filesystem

Access file operations through the `filesystem` property:

**Sync:**

```python
from app_platform_sandbox import Sandbox

sandbox = Sandbox.get_from_id(app_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

# Access filesystem
fs = sandbox.filesystem
```

**Async:**

```python
from app_platform_sandbox import AsyncSandbox

sandbox = await AsyncSandbox.get_from_id(app_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")

# Access async filesystem
fs = sandbox.filesystem
```

## Reading Files

### Read Text Files

**Sync:**

```python
# Read a text file
content = sandbox.filesystem.read_file("/etc/hostname")
print(content)
```

**Async:**

```python
content = await sandbox.filesystem.read_file("/etc/hostname")
print(content)
```

### Read Binary Files

```python
# Read binary file (e.g., image, model weights)
data = sandbox.filesystem.read_file("/app/model.bin", binary=True)
print(f"Read {len(data)} bytes")
```

### Example: Read Configuration

```python
import json

# Read JSON config
config_str = sandbox.filesystem.read_file("/app/config.json")
config = json.loads(config_str)
print(f"Database: {config['database']}")
```

## Writing Files

### Write Text Files

**Sync:**

```python
# Write a text file
sandbox.filesystem.write_file(
    "/app/hello.txt",
    "Hello, World!\nThis is a test file."
)
```

**Async:**

```python
await sandbox.filesystem.write_file(
    "/app/hello.txt",
    "Hello from async!"
)
```

### Write Binary Files

```python
# Write binary data
binary_data = b'\x00\x01\x02\x03\x04'
sandbox.filesystem.write_file("/app/data.bin", binary_data, binary=True)
```

### Append to Files

```python
# Append content to existing file
sandbox.filesystem.append_file("/app/log.txt", "New log entry\n")
sandbox.filesystem.append_file("/app/log.txt", "Another entry\n")
```

### Example: Create Python Script

```python
sandbox.filesystem.write_file("/app/process.py", '''
import sys
import json

data = json.load(sys.stdin)
result = {"processed": len(data), "status": "complete"}
print(json.dumps(result))
''')

# Run the script
result = sandbox.exec("echo '[1,2,3]' | python /app/process.py")
print(result.stdout)  # Output: {"processed": 3, "status": "complete"}
```

## Uploading Files

### Upload from Local Machine

Transfer a file from your local machine to the sandbox:

**Sync:**

```python
# Upload a local file
sandbox.filesystem.upload_file(
    local_path="/path/to/local/data.csv",
    remote_path="/app/data.csv"
)
print("File uploaded")
```

**Async:**

```python
await sandbox.filesystem.upload_file(
    local_path="/path/to/local/script.py",
    remote_path="/app/script.py"
)
```

### Example: Upload Dataset and Process

```python
from app_platform_sandbox import Sandbox

sandbox = Sandbox.get_from_id(app_id="data-sandbox-id")

# Upload dataset
sandbox.filesystem.upload_file(
    local_path="./datasets/training_data.csv",
    remote_path="/data/training.csv"
)

# Process it
result = sandbox.exec('''
python -c "
import pandas as pd
df = pd.read_csv('/data/training.csv')
print(f'Loaded {len(df)} rows with columns: {list(df.columns)}')
"
''')
print(result.stdout)
```

### Example: Upload Model Weights

```python
# Upload pre-trained model weights
sandbox.filesystem.upload_file(
    local_path="./models/bert-weights.bin",
    remote_path="/models/bert-weights.bin"
)

# Verify upload
result = sandbox.exec("ls -lh /models/")
print(result.stdout)
```

## Downloading Files

### Download to Local Machine

Transfer a file from the sandbox to your local machine:

**Sync:**

```python
# Download a file
sandbox.filesystem.download_file(
    remote_path="/app/results.json",
    local_path="./output/results.json"
)
print("File downloaded")
```

**Async:**

```python
await sandbox.filesystem.download_file(
    remote_path="/app/output.csv",
    local_path="./downloads/output.csv"
)
```

### Example: Process and Download Results

```python
from app_platform_sandbox import Sandbox

sandbox = Sandbox.get_from_id(
    app_id="ml-sandbox-id",
    registry="your-registry-name"
)

# Run processing
result = sandbox.exec('''
python -c "
import json
results = {'accuracy': 0.95, 'loss': 0.05, 'epochs': 10}
with open('/app/metrics.json', 'w') as f:
    json.dump(results, f)
print('Metrics saved')
"
''')

# Download results
sandbox.filesystem.download_file(
    remote_path="/app/metrics.json",
    local_path="./results/metrics.json"
)

# Read locally
import json
with open("./results/metrics.json") as f:
    metrics = json.load(f)
print(f"Accuracy: {metrics['accuracy']}")
```

## Directory Operations

### Create Directories

**Sync:**

```python
# Create a single directory
sandbox.filesystem.mkdir("/app/output")

# Create nested directories (recursive)
sandbox.filesystem.mkdir("/app/data/processed/2024", recursive=True)
```

**Async:**

```python
await sandbox.filesystem.mkdir("/workspace/models", recursive=True)
```

### List Directory Contents

**Sync:**

```python
# List directory contents
files = sandbox.filesystem.list_dir("/app")

for f in files:
    file_type = "DIR" if f.is_dir else "FILE"
    size = f.size if f.size else "-"
    print(f"{file_type}  {size:>10}  {f.name}")
```

**Async:**

```python
files = await sandbox.filesystem.list_dir("/app")
for f in files:
    print(f.name)
```

**Output:**

```
DIR           -  data
DIR           -  output
FILE       1024  config.json
FILE       4096  main.py
```

### Remove Files and Directories

**Sync:**

```python
# Remove a file
sandbox.filesystem.rm("/app/temp.txt")

# Remove a directory (must be empty)
sandbox.filesystem.rm("/app/empty_dir")

# Remove directory and contents (recursive)
sandbox.filesystem.rm("/app/old_data", recursive=True)

# Force remove (ignore errors if not exists)
sandbox.filesystem.rm("/app/maybe_exists.txt", force=True)
```

**Async:**

```python
await sandbox.filesystem.rm("/tmp/cache", recursive=True, force=True)
```

## File Metadata

### Check If Path Exists

```python
if sandbox.filesystem.exists("/app/config.json"):
    print("Config file found")
else:
    print("Config not found, using defaults")
```

### Check File Type

```python
path = "/app/data"

if sandbox.filesystem.is_dir(path):
    print(f"{path} is a directory")
elif sandbox.filesystem.is_file(path):
    print(f"{path} is a file")
else:
    print(f"{path} does not exist")
```

### Get File Size

```python
size = sandbox.filesystem.get_size("/app/model.bin")
print(f"Model size: {size} bytes ({size / 1024 / 1024:.2f} MB)")
```

### Change Permissions

```python
# Make a script executable
sandbox.filesystem.chmod("/app/run.sh", "755")

# Restrict access
sandbox.filesystem.chmod("/app/secrets.txt", "600")
```

## Copy and Move Files

### Copy Files

**Sync:**

```python
# Copy a single file
sandbox.filesystem.copy("/app/config.json", "/app/config.backup.json")

# Copy a directory (recursive)
sandbox.filesystem.copy("/app/data", "/backup/data", recursive=True)
```

**Async:**

```python
await sandbox.filesystem.copy("/app/template.py", "/app/main.py")
```

### Move Files

```python
# Move/rename a file
sandbox.filesystem.move("/app/old_name.py", "/app/new_name.py")

# Move to different directory
sandbox.filesystem.move("/tmp/results.csv", "/app/output/results.csv")
```

## Large Files (5MB+)

For files 5MB or larger, use Spaces integration for efficient transfers:

```python
# Check if Spaces is configured
if sandbox.filesystem.has_spaces:
    # Use large file methods
    sandbox.filesystem.upload_large(
        local_path="./large_model.bin",
        remote_path="/models/large_model.bin"
    )
else:
    print("Configure Spaces for large file transfers")
```

See [Large File Transfers](sandbox_large_files.md) for complete documentation on Spaces integration.

## Examples

### Upload Dataset, Process, Download Results

```python
from app_platform_sandbox import Sandbox

sandbox = Sandbox.get_from_id(app_id="data-pipeline-id")

# Setup
sandbox.filesystem.mkdir("/pipeline/input", recursive=True)
sandbox.filesystem.mkdir("/pipeline/output")

# Upload input data
sandbox.filesystem.upload_file(
    local_path="./raw_data.csv",
    remote_path="/pipeline/input/raw.csv"
)

# Write processing script
sandbox.filesystem.write_file("/pipeline/process.py", '''
import pandas as pd

# Load data
df = pd.read_csv('/pipeline/input/raw.csv')

# Process: filter, transform, aggregate
df_clean = df.dropna()
df_clean['processed'] = True

# Save results
df_clean.to_csv('/pipeline/output/processed.csv', index=False)
print(f"Processed {len(df_clean)} rows")
''')

# Run processing
result = sandbox.exec("pip install pandas && python /pipeline/process.py")
print(result.stdout)

# Download results
sandbox.filesystem.download_file(
    remote_path="/pipeline/output/processed.csv",
    local_path="./processed_data.csv"
)
print("Pipeline complete!")
```

### Upload Config Files for Execution

```python
import json
from app_platform_sandbox import Sandbox

sandbox = Sandbox.get_from_id(app_id="ml-inference-id")

# Upload model configuration
config = {
    "model_name": "bert-base-uncased",
    "max_length": 512,
    "batch_size": 16,
    "device": "cpu"
}
sandbox.filesystem.write_file(
    "/app/config.json",
    json.dumps(config, indent=2)
)

# Upload inference script
sandbox.filesystem.upload_file(
    local_path="./inference.py",
    remote_path="/app/inference.py"
)

# Upload test data
sandbox.filesystem.upload_file(
    local_path="./test_inputs.json",
    remote_path="/app/inputs.json"
)

# Run inference
result = sandbox.exec(
    "python inference.py --config config.json --input inputs.json",
    cwd="/app"
)
print(result.stdout)
```

### Binary File Handling

```python
# Read a binary file (e.g., image)
image_data = sandbox.filesystem.read_file("/app/image.png", binary=True)
print(f"Image size: {len(image_data)} bytes")

# Write binary data
import struct
binary_data = struct.pack('fff', 1.0, 2.0, 3.0)  # 3 floats
sandbox.filesystem.write_file("/app/data.bin", binary_data, binary=True)

# Verify
result = sandbox.exec("xxd /app/data.bin | head -1")
print(result.stdout)
```

## Error Handling

```python
from app_platform_sandbox.exceptions import FileOperationError

try:
    content = sandbox.filesystem.read_file("/nonexistent/file.txt")
except FileOperationError as e:
    print(f"File operation failed: {e}")

# Safe file check
if sandbox.filesystem.exists("/app/data.csv"):
    data = sandbox.filesystem.read_file("/app/data.csv")
else:
    print("File not found, creating default...")
    sandbox.filesystem.write_file("/app/data.csv", "col1,col2\n")
```

## Next Steps

- [Large File Transfers](sandbox_large_files.md) - Handle files 5MB+ using DigitalOcean Spaces
- [Background Processes](sandbox_processes.md) - Run long-running jobs in the background
- [Run Commands](sandbox_runcommands.md) - Execute commands with the uploaded files
