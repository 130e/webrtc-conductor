import asyncio
import asyncssh
import os
import json
import argparse
import time

REMOTE_HOST = "wifi-peer"
REMOTE_BASE = "/home/simmer/video-test/webrtc-conductor"

LOCAL_CMD = "./peerconnection_client --server={signal_server} --port={signal_port} --autoconnect --autocall --config={config} 2>local_last_run.log"
REMOTE_CMD = '{remote_base}/peerconnection_client --server={signal_server} --port={signal_port} --autoconnect --force_fieldtrials="WebRTC-DecoderDataDumpDirectory/{masked_dump_dir}/"'


async def restart_signal_server(signal_server_port):
    try:
        async with asyncssh.connect(REMOTE_HOST) as conn:
            restart_cmd = f"{REMOTE_BASE}/restart_signal_server.sh {REMOTE_BASE} {signal_server_port}"
            restart_result = await conn.run(restart_cmd, check=False)
            print(restart_result.stdout, restart_result.stderr)
            return restart_result.exit_status
    except Exception as e:
        print(f"Error: asyncio run failed: {e}")
        await asyncio.sleep(2)
        return 1


async def run_one_pc(
    signal_server,
    signal_port,
    local_config,
    local_env_vars,
    remote_env_vars,
    remote_output,
):
    try:
        async with asyncssh.connect(REMOTE_HOST) as conn:
            masked_output_dir = os.path.dirname(remote_output).replace("/", ";")
            rtc_log = remote_output.replace(".ivf", ".rtc.log")
            remote_cmd = REMOTE_CMD.format(
                remote_base=REMOTE_BASE,
                signal_server=signal_server,
                signal_port=signal_port,
                masked_dump_dir=masked_output_dir,
            )
            local_cmd = LOCAL_CMD.format(
                signal_server=signal_server,
                signal_port=signal_port,
                config=local_config,
            )
            print(f"\n=== Remote: {remote_cmd}")
            print(f"=== Local: {local_cmd}")

            remote_proc = await conn.create_process(
                f"bash -lc '{remote_cmd} 2>{rtc_log}'",
                env=remote_env_vars,
            )

            local_proc = await asyncio.create_subprocess_shell(
                local_cmd,
                env=local_env_vars,
            )
            local_ret = await local_proc.wait()
            remote_result = await remote_proc.wait()
            print(
                f"=== Clients return: local={local_ret}, remote={remote_result.exit_status}"
            )

            cleanup_cmd = f"{REMOTE_BASE}/recv_cleanup.sh {os.path.dirname(remote_output)} {remote_output}"
            result = await conn.run(cleanup_cmd, check=False)
            if result.exit_status != 0:
                print(f"=== Cleanup error: {result.stderr}")
            else:
                print("===", result.stdout)

            return local_ret or remote_result.exit_status or result.exit_status
    except Exception as e:
        print(f"\n=== Error: asyncio run failed: {e}")
        await asyncio.sleep(2)
        return 1


async def orchestrate(args):
    run_start_time = time.time()
    with open(args.config_list, "r") as f:
        config_files = [line.strip() for line in f]

    local_display, remote_display = args.display.split(",")
    local_env = os.environ.copy()
    local_env["DISPLAY"] = f":{local_display}"
    remote_env = {"DISPLAY": f":{remote_display}"}

    print(f"\n=== Starting up signal server at {args.signal_server}:{args.signal_port}")
    await restart_signal_server(args.signal_port)

    DEFAULT_DELAY = 8
    failed = 0
    idx = args.begin
    attempt = 0
    delay = DEFAULT_DELAY
    file_start_time = time.time()
    while idx < len(config_files):
        print(f"\n=== Test {idx}/{len(config_files)}")
        config_file = config_files[idx]
        config = json.load(open(config_file))

        output_path = os.path.normpath(
            config["VideoPath"].replace("rtc_input", "rtc_output")
        )
        output_path = os.path.join(REMOTE_BASE, output_path)
        output_path = output_path.replace(".yuv", ".ivf")

        async_result = await run_one_pc(
            signal_server=args.signal_server,
            signal_port=args.signal_port,
            local_config=config_file,
            local_env_vars=local_env,
            remote_env_vars=remote_env,
            remote_output=output_path,
        )
        if async_result != 0:
            attempt += 1
            failed += 1
            print(f"[WARNING] Return code non-zero - Retrying {attempt} times")
            print(
                f"Restarting signal server at {args.signal_server}:{args.signal_port}"
            )
            delay = round(min(delay * 1.15, 120))
            await restart_signal_server(args.signal_port)
        else:
            idx += 1
            attempt = 0
            delay = DEFAULT_DELAY
            print(f"=== File time: {time.time() - file_start_time}s")
            file_start_time = time.time()

        print(f"\n>>> Waiting for {delay} seconds...")
        await asyncio.sleep(delay)
    # Done
    print("\n=== Orchestration Complete")
    print(f"=== Finished {len(config_files) - args.begin}, retried {failed} times")
    print(f"=== Total time: {time.time() - run_start_time} seconds")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config_list", "-c", type=str, required=True)
    parser.add_argument("--signal_server", "-s", type=str, default="10.13.194.195")
    parser.add_argument("--signal_port", "-p", type=str, default="8880")
    parser.add_argument("--display", "-d", type=str, default="1,0")
    parser.add_argument("--begin", "-b", type=int, default=0)
    args = parser.parse_args()

    asyncio.run(orchestrate(args))
