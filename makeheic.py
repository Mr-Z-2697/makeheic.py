import os,sys
import argparse
import subprocess
import re
import math
from random import choice
import pathlib
from multiprocessing import Pool
import signal

class args:
    pass



class makeheic:
    def __init__(self,in_fp,out_fp,crf=21,delsrc=False,sws=False,alpha=False,noalpha=False,acrf=None,noicc=False,mat=None,depth=10,sample='444',grid=False,pid=choice(range(1000,10000)),sao=None,co=None,psy_rdoq=None,xp=''):
        self.in_fp = in_fp
        self.out_fp = out_fp
        self.crf = crf
        self.delsrc = delsrc
        self.sws = sws
        self.alpha = alpha
        self.noalpha = noalpha
        self.acrf = acrf if acrf != None else crf
        self.noicc = noicc
        self.mat = mat
        self.depth = depth
        self.sample=sample
        self.pid = pid if not pid == None else choice(range(1000,10000))
        self.sao = sao
        self.co = co
        self.psy_rdoq = psy_rdoq
        self.xp = xp
        if sample == '444':
            self.subs_w=0
            self.subs_h=0
        elif sample == '422':
            self.subs_w=1
            self.subs_h=0
        elif sample == '420':
            self.subs_w=1
            self.subs_h=1
        else:
            raise TypeError('output subsampling not supported.')
        if depth == 10:
            self.bits=10
        elif depth == 8:
            self.bits=8
        elif depth == 12:
            self.bits=12
        else:
            raise TypeError('output bitdepth not supported')
        if grid:
            self.grid=True
            g=grid.split('x')
            if len(g)==1:
                self.gw=self.gh=int(g[0])
            else:
                self.gw=int(g[0])
                self.gh=int(g[1])
        else:
            self.grid=False

    def run_probe(self):
        if not self.noicc:
            self.hasicc = not subprocess.run(r'magick "{INP}" "{OUT}.{PID}.icc"'.format(INP=self.in_fp,OUT=r'%temp%\make.heic',PID=self.pid),shell=True).returncode
        else:
            self.hasicc = False

        probe = subprocess.Popen(r'ffprobe -hide_banner -i "{INP}"'.format(INP=self.in_fp),shell=True,   stderr=subprocess.PIPE)
        probe_result = probe.stderr.read().decode()

        #Use extra characters to hopefully ensure that it's grabbing what I want.
        self.probe_codec = re.search('Video: [a-z0-9A-Z]+',probe_result,re.M)
        if self.probe_codec:
            self.probe_codec=self.probe_codec.group()
            #I'm kinda lazy, feel free to add whatever ffmpeg supports.
            if not self.probe_codec[7:] in ('webp','png','mjpeg','bmp','ppm','tiff'): 
                print(r'input file "{INP}" codec not supported.'.format(INP=in_fp))
                return False
        else:
            return False

        self.probe_pixfmt = re.search(', yuv|, [a]*rgb[albepf0-9]*|, [a]*bgr[albepf0-9]*|, [a]*gbr[albepf0-9]*|, pal8|, gray|, ya',probe_result)
        self.probe_alpha = re.search('yuva4|argb|bgra|rgba|gbra|ya[81]',probe_result)
        if not self.probe_pixfmt:
            print(r'input file "{INP}" pixel format not supported.'.format(INP=in_fp))
            return False
        else:
            self.probe_pixfmt = self.probe_pixfmt.group()
        probe_sub = None
        probe_mat = False

        if self.probe_pixfmt == ', yuv':
            probe_sub = re.search('4[4210]+p',probe_result).group(0)
            probe_mat = re.search('bt470bg|bt709',probe_result)

        if probe_sub in ['444p',None]:
            self.probe_subs_w=0
            self.probe_subs_h=0
        elif probe_sub == '422p':
            self.probe_subs_w=1
            self.probe_subs_h=0
        else:
            self.probe_subs_w=1
            self.probe_subs_h=1

        if probe_mat and self.mat==None:
            self.mat_l=('smpte170m' if probe_mat.group(0)=='bt470bg' else 'bt709')
            self.mat_s=('170m' if probe_mat.group(0)=='bt470bg' else '709')
        else:
            self.mat_l=('smpte170m' if self.mat=='bt601' else 'bt709')
            self.mat_s=('170m' if self.mat=='bt601' else '709')

        probe_resolution = re.search('[0-9]+x[0-9]+',probe_result).group(0).split('x')
        self.probe_res_w=int(probe_resolution[0])
        self.probe_res_h=int(probe_resolution[1])
        self.probe_w_odd = self.probe_res_w % 2
        self.probe_h_odd = self.probe_res_h % 2

        if self.grid:
            self.g_columns=math.ceil(self.probe_res_w/self.gw)
            self.g_rows=math.ceil(self.probe_res_h/self.gh)
            self.g_padded_w=self.g_columns*self.gw
            self.g_padded_h=self.g_rows*self.gh
            self.items=self.g_columns*self.g_rows
        return True

    def cmd_line_gen(self):
        icc_opt = r':icc_path=make.heic.{PID}.icc'.format(PID=self.pid) if self.hasicc else ''
        #Use padding if output is subsampled and image w/h not mod by 2
        pad_w=self.probe_w_odd and self.subs_w
        pad_h=self.probe_h_odd and self.subs_h
        if pad_w or pad_h:
            pad = 'pad={W}:{H},'.format(W=self.probe_res_w+pad_w, H=self.probe_res_h+pad_h)
        else:
            pad = ''
        #Use swscale to handle weird "subsampled but not mod by 2" images, and use zimg for better  conversion if there's no chroma re-subsampling.
        c_resubs = (self.probe_subs_w != self.subs_w) or (self.probe_subs_h != self.subs_h)
        if c_resubs or self.sws:
            scale_filter = r'scale=out_range=pc:flags=spline:sws_dither=ed:out_v_chr_pos={VC}:out_h_chr_pos={HC}:out_color_matrix={MAT_L}'.format(MAT_L=self.mat_l,VC=(127 if self.subs_h else 0),HC=(127 if self.subs_w else 0))
        else:
            scale_filter = r'zscale=r=pc:f=spline36:d=error_diffusion:c=1:m={MAT_S}'.format(MAT_S=self.mat_s)
        ff_pixfmt='yuv{S}p{D}'.format(S=self.sample,D=(str(self.bits) if self.bits>8 else '')) + ('le' if self.bits>8 else '')
        ff_pixfmt_a='gray{D}'.format(D=(str(self.bits) if self.bits>8 else '')) + ('le' if self.bits>8 else '')
        coffs = (-2 if self.subs_w and self.subs_h else 1)
        if self.co != None:
            if self.co[0] == '+':
                coffs += int(self.co[1:])
            else:
                coffs = int(self.co)
        if self.psy_rdoq == None:
            prdo = 8
        else:
            prdo = self.psy_rdoq
        if self.sao == None:
            sao = 0
        else:
            sao = self.sao
        if not self.grid:
            self.ff_cmd_img=r'ffmpeg -hide_banner -r 1 -i "{INP}" -vf {PD}{SF},format={PF} -frames 1 -c:v libx265    -preset 6 -crf {Q} -x265-params    sao={SAO}:ref=1:bframes=0:aq-mode=1:psy-rdoq={PRDO}:cbqpoffs={CO}:crqpoffs={CO}:range=full:colormatrix={MAT_L}:transfer=iec61966-2-1:no-info=1:{XP} "%temp%\make.heic.{PID}.hevc" -y'.format(INP=self.in_fp,PD=pad,SF=scale_filter,Q=self.crf,MAT_L=self.mat_l,PF=ff_pixfmt,CO=coffs,PID=self.pid,SAO=sao,PRDO=prdo,XP=self.xp)

            self.m4b_cmd_img=r'cd /d %temp% && mp4box -add-image "make.heic.{PID}.hevc":primary:image-size={WxH}{ICC} -brand heic -new "{OUT}" && del "make.heic.{PID}.hevc"'.format(OUT=self.out_fp,ICC=icc_opt,PID=self.pid,WxH=str(self.probe_res_w)+'x'+str(self.probe_res_h))

            self.ff_cmd_a=r'ffmpeg -hide_banner -r 1 -i "{INP}" -vf {PD}{SF},format={PF} -frames 1 -c:v libx265    -preset 6 -crf {Q} -x265-params    sao={SAO}:ref=1:bframes=0:aq-mode=1:psy-rdoq={PRDO}:cbqpoffs={CO}:crqpoffs={CO}:range=full:colormatrix={MAT_L}:transfer=iec61966-2-1:no-info=1:{XP} "%temp%\make.heic.{PID}.hevc" -y -map v:0 -vf {PD}extractplanes=a,format={PF2} -frames 1 -c:v libx265 -preset 6 -crf {Q2} -x265-params sao={SAO}:ref=1:bframes=0:aq-mode=1:psy-rdoq={PRDO}:cbqpoffs=1:crqpoffs=1:range=full:colormatrix={MAT_L}:transfer=iec61966-2-1:no-info=1:{XP} "%temp%\make.heic.alpha.{PID}.hevc" -y'.format(INP=self.in_fp,PD=pad,SF=scale_filter,Q=self.crf,MAT_L=self.mat_l,PF=ff_pixfmt,CO=coffs,PID=self.pid,PF2=ff_pixfmt_a,Q2=self.acrf,SAO=sao,PRDO=prdo,XP=self.xp)

            self.m4b_cmd_a=r'cd /d %temp% && mp4box -add-image "make.heic.{PID}.hevc":primary:image-size={WxH}{ICC}  -add-image "make.heic.alpha.{PID}.hevc":ref=auxl,1:alpha:image-size={WxH} -brand heic -new "{OUT}" && del "make.heic.alpha.{PID}.hevc"'.format(OUT=self.out_fp,PID=self.pid,ICC=icc_opt,WxH=str(self.probe_res_w)+'x'+str(self.probe_res_h))
        else:
            self.ff_cmd_img=r'ffmpeg -hide_banner -r 1 -i "{INP}" -vf pad={PW}:{PH},untile={UNT},setpts=N/TB,{SF},format={PF} -vsync vfr -r 1 -c:v libx265    -preset 6 -crf {Q} -x265-params    keyint=1:sao={SAO}:ref=1:bframes=0:aq-mode=1:psy-rdoq={PRDO}:cbqpoffs={CO}:crqpoffs={CO}:range=full:colormatrix={MAT_L}:transfer=iec61966-2-1:no-info=1:{XP} "%temp%\make.heic.{PID}.hevc" -y'.format(INP=self.in_fp,PD=pad,SF=scale_filter,Q=self.crf,MAT_L=self.mat_l,PF=ff_pixfmt,CO=coffs,PID=self.pid,PW=self.g_padded_w,PH=self.g_padded_h,UNT=str(self.g_columns)+'x'+str(self.g_rows),SAO=sao,PRDO=prdo,XP=self.xp)

            refs=''
            for x in range(1,self.items+1):
                refs+=f'ref=dimg,{x}:'

            self.m4b_cmd_img=r'cd /d %temp% && mp4box -add-image "make.heic.{PID}.hevc":time=-1:hidden -add-derived-image :type=grid:image-grid-size={GS}:{REFS}primary:image-size={WxH}{ICC} -brand heic -new "{OUT}" && del "make.heic.{PID}.hevc"'.format(OUT=self.out_fp,ICC=icc_opt,PID=self.pid,WxH=str(self.probe_res_w)+'x'+str(self.probe_res_h),GS=str(self.g_rows)+'x'+str(self.g_columns),REFS=refs)
            
            self.ff_cmd_a=r'ffmpeg -hide_banner -r 1 -i "{INP}" -vf pad={PW}:{PH},untile={UNT},setpts=N/TB,{SF},format={PF} -vsync vfr -r 1 -c:v libx265    -preset 6 -crf {Q} -x265-params    keyint=1:sao={SAO}:ref=1:bframes=0:aq-mode=1:psy-rdoq={PRDO}:cbqpoffs={CO}:crqpoffs={CO}:range=full:colormatrix={MAT_L}:transfer=iec61966-2-1:no-info=1:{XP} "%temp%\make.heic.{PID}.hevc" -y -map v:0 -vf pad={PW}:{PH},untile={UNT},setpts=N/TB,extractplanes=a,format={PF2} -vsync vfr -r 1 -c:v libx265 -preset 6 -crf {Q2} -x265-params keyint=1:sao={SAO}:ref=1:bframes=0:aq-mode=1:psy-rdoq={PRDO}:cbqpoffs=1:crqpoffs=1:range=full:colormatrix={MAT_L}:transfer=iec61966-2-1:no-info=1:{XP} "%temp%\make.heic.alpha.{PID}.hevc" -y'.format(INP=self.in_fp,PD=pad,SF=scale_filter,Q=self.crf,MAT_L=self.mat_l,PF=ff_pixfmt,CO=coffs,PID=self.pid,PF2=ff_pixfmt_a,Q2=self.acrf,PW=self.g_padded_w,PH=self.g_padded_h,UNT=str(self.g_columns)+'x'+str(self.g_rows),SAO=sao,PRDO=prdo,XP=self.xp)

            refs2=''
            for x in range(self.items+2,self.items*2+2):
                refs2+=f'ref=dimg,{x}:'

            self.m4b_cmd_a=r'cd /d %temp% && mp4box -add-image "make.heic.{PID}.hevc":time=-1:hidden -add-derived-image :type=grid:image-grid-size={GS}:{REFS}primary:image-size={WxH}{ICC} -add-image "make.heic.alpha.{PID}.hevc":time=-1:hidden -add-derived-image :type=grid:image-grid-size={GS}:{REFS2}ref=auxl,{GID}:alpha:image-size={WxH} -brand heic -new "{OUT}" && del "make.heic.alpha.{PID}.hevc"'.format(OUT=self.out_fp,PID=self.pid,ICC=icc_opt,WxH=str(self.probe_res_w)+'x'+str(self.probe_res_h),GS=str(self.g_rows)+'x'+str(self.g_columns),REFS=refs,GID=self.items+1,REFS2=refs2)

    def encode(self):
        
        if (self.probe_alpha or self.alpha) and not self.noalpha:
            subprocess.run(self.ff_cmd_a,shell=True)
            subprocess.run(self.m4b_cmd_a,shell=True)
        else:
            subprocess.run(self.ff_cmd_img,shell=True)
            subprocess.run(self.m4b_cmd_img,shell=True)
        if self.hasicc:
            subprocess.run(r'del %temp%\make.heic.{PID}.icc'.format(PID=self.pid),shell=True)
        #Delete source file or not?
        if self.delsrc:
            os.remove(self.in_fp)

    def make(self):
        if not self.run_probe():
            return False
        self.cmd_line_gen()
        self.encode()
        return True

