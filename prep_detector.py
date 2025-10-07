#!/usr/bin/env python3

import argparse
import os
import sys
import csv
from pathlib import Path
import av
from typing import List, Tuple, Dict, Any


def parse_csv_row(row: Dict[str, str]) -> Dict[str, Any]:
    """Parse a CSV row with proper typing based on the expected headers"""
    parsed_row = {}

    # String fields (keep as strings)
    string_fields = {
        "video_key_frame",
        "video_pict_type",
        "video_is_corrupt",
        "log_frameType",
    }

    # Integer fields
    int_fields = {
        "frame_index",
        "video_pts",
        "video_size",
        "video_width",
        "video_height",
        "log_ts",
        "log_First",
        "log_Last",
        "log_qp",
        "log_w",
        "log_h",
        "log_Assembled_First",
        "log_Assembled_Last",
        "log_Assembled_EncodedBufsz",
        "log_Assembled_NumPktExp",
        "log_Assembled_NumPktRecv",
        "log_Assembled_NumNack",
        "log_Assembled_MaxNack",
    }

    # Float fields (time units and numeric values)
    float_fields = {
        "video_RelativeTime",
        "video_time",
        "sync_error",
        "log_RelativeTime",
    }

    for key, value in row.items():
        if key in string_fields:
            parsed_row[key] = value
        elif key in int_fields:
            try:
                parsed_row[key] = int(value) if value and value != "None" else 0
            except (ValueError, TypeError):
                parsed_row[key] = 0
        elif key in float_fields:
            try:
                parsed_row[key] = float(value) if value and value != "None" else 0.0
            except (ValueError, TypeError):
                parsed_row[key] = 0.0
        else:
            # For any unexpected fields, keep as string
            parsed_row[key] = value

    return parsed_row


