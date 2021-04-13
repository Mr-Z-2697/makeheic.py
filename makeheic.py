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
parser.add_argument('--delete-src',required=False,help='Delete source file switch, add this argument means "ON".',action='store_true')
parser.add_argument('--sws',required=False,help='Force to use swscale switch.',action='store_true')
parser.add_argument('--alpha',required=False,help='Force to try to encode alpha plane.',action='store_true')
    #New version of libheif seems to use matrixs accordingly, so I think it's better to use modern bt709 as default.
parser.add_argument('--mat',type=str,required=False,help='Matrix used in target image, should be either bt709 or bt601 currently.',default='bt709')
parser.add_argument('--depth',type=int,required=False,help='Bitdepth for hevc-yuv output, default 10.',default=10)
parser.add_argument('--sample',type=str,required=False,help='Chroma subsumpling for hevc-yuv output, default "444"',default='444')
parser.add_argument('INPUTFILE',type=str,help='Input file.',nargs='+')
parser.parse_args(sys.argv[1:],args)

mat_l=('smpte170m' if args.mat=='bt601' else 'bt709')
mat_s=('170m' if args.mat=='bt601' else '709')

if args.sample == '444':
    subs_w=0
    subs_h=0
elif args.sample == '422':
    subs_w=1
    subs_h=0
elif args.sample == '420':
    subs_w=1
    subs_h=1
else:
    raise TypeError('output subsampling not supported.')

if args.depth == 10:
    bits=10
elif args.depth == 8:
    bits=8
elif args.depth == 12:
    bits=12
else:
    raise TypeError('output bitdepth not supported')



#If you drop a bunch of files to this script this should supposedly work fine.
for in_fp in args.INPUTFILE:
    if args.o == None:
        out_fp = in_fp + '.heic'
    else:
        out_fp = args.o

#ffprobe
    probe = subprocess.Popen(r'ffprobe -hide_banner -i "{INP}"'.format(INP=in_fp),shell=True,stderr=subprocess.PIPE)
    probe_result = probe.stderr.read().decode('ansi')

    #Use extra characters to hopefully ensure that it's grabbing what I want.
    probe_codec = re.search('Video: [a-z0-9A-Z]+',probe_result,re.M).group()
    #I'm kinda lazy, feel free to add whatever ffmpeg supports.
    if not probe_codec[7:] in ('webp','png','mjpeg','bmp','ppm',): 
        raise TypeError(r'input file "{INP}" codec not supported.'.format(INP=in_fp))

    probe_pixfmt = re.search(', yuv|, [a]*rgb[albepf0-9]*|, [a]*bgr[albepf0-9]*|, [a]*gbr[albepf0-9]*|, pal8|, gray|, ya',probe_result)
    probe_alpha = re.search('yuva4|argb|bgra|rgba|gbra|ya[81]',probe_result)
    if not probe_pixfmt:
        raise TypeError(r'input file "{INP}" pixel format not supported.'.format(INP=in_fp))
    else:
        probe_pixfmt = probe_pixfmt.group()
    probe_sub = None

    if probe_pixfmt == ', yuv':
        probe_sub = re.search('4[4210]+p',probe_result).group(0)
    if probe_sub in ['444p',None]:
        probe_subs_w=0
        probe_subs_h=0
    elif probe_sub == '422p':
        probe_subs_w=1
        probe_subs_h=0
    else:
        probe_subs_w=1
        probe_subs_s=1

    probe_resolution = re.search('[0-9]+x[0-9]+',probe_result).group(0).split('x')
    probe_res_w=int(probe_resolution[0])
    probe_res_h=int(probe_resolution[1])
    probe_w_odd = probe_res_w % 2
    probe_h_odd = probe_res_h % 2

#Determine command line parameters
    #Use padding if output is subsampled and image w/h not mod by 2
    pad_w=probe_w_odd and subs_w
    pad_h=probe_h_odd and subs_h
    if pad_w or pad_h:
        pad = 'pad={W}:{H},'.format(W=probe_res_w+pad_w, H=probe_res_h+pad_h)
    else:
        pad = ''
    #Use swscale to handle weird "subsampled but not mod by 2" images, and use zimg for better conversion if there's no chroma re-subsampling.
    c_resubs = (probe_subs_w != subs_w) or (probe_subs_h != subs_h)
    if c_resubs or args.sws:
        scale_filter = r'scale=out_range=pc:flags=spline:sws_dither=ed:out_v_chr_pos=127:out_h_chr_pos=127:out_color_matrix={MAT_L}'.format(MAT_L=mat_l)
    else:
        scale_filter = r'zscale=r=pc:f=spline36:d=error_diffusion:c=1:m={MAT_S}'.format(MAT_S=mat_s)
    ff_pixfmt='yuv{S}p{D}'.format(S=args.sample,D=(str(args.depth) if bits>8 else '')) + ('le' if bits>8 else '')
    coffs = (-2 if subs_w and subs_h else 1)

    ff_cmd_img=r'ffmpeg -hide_banner -r 1 -i "{INP}" -vf {PD}{SF},format={PF} -frames 1 -c:v libx265 -preset 6 -crf {Q} -x265-params no-sao=1:selective-sao=0:ref=1:bframes=0:aq-mode=1:psy-rd=2:psy-rdoq=8:cbqpoffs={CO}:crqpoffs={CO}:range=full:colormatrix={MAT_L}:transfer=iec61966-2-1:no-info=1 "%temp%\make.heic.hevc" -y'.format(INP=in_fp,PD=pad,SF=scale_filter,Q=args.q,MAT_L=mat_l,PF=ff_pixfmt,CO=coffs)
    m4b_cmd_img=r'mp4box -add-image "%temp%\make.heic.hevc":primary -brand heic -new "{OUT}" && del "%temp%\make.heic.hevc"'.format(OUT=out_fp)
    ff_cmd_a=r'ffmpeg -hide_banner -r 1 -i "{INP}" -vf {PD}extractplanes=a,{SF},format=gray10le -frames 1 -c:v libx265 -preset 6 -crf {Q} -x265-params no-sao=1:selective-sao=0:ref=1:bframes=0:aq-mode=1:psy-rd=2:psy-rdoq=8:cbqpoffs=1:crqpoffs=1:range=full:colormatrix={MAT_L}:transfer=iec61966-2-1:no-info=1 "%temp%\make.heic.alpha.hevc" -y'.format(INP=in_fp,PD=pad,SF=':'.join(scale_filter.split(':')[:-1]),Q=args.q,MAT_L=mat_l)
    m4b_cmd_a=r'mp4box -add-image "%temp%\make.heic.alpha.hevc":ref=auxl,1:alpha -brand heic "{OUT}" && del "%temp%\make.heic.alpha.hevc"'.format(OUT=out_fp)

#Doing actual conversion.
    subprocess.run(ff_cmd_img,shell=True)
    subprocess.run(m4b_cmd_img,shell=True)
    if probe_alpha or args.alpha:
        subprocess.run(ff_cmd_a,shell=True)
        subprocess.run(m4b_cmd_a,shell=True)
    #Delete source file or not?
    if args.delete_src:
        os.remove(in_fp)

if not args.s:
    input('enter to exit.')
