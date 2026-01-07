# 40-Sandbox 1-Hour Stress Test Plan

> **Purpose**: Validate SandboxManager functionality with moderate scale
> **Scale**: 40 concurrent sandboxes (20 Python + 20 Node)
> **Duration**: 1 hour continuous operation
> **Users**: 16 simulated users

---

## Executive Summary

This plan defines a 1-hour stress test at moderate scale (40 sandboxes). This is a scaled-down version of the 500-sandbox 8-hour test, designed for quick validation and iterative development.

### Key Objectives

1. **Validate Core Functionality**: Acquire/release cycle works correctly
2. **Test Pool Behavior**: Pre-warmed pools reduce latency
3. **Verify Scale-Down**: Idle periods trigger proper cleanup
4. **Monitor Resource Usage**: No memory/FD leaks over 1 hour
5. **Measure Performance**: Pool hit rate, latency metrics

---

## Test Configuration

### Pool Settings

| Parameter | Python Pool | Node Pool |
|-----------|-------------|-----------|
| Target Ready | 5 | 5 |
| Max Sandboxes | 20 | 20 |
| Idle Timeout | 120s | 120s |
| Scale-Down Delay | 60s | 60s |
| Cooldown After Acquire | 180s | 180s |
| Max Warm Age | 1200s (20 min) | 1200s (20 min) |

### Global Settings

| Parameter | Value |
|-----------|-------|
| Max Total Sandboxes | 40 |
| Max Concurrent Creates | 10 |
| Metrics Interval | 10s |

### User Groups

| Group | Count | Image | Pattern | Task Duration |
|-------|-------|-------|---------|---------------|
| python_steady | 4 | Python | Steady | 2-5 min |
| python_burst | 4 | Python | Burst | 1-3 min |
| node_steady | 4 | Node | Steady | 2-5 min |
| node_burst | 4 | Node | Burst | 1-3 min |

### Idle Periods (Scale-Down Testing)

| Time | Duration | Purpose |
|------|----------|---------|
| 20 min | 5 min | First scale-down test |
| 40 min | 5 min | Second scale-down test |

---

## Success Criteria

### Hard Requirements (Must Pass)

- [ ] 100% uptime (no crashes or unhandled exceptions)
- [ ] >= 95% task success rate
- [ ] No memory growth > 20% from baseline
- [ ] Zero invariant violations (ready + creating + in_use = total)

### Soft Targets (Goal)

- [ ] >= 50% pool hit rate (warm sandboxes utilized)
- [ ] < 500ms average pool hit latency
- [ ] < 90s average cold start latency
- [ ] Successful scale-down during idle periods

---

## Running the Test

### Prerequisites

```bash
# Ensure DIGITALOCEAN_TOKEN is set
export DIGITALOCEAN_TOKEN=your_token_here

# Verify programs exist
uv run python -m tests.manager_stress --validate-programs
```

### Execute Test

```bash
# Run the 1-hour test
uv run python -m tests.manager_stress --scenario sandbox_40_1hr -v

# Or with custom output directory
uv run python -m tests.manager_stress --scenario sandbox_40_1hr -v --output-dir /path/to/output
```

### Monitor Progress

Watch the logs for:
- Pool metrics every 10 seconds
- User acquisitions and task completions
- Scale-down events during idle periods
- Any errors or warnings

---

## Expected Timeline

| Time | Phase | What Happens |
|------|-------|--------------|
| 0-5 min | Warm-Up | Sandboxes created, pools filling |
| 5-20 min | Steady State | Normal operation, all users active |
| 20-25 min | Idle Period 1 | Users pause, scale-down begins |
| 25-40 min | Recovery | Users resume, pools refill |
| 40-45 min | Idle Period 2 | Second scale-down test |
| 45-60 min | Final Phase | Normal operation until completion |

---

## Cost Estimate

- **Sandbox Cost**: 40 sandboxes x 1 hour x ~$0.02/hr = ~$0.80
- **API Calls**: Negligible
- **Total**: ~$0.80 per full test run

---

## Output Artifacts

After the test completes, find these files in `tests/artifacts/stress/`:

- `metrics_TIMESTAMP.csv` - Pool snapshots every 10s
- `system_TIMESTAMP.csv` - Memory, FD, asyncio metrics every 30s
- `tasks_TIMESTAMP.json` - Individual task results
- `summary_TIMESTAMP.json` - Aggregate statistics
- `report_TIMESTAMP.html` - Interactive dashboard

---

## Troubleshooting

### Common Issues

1. **"Pool empty for X, creating sandbox on-demand"**
   - Normal during initial warm-up phase
   - Should decrease as pools fill up

2. **High cold-start percentage**
   - Check if `target_ready` is too low
   - Verify `cooldown_after_acquire` isn't too long

3. **Test fails with < 95% success**
   - Check DO API rate limits
   - Review task errors in JSON output

4. **Memory growth detected**
   - Check for sandbox cleanup
   - Verify `manager.shutdown()` is called

---

## Comparison to 500-Sandbox Test

| Aspect | 40-Sandbox | 500-Sandbox |
|--------|------------|-------------|
| Duration | 1 hour | 8 hours |
| Sandboxes | 40 | 500 |
| Users | 16 | 200 |
| Cost | ~$0.80 | ~$240 |
| Corner Cases | Basic | Comprehensive |
| Leak Detection | Limited | Thorough |