def adjust_dimensions_for_h264(width: int, height: int) -> Tuple[int, int]:
    """Adjust dimensions to be H.264 compatible (width multiple of 16, height multiple of 2)"""
    # Round width to nearest multiple of 16
    adjusted_width = ((width + 15) // 16) * 16

    # Round height to nearest multiple of 2
    adjusted_height = ((height + 1) // 2) * 2

    return adjusted_width, adjusted_height


def convert_path(path_str: str, keyword: str, new_prefix: str) -> str:
    path = Path(path_str)

    parts = path.parts
    try:
        idx = parts.index(keyword)
    except ValueError:
        raise ValueError(f"'{keyword}' not found in path")

    relative = Path(*parts[idx:])

    return str(Path(new_prefix) / relative)


def split_video(video_path: str, frame_ranges: List, output_video: str):
    try:
        container = av.open(video_path)
        frames = [frame for frame in container.decode(video=0)]
        container.close()
    except Exception as e:
        print(f"Error opening video file {video_path}: {e}")
        return

    output_videos = []
    print("Output video slices:")
    for fm_range in frame_ranges:
        begin, end = fm_range["begin"], fm_range["end"]
        fps = fm_range["fps"]
        width, height = fm_range["width"], fm_range["height"]

        output_video_path = output_video.replace(".mp4", f"_{begin}_{end}.mp4")

        # Adjust dimensions for H.264 compatibility
        adjusted_width, adjusted_height = adjust_dimensions_for_h264(width, height)

        try:
            output_container = av.open(output_video_path, mode="w")

            # Create libx264 stream
            out_stream = output_container.add_stream("libx264")
            out_stream.width = adjusted_width
            out_stream.height = adjusted_height
            out_stream.pix_fmt = "yuv420p"
            out_stream.rate = int(fps)

            # Minimal options to avoid codec issues
            out_stream.options = {"crf": "23"}

            for frame in frames[begin:end]:
                for packet in out_stream.encode(frame):
                    output_container.mux(packet)

            # Flush encoder
            for packet in out_stream.encode(None):
                output_container.mux(packet)

            output_container.close()
            print(f"{output_video_path}")
            output_videos.append(output_video_path)

        except Exception as e:
            print(f"Error processing segment {begin}-{end}: {e}")
            continue

    return output_videos


def filter_frames(frames_info: List):
    # Split resolutions
    resolution_segments = []
    current_resolution = (0, 0)
    current_segment = {"resolution": (0, 0), "frames": []}
    for frame_info in frames_info:
        resolution = (frame_info["video_width"], frame_info["video_height"])

        if resolution != current_resolution:
            current_resolution = resolution
            current_segment = {
                "resolution": resolution,
                "frames": [frame_info["frame_index"]],
            }
            resolution_segments.append(current_segment)
        else:
            current_segment["frames"].append(frame_info["frame_index"])
    print(f"Found {len(resolution_segments)} resolution segments")

    result_segments = []
    max_duration = 10  # seconds

    for segment in resolution_segments:
        frames = segment["frames"]
        resolution = segment["resolution"]
        width, height = resolution

        # Sort frames by frame index to ensure proper order
        frames.sort()

        # Split into time-based segments within this resolution
        current_time_segment = []
        segment_start_time = None

        for frame_idx in frames:
            frame_info = frames_info[frame_idx]
            current_time = float(frame_info["video_RelativeTime"])

            if segment_start_time is None:
                segment_start_time = current_time
                current_time_segment = [frame_idx]
            else:
                # Check if adding this frame would exceed max_duration
                if current_time - segment_start_time > max_duration:
                    # Save current segment and start new one
                    if current_time_segment:
                        result_segments.append(
                            create_segment(
                                current_time_segment, frames_info, width, height
                            )
                        )
                    segment_start_time = current_time
                    current_time_segment = [frame_idx]
                else:
                    current_time_segment.append(frame_idx)

        # Add the last segment if it has frames
        if current_time_segment:
            result_segments.append(
                create_segment(current_time_segment, frames_info, width, height)
            )

    print(f"Created {len(result_segments)} time segments")
    return result_segments


def create_segment(
    frame_indices: List, frames_info: List, width: int, height: int
) -> dict:
    """Create a segment dictionary with begin, end, width, height, fps"""
    if not frame_indices:
        return None

    # Get frame info for first and last frames
    first_frame = frames_info[frame_indices[0]]
    last_frame = frames_info[frame_indices[-1]]

    begin = int(first_frame["frame_index"])
    end = int(last_frame["frame_index"])

    # Calculate FPS based on frame timing
    # if len(frame_indices) > 1:
    #     time_span = float(last_frame["video_RelativeTime"]) - float(first_frame["video_RelativeTime"])
    #     frame_count = len(frame_indices)
    #     fps = frame_count / time_span if time_span > 0 else 30.0  # Default to 30 fps if no time span
    # else:
    #     fps = 30.0  # Default FPS for single frame
    fps = 30

    return {"begin": begin, "end": end, "width": width, "height": height, "fps": fps}


# TODO: Hard-coded for Celeb-DF for now
def generate_detector_input(output_videos: List, dataset_dir: str):
    if not output_videos:
        print("No output videos to process")
        return
    
    # Create the list file path for Celeb-DF
    list_file_path = os.path.join(dataset_dir, "Celeb-DF", "List_of_testing_videos.txt")
    # os.makedirs(os.path.join(dataset_dir, "Celeb-DF", "Celeb-real"), exist_ok=True)
    # os.makedirs(os.path.join(dataset_dir, "Celeb-DF", "Celeb-synthesis"), exist_ok=True)
    # os.makedirs(os.path.join(dataset_dir, "Celeb-DF", "YouTube-real"), exist_ok=True)
    
    # Extract relative paths and write to file
    dataset_dir = os.path.join(dataset_dir, "Celeb-DF")
    with open(list_file_path, "a") as f:
        for video_path in output_videos:
            # Convert absolute path to relative path from dataset_dir
            relative_path = os.path.relpath(video_path, dataset_dir)
            f.write(f"1 {relative_path}\n")
    
    print(f"Generated detector input list: {list_file_path}")
    print(f"Added {len(output_videos)} videos to the list")


def main():
    parser = argparse.ArgumentParser(description="Prepare detector")
    parser.add_argument("--input", "-i", type=str, required=True)
    args = parser.parse_args()

    # Process and filter frames
    with open(args.input, "r") as f:
        reader = csv.DictReader(f)
        results = []
        for row in reader:
            parsed_row = parse_csv_row(row)
            results.append(parsed_row)

    frame_ranges = filter_frames(results)
    # print(frame_ranges)

    rtc_output_video = (
        os.path.normpath(args.input)
        .replace("processed_rtc", "rtc_output")
        .replace(".csv", ".ivf")
    )

    test_name = "test0"
    output_video_prefix = rtc_output_video.replace(
        "rtc_output", f"detector_input/{test_name}"
    )
    output_video_prefix = output_video_prefix.replace(".ivf", ".mp4")
    os.makedirs(os.path.dirname(output_video_prefix), exist_ok=True)
    # print(video_path, output_video)
    output_videos = split_video(rtc_output_video, frame_ranges, output_video_prefix)

    dataset_dir = f"data/detector_input/{test_name}"
    generate_detector_input(output_videos, dataset_dir)


if __name__ == "__main__":
    main()