def pool_init():
    signal.signal(signal.SIGINT,signal.SIG_IGN)

fail=0
def makeheic_wrapper(args):
    heic = makeheic(*args)
    if not heic.make():
        fail+=1

if __name__ == '__main__':
    #Arguments, ordinary stuff I guess.
    parser = argparse.ArgumentParser(description='HEIC encode script using ffmpeg & mp4box.',formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-q',type=int,required=False,help='Quality(crf), default 21.\n ',default=21)
    parser.add_argument('-o',type=str,required=False,help='Output(s), default input full name (ext. incl.) + ".heic" for file, \ninput main folder path + "_heic" and filename exts. replaced by ".heic" for folder.\n ',nargs='*')
    parser.add_argument('-s',required=False,help='Silent mode, disables "enter to exit".\n ',action='store_true')
    parser.add_argument('-g',required=False,help='Grid mode switch and size, should be 1 or 2 interger(s) in "WxH" format, or False, default False. \nIf only 1 interger is specified, it is used for both W and H. \nOh, and don\'t use the f___ing odd numbers with yuv420, things will be easier. \nMany softwares can\'t open 10bit gridded images, you can try to upgrade them.\n ',default=False)
    parser.add_argument('--delete-src',required=False,help='Delete source file switch, add this argument means "ON".\n ',action='store_true')
    parser.add_argument('--sws',required=False,help='Force to use swscale switch.\n ',action='store_true')
    parser.add_argument('--alpha',required=False,help='Force to try to encode alpha plane switch.\n ',action='store_true')
    parser.add_argument('--no-alpha',required=False,help='Ignore alpha plane switch.\n ',action='store_true')
    parser.add_argument('--alphaq',type=int,required=False,help='Alpha quality(crf), default None(same as -q).\n ',default=None)
    parser.add_argument('--no-icc',required=False,help='Ignore icc profile of source image switch.\n ',action='store_true')
    #New version of libheif seems to decode with matrixs accordingly, so I think it's better to use modern bt709 as default.
    parser.add_argument('-m','--mat',type=str,required=False,help='Matrix used to convert RGB input file, should be either bt709 or bt601 currently. \nIf a input file is in YUV, it\'s original matrix will be "preserved" if this option isn\'t set.\n ',default=None)
    parser.add_argument('-b','--depth',type=int,required=False,help='Bitdepth for hevc-yuv output, default 10.\n ',default=10)
    parser.add_argument('-c','--sample',type=str,required=False,help='Chroma subsumpling for hevc-yuv output, default "444"\n ',default='444')
    parser.add_argument('--sao',required=False,help='Turn SAO off or on, 0 or 1, 0 is off, 1 is on, default 0.\n ',default=None)
    parser.add_argument('--coffs',required=False,help='Chroma QP offset, [-12..12]. Default -2 for 420, 1 for 444. \nUse +n for offset to default(n can be negative).\n ',default=None)
    parser.add_argument('--psy-rdoq',required=False,help='Same with x265, default 8.\n ',default=None)
    parser.add_argument('-sp',required=False,help='A quick switch to set sao=1 coffs=+2 psy-rdoq=1. \nMay be helpful when compressing pictures to a small file size.\n ',action='store_true')
    parser.add_argument('-x265-params',required=False,help='Custom x265 parameters, in ffmpeg style. Appends to parameters set by above arguments.\n ',default='')
    parser.add_argument('--kfs',required=False,help='Keep folder structure.\n ',default=True,action=argparse.BooleanOptionalAction)
    parser.add_argument('-j',type=int,required=False,help='Parallel jobs, default 1. This will make programs\' info output a scramble.\n ',default=1)
    parser.add_argument('INPUTFILE',type=str,help='Input file(s) or folder(s).',nargs='+')
    parser.parse_args(sys.argv[1:],args)
    pid = os.getpid()
    if args.g=='False':
        args.g=False
    if args.sp:
        args.sao = 1
        args.coffs = '+2'
        args.psy_rdoq = 1
    #If you drop a bunch of files or folder to this script this should probably works fine.
    if (args.o != None) and (len(args.INPUTFILE) != len(args.o)):
        raise TypeError('the number of input and output should match if output is specified.')
    
    i=0
    jobs=[]
    for in_fp in args.INPUTFILE:
        in_fp = os.path.abspath(in_fp)
        if os.path.isdir(in_fp):
            dirp=pathlib.Path(in_fp)
            files=[path for path in dirp.rglob('*') if os.path.isfile(path)]
            subdirs=[path for path in dirp.rglob('*') if os.path.isdir(path)]

            if args.o == None:
                out_fp = in_fp + '_heic'
            else:
                out_fp = args.o[i]
                i+=1
                if os.path.exists(out_fp) and not os.path.isdir(out_fp):
                    raise TypeError('folder input\'s corresponding output must be a folder!')
            out_fp = os.path.abspath(out_fp)

            if not os.path.exists(out_fp):
                os.mkdir(out_fp)
            if args.kfs:
                for subdir in subdirs:
                    newdir=str(subdir).replace(in_fp,out_fp)
                    if not os.path.exists(newdir):
                        os.mkdir(newdir)

            for file in files:
                in_fp_sf=str(file)
                if args.kfs:
                    out_fp_sf='.'.join(in_fp_sf.replace(in_fp,out_fp).split('.')[:-1])+'.heic'
                else:
                    out_fp_sf=out_fp+'\\'+file.stem+'.heic'
                jobs.append([in_fp_sf,out_fp_sf,args.q,args.delete_src,args.sws,args.alpha,args.no_alpha,args.alphaq,args.no_icc,args.mat,args.depth,args.sample,args.g,None,args.sao,args.coffs,args.psy_rdoq,args.x265_params])

        else:
            if args.o == None:
                out_fp = in_fp + '.heic'
            else:
                out_fp = args.o[i]
                i+=1
            out_fp = os.path.abspath(out_fp)
            jobs.append([in_fp,out_fp,args.q,args.delete_src,args.sws,args.alpha,args.no_alpha,args.alphaq,args.no_icc,args.mat,args.depth,args.sample,args.g,None,args.sao,args.coffs,args.psy_rdoq,args.x265_params])
    if args.j>1:
        with Pool(processes=args.j,initializer=pool_init) as pool:
            try:
                for x in pool.imap_unordered(makeheic_wrapper,jobs):
                    pass
            except KeyboardInterrupt:
                pass
    else:
        for x in map(makeheic_wrapper,jobs):
            pass

    if args.delete_src:
        for in_fp in args.INPUTFILE:
            in_fp = os.path.abspath(in_fp)
            if os.path.isdir(in_fp):
                dirp=pathlib.Path(in_fp)
                subdirs=[path for path in dirp.rglob('*') if os.path.isdir(path)]
                for subdir in subdirs[::-1]:
                    os.rmdir(subdir)
                os.rmdir(in_fp)

    if not args.s:
        print(fail,'conversion(s) failed.')
        input('enter to exit.')
