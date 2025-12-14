## App Platform Commands (doctl)

### List apps
doctl apps list --format ID,Spec.Name

### Get app details
```
# Full app spec (YAML by default)
doctl apps get <app_id>

# JSON format (easier to parse)
doctl apps get <app_id> -o json

# Find component names (useful for logs)
doctl apps get <app_id> -o json | jq -r '.[0].spec.services[].name, .[0].spec.workers[].name, .[0].spec.jobs[].name'

# Find all "name" fields in the spec (comprehensive)
doctl apps get <app_id> -o json | jq -r '
  .[0] | paths as $p
  | ($p[-1] | tostring) as $key
  | select($key | test("name"; "i"))
  | select(($p | map(tostring) | join(".")) | test("active_deployment") | not)
  | "\($p | map(tostring) | join(".")) = \(getpath($p))"
'
```

### View logs
# Runtime logs (most recent, follow for real-time)
doctl apps logs <app_id> <component_name> --type run --follow

# Build logs
doctl apps logs <app_id> <component_name> --type build

# Deploy logs
doctl apps logs <app_id> <component_name> --type deploy

### Execute commands in running containers

For direct access to a running container's shell, use the remote exec tool:

```bash
# Using the doctl_remote_exec Python utility
cd doctl_remote_exec

# With uv
uv run python doctl_remote_exec.py <app-id> <component-name> "<command>"

# With virtualenv (first time setup)
python -m venv venv
source venv/bin/activate
pip install pexpect>=4.9.0

# Run command
python doctl_remote_exec.py <app-id> <component-name> "<command>"

# Examples
python doctl_remote_exec.py abc123... dev-workspace "ls -la /workspaces/app"
python doctl_remote_exec.py abc123... dev-workspace "cat /workspaces/app/package.json"
python doctl_remote_exec.py abc123... dev-workspace "ps aux | grep node"
```

**Use cases:**
- Inspect running processes
- Check file system state
- Verify environment variables: `env | grep GITHUB`
- Debug git sync: `cd /workspaces/app && git log -1`
- Check disk usage: `df -h`

**Note:** Requires Python 3.14+ and pexpect library. See `doctl_remote_exec/README.md` for details.

### Create new app
```
# Create app from spec file (app.yaml)
doctl apps create --spec app.yaml

### Update app

# Method 1: Trigger new deployment (pulls latest code from repo)
doctl apps create-deployment <app_id>
doctl apps create-deployment <app_id> --force-rebuild  # Force full rebuild

Note: If the app is configured to auto-update from github or container registry, then the above may be redundant.


# Method 2: Update app spec (preferred for config changes)
1. Get current spec: doctl apps get <app_id> > app.yaml, unless you already have the working/latest version
2. Edit app.yaml
3. Apply changes:

doctl apps update <app_id> --spec app.yaml
```

### Check if auto-deployment (deploy-on-push) from Git is enabled
```
doctl apps get cf26138c-fdee-436a-934c-f117841363c2 -o json | jq -r '
  .[0] | paths as $p
  | select(getpath($p) | type == "boolean")
  | select(($p[-1] | tostring) == "deploy_on_push")
  | select(($p | map(tostring) | join(".")) | test("active_deployment") | not)
  | "\($p | map(tostring) | join(".")) = \(getpath($p))"
'
```

### Monitor deployment progress
doctl apps get <app_id> -o json | jq -r '.[0].active_deployment.phase'

Phases are PENDING_BUILD, BUILDING, PENDING_DEPLOY, DEPLOYING, ACTIVE, ERROR, CANCELED


### Common workflow for debugging
1. List apps and get ID
2. Get component names from spec
3. Check deployment status
4. View build/deploy logs if not ACTIVE
5. View runtime logs for application errors
6. Update and redeploy if needed

### App Spec Reference
https://docs.digitalocean.com/products/app-platform/reference/app-spec/
