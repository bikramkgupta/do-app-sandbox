#!/usr/bin/env python3
"""
Test for WebSocket connection stability and throughput.

This test creates a single sandbox and issues commands continuously for a specified duration.
It measures:
- Connection stability (failures)
- Throughput (commands per second)
- Latency (avg time per command)
"""

import argparse
import os
import sys
import time
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from do_app_sandbox import Sandbox


def main():
    parser = argparse.ArgumentParser(description="Test WebSocket connection stability.")
    parser.add_argument("--image", default="python", help="Sandbox image to use")
    parser.add_argument("--duration", type=int, default=300, help="Test duration in seconds (default: 300)")
    parser.add_argument("--region", default="syd1", help="Region to create sandbox in")
    parser.add_argument("--command", default="echo test", help="Command to execute repeatedly")
    args = parser.parse_args()

    print("Starting Connection Stability Test")
    print(f"  Image: {args.image}")
    print(f"  Duration: {args.duration}s")
    print(f"  Region: {args.region}")
    print(f"  Command: {args.command}")
    print("-" * 60)

    sandbox = None
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Creating sandbox...")
        start_create = time.time()
        sandbox = Sandbox.create(image=args.image, region=args.region, wait_ready=True, timeout=300)
        create_time = time.time() - start_create
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Sandbox created in {create_time:.1f}s: {sandbox.app_id}")

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting command loop for {args.duration}s...")

        start_test = time.time()
        end_time = start_test + args.duration

        total_commands = 0
        success_count = 0
        failure_count = 0
        latencies = []

        while time.time() < end_time:
            cmd_start = time.time()
            try:
                result = sandbox.exec(args.command)
                cmd_duration = time.time() - cmd_start
                latencies.append(cmd_duration)

                if result.success:
                    success_count += 1
                else:
                    failure_count += 1
                    print(f"Command failed: {result.stderr}")
            except Exception as e:
                print(f"Execution exception: {e}")
                failure_count += 1

            total_commands += 1

            # Print progress every 10 seconds or 100 commands
            if total_commands % 100 == 0:
                elapsed = time.time() - start_test
                rate = total_commands / elapsed
                print(
                    f"  Progress: {total_commands} cmds | {elapsed:.1f}s | {rate:.1f} cmd/s | Failures: {failure_count}"
                )

        total_time = time.time() - start_test
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        throughput = total_commands / total_time if total_time > 0 else 0

        print("-" * 60)
        print("RESULTS")
        print("-" * 60)
        print(f"Total Duration: {total_time:.1f}s")
        print(f"Total Commands: {total_commands}")
        print(f"Successful:     {success_count} ({success_count / total_commands * 100:.1f}%)")
        print(f"Failed:         {failure_count} ({failure_count / total_commands * 100:.1f}%)")
        print(f"Throughput:     {throughput:.1f} cmds/sec")
        print(f"Avg Latency:    {avg_latency * 1000:.1f} ms")
        print(f"Min Latency:    {min(latencies) * 1000:.1f} ms" if latencies else "Min Latency: N/A")
        print(f"Max Latency:    {max(latencies) * 1000:.1f} ms" if latencies else "Max Latency: N/A")

        if failure_count == 0:
            print("\nSTATUS: PASS")
        else:
            print("\nSTATUS: FAIL (failures detected)")

    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        import traceback

        traceback.print_exc()
    finally:
        if sandbox:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Deleting sandbox...")
            sandbox.delete()
            print("Sandbox deleted.")


if __name__ == "__main__":
    main()
