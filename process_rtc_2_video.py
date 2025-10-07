import argparse
import av
import os
import csv
from pathlib import Path
from typing import List
import re
import code
import json


# Legacy function
def parse_frames(video: str):
    frame_info = []
    container = av.open(video)
    for frame in container.decode(video=0):
        frame_info.append(
            [
                frame.time,
                frame.pts,
                frame.width,
                frame.height,
                frame.key_frame,
                frame.pict_type,
                frame.is_corrupt,
            ]
        )
    return frame_info


def parse_rtc_log(log_file: str):
    assembled_pattern = re.compile(
        r"AssembledFrame: First=(\d+) Last=(\d+) EncodedBufsz=(\d+) NumPktExp=(\d+) NumPktRecv=(\d+) NumNack=(\d+) MaxNack=(\d+)"
    )
    decoded_pattern = re.compile(
        r"Decoded frame: ts=(\d+) us First=(\d+) Last=(\d+) qp=(\d+) w=(\d+) h=(\d+) type=(\w+)"
    )

    assembled_frames = {}
    decoded_frames = []

    with open(log_file, "r") as f:
        for line in f:
            a_match = assembled_pattern.search(line)
            d_match = decoded_pattern.search(line)

            if a_match:
                first, last, encoded_bufsz, num_exp, num_recv, num_nack, max_nack = (
                    a_match.groups()
                )
                key = (int(first), int(last))
                # keep the last assembled frame info for this key
                assembled_frames[key] = {
                    "First": int(first),
                    "Last": int(last),
                    "EncodedBufsz": int(encoded_bufsz),
                    "NumPktExp": int(num_exp),
                    "NumPktRecv": int(num_recv),
                    "NumNack": int(num_nack),
                    "MaxNack": int(max_nack),
                }

            elif d_match:
                ts, first, last, qp, w, h, ftype = d_match.groups()
                key = (int(first), int(last))
                decoded_frames.append(
                    {
                        "RelativeTime": int(ts) / 1e6,
                        "ts": int(ts),
                        "First": int(first),
                        "Last": int(last),
                        "qp": int(qp),
                        "w": int(w),
                        "h": int(h),
                        "frameType": ftype,
                        # Defer join; logs may be out-of-order
                        "Assembled": None,
                    }
                )

    # sort by timestamp
    decoded_frames.sort(key=lambda x: x["ts"])

    first_frame_time = decoded_frames[0]["RelativeTime"]
    for frame in decoded_frames:
        frame["Assembled"] = assembled_frames.get((frame["First"], frame["Last"]), None)
        frame["RelativeTime"] = frame["RelativeTime"] - first_frame_time

    print(
        f"Parsed {log_file}. Assmembled: {len(assembled_frames)}, Decoded: {len(decoded_frames)}"
    )
    return decoded_frames, assembled_frames


def parse_frame_dump(video: str):
    container = av.open(video)
    if not container.streams.video:
        return []
    stream = container.streams.video[0]

    frames_info = []
    first_time = None
    dup_count = 0
    for packet in container.demux(stream):
        if packet.size == 0:
            continue
        frames = packet.decode()
        if len(frames) != 1:
            dup_count += 1
            continue
        t = float(packet.pts * stream.time_base)
        if first_time is None:
            first_time = t
        frames_info.append(
            {
                "RelativeTime": float(t - first_time),
                "time": float(t),
                "pts": packet.pts,
                "size": int(packet.size),
                "width": frames[0].width,
                "height": frames[0].height,
                "key_frame": frames[0].key_frame,
                "pict_type": frames[0].pict_type,
                "is_corrupt": frames[0].is_corrupt,
            }
        )
    if dup_count > 0:
        print(
            f"Warning: {dup_count} number of times multiple frames are decoded from the same packet"
        )

    return frames_info


