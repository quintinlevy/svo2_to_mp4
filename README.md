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

## Usage

```
python svo2_split.py <input.svo2> [--format {mp4,avi}] [--camera {left,right,both}]
                                  [--output-dir DIR] [--unrectified]
```

| Option | Default | Description |
|---|---|---|
| `input` | *(required)* | Path to the `.svo` or `.svo2` file |
| `--format` | `mp4` | Output container: `mp4` (codec `mp4v`) or `avi` (codec `XVID`) |
| `--camera` | `both` | Which camera(s) to export: `left`, `right`, or `both` |
| `--output-dir` | input file's folder | Where to write the videos (created if missing) |
| `--unrectified` | off | Export raw sensor images instead of rectified images |

### Examples

```
# Both cameras as MP4, next to the input file
python svo2_split.py recording.svo2

# Left camera only, as AVI
python svo2_split.py recording.svo2 --format avi --camera left

# Right camera, raw images, into a separate folder
python svo2_split.py recording.svo2 --camera right --output-dir out/ --unrectified
```

### Output

Files are named after the input file:

```
recording_left.mp4
recording_right.mp4
```

Videos use the recording's original resolution and frame rate. Press Ctrl-C to stop early; frames written so far are kept.

## Notes

- Depth computation is disabled during export, so conversion is faster than the Stereolabs sample.
- `mp4v` output is widely supported but not as efficient as H.264. If you need smaller files, re-encode with ffmpeg:
  ```
  ffmpeg -i recording_left.mp4 -c:v libx264 -crf 20 recording_left_h264.mp4
  ```

## License

This project is released under the [MIT License](LICENSE).

It uses the ZED SDK, which is proprietary software from Stereolabs under its own license and is not included in this repository. Users must install the SDK themselves.
