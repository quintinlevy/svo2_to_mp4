"""
Convert a Stereolabs .svo/.svo2 recording into separate left and right
camera video files (.mp4 or .avi).

Requires the ZED SDK (with its Python API, pyzed) and OpenCV.
The "high" and "lossless" quality options also require ffmpeg on the PATH.

Examples:
    python svo2_split.py recording.svo2
    python svo2_split.py recording.svo2 --format avi --camera left
    python svo2_split.py recording.svo2 --quality high --output-dir out/ --unrectified
    python svo2_split.py recording.svo2 --verify full
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import pyzed.sl as sl

# OpenCV FourCC codec per container format (used for --quality normal)
CODECS = {
    "mp4": "mp4v",
    "avi": "XVID",
}

# ffmpeg encoder arguments per (format, quality)
FFMPEG_ARGS = {
    # H.264, visually lossless
    ("mp4", "high"): ["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p"],
    # H.264 lossless in full-resolution colour (only RGB->YUV rounding is lost)
    ("mp4", "lossless"): ["-c:v", "libx264", "-preset", "ultrafast", "-qp", "0", "-pix_fmt", "yuv444p"],
    # MPEG-4 Part 2 at its highest quality setting
    ("avi", "high"): ["-c:v", "mpeg4", "-q:v", "2", "-pix_fmt", "yuv420p"],
    # FFV1 in RGB, bit-exact
    ("avi", "lossless"): ["-c:v", "ffv1", "-pix_fmt", "bgr0"],
}

VIEWS = {
    "left": (sl.VIEW.LEFT, sl.VIEW.LEFT_UNRECTIFIED),
    "right": (sl.VIEW.RIGHT, sl.VIEW.RIGHT_UNRECTIFIED),
}


class ResolutionMismatch(Exception):
    """A retrieved frame doesn't match the SVO's resolution."""


class FFmpegWriter:
    """Pipes raw BGR frames into an ffmpeg process."""

    def __init__(self, path, fps, size, encoder_args):
        width, height = size
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{width}x{height}", "-r", str(fps),
            "-i", "-",
            *encoder_args,
            str(path),
        ]
        # Own session so Ctrl-C reaches only this script, which then closes ffmpeg cleanly
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, start_new_session=True)

    def write(self, frame):
        self.proc.stdin.write(frame.tobytes())

    def release(self):
        try:
            self.proc.stdin.close()
        except BrokenPipeError:
            pass
        if self.proc.wait() != 0:
            print(f"\nWarning: ffmpeg exited with code {self.proc.returncode}")


def open_writer(path, fmt, quality, fps, size):
    if quality == "normal":
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter.fourcc(*CODECS[fmt]), fps, size)
        if not writer.isOpened():
            raise RuntimeError(f"Could not open video writer for {path}. Check the path and write permissions.")
        return writer
    return FFmpegWriter(path, fps, size, FFMPEG_ARGS[(fmt, quality)])


def probe_header(path):
    """Return (width, height, frame_count) from the video's container, without decoding.

    frame_count is None if it can't be determined.
    """
    if shutil.which("ffprobe"):
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
             "-show_entries", "stream=width,height,nb_read_packets", "-of", "json", str(path)],
            capture_output=True, text=True,
        )
        streams = json.loads(result.stdout or "{}").get("streams", [])
        if result.returncode != 0 or not streams:
            raise RuntimeError(f"ffprobe could not read the file: {result.stderr.strip()}")
        stream = streams[0]
        frames = stream.get("nb_read_packets")
        return int(stream["width"]), int(stream["height"]), int(frames) if frames else None

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError("OpenCV could not open the file")
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return width, height, frames if frames > 0 else None


def verify_output(path, width, height, expected_frames, mode):
    """Check an output video's resolution and frame count. Returns True on pass."""
    expected = f"expected {width}x{height}, {expected_frames} frames"
    try:
        if mode == "full":
            # Decode every frame and check each one's size
            cap = cv2.VideoCapture(str(path))
            if not cap.isOpened():
                raise RuntimeError("OpenCV could not open the file")
            frames = wrong_size = 0
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                frames += 1
                if frame.shape[:2] != (height, width):
                    wrong_size += 1
            cap.release()
            passed = wrong_size == 0 and frames == expected_frames
            found = f"{frames} frames decoded, {wrong_size} with wrong size"
        else:
            got_w, got_h, frames = probe_header(path)
            size_ok = (got_w, got_h) == (width, height)
            if frames is None:
                passed = size_ok
                found = f"{got_w}x{got_h}, frame count unavailable"
            else:
                passed = size_ok and frames == expected_frames
                found = f"{got_w}x{got_h}, {frames} frames"
    except (RuntimeError, OSError, ValueError, KeyError) as e:
        passed = False
        found = f"could not verify ({e})"

    print(f"  {'PASS' if passed else 'FAIL'}  {path.name}: {found} ({expected})")
    return passed


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
    parser.add_argument("--quality", choices=["normal", "high", "lossless"], default="normal",
                        help="normal: OpenCV encoder, no extra dependencies. "
                             "high: visually lossless (needs ffmpeg). "
                             "lossless: no compression loss, very large files (needs ffmpeg). "
                             "(default: normal)")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Directory for output videos (default: same folder as the input)")
    parser.add_argument("--unrectified", action="store_true",
                        help="Export raw (unrectified) images instead of rectified ones")
    parser.add_argument("--verify", nargs="?", const="quick", choices=["quick", "full"], default=None,
                        help="After conversion, check each output's resolution and frame count. "
                             "quick (default if no value given): read the file header. "
                             "full: decode every frame (slower).")
    args = parser.parse_args()

    if args.input.suffix.lower() not in (".svo", ".svo2"):
        parser.error(f"input must be a .svo or .svo2 file: {args.input}")
    if not args.input.is_file():
        parser.error(f"input file does not exist: {args.input}")
    if args.quality != "normal" and shutil.which("ffmpeg") is None:
        print("Warning: ffmpeg not found on PATH; falling back to --quality normal.")
        args.quality = "normal"
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
    print(f"Quality: {args.quality}")

    # One writer and one image buffer per selected camera
    outputs = {}
    out_paths = []
    for cam in cameras:
        out_path = args.output_dir / f"{args.input.stem}_{cam}.{args.format}"
        try:
            writer = open_writer(out_path, args.format, args.quality, fps, (width, height))
        except (RuntimeError, OSError) as e:
            print(e)
            for w, _, _ in outputs.values():
                w.release()
            zed.close()
            return 1
        view = VIEWS[cam][1 if args.unrectified else 0]
        outputs[cam] = (writer, sl.Mat(), view)
        out_paths.append(out_path)
        print(f"Writing {cam} camera -> {out_path}")

    runtime_params = sl.RuntimeParameters()
    print("Converting... press Ctrl-C to stop early.")

    frames_written = 0
    exit_code = 0
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

            # Retrieve and size-check every camera's frame before writing any of them,
            # so all outputs keep the same frame count
            frames = []
            for writer, image, view in outputs.values():
                zed.retrieve_image(image, view)
                data = image.get_data()
                if data.shape[:2] != (height, width):
                    raise ResolutionMismatch(f"frame {frames_written} is {data.shape[1]}x{data.shape[0]}, "
                                     f"expected {width}x{height}")
                # ZED images are BGRA; video writers expect BGR
                frames.append((writer, cv2.cvtColor(data, cv2.COLOR_BGRA2BGR)))
            for writer, frame in frames:
                writer.write(frame)
            frames_written += 1

            if nb_frames > 0:
                progress_bar(min((zed.get_svo_position() + 1) / nb_frames * 100, 100))
    except KeyboardInterrupt:
        print("\nInterrupted; keeping frames written so far.")
    except BrokenPipeError:
        print("\nffmpeg stopped unexpectedly; see its error output above.")
        exit_code = 1
    except ResolutionMismatch as e:
        print(f"\nResolution mismatch, stopping: {e}")
        exit_code = 1
    finally:
        for writer, _, _ in outputs.values():
            writer.release()
        zed.close()

    print(f"Frames written per camera: {frames_written} (SVO reports {nb_frames})")

    if args.verify:
        print(f"Verifying outputs ({args.verify})...")
        results = [verify_output(p, width, height, frames_written, args.verify) for p in out_paths]
        if not all(results):
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