def correlate_frames(frames_info, decoded_frames):
    correlated_frames = []
    unmatched_ivf = []
    unmatched_log = []

    def is_match(ivf_item, log_item):
        if log_item is None:
            return False
        assembled = log_item.get("Assembled")
        if assembled is None:
            return False
        return (
            ivf_item["width"] == log_item["w"]
            and ivf_item["height"] == log_item["h"]
            and ivf_item["size"] == assembled.get("EncodedBufsz")
        )

    i, j = 0, 0
    n, m = len(frames_info), len(decoded_frames)

    # Two-pointer with one-frame resync lookahead
    while i < n and j < m:
        # Skip log frames with no assembled info
        if decoded_frames[j].get("Assembled") is None:
            unmatched_log.append(
                {
                    "log_index": j,
                    "log": decoded_frames[j],
                    "reason": "extra_log_no_assembled",
                }
            )
            j += 1
            continue

        if is_match(frames_info[i], decoded_frames[j]):
            correlated_frames.append(
                {
                    "ivf_index": i,
                    "log_index": j,
                    "ivf": frames_info[i],
                    "log": decoded_frames[j],
                    "sync_error": "None",
                }
            )
            i += 1
            j += 1
            continue

        # Need resync
        sync_error = None
        # Try resync by skipping one IVF frame if next two align
        skip_ivf_realigns = (
            i + 1 < n
            and is_match(frames_info[i + 1], decoded_frames[j])
            and (
                i + 2 < n
                and j + 1 < m
                and is_match(frames_info[i + 2], decoded_frames[j + 1])
            )
        )
        if skip_ivf_realigns:
            sync_error = "extra_frame"
            unmatched_ivf.append(
                {"ivf_index": i, "ivf": frames_info[i], "reason": sync_error}
            )
            i += 1
            correlated_frames.append(
                {
                    "ivf_index": i,
                    "log_index": j,
                    "ivf": frames_info[i],
                    "log": {},
                    "sync_error": sync_error,
                }
            )
            continue

        # Try resync by skipping one Log frame if next two align
        # Don't add to correlated frames
        skip_log_realigns = (
            j + 1 < m
            and is_match(frames_info[i], decoded_frames[j + 1])
            and (
                i + 1 < n
                and j + 2 < m
                and is_match(frames_info[i + 1], decoded_frames[j + 2])
            )
        )
        if skip_log_realigns:
            sync_error = "extra_log"
            unmatched_log.append(
                {"log_index": j, "log": decoded_frames[j], "reason": sync_error}
            )
            j += 1
            continue

        # If still no alignment, mark both sides as a paired size mismatch and advance both
        sync_error = "mismatch"
        unmatched_ivf.append(
            {"ivf_index": i, "ivf": frames_info[i], "reason": sync_error}
        )
        unmatched_log.append(
            {"log_index": j, "log": decoded_frames[j], "reason": sync_error}
        )
        i += 1
        j += 1
        correlated_frames.append(
            {
                "ivf_index": i,
                "log_index": j,
                "ivf": frames_info[i],
                "log": decoded_frames[j],
                "sync_error": sync_error,
            }
        )

    # Any tails are unmatched
    while i < n:
        unmatched_ivf.append(
            {"ivf_index": i, "ivf": frames_info[i], "reason": "extra_ivf_tail"}
        )
        i += 1
        correlated_frames.append(
            {
                "ivf_index": i,
                "log_index": j,
                "ivf": frames_info[i],
                "log": decoded_frames[j],
                "sync_error": "extra_frame",
            }
        )
    while j < m:
        unmatched_log.append(
            {"log_index": j, "log": decoded_frames[j], "reason": "extra_log_tail"}
        )
        j += 1

    return {
        "correlated_frames": correlated_frames,
        "unmatched_ivf": unmatched_ivf,
        "unmatched_log": unmatched_log,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Align RTC log and video frames")
    parser.add_argument(
        "--config", "-c", type=str, required=True, help="Path to the video config"
    )
    args = parser.parse_args()

    with open(args.config, "r") as f:
        config = json.load(f)
        rtc_output_path = os.path.normpath(config["VideoPath"]).replace(
            "rtc_input", "rtc_output"
        )
        rtc_log_path = rtc_output_path.replace(".yuv", ".rtc.log")
        ivf_path = rtc_output_path.replace(".yuv", ".ivf")

        print(f"Processing {rtc_log_path} and {ivf_path}")

        log_decoded_frames, log_assembled_frames = parse_rtc_log(rtc_log_path)
        frames_info = parse_frame_dump(ivf_path)

        result = correlate_frames(frames_info, log_decoded_frames)

        print("\nCorrelation summary:")
        print(f"  IVF frames: {len(frames_info)}")
        print(f"  Log decoded frames: {len(log_decoded_frames)}")
        print(f"  Output frames: {len(result['correlated_frames'])}")

        # Breakdown unmatched by reason
        ivf_extra = sum(
            1
            for u in result["unmatched_ivf"]
            if u.get("reason") in ("extra_frame", "extra_frame_tail")
        )
        ivf_mismatch = sum(
            1 for u in result["unmatched_ivf"] if u.get("reason") == "mismatch"
        )
        log_extra = sum(
            1
            for u in result["unmatched_log"]
            if u.get("reason")
            in ("extra_log", "extra_log_tail", "extra_log_no_assembled")
        )
        log_mismatch = sum(
            1 for u in result["unmatched_log"] if u.get("reason") == "mismatch"
        )

        print(
            f"  Sync errors IVF frames: {len(result['unmatched_ivf'])} (extra={ivf_extra}, mismatch={ivf_mismatch})"
        )
        print(
            f"  Sync errors Log frames: {len(result['unmatched_log'])} (extra={log_extra}, mismatch={log_mismatch})"
        )

        # Save the results to a csv file
        output_csv = rtc_log_path.replace("rtc_output", "processed_rtc")
        output_csv = output_csv.replace(".rtc.log", ".csv")

        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_csv), exist_ok=True)

        with open(output_csv, "w", newline="") as f:
            writer = csv.writer(f)

            # Write header
            header = [
                "frame_index",
                "video_RelativeTime",
                "video_time",
                "video_pts",
                "video_size",
                "video_width",
                "video_height",
                "video_key_frame",
                "video_pict_type",
                "video_is_corrupt",
                "sync_error",
                "log_RelativeTime",
                "log_ts",
                "log_First",
                "log_Last",
                "log_qp",
                "log_w",
                "log_h",
                "log_frameType",
                "log_Assembled_First",
                "log_Assembled_Last",
                "log_Assembled_EncodedBufsz",
                "log_Assembled_NumPktExp",
                "log_Assembled_NumPktRecv",
                "log_Assembled_NumNack",
                "log_Assembled_MaxNack",
            ]
            writer.writerow(header)

            # Write data rows
            for idx, frame in enumerate(result["correlated_frames"]):
                ivf = frame["ivf"]
                log = frame["log"]

                # Handle empty log case (extra IVF frames)
                if not log:
                    assembled = {}
                    log_data = [None] * 8  # 8 log fields
                else:
                    assembled = log.get("Assembled", {})
                    log_data = [
                        log.get("RelativeTime"),
                        log.get("ts"),
                        log.get("First"),
                        log.get("Last"),
                        log.get("qp"),
                        log.get("w"),
                        log.get("h"),
                        log.get("frameType"),
                    ]

                row = (
                    [
                        idx,
                        ivf["RelativeTime"],
                        ivf["time"],
                        ivf["pts"],
                        ivf["size"],
                        ivf["width"],
                        ivf["height"],
                        ivf["key_frame"],
                        ivf["pict_type"],
                        ivf["is_corrupt"],
                        frame["sync_error"],
                    ]
                    + log_data
                    + [
                        assembled.get("First"),
                        assembled.get("Last"),
                        assembled.get("EncodedBufsz"),
                        assembled.get("NumPktExp"),
                        assembled.get("NumPktRecv"),
                        assembled.get("NumNack"),
                        assembled.get("MaxNack"),
                    ]
                )
                writer.writerow(row)

        print(f"Saved correlated frames to: {output_csv}")
