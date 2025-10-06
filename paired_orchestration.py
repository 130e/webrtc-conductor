import asyncio
import asyncssh
import os
import json
import argparse

REMOTE_HOST = "wifi-peer"
REMOTE_BASE = "/home/simmer/video-test/webrtc-conductor"

LOCAL_CMD = "./peerconnection_client --server={signal_server} --port={signal_port} --autoconnect --autocall --config={config} 2>local_last_run.log"
REMOTE_CMD = '{remote_base}/peerconnection_client --server={signal_server} --port={signal_port} --autoconnect --force_fieldtrials="WebRTC-DecoderDataDumpDirectory/{masked_dump_dir}/"'


async def restart_signal_server():
    try:
        async with asyncssh.connect(REMOTE_HOST) as conn:
            restart_cmd = f"{REMOTE_BASE}/restart_server.sh {REMOTE_BASE}"
            restart_result = await conn.run(restart_cmd, check=False)
            print(restart_result.stdout, restart_result.stderr)
            return restart_result.exit_status
    except Exception as e:
        print(f"Error: asyncio run failed: {e}")
        await asyncio.sleep(2)
        return 1

async def run_one_pc(
    signal_server, signal_port, local_config, local_env_vars, remote_env_vars, remote_output
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
            print(f"\n=== Remote: {remote_cmd} ===")
            print(f"=== Local: {local_cmd} ===\n")

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
            print(f"Done: local={local_ret}, remote={remote_result.exit_status}")

            cleanup_cmd = f"{REMOTE_BASE}/cleanup_ivf.sh {os.path.dirname(remote_output)} {remote_output}"
            result = await conn.run(cleanup_cmd, check=False)
            if result.exit_status != 0:
                print(f"Cleanup finished with error: {result.stderr}")
            else:
                print("Cleanup done: ", result.stdout)
            
            if local_ret or remote_result.exit_status or result:
                return 1
            else:
                return 0
    except Exception as e:
        print(f"Error: asyncio run failed: {e}")
        await asyncio.sleep(2)
        return 1

async def orchestrate(args):
    with open(args.config_list, "r") as f:
        config_files = [line.strip() for line in f]

    local_display,remote_display = args.display.split(",")
    local_env = os.environ.copy()
    local_env["DISPLAY"] = f":{local_display}"
    remote_env = {"DISPLAY": f":{remote_display}"}
    
    idx = 0
    while idx < len(config_files):
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
            # Retry
            print("Attempting retry...")
            await restart_signal_server()
            asyncio.sleep(5)
        else:
            idx += 1
        
        await asyncio.sleep(5)
            
        break


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config_list", "-c", type=str, required=True)
    parser.add_argument("--signal_server", "-s", type=str, default="10.13.194.195")
    parser.add_argument("--signal_port", "-p", type=str, default="8880")
    parser.add_argument("--display", "-d", type=str, default="1,0")
    args = parser.parse_args()

    asyncio.run(orchestrate(args))