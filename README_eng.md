# makeheic.py
A crappy script that uses ffmpeg &amp; mp4box to convert pictures to heic.

## Features:
1. Convert images to YUV(444/422/420)P(8/10/12) HEIC.
2. Multi process parallel work
3. Supports folder input
4. Supports alpha channel auxiliary image item
5. Supports split to grid
6. Supports ICC and EXIF copying
7. Supports thumbnail auxiliary image item
8. (experimantal) Animated sequence
9. Hardware encoding available
10. Image scaling available
11. Vulkan accelerated libplacebo available for color space conversion etc.

## Requirements:
1. Python 3.9+
2. FFmpeg & FFprobe with libx265 biult-in.
3. Mp4box(GPAC) 2.0+
4. ImageMagick (only need for icc and animated webp workaround)
5. Exiftool if you need to copy exif
6. webpmux (only need for animated webp workaround)

## Usage:
1. Drag and drop (will use default settings).
2. Command line, see `makeheic.py -h`

## Notice:
1. Scaling function is just for quick use, if you are serious about scaling quality, please use tools like GIMP.
2. Default encoding parameters is good for "visually lossless" compression, "fast" parameters can cause some unwanted artifacts, perhaps even using hwenc would be better in that case.
3. Unfortunately, the lossless compression of existing video codecs is trash for still picture, so I don't provide a simple switch for lossless compression, webp or jxl are better solutions. And don't take those tools that convert to yuv first then call it f__king "lossless" against me.
