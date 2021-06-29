import os,sys
import argparse
import subprocess
import re

class args:
    pass

#Arguments, ordinary stuff I guess.
parser = argparse.ArgumentParser(description='HEIC encode script using ffmpeg & mp4box.',formatter_class=argparse.RawTextHelpFormatter)
parser.add_argument('-q',type=float,required=False,help='Quality(crf), default 21.',default=21)
parser.add_argument('-o',type=str,required=False,help='Output(s), default input full name (ext. incl.) + ".heic".',nargs='*')
parser.add_argument('-s',required=False,help='Silent mode, disables "enter to exit".',action='store_true')
parser.add_argument('--delete-src',required=False,help='Delete source file switch, add this argument means "ON".',action='store_true')
parser.add_argument('--sws',required=False,help='Force to use swscale switch.',action='store_true')
parser.add_argument('--alpha',required=False,help='Force to try to encode alpha plane switch.',action='store_true')
parser.add_argument('--no-alpha',required=False,help='Ignore alpha plane switch.',action='store_true')
parser.add_argument('--no-icc',required=False,help='Ignore icc profile of source image switch.',action='store_true')
    #New version of libheif seems to decode with matrixs accordingly, so I think it's better to use modern bt709 as default.
parser.add_argument('--mat',type=str,required=False,help='Matrix used to convert RGB input file, should be either bt709 or bt601 currently. If a input file is in YUV, it\'s original matrix will be "preserved". ',default='bt709')
parser.add_argument('--depth',type=int,required=False,help='Bitdepth for hevc-yuv output, default 10.',default=10)
parser.add_argument('--sample',type=str,required=False,help='Chroma subsumpling for hevc-yuv output, default "444"',default='444')
parser.add_argument('INPUTFILE',type=str,help='Input file.',nargs='+')
parser.parse_args(sys.argv[1:],args)



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

pid = os.getpid()

#If you drop a bunch of files to this script this should supposedly work fine.
if (args.o != None) and (len(args.INPUTFILE) != len(args.o)):
    raise TypeError('the number of input and output should match if output is specified.')
i=0
for in_fp in args.INPUTFILE:
    in_fp = os.path.abspath(in_fp)
    if args.o == None:
        out_fp = in_fp + '.heic'
    else:
        out_fp = args.o[i]
        i+=1
    out_fp = os.path.abspath(out_fp)

    mat_l=('smpte170m' if args.mat=='bt601' else 'bt709')
    mat_s=('170m' if args.mat=='bt601' else '709')

#ffprobe&imagemagick
    if not args.no_icc:
        hasicc = not subprocess.run(r'magick "{INP}" "{OUT}.{PID}.icc"'.format(INP=in_fp,OUT=r'%temp%\make.heic',PID=pid),shell=True).returncode
    else:
        hasicc = False
    
    probe = subprocess.Popen(r'ffprobe -hide_banner -i "{INP}"'.format(INP=in_fp),shell=True,stderr=subprocess.PIPE)
    probe_result = probe.stderr.read().decode()

    #Use extra characters to hopefully ensure that it's grabbing what I want.
    probe_codec = re.search('Video: [a-z0-9A-Z]+',probe_result,re.M).group()
    #I'm kinda lazy, feel free to add whatever ffmpeg supports.
    if not probe_codec[7:] in ('webp','png','mjpeg','bmp','ppm','tiff'): 
        raise TypeError(r'input file "{INP}" codec not supported.'.format(INP=in_fp))

    probe_pixfmt = re.search(', yuv|, [a]*rgb[albepf0-9]*|, [a]*bgr[albepf0-9]*|, [a]*gbr[albepf0-9]*|, pal8|, gray|, ya',probe_result)
    probe_alpha = re.search('yuva4|argb|bgra|rgba|gbra|ya[81]',probe_result)
    if not probe_pixfmt:
        raise TypeError(r'input file "{INP}" pixel format not supported.'.format(INP=in_fp))
    else:
        probe_pixfmt = probe_pixfmt.group()
    probe_sub = None
    probe_mat = False

    if probe_pixfmt == ', yuv':
        probe_sub = re.search('4[4210]+p',probe_result).group(0)
        probe_mat = re.search('bt470bg|bt709',probe_result)

    if probe_sub in ['444p',None]:
        probe_subs_w=0
        probe_subs_h=0
    elif probe_sub == '422p':
        probe_subs_w=1
        probe_subs_h=0
    else:
        probe_subs_w=1
        probe_subs_h=1

    if probe_mat:
        mat_l=('smpte170m' if probe_mat.group(0)=='bt470bg' else 'bt709')
        mat_s=('170m' if probe_mat.group(0)=='bt470bg' else '709')

    probe_resolution = re.search('[0-9]+x[0-9]+',probe_result).group(0).split('x')
    probe_res_w=int(probe_resolution[0])
    probe_res_h=int(probe_resolution[1])
    probe_w_odd = probe_res_w % 2
    probe_h_odd = probe_res_h % 2

