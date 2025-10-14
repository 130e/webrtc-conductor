import asyncio
import asyncssh
import os
import json
import argparse
import time
import yaml

LOCAL_CMD = "./peerconnection_client --server={signal_server} --port={signal_port} --autoconnect --autocall --config={config} 2>local_last_run.log"
REMOTE_CMD = '{remote_base}/peerconnection_client --server={signal_server} --port={signal_port} --autoconnect --force_fieldtrials="WebRTC-DecoderDataDumpDirectory/{masked_dump_dir}/"'


async def restart_signal_server(remote_host, remote_base_dir, signal_server_port):
    try:
        async with asyncssh.connect(remote_host) as conn:
            restart_cmd = f"{remote_base_dir}/restart_signal_server.sh {remote_base_dir} {signal_server_port}"
            restart_result = await conn.run(restart_cmd, check=False)
            print(restart_result.stdout, restart_result.stderr)
            return restart_result.exit_status
    except Exception as e:
        print(f"Error: asyncio run failed: {e}")
        await asyncio.sleep(2)
        return 1


async def run_one_pc(
    remote_host,
    remote_base_dir,
    signal_server,
    signal_port,
    local_config,
    local_env_vars,
    remote_env_vars,
    remote_output,
    collect_output,
):
    try:
        async with asyncssh.connect(remote_host) as conn:
            masked_output_dir = os.path.dirname(remote_output).replace("/", ";")
            rtc_log = remote_output.replace(".ivf", ".rtc.log")
            remote_cmd = REMOTE_CMD.format(
                remote_base=remote_base_dir,
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

            cleanup_cmd = f"{remote_base_dir}/recv_cleanup.sh {os.path.dirname(remote_output)} {remote_output}"
            result = await conn.run(cleanup_cmd, check=False)
            if result.exit_status != 0:
                print(f"=== Cleanup error: {result.stderr}")
            else:
                print("===", result.stdout)
                if collect_output:
                    log_path = remote_output.replace(".ivf", ".rtc.log")
                    print(f"=== Collecting output: {remote_output}, {log_path}")
                    async with conn.start_sftp_client() as sftp:
                        os.makedirs(os.path.dirname(remote_output), exist_ok=True)
                        sftp_video = await sftp.get(remote_output, remote_output)
                        sftp_log = await sftp.get(log_path, log_path)
                        if sftp_video.exit_status != 0 or sftp_log.exit_status != 0:
                            print(
                                f"=== SFTP error: {sftp_video.stderr}, {sftp_log.stderr}"
                            )

            return local_ret or remote_result.exit_status or result.exit_status

    except Exception as e:
        print(f"\n=== Error: asyncio run failed: {e}")
        await asyncio.sleep(2)
        return 1


async def orchestrate(config):
    run_start_time = time.time()
    rtc_cfg = config["rtc_stream"]
    with open(rtc_cfg["videos"], "r") as f:
        video_lists = [line.strip() for line in f]

    print(f"=== {len(video_lists)} videos to run")

    local_display, remote_display = rtc_cfg["local_display"], rtc_cfg["remote_display"]
    local_env = os.environ.copy()
    local_env["DISPLAY"] = f":{local_display}"
    remote_env = {"DISPLAY": f":{remote_display}"}

    print(
        f"\n=== Starting up signal server at {rtc_cfg["signal_server"]}:{rtc_cfg["signal_port"]}"
    )
    await restart_signal_server(
        rtc_cfg["remote_host"], rtc_cfg["remote_base_dir"], rtc_cfg["signal_port"]
    )

    idx = rtc_cfg["start_idx"]
    delay = rtc_cfg["delay"]
    attempt = 0
    total_attempts = 0
    skipped = []

    file_start_time = time.time()
    while idx < len(video_lists):
        print(f"\n=== Test {idx}/{len(video_lists)}")
        video_id = video_lists[idx]
        video_config_file = os.path.join(
            config["rtc_input"]["dir"],
            config["source"]["dataset"],
            video_id.replace(config["source"]["video_suffix"], ".json"),
        )

        output_path = os.path.join(
            rtc_cfg["remote_base_dir"],
            rtc_cfg["dir"],
            config["source"]["dataset"],
            video_id.replace(config["source"]["video_suffix"], ".ivf"),
        )

        async_result = await run_one_pc(
            remote_host=rtc_cfg["remote_host"],
            remote_base_dir=rtc_cfg["remote_base_dir"],
            signal_server=rtc_cfg["signal_server"],
            signal_port=rtc_cfg["signal_port"],
            local_config=video_config_file,
            local_env_vars=local_env,
            remote_env_vars=remote_env,
            remote_output=output_path,
            collect_output=rtc_cfg["collect_output"],
        )

        if async_result != 0:
            attempt += 1
            total_attempts += 1
            if attempt > rtc_cfg["max_retry"]:
                print(f"[WARNING] Maximum retries reached - Skipping")
                skipped.append(video_id)
            else:
                # Retry
                print(f"[WARNING] Return code non-zero - Retrying {attempt} times")
                delay = round(delay * rtc_cfg["delay_factor"])
                await restart_signal_server(
                    rtc_cfg["remote_host"],
                    rtc_cfg["remote_base_dir"],
                    rtc_cfg["signal_port"],
                )
                print(
                    f"Signal server restarted {rtc_cfg["signal_server"]}:{rtc_cfg["signal_port"]}"
                )
                continue

        # Next file
        idx += 1
        attempt = 0
        delay = rtc_cfg["delay"]
        print(f"=== File time: {time.time() - file_start_time}s")
        file_start_time = time.time()

        print(f"\n>>> Waiting for {delay} seconds...")
        await asyncio.sleep(delay)
    # Done
    print("\n=== Orchestration Complete")
    print(
        f"=== Finished {len(video_lists) - rtc_cfg["start_idx"]}, retried {total_attempts} times"
    )
    print(f"=== Skipped: {len(skipped)} files: {skipped}")
    print(f"=== Total time: {time.time() - run_start_time} seconds")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate RTC input")
    parser.add_argument(
        "--config", "-c", type=str, required=True, help="Path to config file"
    )
    args = parser.parse_args()

    # Load configuration
    with open(args.config, "r") as f:
        config = yaml.safe_load(f)

    asyncio.run(orchestrate(config))
