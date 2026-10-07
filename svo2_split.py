"""
Convert a Stereolabs .svo/.svo2 recording into separate left and/or right
camera video files (.mp4 or .avi).

Requires the ZED SDK (with its Python API, pyzed) and opencv-python.

Examples:
    python svo2_split.py recording.svo2
    python svo2_split.py recording.svo2 --format avi --camera left
    python svo2_split.py recording.svo2 --camera both --output-dir out/ --unrectified
"""

import argparse
import sys
from pathlib import Path

import cv2
import pyzed.sl as sl

# FourCC codec per container format
CODECS = {
    "mp4": "mp4v",
    "avi": "XVID",
}

VIEWS = {
    "left": (sl.VIEW.LEFT, sl.VIEW.LEFT_UNRECTIFIED),
    "right": (sl.VIEW.RIGHT, sl.VIEW.RIGHT_UNRECTIFIED),
}


def progress_bar(percent_done, bar_length=40):
    done_length = int(bar_length * percent_done / 100)
    bar = "=" * done_length + "-" * (bar_length - done_length)
    sys.stdout.write(f"[{bar}] {percent_done:5.1f}%\r")
    sys.stdout.flush()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Split a ZED .svo/.svo2 file into separate left/right camera videos."
    )
    parser.add_argument("input", type=Path, help="Path to the .svo or .svo2 file")
    parser.add_argument("--format", choices=CODECS.keys(), default="mp4",
                        help="Output video container (default: mp4)")
    parser.add_argument("--camera", choices=["left", "right", "both"], default="both",
                        help="Which camera(s) to export (default: both)")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Directory for output videos (default: same folder as the input)")
    parser.add_argument("--unrectified", action="store_true",
                        help="Export raw (unrectified) images instead of rectified ones")
    args = parser.parse_args()

    if args.input.suffix.lower() not in (".svo", ".svo2"):
        parser.error(f"input must be a .svo or .svo2 file: {args.input}")
    if not args.input.is_file():
        parser.error(f"input file does not exist: {args.input}")
    if args.output_dir is None:
        args.output_dir = args.input.parent
    args.output_dir.mkdir(parents=True, exist_ok=True)
    return args


def main():
    args = parse_args()
    cameras = ["left", "right"] if args.camera == "both" else [args.camera]

    init_params = sl.InitParameters()
    init_params.set_from_svo_file(str(args.input))
    init_params.svo_real_time_mode = False  # Process every frame as fast as possible
    init_params.depth_mode = sl.DEPTH_MODE.NONE  # Depth not needed, speeds up conversion

    zed = sl.Camera()
    err = zed.open(init_params)
    if err > sl.ERROR_CODE.SUCCESS:
        print(f"Failed to open SVO file: {err}")
        zed.close()
        return 1

    config = zed.get_camera_information().camera_configuration
    width, height = config.resolution.width, config.resolution.height
    fps = config.fps
    nb_frames = zed.get_svo_number_of_frames()
    print(f"Input: {args.input.name}  {width}x{height} @ {fps} fps, {nb_frames} frames")

    # One writer and one image buffer per selected camera
    fourcc = cv2.VideoWriter.fourcc(*CODECS[args.format])
    outputs = {}
    for cam in cameras:
        out_path = args.output_dir / f"{args.input.stem}_{cam}.{args.format}"
        writer = cv2.VideoWriter(str(out_path), fourcc, fps, (width, height))
        if not writer.isOpened():
            print(f"Could not open video writer for {out_path}. Check the path and write permissions.")
            for w, _, _ in outputs.values():
                w.release()
            zed.close()
            return 1
        view = VIEWS[cam][1 if args.unrectified else 0]
        outputs[cam] = (writer, sl.Mat(), view)
        print(f"Writing {cam} camera -> {out_path}")

    runtime_params = sl.RuntimeParameters()
    print("Converting... press Ctrl-C to stop early.")

    try:
        while True:
            err = zed.grab(runtime_params)
            if err == sl.ERROR_CODE.END_OF_SVOFILE_REACHED:
                progress_bar(100)
                print("\nDone.")
                break
            if err > sl.ERROR_CODE.SUCCESS:
                print(f"\nStopped on grab error: {err}")
                break

            for writer, image, view in outputs.values():
                zed.retrieve_image(image, view)
                # ZED images are BGRA; video writers expect BGR
                writer.write(cv2.cvtColor(image.get_data(), cv2.COLOR_BGRA2BGR))

            if nb_frames > 0:
                progress_bar(min((zed.get_svo_position() + 1) / nb_frames * 100, 100))
    except KeyboardInterrupt:
        print("\nInterrupted; keeping frames written so far.")
    finally:
        for writer, _, _ in outputs.values():
            writer.release()
        zed.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
