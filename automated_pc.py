#!/usr/bin/env python3
import argparse
import os
import subprocess
from time import sleep
from typing import List
import json
import glob


def run_process(
    command_tokens: List[str], env_vars: dict = None, stderr_file: str = None
):
    cmd = list(command_tokens)
    print(f"\n=== Running: {' '.join(cmd)} ===")
    print(f"=== Command tokens: {cmd} ===")
    print(f"=== Environment: {env_vars} ===")
    if stderr_file:
        print(f"=== Stderr will be written to: {stderr_file} ===")
    # return 1

    # Prepare environment
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)

    try:
        # Handle stderr redirection - don't capture stderr if redirecting to file
        if stderr_file:
            with open(stderr_file, "w") as stderr_handle:
                result = subprocess.run(
                    cmd,
                    env=env,
                    stdout=subprocess.PIPE,  # Still capture stdout for debugging
                    stderr=stderr_handle,  # Redirect stderr to file
                    text=True,
                )
        else:
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)

        print(f"=== Return code: {result.returncode} ===")
        if result.stdout:
            print(f"=== STDOUT: {result.stdout} ===")
        if result.stderr and not stderr_file:
            print(f"=== STDERR: {result.stderr} ===")
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
    parser.add_argument("--signal_server", "-s", type=str, default="localhost")
    parser.add_argument("--mode", "-m", type=str, required=True)
    parser.add_argument("--display", "-d", type=str, default="1")
    args = parser.parse_args()

    with open(args.configs, "r") as f:
        config_files = f.readlines()

        env_vars = {"DISPLAY": f":{args.display}"}
        for idx, config_file in enumerate(config_files):
            config_file = config_file.strip()

            if args.mode == "send":
                stderr_file = "/dev/null"
                cmd_tokens = [
                    args.executable,
                    f"--server={args.signal_server}",
                    "--port=8888",
                    "--autoconnect",
                    "--autocall",
                    "--config",
                    config_file,
                ]

            elif args.mode == "dump":
                config = json.load(open(config_file))
                output_path = config["VideoPath"].replace("rtc_input", "rtc_output")

                output_dir = os.path.dirname(output_path)
                os.makedirs(output_dir, exist_ok=True)
                output_dir = os.path.abspath(output_dir)
                masked_output_dir = output_dir.replace("/", ";")

                output_video = output_path.replace(".yuv", ".ivf")

                stderr_file = output_path.replace(".yuv", ".rtc.log")

                cmd_tokens = [
                    args.executable,
                    f"--server={args.signal_server}",
                    "--port=8888",
                    "--autoconnect",
                    f"--force_fieldtrials=WebRTC-DecoderDataDumpDirectory/{masked_output_dir}/",
                ]

            return_code = run_process(cmd_tokens, env_vars, stderr_file)
            if return_code != 0:
                print(f"Process exited with code {return_code}")
                break

            if args.mode == "send":
                sleep(2)
            elif args.mode == "dump":
                attempts = 0
                # Rename dump file created by webrtc
                while True:
                    ivf_pattern = os.path.join(
                        output_dir, "webrtc_receive_stream_*.ivf"
                    )
                    ivf_files = glob.glob(ivf_pattern)

                    if len(ivf_files) == 0:
                        print(
                            "No IVF files found matching pattern webrtc_receive_stream_*.ivf"
                        )
                        attempts += 1
                        if attempts > 3:
                            raise TimeoutError(
                                "Timeout waiting for IVF file to be created"
                            )
                        sleep(2)
                    elif len(ivf_files) > 1:
                        raise ValueError(
                            f"Multiple IVF files found ({len(ivf_files)}): {ivf_files}. Cannot determine which one to rename."
                        )
                    else:
                        source_file = ivf_files[0]
                        os.rename(source_file, output_video)
                        print(f"Renamed {source_file} to {output_video}")
                        break


if __name__ == "__main__":
    exit(main())