#Determine command line parameters
    icc_opt = r':icc_path=make.heic.{PID}.icc'.format(PID=pid) if hasicc else ''
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
        scale_filter = r'scale=out_range=pc:flags=spline:sws_dither=ed:out_v_chr_pos={VC}:out_h_chr_pos={HC}:out_color_matrix={MAT_L}'.format(MAT_L=mat_l,VC=(127 if subs_h else 0),HC=(127 if subs_w else 0))
    else:
        scale_filter = r'zscale=r=pc:f=spline36:d=error_diffusion:c=1:m={MAT_S}'.format(MAT_S=mat_s)
    ff_pixfmt='yuv{S}p{D}'.format(S=args.sample,D=(str(args.depth) if bits>8 else '')) + ('le' if bits>8 else '')
    ff_pixfmt_a='gray{D}'.format(D=(str(args.depth) if bits>8 else '')) + ('le' if bits>8 else '')
    coffs = (-2 if subs_w and subs_h else 1)

    ff_cmd_img=r'ffmpeg -hide_banner -r 1 -i "{INP}" -vf {PD}{SF},format={PF} -frames 1 -c:v libx265 -preset 6 -crf {Q} -x265-params no-sao=1:selective-sao=0:ref=1:bframes=0:aq-mode=1:psy-rd=2:psy-rdoq=8:cbqpoffs={CO}:crqpoffs={CO}:range=full:colormatrix={MAT_L}:transfer=iec61966-2-1:no-info=1 "%temp%\make.heic.{PID}.hevc" -y'.format(INP=in_fp,PD=pad,SF=scale_filter,Q=args.q,MAT_L=mat_l,PF=ff_pixfmt,CO=coffs,PID=pid)

    m4b_cmd_img=r'cd /d %temp% && mp4box -add-image "make.heic.{PID}.hevc":primary{ICC} -brand heic -new "{OUT}" && del "make.heic.{PID}.hevc"'.format(OUT=out_fp,ICC=icc_opt,PID=pid)

    ff_cmd_a=r'ffmpeg -hide_banner -r 1 -i "{INP}" -vf {PD}extractplanes=a,format={PF} -frames 1 -c:v libx265 -preset 6 -crf {Q} -x265-params no-sao=1:selective-sao=0:ref=1:bframes=0:aq-mode=1:psy-rd=2:psy-rdoq=8:cbqpoffs=1:crqpoffs=1:range=full:colormatrix={MAT_L}:transfer=iec61966-2-1:no-info=1 "%temp%\make.heic.alpha.{PID}.hevc" -y'.format(INP=in_fp,PD=pad,SF=':'.join(scale_filter.split(':')[:-1]),Q=args.q,MAT_L=mat_l,PF=ff_pixfmt_a,PID=pid)

    m4b_cmd_a=r'cd /d %temp% && mp4box -add-image "make.heic.alpha.{PID}.hevc":ref=auxl,1:alpha -brand heic "{OUT}" && del "make.heic.alpha.{PID}.hevc"'.format(OUT=out_fp,PID=pid)

#Doing actual conversion.
    subprocess.run(ff_cmd_img,shell=True)
    subprocess.run(m4b_cmd_img,shell=True)
    if (probe_alpha or args.alpha) and not args.no_alpha:
        subprocess.run(ff_cmd_a,shell=True)
        subprocess.run(m4b_cmd_a,shell=True)
    if hasicc:
        subprocess.run(r'del %temp%\make.heic.{PID}.icc'.format(PID=pid),shell=True)
    #Delete source file or not?
    if args.delete_src:
        os.remove(in_fp)

if not args.s:
    input('enter to exit.')
