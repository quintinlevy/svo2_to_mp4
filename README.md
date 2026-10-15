# svo2_split

Convert a Stereolabs ZED `.svo` / `.svo2` recording into **separate** left and right camera videos (`.mp4` or `.avi`).

The official Stereolabs export sample writes both cameras side by side into a single AVI. This script writes one video file per camera instead, so you can export just the left camera, just the right, or both.

## Requirements

- An NVIDIA GPU with CUDA (needed by the ZED SDK)
- [ZED SDK](https://www.stereolabs.com/developers/release) and its Python API (`pyzed`)
  - After installing the SDK, run the `get_python_api.py` script included with it to install `pyzed`
- Python 3 with OpenCV:
  ```
  pip install opencv-python
  ```
- [ffmpeg](https://ffmpeg.org/) on the PATH, only for `--quality high` or `lossless`:
  ```
  sudo apt install ffmpeg
  ```

## Usage

```
python svo2_split.py <input.svo2> [--format {mp4,avi}] [--camera {left,right,both}]
                                  [--quality {normal,high,lossless}]
                                  [--output-dir DIR] [--unrectified]
                                  [--verify [{quick,full}]]
```

| Option | Default | Description |
|---|---|---|
| `input` | *(required)* | Path to the `.svo` or `.svo2` file |
| `--format` | `mp4` | Output container: `mp4` or `avi` |
| `--camera` | `both` | Which camera(s) to export: `left`, `right`, or `both` |
| `--quality` | `normal` | Encoding quality, see [Quality](#quality) |
| `--output-dir` | input file's folder | Where to write the videos (created if missing) |
| `--unrectified` | off | Export raw sensor images instead of rectified images |
| `--verify` | off | Check the output videos after conversion, see [Verification](#verification) |

### Examples

```
# Both cameras as MP4, next to the input file
python svo2_split.py recording.svo2

# Left camera only, as AVI
python svo2_split.py recording.svo2 --format avi --camera left

# Right camera, raw images, into a separate folder
python svo2_split.py recording.svo2 --camera right --output-dir out/ --unrectified

# Both cameras, visually lossless H.264
python svo2_split.py recording.svo2 --quality high

# Convert, then decode every output frame to confirm resolution and frame count
python svo2_split.py recording.svo2 --verify full
```

### Quality

| `--quality` | `.mp4` | `.avi` | Notes |
|---|---|---|---|
| `normal` | `mp4v` (OpenCV) | `XVID` (OpenCV) | No extra dependencies. Visible compression loss. |
| `high` | H.264, CRF 18 | MPEG-4, `-q:v 2` | Visually lossless. Needs ffmpeg. |
| `lossless` | H.264, QP 0, 4:4:4 | FFV1, RGB | Very large files. Needs ffmpeg. |

- `lossless` `.avi` (FFV1) is bit-exact. `lossless` `.mp4` loses only tiny rounding from RGB→YUV conversion, and some players can't play 4:4:4 H.264. Use `.avi` if you need exact pixels.
- If ffmpeg isn't installed, `high` and `lossless` fall back to `normal` with a warning.
- No setting can be better than the SVO itself. If the recording was made with lossy compression, that loss is already baked in.
- ffmpeg encodes on the CPU, so `high` and `lossless` are slower, especially on a Jetson.

### Output

Files are named after the input file:

```
recording_left.mp4
recording_right.mp4
```

Videos use the recording's original resolution and frame rate. Press Ctrl-C to stop early; frames written so far are kept.

### Verification

The output videos keep the SVO2 recording's native resolution. The script reads the resolution and frame rate from the ZED SDK, sets up each video writer with exactly those values, and writes frames without resizing or cropping. It checks this in two ways:

- **Every frame, always on:** before writing, each frame's width and height are compared with the SVO's. On a mismatch, the script stops with an error instead of writing a bad frame. This adds no measurable time.
- **After conversion, with `--verify`:** each output file is checked against the SVO's resolution and the number of frames written.

| Mode | What it checks | Cost |
|---|---|---|
| `--verify` or `--verify quick` | Width, height and frame count from the file header (via `ffprobe` if installed, otherwise OpenCV) | Negligible |
| `--verify full` | Decodes every frame, checking each frame's size and the total count | Roughly 10–30% extra time (estimate) |

Each file gets a `PASS` or `FAIL` line, and the script exits with code 1 if any check fails:

```
Verifying outputs (full)...
  PASS  recording_left.mp4: 900 frames decoded, 0 with wrong size (expected 1920x1080, 900 frames)
```

Why check at all? OpenCV's video writer drops a frame whose size doesn't match without telling the calling program (it only logs a warning), and ffmpeg's raw-video input would misread every frame after a wrong-sized one. In normal use every frame comes from the same SVO at its native size, so these checks confirm correctness rather than catch a known problem.

## Notes

- Depth computation is disabled during export, so conversion is faster than the Stereolabs sample.
- Rectified images are resampled to correct lens distortion, which softens them very slightly. Use `--unrectified` for the pixels as recorded.

## License

This project is released under the [MIT License](LICENSE).

It uses the ZED SDK, which is proprietary software from Stereolabs under its own license and is not included in this repository. Users must install the SDK themselves.
