#!/usr/bin/env python3
import argparse
import os
import shlex
import subprocess
import sys
from time import sleep
from typing import List
import json


def run_process(command_tokens: List[str]):
    cmd = list(command_tokens)
    print(f"\n=== Running: {' '.join(cmd)} ===")
    return 1
    try:
        result = subprocess.run(cmd)
        return result.returncode
    except FileNotFoundError:
        print(f"Error: Executable not found: {command_tokens[0]}")
        return 127
    except KeyboardInterrupt:
        print("Interrupted by user.")
        return 130
    except Exception as e:
        print(f"Error: {e}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Automated PC")
    parser.add_argument("--configs", "-c", type=str, required=True)
    parser.add_argument(
        "--executable", "-e", type=str, default="./peerconnection_client"
    )
    parser.add_argument("--mode", "-m", type=str, required=True)
    parser.add_argument("--display", "-d", type=str, default="1")
    args = parser.parse_args()

    output_base_dir = "./data/rtc_output"

    with open(args.configs, "r") as f:
        config_files = f.readlines()

        for idx, config_file in enumerate(config_files):
            config_file = config_file.strip()
            
            if args.mode == "send":
                stderr_file = "/dev/null"
                cmd_tokens = [
                    f"DISPLAY=:{args.display}",
                    args.executable,
                    "--server=10.13.194.195",
                    "--port=8888",
                    "--autoconnect",
                    "--autocall",
                    "--config",
                    config_file,
                    f"2>{stderr_file}",
                ]

            elif args.mode == "dump":
                config = json.load(open(config_file))
                output_dir = (
                    config["VideoPath"]
                    .replace("rtc_input", "rtc_output")
                )
                output_dir = os.path.dirname(output_dir)
                os.makedirs(output_dir, exist_ok=True)
                output_dir = os.path.abspath(output_dir)
                output_dir = output_dir.replace("/", ";")

                stderr_file = (
                    config["VideoPath"]
                    .replace("rtc_input", "rtc_output")
                    .replace(".yuv", ".rtc.log")
                )

                cmd_tokens = [
                    f"DISPLAY=:{args.display}",
                    args.executable,
                    "--server=localhost",
                    "--port=8888",
                    "--autoconnect",
                    f'--force_fieldtrials="WebRTC-DecoderDataDumpDirectory/{output_dir}/"',
                    f"2>{stderr_file}",
                ]

            return_code = run_process(cmd_tokens)
            if return_code != 0:
                print(f"Process exited with code {return_code}")
                break


if __name__ == "__main__":
    exit(main())
