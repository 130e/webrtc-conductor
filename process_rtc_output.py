import argparse
import av
import os
import csv
from pathlib import Path
from typing import List
import re


def convert_path(path_str: str, keyword: str, new_prefix: str) -> str:
    path = Path(path_str)

    parts = path.parts
    try:
        idx = parts.index(keyword)
    except ValueError:
        raise ValueError(f"'{keyword}' not found in path")

    relative = Path(*parts[idx:])

    return str(Path(new_prefix) / relative)


def process_video(video: str, out_dir: str) -> List[str]:
    out_files = []
    container = av.open(video)

    for i, frame in enumerate(container.decode(video=0)):
        # Get actual resolution of this frame
        w, h = frame.width, frame.height

        # Build output filename (frame index + resolution)
        file_path = Path(video)
        basename = file_path.name.removesuffix("".join(file_path.suffixes))
        out_path = os.path.join(out_dir, f"{basename}_frames_{i:05d}_{w}x{h}.jpg")

        # Save as JPEG
        frame.to_image().save(out_path, format="JPEG")

        out_files.append(out_path)

    print(f"Done Extracted {i+1} frames to {out_dir}/")

    return out_files


def read_csv_data(csv_file_path):
    """Read and parse the RTC output CSV file."""
    data = []

    try:
        with open(csv_file_path, "r", newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Convert numeric fields to appropriate types
                processed_row = {
                    "frame_dump": row["frame_dump"],
                    "rtc_log": row["rtc_log"],
                    "test_duration_ms": int(row["test_duration_ms"]),
                    "original_video_width": int(row["original_video_width"]),
                    "original_video_height": int(row["original_video_height"]),
                    "original_video_fps": int(row["original_video_fps"]),
                    "original_video_duration_ms": int(
                        row["original_video_duration_ms"]
                    ),
                }
                data.append(processed_row)
    except FileNotFoundError:
        print(f"Error: CSV file '{csv_file_path}' not found.")
        return None
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return None

    return data


def parse_rtc_log(log_file: str, frames: List[str], out_file: str):
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
                        "ts": int(ts),
                        "First": int(first),
                        "Last": int(last),
                        "qp": int(qp),
                        "w": int(w),
                        "h": int(h),
                        "type": ftype,
                        "Assembled": assembled_frames.get(key, None),  # join if exists
                    }
                )

    # sort by timestamp
    decoded_frames.sort(key=lambda x: x["ts"])

    if len(decoded_frames) != len(frames):
        print(f"Error: rtc logs ({len(decoded_frames)}) and video frames ({len(frames)}) mismatch!")
        return 1

    with open(out_file, "w", newline="") as csvfile:
        fieldnames = [
            "ts",
            "First",
            "Last",
            "qp",
            "w",
            "h",
            "type",
            "EncodedBufsz",
            "NumPktExp",
            "NumPktRecv",
            "NumNack",
            "MaxNack",
            "File",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for i, frame in enumerate(decoded_frames):
            row = {
                "ts": frame["ts"],
                "First": frame["First"],
                "Last": frame["Last"],
                "qp": frame["qp"],
                "w": frame["w"],
                "h": frame["h"],
                "type": frame["type"],
                "EncodedBufsz": (
                    frame["Assembled"]["EncodedBufsz"] if frame["Assembled"] else ""
                ),
                "NumPktExp": (
                    frame["Assembled"]["NumPktExp"] if frame["Assembled"] else ""
                ),
                "NumPktRecv": (
                    frame["Assembled"]["NumPktRecv"] if frame["Assembled"] else ""
                ),
                "NumNack": frame["Assembled"]["NumNack"] if frame["Assembled"] else "",
                "MaxNack": frame["Assembled"]["MaxNack"] if frame["Assembled"] else "",
                "File": frames[i],
            }
            writer.writerow(row)

        print(
            f"Parsed {log_file}. Assmembled: {len(assembled_frames)}, Decoded: {len(decoded_frames)}, Recorded Frames: {i+1}"
        )
        return 0


def main():
    parser = argparse.ArgumentParser(description="Process RTC output")
    parser.add_argument(
        "--input", "-i", type=str, required=True, help="Path to the RTC output CSV file"
    )
    parser.add_argument("--dataset", "-d", type=str, required=True, help="Dataset name")
    args = parser.parse_args()

    # Read the CSV data
    csv_data = read_csv_data(args.input)

    if csv_data is None:
        return 1

    print(f"Successfully read {len(csv_data)} records from CSV file")

    output_base_dir = "./data/processed_rtc"

    for row in csv_data:
        print(f"Processing {row['frame_dump']}")

        output_dir = convert_path(
            os.path.dirname(row["frame_dump"]), args.dataset, output_base_dir
        )
        os.makedirs(output_dir, exist_ok=True)
        frame_files = process_video(row["frame_dump"], output_dir)

        output_csv = os.path.basename(row["rtc_log"]).replace(".rtc.log", ".csv")

        ret = parse_rtc_log(
            row["rtc_log"], frame_files, os.path.join(output_dir, output_csv)
        )
        if ret != 0:
            return 1

    return 0


if __name__ == "__main__":
    exit(main())
