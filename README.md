# makeheic.py
A crappy script that uses ffmpeg &amp; mp4box to convert pictures to heic.

~Yeah now I'm actually making it more than just a .bat file.~

## Requirements:
1. Python 3.9+
2. FFmpeg & FFprobe with libx265 biult-in.
3. Mp4box(GPAC) 2.0+
4. ImageMagick (only need for icc and animated webp workaround)
5. Exiftool if you need to copy exif

## Usage:
1. Drag and drop (will use default settings).
2. Command line

## Notice:
1. Scaling function is just for quick use, if you are serious about scaling quality, please use tools like GIMP.
2. Default encoding parameters is good for "visually lossless" compression, "fast" parameters can cause some unwanted artifacts, perhaps even you'd better use hwenc in that case.
3. Unfortunately, the lossless compression of existing video codecs is trash for still picture, so I don't provide a simple switch for lossless compression, for lossless compression webp or jxl is better solutions.
