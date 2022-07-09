[English](README_eng.md)
# makeheic.py
一个用 ffmpeg 和 mp4box 来将图片转换为 heic 的腊鸡脚本

## 功能：
1. 将图片转换为YUV420、YUV422或YUV444的，8、10或12位深度的HEIC
2. 多进程并行转换
3. 支持文件夹处理
4. 支持透明度通道辅助图像元素
5. 支持网格化分割编码
6. 支持ICC和EXIF的复制
7. 支持缩略图辅助图像元素
8. （实验性）HEIF动态图像序列
9. 可使用硬件编码器，如hevc_nvenc
10. 可在编码之前对图像进行比例缩放
11. 可使用Vulkan加速的libplacebo进行颜色空间转换等操作（再加上硬件编码，解放CPU的时代，到来了！~~良い世、来いよ~~）

## 需要：
1. Python 3.9+
2. 启用了 libx265 编译的 FFmpeg 和 FFprobe.
3. Mp4box(GPAC) 2.0+
4. ImageMagick (只为icc复制和“webp动态图支持方案”所需要)
5. Exiftool，如果你需要复制exif到heic

## 使用方式：
1. 拖放图片文件/文件夹到脚本（将会以默认参数进行批量编码，建议另存一份修改了默认参数的副本）
2. 命令行：详见 `makeheic.py -h` （目前只有英文）

## 温馨提示：
1. 脚本提供的缩放只是为了方便的一个简陋功能，如果在意缩放质量，请使用GIMP之类的专业工具。
2. 默认的编码参数适合用于**高品质**的编码，在压缩率优先的情况下请适当调整参数；“fast”开关的参数会导致额外的瑕疵，在意速度的情况下，如果有硬件编码可用或许更为合适。
3. 不巧的是，现存的视频编码器的无损压缩模式用在静态图片上就是垃圾，所以我并没有提供一个可以快速开启的无损开关，无损webp或jpeg-xl是更佳选择。请注意有的工具会先把输入的RGB图片转换成YUV再进行无损编码，不要拿这种寄吧假无损来反驳我。
