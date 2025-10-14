#!/usr/bin/env python3

import argparse
import json
import os
from os import path
import subprocess
from typing import List, Dict, Any
import yaml


def find_files(dir: str, suffix: str) -> List[str]:
    results: List[str] = []
    for root, _, files in os.walk(dir):
        for filename in files:
            if filename.lower().endswith(suffix):
                file_path = os.path.join(root, filename)
                results.append(file_path)
    return results


def process_video(
    video_path: str,
    output_path: str,
    overwrite: bool,
    pixel_format: str,
    extra_duration_ms: int,
):
    output_path = os.path.normpath(output_path)

    # Convert video
    if not overwrite and os.path.exists(output_path):
        print(f"--> Overwrite set to false - skipping")
    else:
        cmd = [
            "ffmpeg",
            "-i",
            video_path,
            "-pix_fmt",
            pixel_format,
            "-y",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if result.returncode != 0:
            print(f"Error processing {video_path}: {result.stderr}")
            return ""

    # Generate config
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        video_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)

    # Find 1st video stream
    video_stream = None
    for stream in data["streams"]:
        if stream["codec_type"] == "video":
            video_stream = stream
            break

    if not video_stream:
        print(f"No video stream found for {video_path}")
        return ""

    # Extract duration from format
    duration = float(data["format"]["duration"])
    duration_ms = int(duration * 1000)

    # Generate config
    video_config = {
        "Width": video_stream["width"],
        "Height": video_stream["height"],
        "Fps": int(eval(video_stream["r_frame_rate"])),
        "OriginalDurationMS": duration_ms,
        "VideoPath": output_path,
        "DurationMS": duration_ms + extra_duration_ms,
    }

    return video_config


def main():
    parser = argparse.ArgumentParser(description="Generate RTC input")
    parser.add_argument(
        "--config", "-c", type=str, required=True, help="Path to config file"
    )
    args = parser.parse_args()

    # Load configuration
    with open(args.config, "r") as f:
        config = yaml.safe_load(f)

    # Process all files in the input directory
    video_files = find_files(
        path.join(config["source"]["dir"], config["source"]["dataset_name"]),
        config["source"]["video_suffix"],
    )
    print(f"Found {len(video_files)} files")

    video_files.sort()

    generated_videos = []

    for i, video in enumerate(video_files):
        # Example
        # video: Celeb-synthesis/Celeb-synthesis_00001.mp4
        # Actual path: Celeb-DF-v1/Celeb-synthesis/Celeb-synthesis_00001.mp4
        rel_path = os.path.relpath(video, start=config["source"]["dir"])
        rtc_input_video = os.path.join(config["rtc_input"]["dir"], rel_path)
        rtc_input_video = rtc_input_video.replace(
            config["source"]["video_suffix"], ".yuv"
        )
        os.makedirs(os.path.dirname(rtc_input_video), exist_ok=True)
        video_config = process_video(
            video,
            rtc_input_video,
            config["rtc_input"]["overwrite"],
            config["rtc_input"]["pixel_format"],
            config["rtc_input"]["duration_extension_ms"],
        )
        if not video_config:
            print(f"Error processing {video}")
            break
        video_config_path = rtc_input_video.replace(".yuv", ".json")
        with open(video_config_path, "w") as f:
            json.dump(video_config, f, indent=4)
            print(f"Processed {i+1}/{len(video_files)}: {video} -> {video_config_path}")

        video_id = os.path.relpath(rel_path, start=config["source"]["dataset_name"])

        generated_videos.append(video_id)

    # Log down the lists of videos generated
    with open(config["rtc_input"]["videos"], "w") as f:
        for video_id in generated_videos:
            f.write(video_id + "\n")
    print(f"Config list saved to {config["rtc_input"]["videos"]}")

    return 0


if __name__ == "__main__":
    exit(main())
