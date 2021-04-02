import os,sys
import argparse
import subprocess
import re

class args:
    pass

#Arguments, ordinary stuff I guess.
parser = argparse.ArgumentParser(description='HEIC encode script using ffmpeg & mp4box.',formatter_class=argparse.RawTextHelpFormatter)
parser.add_argument('-q',type=float,required=False,help='Quality(crf), default 21.',default=21)
parser.add_argument('-o',type=str,required=False,help='Output, default input full name (ext. incl.) + ".heic".')
parser.add_argument('-s',required=False,help='Silent mode, disables "enter to exit".',action='store_true')
parser.add_argument('--delete-src',required=False,help='Delete source file switch.',action='store_true')
parser.add_argument('INPUTFILE',type=str,help='Input file.',nargs='+')
parser.parse_args(sys.argv[1:],args)

#If you drop a bunch of files to this script this should supposedly work fine.
for in_fp in args.INPUTFILE:
    if args.o == None:
        out_fp = in_fp + '.heic'
    else:
        out_fp = args.o

    probe = subprocess.Popen(r'ffprobe -hide_banner -i "{INP}"'.format(INP=in_fp),shell=True,stderr=subprocess.PIPE)
    probe_result = probe.stderr.read().decode('ansi')

    #Use extra characters to hopefully ensure that it's grabbing what I want.
    probe_codec = re.search('Video: [a-z0-9A-Z]+',probe_result,re.M).group()
    #I'm kinda lazy, feel free to add whatever ffmpeg supports.
    if not probe_codec[7:] in ('webp','png','mjpeg','bmp','ppm',): 
        raise TypeError(r'input file "{INP}" codec not supported.'.format(INP=in_fp))

    probe_pixfmt = re.search(', yuv|, rgb|, bgr|, gbr|, pal8|, gray|, ya',probe_result)
    probe_alpha = re.search('yuva4|argb|bgra|rgba|gbra|ya[81]',probe_result)
    if not probe_pixfmt:
        raise TypeError(r'input file "{INP}" pixel format not supported.'.format(INP=in_fp))
    else:
        probe_pixfmt = probe_pixfmt.group()
    probe_sub = None
    if probe_pixfmt == ', yuv':
        probe_sub = re.search('4[210]+p',probe_result)

    #Use swscale to handle weird "subsampled but not mod by 2" images, and use zimg for better conversion if there's no chroma subsampling.
    if probe_sub:
        scale_filter = r'scale=out_range=pc:flags=lanczos:sws_dither=ed:out_color_matrix=smpte170m'
    else:
        scale_filter = r'zscale=r=pc:f=bicubic:d=error_diffusion:m=170m'
    
    #Doing actual conversion.
    subprocess.run(r'ffmpeg -hide_banner -i "{INP}" -vf {SF},format=yuv444p10le -frames 1 -c:v libx265 -preset 6 -crf {Q} -x265-params no-sao=1:selective-sao=0:ref=1:bframes=0:aq-mode=1:psy-rd=2:psy-rdoq=8:cbqpoffs=1:crqpoffs=1:range=full:colormatrix=smpte170m:transfer=iec61966-2-1:no-info=1 "%temp%\make.heic.hevc" -y'.format(INP=in_fp,SF=scale_filter,Q=args.q),shell=True)
    subprocess.run(r'mp4box -add-image "%temp%\make.heic.hevc":primary -brand heic -new "{OUT}" && del "%temp%\make.heic.hevc"'.format(OUT=out_fp),shell=True)
    if probe_alpha:
        subprocess.run(r'ffmpeg -hide_banner -i "{INP}" -vf extractplanes=a,{SF},format=gray10le -frames 1 -c:v libx265 -preset 6 -crf {Q} -x265-params no-sao=1:selective-sao=0:ref=1:bframes=0:aq-mode=1:psy-rd=2:psy-rdoq=8:cbqpoffs=1:crqpoffs=1:range=full:colormatrix=smpte170m:transfer=iec61966-2-1:no-info=1 "%temp%\make.heic.alpha.hevc" -y'.format(INP=in_fp,SF=':'.join(scale_filter.split(':')[:-1]),Q=args.q),shell=True)
        subprocess.run(r'mp4box -add-image "%temp%\make.heic.alpha.hevc":ref=auxl,1:alpha -brand heic "{OUT}" && del "%temp%\make.heic.alpha.hevc"'.format(OUT=out_fp),shell=True)
    
    if args.delete_src:
        os.remove(in_fp)

if not args.s:
    input('enter to exit.')
