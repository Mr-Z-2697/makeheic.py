import os,sys
import argparse
import subprocess
import re
import math
from random import choice
import pathlib
from multiprocessing import Pool
import signal
import tempfile

class makeheic:
    def __init__(self,in_fp,out_fp,crf=18,delsrc=False,sws=False,alpha=False,noalpha=False,acrf=None,noicc=False,mat=None,depth=10,sample='444',grid=False,pid=choice(range(1000,10000)),sao=None,co=None,psy_rdoq=None,xp='',gos=True,tempfolder=None,crft=None,alpbl=0,lpbo=False,scale=[1,1],hwenc='none',exiftr=0,thumbnail=0,trim=[],rgb_color=False):
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
            self.gridF=False
            if grid[0]=='+':
                self.gridF=True
                grid=grid[1:]
            g=grid.split('x')
            if len(g)==1:
                self.gw=self.gh=int(g[0])
            else:
                self.gw=int(g[0])
                self.gh=int(g[1])
        else:
            self.grid=False
            self.gridF=False
        self.gos=gos
        self.medium_img=False
        self.temp_folder=tempfile.gettempdir() if tempfolder==None else tempfolder
        self.crft=crf+6 if crf<=51-6 else 51 if crft==None else crft
        self.alpbl=alpbl
        self.lpbo=lpbo
        self.scale=scale
        self.hwenc=hwenc if hwenc in ['hevc_nvenc','hevc_qsv','hevc_amf'] else None
        self.exiftr=True if exiftr==1 else False
        self.thumbnail=thumbnail
        self.trim=' -ss {S} -to {T}'.format(S=trim[0],T=trim[1]) if len(trim)==2 else ''
        self.rgb_color=rgb_color

    def run_probe(self):
        probe = subprocess.Popen(r'ffprobe -hide_banner -i "{INP}"'.format(INP=self.in_fp),shell=True,stderr=subprocess.PIPE)
        probe_result = probe.stderr.read().decode()
        probe_result = '\n'.join(probe_result.split('\n')[1:])

        if re.search('Could not find codec parameters for stream',probe_result):
            #Quality option only affects compression level for png. 1 is the least compress one can get with IM. Intermedia image doesn't need high compress, but 10 is a nice tradeoff I suppose.
            subprocess.run(r'magick convert -quality 10 "{INP}" "{OUT}.{PID}.%d.png" && ffmpeg -loglevel error -i "{OUT}.{PID}.%d.png" -c apng -compression_level 0 "{OUT}.{PID}.apng"'.format(INP=self.in_fp,OUT=r'{TMPF}\make.heic'.format(TMPF=self.temp_folder),PID=self.pid),shell=True)
            self.src_fp=self.in_fp
            self.in_fp=os.path.abspath(f'{self.temp_folder}\\make.heic.{self.pid}.apng')
            for p in pathlib.Path(self.in_fp).parent.glob(f'make.heic.{self.pid}.*.png'):
                os.remove(p)
            self.medium_img=True
            return self.run_probe()

        #Use extra characters to hopefully ensure that it's grabbing what I want.
        self.probe_codec = re.search('Video: [a-z0-9A-Z]+',probe_result,re.M)
        if self.probe_codec:
            self.probe_codec=self.probe_codec.group()
            #I'm kinda lazy, feel free to add whatever ffmpeg supports.
            if not self.probe_codec[7:] in ('jpegxl','webp','png','mjpeg','bmp','ppm','tiff','gif','apng','h264','hevc','vp8','vp9','av1','mpeg4','mpeg2video','wmv1','wmv2','wmv3'):
                print(r'input file "{INP}" codec not supported.'.format(INP=self.in_fp))
                return False
            #Stupid workaround for non-animated webp with animated webp style metadata
            elif self.probe_codec[7:]=='png' and self.medium_img:
                os.remove(self.in_fp)
                subprocess.run(r'magick convert -quality 10 "{INP}" "{OUT}.{PID}.png"'.format(INP=self.src_fp,OUT=r'{TMPF}\make.heic'.format(TMPF=self.temp_folder),PID=self.pid),shell=True)
                self.in_fp=os.path.abspath(f'{self.temp_folder}\\make.heic.{self.pid}.png')
                self.isseq = False
            elif self.probe_codec[7:] in ('gif','apng','h264','hevc','vp8','vp9','av1','mpeg4','mpeg2video','wmv1','wmv2','wmv3'):
                self.isseq=subprocess.Popen(r'ffprobe -hide_banner -count_packets -print_format csv -select_streams V -show_entries stream=nb_read_packets -threads 4 -i "{INP}"'.format(INP=self.in_fp),shell=True,stdout=subprocess.PIPE).stdout.read()
                self.isseq = not self.isseq==b'stream,1\r\n'
            else:
                self.isseq = False
        else:
            return False

        if not self.noicc and not self.probe_codec[7:] in ('h264','hevc','vp8','vp9','av1','mpeg4','mpeg2video','wmv1','wmv2','wmv3'):
            self.hasicc = not subprocess.run(r'magick "{INP}" "{OUT}.{PID}.icc"'.format(INP=self.in_fp,OUT=r'{TMPF}\make.heic'.format(TMPF=self.temp_folder),PID=self.pid),shell=True).returncode
        else:
            self.hasicc = False

        self.probe_pixfmt = re.search(', yuv[j]*[420]{3}p[0-9]*[lbe]*|, [a]*rgb[albepf0-9]*|, [a]*bgr[albepf0-9]*|, [a]*gbr[albepf0-9]*|, pal8|, gray[0-9flbe]*|, ya[0-9]+[lbe*]',probe_result)
        self.probe_alpha = re.search('yuva4|argb|bgra|rgba|gbra|ya[81]',probe_result)
        if not self.probe_pixfmt:
            print(r'input file "{INP}" pixel format not supported.'.format(INP=self.in_fp))
            return False
        else:
            self.probe_pixfmt = self.probe_pixfmt.group()
        probe_sub = None
        probe_mat = False

        if ', yuv' in self.probe_pixfmt:
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

        if self.rgb_color:
            self.mat_l='gbr'
            self.mat_s='gbr'
            self.mat_a='bt709'
        elif probe_mat and self.mat==None:
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
            width,height=[self.probe_res_w,self.probe_res_h] if self.scale[0]==self.scale[1]==1 else [int(self.probe_res_w*self.scale[0]),int(self.probe_res_h*self.scale[1])]
            self.g_columns=math.ceil(width/self.gw)
            self.g_rows=math.ceil(height/self.gh)
            self.g_padded_w=self.g_columns*self.gw
            self.g_padded_h=self.g_rows*self.gh
            self.items=self.g_columns*self.g_rows
        else:
            self.g_columns=self.g_rows=self.g_padded_h=self.g_padded_w=self.items=1
        return True

    def cmd_line_gen(self):
        icc_opt = r':icc_path=make.heic.{PID}.icc'.format(PID=self.pid) if self.hasicc else ''
        #Use padding if output is subsampled and image w/h not mod by 2
        pad_w=self.probe_w_odd and self.subs_w
        pad_h=self.probe_h_odd and self.subs_h
        if pad_w or pad_h:
            W=self.probe_res_w+pad_w
            H=self.probe_res_h+pad_h
            pad = f'pad={W}:{H},'
            if self.gos and (not self.grid or (self.items==1 and not self.gridF)):
                self.grid=self.gridF=True
                self.g_padded_w=W
                self.g_padded_h=H
                self.g_columns=self.g_rows=self.items=1
        else:
            pad = ''
        #Use swscale to handle scaling and weird "subsampled but not mod by 2" images, and use zimg for better conversion if there's no any resampling(scaling).
        #Or you can manually choose libplacebo, which should do scaling like swscale, but there might be some problems, and due to some limitations I have to make more stupid workarounds.
        c_resubs = (self.probe_subs_w != self.subs_w) or (self.probe_subs_h != self.subs_h)
        ff_pixfmt='yuv{S}p{D}'.format(S=self.sample,D=(str(self.bits) if self.bits>8 else '')) + ('le' if self.bits>8 else '') if not self.rgb_color else 'gbrp'
        ff_pixfmt_a='gray{D}'.format(D=(str(self.bits) if self.bits>8 else '')) + ('le' if self.bits>8 else '') if not self.rgb_color else 'gray'
        if (', gray' in self.probe_pixfmt or ', ya' in self.probe_pixfmt) and not self.lpbo:
            ff_pixfmt=ff_pixfmt_a
        if self.lpbo:
            rs=f'libplacebo=w=round(iw*{self.scale[0]}):h=round(ih*{self.scale[1]}):upscaler=ewa_lanczos:downscaler=catmull_rom:dithering=1,' if not self.scale[0]==self.scale[1]==1 else ''
            scale_filter = r'lut=c3=maxval,hwupload,{RS}libplacebo=format={FMT}:colorspace={MAT_L}:range=full:upscaler=ewa_lanczos:downscaler=catmull_rom:dithering=1,hwdownload'.format(FMT=ff_pixfmt,MAT_L=self.mat_l,RS=rs)
        elif c_resubs or self.sws or ((self.probe_alpha or self.alpha) and self.alpbl) or (not self.scale[0]==self.scale[1]==1):
            scale_filter = r'scale=w=round(iw*{FW}):h=round(ih*{FH}):out_range=pc:flags=spline:gamma=false:out_v_chr_pos={VC}:out_h_chr_pos={HC}:out_color_matrix={MAT_L}{ABL}'.format(MAT_L=self.mat_l,VC=(127 if self.subs_h else 0),HC=(127 if self.subs_w else 0),ABL=':alphablend='+str(self.alpbl) if self.alpbl else '',FW=self.scale[0],FH=self.scale[1])
            
        else:
            scale_filter = r'zscale=r=pc:f=spline36:d=ordered:c=1:m={MAT_S}'.format(MAT_S=self.mat_s if not ', gray' in self.probe_pixfmt or ', ya' in self.probe_pixfmt else 'input')

        if not self.scale[0]==self.scale[1]==1:
            scale_filter_a = r'extractplanes=a,scale=w=round(iw*{FW}):h=round(ih*{FH}):in_range=pc:out_range=pc:flags=spline:gamma=true:out_color_matrix={MAT_A},'.format(MAT_A=self.mat_l if not self.rgb_color else self.mat_a,FW=self.scale[0],FH=self.scale[1],FMT=self.probe_pixfmt[2:])\
                if not self.lpbo else\
                r'hwupload,libplacebo=w=round(iw*{FW}):h=round(ih*{FH}):upscaler=ewa_lanczos:downscaler=catmull_rom:dithering=1,hwdownload,format={FMT},extractplanes=a,'.format(FW=self.scale[0],FH=self.scale[1],FMT=self.probe_pixfmt[2:])
        else:
            scale_filter_a = 'extractplanes=a,'

        coffs = (-2 if self.subs_w and self.subs_h else 1)
        brand='heic' if ff_pixfmt=='yuv420p' else 'heix'
        hwd=' -init_hw_device vulkan=vk:0 -filter_hw_device vk' if self.lpbo else ''
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

        if self.thumbnail:
            if self.hwenc==None:
                tmbn=r' -vf scale={W}:-2,{PD}{SF},format={PF} -map v:0 -frames 1 -c:v libx265 -preset 6 -crf {Q} -x265-params sao={SAO}:ref=1:rc-lookahead=0:bframes=0:aq-mode=1:psy-rdoq={PRDO}:cbqpoffs={CO}:crqpoffs={CO}:range=full:colormatrix={MAT_L}:transfer=iec61966-2-1:no-info=1{XP} "{TMPF}\make.heic.thumb.{PID}.hevc"'
            else:
                tmbn=r' -vf scale={W}:-2,{PD}{SF},format={PF} -map v:0 -frames 1 -c:v {HWE} -color_range pc -colorspace {MAT_L} -bf 0 -qp {Q} "{TMPF}\make.heic.thumb.{PID}.hevc"'
            tmbn=tmbn.format(W=self.thumbnail,PD=pad,SF=scale_filter,PF=ff_pixfmt,Q=self.crf,MAT_L=self.mat_l,SAO=sao,PRDO=prdo,CO=coffs,XP=self.xp,TMPF=self.temp_folder,PID=self.pid,HWE=self.hwenc)
            tmbn_m4b=r'-add-image "{TMPF}\make.heic.thumb.{PID}.hevc":hidden:ref=thmb,{MID} '.format(TMPF=self.temp_folder,PID=self.pid,MID=self.items+1)
            tmbn_del=r' && del "make.heic.thumb.{PID}.hevc"'.format(PID=self.pid)
        else:
            tmbn=''
            tmbn_m4b=''
            tmbn_del=''

        self.et_cmd=rf'exiftool -overwrite_original -tagsFromFile "{self.in_fp}" "{self.out_fp}"'
        refs=refs2=''
        #This isseq thing looks stupid but it's a lot easier for me
        if not self.isseq:
            if not self.grid or (self.items==1 and not self.gridF):
                self.ff_cmd_img=r'ffmpeg -hide_banner{HWD} -r 1 -i "{INP}" -vf {PD}{SF},format={PF} -frames 1 -c:v libx265 -preset 6 -crf {Q} -x265-params sao={SAO}:ref=1:rc-lookahead=0:bframes=0:aq-mode=1:psy-rdoq={PRDO}:cbqpoffs={CO}:crqpoffs={CO}:range=full:colormatrix={MAT_L}:transfer=iec61966-2-1:no-info=1{XP} "{TMPF}\make.heic.{PID}.hevc"{TMBN} -y'

                self.m4b_cmd_img=r'cd /d {TMPF} && mp4box -add-image "make.heic.{PID}.hevc":primary:image-size={WxH}{ICC} {TMBN}-brand {BN} -new "{OUT}" && del "make.heic.{PID}.hevc"{TMBD}'

                self.ff_cmd_a=r'ffmpeg -hide_banner{HWD} -r 1 -i "{INP}" -vf {PD}{SF},format={PF} -frames 1 -c:v libx265 -preset 6 -crf {Q} -x265-params sao={SAO}:ref=1:rc-lookahead=0:bframes=0:aq-mode=1:psy-rdoq={PRDO}:cbqpoffs={CO}:crqpoffs={CO}:range=full:colormatrix={MAT_L}:transfer=iec61966-2-1:no-info=1{XP} "{TMPF}\make.heic.{PID}.hevc" -y -map v:0 -vf {PD}{SFA}format={PF2} -frames 1 -c:v libx265 -preset 6 -crf {Q2} -x265-params sao={SAO}:ref=1:rc-lookahead=0:bframes=0:aq-mode=1:psy-rdoq={PRDO}:cbqpoffs=1:crqpoffs=1:range=full:colormatrix={MAT_A}:transfer=iec61966-2-1:no-info=1{XP} "{TMPF}\make.heic.alpha.{PID}.hevc"{TMBN} -y'

                self.m4b_cmd_a=r'cd /d {TMPF} && mp4box -add-image "make.heic.{PID}.hevc":primary:image-size={WxH}{ICC} -add-image "make.heic.alpha.{PID}.hevc":ref=auxl,1:alpha:image-size={WxH} {TMBN}-brand {BN} -new "{OUT}" && del "make.heic.alpha.{PID}.hevc" && del "make.heic.{PID}.hevc"{TMBD}'
            else:
                self.ff_cmd_img=r'ffmpeg -hide_banner{HWD} -r 1 -i "{INP}" -vf pad={PW}:{PH},untile={UNT},setpts=N/TB,{SF},format={PF} -fps_mode vfr -c:v libx265 -preset 6 -crf {Q} -x265-params keyint=1:sao={SAO}:ref=1:rc-lookahead=0:bframes=0:aq-mode=1:psy-rdoq={PRDO}:cbqpoffs={CO}:crqpoffs={CO}:range=full:colormatrix={MAT_L}:transfer=iec61966-2-1:no-info=1{XP} "{TMPF}\make.heic.{PID}.hevc"{TMBN} -y'

                for x in range(1,self.items+1):
                    refs+=f'ref=dimg,{x}:'

                self.m4b_cmd_img=r'cd /d {TMPF} && mp4box -add-image "make.heic.{PID}.hevc":time=-1:hidden -add-derived-image :type=grid:image-grid-size={GS}:{REFS}primary:image-size={WxH}{ICC} {TMBN}-brand {BN} -new "{OUT}" && del "make.heic.{PID}.hevc"{TMBD}'

                self.ff_cmd_a=r'ffmpeg -hide_banner{HWD} -r 1 -i "{INP}" -vf {SF},pad={PW}:{PH},untile={UNT},setpts=N/TB,format={PF} -fps_mode vfr -c:v libx265 -preset 6 -crf {Q} -x265-params keyint=1:sao={SAO}:ref=1:rc-lookahead=0:bframes=0:aq-mode=1:psy-rdoq={PRDO}:cbqpoffs={CO}:crqpoffs={CO}:range=full:colormatrix={MAT_L}:transfer=iec61966-2-1:no-info=1{XP} "{TMPF}\make.heic.{PID}.hevc" -y -map v:0 -vf {SFA}pad={PW}:{PH},untile={UNT},setpts=N/TB,format={PF2} -fps_mode vfr -c:v libx265 -preset 6 -crf {Q2} -x265-params keyint=1:sao={SAO}:ref=1:rc-lookahead=0:bframes=0:aq-mode=1:psy-rdoq={PRDO}:cbqpoffs=1:crqpoffs=1:range=full:colormatrix={MAT_A}:transfer=iec61966-2-1:no-info=1{XP} "{TMPF}\make.heic.alpha.{PID}.hevc"{TMBN} -y'

                for x in range(self.items+2,self.items*2+2):
                    refs2+=f'ref=dimg,{x}:'

                self.m4b_cmd_a=r'cd /d {TMPF} && mp4box -add-image "make.heic.{PID}.hevc":time=-1:hidden -add-derived-image :type=grid:image-grid-size={GS}:{REFS}primary:image-size={WxH}{ICC} -add-image "make.heic.alpha.{PID}.hevc":time=-1:hidden -add-derived-image :type=grid:image-grid-size={GS}:{REFS2}ref=auxl,{GID}:alpha:image-size={WxH} {TMBN}-brand {BN} -new "{OUT}" && del "make.heic.alpha.{PID}.hevc" && del "make.heic.{PID}.hevc"{TMBD}'
        else:
            #Totally experimental, there's not even any decent pic viewer can decode it so don't expect it to work well. However it is possible to open it with normal video player.
            self.ff_cmd_seq=r'ffmpeg -hide_banner{HWD} -probesize 100M{ST} -i "{INP}" -vf {PD}{SF},format={PF} -c:v libx265 -preset 6 -crf {Q} -fps_mode vfr -x265-params sao={SAO}:rect=0:ctu=32:b-intra=1:weightb=1:strong-intra-smoothing=0:aq-mode=1:psy-rdoq={PRDO}:cbqpoffs={CO}:crqpoffs={CO}:range=full:colormatrix={MAT_L}:transfer=iec61966-2-1:no-info=1{XP} "{TMPF}\make.heic.{PID}.mp4" -y -map v:0 -vf {PD}{SF},format={PF} -frames 1 -c:v libx265 -preset 6 -crf {Q2} -x265-params sao={SAO}:ref=1:rc-lookahead=0:bframes=0:aq-mode=1:psy-rdoq={PRDO}:cbqpoffs={CO}:crqpoffs={CO}:range=full:colormatrix={MAT_L}:transfer=iec61966-2-1:no-info=1{XP} "{TMPF}\make.heic.thumb.{PID}.hevc" -y'.format(INP=self.in_fp,PD=pad,SF=scale_filter,Q=self.crf,MAT_L=self.mat_l,PF=ff_pixfmt,CO=coffs,PID=self.pid,SAO=sao,PRDO=prdo,XP=self.xp,TMPF=self.temp_folder,HWD=hwd,ST=self.trim,Q2=self.crft)

            self.m4b_cmd_seq=r'cd /d {TMPF} && mp4box -add-image "make.heic.thumb.{PID}.hevc":primary{ICC} -brand heis -new "{OUT}" & mp4box -add "make.heic.{PID}.mp4" -brand heis "{OUT}" && del "make.heic.{PID}.mp4" && del "{TMPF}\make.heic.thumb.{PID}.hevc"'.format(OUT=self.out_fp,ICC=icc_opt,PID=self.pid,TMPF=self.temp_folder)
            if self.hwenc==None:
                return True
########################################
        self.ff_cmd_img=self.ff_cmd_img.format(INP=self.in_fp,PD=pad,SF=scale_filter,Q=self.crf,MAT_L=self.mat_l,PF=ff_pixfmt,CO=coffs,PID=self.pid,SAO=sao,PRDO=prdo,XP=self.xp,TMPF=self.temp_folder,HWD=hwd,PW=self.g_padded_w,PH=self.g_padded_h,UNT=str(self.g_columns)+'x'+str(self.g_rows),TMBN=tmbn)
        self.m4b_cmd_img=self.m4b_cmd_img.format(OUT=self.out_fp,ICC=icc_opt,PID=self.pid,WxH=str(int(self.probe_res_w*self.scale[0]))+'x'+str(int(self.probe_res_h*self.scale[1])),BN=brand,TMPF=self.temp_folder,GS=str(self.g_rows)+'x'+str(self.g_columns),REFS=refs,TMBN=tmbn_m4b,TMBD=tmbn_del)

        self.ff_cmd_a=self.ff_cmd_a.format(INP=self.in_fp,PD=pad,SF=scale_filter,Q=self.crf,MAT_L=self.mat_l,PF=ff_pixfmt,CO=coffs,PID=self.pid,PF2=ff_pixfmt_a,Q2=self.acrf,SAO=sao,PRDO=prdo,XP=self.xp,TMPF=self.temp_folder,HWD=hwd,SFA=scale_filter_a,PW=self.g_padded_w,PH=self.g_padded_h,UNT=str(self.g_columns)+'x'+str(self.g_rows),TMBN=tmbn,MAT_A=self.mat_l if not self.rgb_color else self.mat_a)
        self.m4b_cmd_a=self.m4b_cmd_a.format(OUT=self.out_fp,PID=self.pid,ICC=icc_opt,WxH=str(int(self.probe_res_w*self.scale[0]))+'x'+str(int(self.probe_res_h*self.scale[1])),BN=brand,TMPF=self.temp_folder,GS=str(self.g_rows)+'x'+str(self.g_columns),REFS=refs,GID=self.items+1,REFS2=refs2,TMBN=tmbn_m4b,TMBD=tmbn_del)

        if self.hwenc==None:
            return True
########################################

        #I'm lazy so I copy-paste
        if not self.isseq:
            if not self.grid or (self.items==1 and not self.gridF):
                self.ff_cmd_img=r'ffmpeg -hide_banner{HWD} -r 1 -i "{INP}" -vf {PD}{SF},format={PF} -frames 1 -c:v {HWE} -color_range pc -colorspace {MAT_L} -bf 0 -qp {Q} "{TMPF}\make.heic.{PID}.hevc"{TMBN} -y'

                self.m4b_cmd_img=r'cd /d {TMPF} && mp4box -add-image "make.heic.{PID}.hevc":primary:image-size={WxH}{ICC} {TMBN}-brand {BN} -new "{OUT}" && del "make.heic.{PID}.hevc"{TMBD}'

                self.ff_cmd_a=r'ffmpeg -hide_banner{HWD} -r 1 -i "{INP}" -vf {PD}{SF},format={PF} -frames 1 -c:v {HWE} -color_range pc -colorspace {MAT_L} -bf 0 -qp {Q} "{TMPF}\make.heic.{PID}.hevc" -y -map v:0 -vf {PD}{SFA}format={PF2} -frames 1 -c:v {HWE} -color_range pc -colorspace {MAT_L} -bf 0 -qp {Q2} "{TMPF}\make.heic.alpha.{PID}.hevc"{TMBN} -y'

                self.m4b_cmd_a=r'cd /d {TMPF} && mp4box -add-image "make.heic.{PID}.hevc":primary:image-size={WxH}{ICC} -add-image "make.heic.alpha.{PID}.hevc":ref=auxl,1:alpha:image-size={WxH} {TMBN}-brand {BN} -new "{OUT}" && del "make.heic.alpha.{PID}.hevc" && del "make.heic.{PID}.hevc"{TMBD}'
            else:
                self.ff_cmd_img=r'ffmpeg -hide_banner{HWD} -r 1 -i "{INP}" -vf pad={PW}:{PH},untile={UNT},setpts=N/TB,{SF},format={PF} -fps_mode vfr -r 1 -c:v {HWE} -color_range pc -colorspace {MAT_L} -bf 0 -g 1 -qp {Q} "{TMPF}\make.heic.{PID}.hevc"{TMBN} -y'

                refs=''
                for x in range(1,self.items+1):
                    refs+=f'ref=dimg,{x}:'

                self.m4b_cmd_img=r'cd /d {TMPF} && mp4box -add-image "make.heic.{PID}.hevc":time=-1:hidden -add-derived-image :type=grid:image-grid-size={GS}:{REFS}primary:image-size={WxH}{ICC} {TMBN}-brand {BN} -new "{OUT}" && del "make.heic.{PID}.hevc"{TMBD}'

                self.ff_cmd_a=r'ffmpeg -hide_banner{HWD} -r 1 -i "{INP}" -vf {SF},pad={PW}:{PH},untile={UNT},setpts=N/TB,format={PF} -fps_mode vfr -r 1 -c:v {HWE} -color_range pc -colorspace {MAT_L} -bf 0 -g 1 -qp {Q} "{TMPF}\make.heic.{PID}.hevc" -y -map v:0 -vf {SFA}pad={PW}:{PH},untile={UNT},setpts=N/TB,format={PF2} -fps_mode vfr -r 1 -c:v {HWE} -color_range pc -colorspace {MAT_L} -bf 0 -g 1 -qp {Q2} "{TMPF}\make.heic.alpha.{PID}.hevc"{TMBN} -y'

                refs2=''
                for x in range(self.items+2,self.items*2+2):
                    refs2+=f'ref=dimg,{x}:'

                self.m4b_cmd_a=r'cd /d {TMPF} && mp4box -add-image "make.heic.{PID}.hevc":time=-1:hidden -add-derived-image :type=grid:image-grid-size={GS}:{REFS}primary:image-size={WxH}{ICC} -add-image "make.heic.alpha.{PID}.hevc":time=-1:hidden -add-derived-image :type=grid:image-grid-size={GS}:{REFS2}ref=auxl,{GID}:alpha:image-size={WxH} {TMBN}-brand {BN} -new "{OUT}" && del "make.heic.alpha.{PID}.hevc" && del "make.heic.{PID}.hevc"{TMBD}'
        else:
            #Totally experimental, there's not even any decent pic viewer can decode it so don't expect it to work well. However it is possible to open it with normal video player.
            self.ff_cmd_seq=r'ffmpeg -hide_banner{HWD} -probesize 100M{ST} -i "{INP}" -vf {PD}{SF},format={PF} -c:v {HWE} -color_range pc -colorspace {MAT_L} -qp {Q} -fps_mode vfr "{TMPF}\make.heic.{PID}.mp4" -y -map v:0 -vf {PD}{SF},format={PF} -frames 1 -c:v {HWE} -color_range pc -colorspace {MAT_L} -bf 0 -qp {Q2} "{TMPF}\make.heic.thumb.{PID}.hevc" -y'.format(INP=self.in_fp,PD=pad,SF=scale_filter,Q=self.crf,MAT_L=self.mat_l,PF=ff_pixfmt,CO=coffs,PID=self.pid,SAO=sao,PRDO=prdo,XP=self.xp,TMPF=self.temp_folder,HWD=hwd,HWE=self.hwenc,ST=self.trim,Q2=self.crft)

            self.m4b_cmd_seq=r'cd /d {TMPF} && mp4box -add-image "make.heic.thumb.{PID}.hevc":primary{ICC} -brand heis -new "{OUT}" & mp4box -add "make.heic.{PID}.mp4" -brand heis "{OUT}" && del "make.heic.{PID}.mp4" && del "{TMPF}\make.heic.thumb.{PID}.hevc"'.format(OUT=self.out_fp,ICC=icc_opt,PID=self.pid,TMPF=self.temp_folder)

            return True
########################################
        self.ff_cmd_img=self.ff_cmd_img.format(INP=self.in_fp,PD=pad,SF=scale_filter,Q=self.crf,MAT_L=self.mat_l,PF=ff_pixfmt,CO=coffs,PID=self.pid,SAO=sao,PRDO=prdo,XP=self.xp,TMPF=self.temp_folder,HWD=hwd,HWE=self.hwenc,PW=self.g_padded_w,PH=self.g_padded_h,UNT=str(self.g_columns)+'x'+str(self.g_rows),TMBN=tmbn)
        self.m4b_cmd_img=self.m4b_cmd_img.format(OUT=self.out_fp,ICC=icc_opt,PID=self.pid,WxH=str(int(self.probe_res_w*self.scale[0]))+'x'+str(int(self.probe_res_h*self.scale[1])),BN=brand,TMPF=self.temp_folder,GS=str(self.g_rows)+'x'+str(self.g_columns),REFS=refs,TMBN=tmbn_m4b,TMBD=tmbn_del)

        self.ff_cmd_a=self.ff_cmd_a.format(INP=self.in_fp,PD=pad,SF=scale_filter,Q=self.crf,MAT_L=self.mat_l,PF=ff_pixfmt,CO=coffs,PID=self.pid,PF2=ff_pixfmt_a,Q2=self.acrf,SAO=sao,PRDO=prdo,XP=self.xp,TMPF=self.temp_folder,HWD=hwd,SFA=scale_filter_a,HWE=self.hwenc,PW=self.g_padded_w,PH=self.g_padded_h,UNT=str(self.g_columns)+'x'+str(self.g_rows),TMBN=tmbn,MAT_A=self.mat_l if not self.rgb_color else self.mat_a)
        self.m4b_cmd_a=self.m4b_cmd_a.format(OUT=self.out_fp,PID=self.pid,ICC=icc_opt,WxH=str(int(self.probe_res_w*self.scale[0]))+'x'+str(int(self.probe_res_h*self.scale[1])),BN=brand,TMPF=self.temp_folder,GS=str(self.g_rows)+'x'+str(self.g_columns),REFS=refs,GID=self.items+1,REFS2=refs2,TMBN=tmbn_m4b,TMBD=tmbn_del)
        return True
########################################

    def encode(self):
        err=0
        if self.isseq:
            err+=subprocess.run(self.ff_cmd_seq,shell=True).returncode
            err+=subprocess.run(self.m4b_cmd_seq,shell=True).returncode
        elif (self.probe_alpha or self.alpha) and not self.noalpha:
            err+=subprocess.run(self.ff_cmd_a,shell=True).returncode
            err+=subprocess.run(self.m4b_cmd_a,shell=True).returncode
        else:
            err+=subprocess.run(self.ff_cmd_img,shell=True).returncode
            err+=subprocess.run(self.m4b_cmd_img,shell=True).returncode
        if self.hasicc:
            err+=subprocess.run(r'del {TMPF}\make.heic.{PID}.icc'.format(PID=self.pid,TMPF=self.temp_folder),shell=True).returncode
        if self.exiftr:
            err+=subprocess.run(self.et_cmd,shell=True).returncode
        if self.medium_img:
            os.remove(self.in_fp)
        #Delete source file or not?
        if err==0 and os.path.exists(self.out_fp):
            if self.delsrc:
                if self.medium_img:
                    os.remove(self.src_fp)
                else:
                    os.remove(self.in_fp)
        return err

    def make(self):
        if not self.run_probe():
            return False
        self.cmd_line_gen()
        if self.encode():
            return False
        return True

def pool_init():
    signal.signal(signal.SIGINT,signal.SIG_IGN)

fail=0
def makeheic_wrapper(args):
    global fail
    heic = makeheic(*args)
    if not heic.make():
        fail+=1

if __name__ == '__main__':
    #Arguments, ordinary stuff I guess.
    parser = argparse.ArgumentParser(description='HEIC encode script using ffmpeg & mp4box.',formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-q',type=float,required=False,help='Quality(crf), default 18.\n ',
                        default=18)
    parser.add_argument('-o',type=str,required=False,help='Output(s), default input full name (ext. incl.) + ".heic" for file, \ninput main folder path + "_heic" and filename exts. replaced by ".heic" for folder.\n ',nargs='*')
    parser.add_argument('-s',required=False,help='Silent mode, disables "enter to exit".\n ',
                        action='store_true')
    parser.add_argument('-g',required=False,help='Grid mode switch and size, should be 1 or 2 interger(s) in "WxH" format, or False, default False. \nIf only 1 interger is specified, it is used for both W and H. \nOh, and don\'t use the f___ing odd numbers with yuv420, things will be easier. \nMany softwares can\'t open 10bit gridded images, you can try to upgrade them.\n ',
                        default=False)
    parser.add_argument('--delete-src',required=False,help='Delete source file switch.\n ',
                        default=False,action=argparse.BooleanOptionalAction)
    parser.add_argument('--sws',required=False,help='Force to use swscale switch.\n ',
                        default=False,action=argparse.BooleanOptionalAction)
    parser.add_argument('--alpha',required=False,help='Force to try to encode alpha plane switch.\n ',
                        action='store_true')
    parser.add_argument('--no-alpha',required=False,help='Ignore alpha plane switch.\n ',
                        action='store_true')
    parser.add_argument('--alphaq',type=int,required=False,help='Alpha quality(crf), default None(same as -q).\n ',
                        default=None)
    parser.add_argument('--icc',required=False,help='Ignore icc profile of source image switch.\n ',
                        default=True,action=argparse.BooleanOptionalAction)
    #New version of libheif seems to decode with matrixs accordingly, so I think it's better to use modern bt709 as default.
    parser.add_argument('-m','--mat',type=str,required=False,help='Matrix used to convert RGB input file, should be either bt709 or bt601 currently. \nIf a input file is in YUV, it\'s original matrix will be "preserved" if this option isn\'t set.\n ',
                        default=None)
    parser.add_argument('-b','--depth',type=int,required=False,help='Bitdepth for hevc-yuv output, default 10.\n ',
                        default=10)
    parser.add_argument('-c','--sample',type=str,required=False,help='Chroma subsumpling for hevc-yuv output, default "444"\n ',
                        default='444')
    parser.add_argument('--rgb-color',required=False,help='Use RGB instead of YUV. No affect on alpha channel.\n ',
                        default=False,action=argparse.BooleanOptionalAction)
    parser.add_argument('--sao',required=False,help='Turn SAO off or on, 0 or 1, 0 is off, 1 is on, default 0.\n ',
                        default=None)
    parser.add_argument('--coffs',required=False,help='Chroma QP offset, [-12..12]. Default -2 for 420, 1 for 444. \nUse +n for offset to default(n can be negative).\n ',
                        default=None)
    parser.add_argument('--psy-rdoq',required=False,help='Same with x265, default 8.\n ',
                        default=None)
    parser.add_argument('--sp',required=False,help='A quick switch to set sao=1 coffs=+2 psy-rdoq=1. \nMay be helpful when compressing pictures to a small file size.\n ',
                        default=False,action=argparse.BooleanOptionalAction)
    parser.add_argument('-x265-params',required=False,help='Custom x265 parameters, in ffmpeg style. Appends to parameters set by above arguments.\n ',
                        default='')
    parser.add_argument('--kfs',required=False,help='Keep folder structure.\n ',
                        default=True,action=argparse.BooleanOptionalAction)
    parser.add_argument('--sf',required=False,help='Include subfolder or not.\n ',
                        default=True,action=argparse.BooleanOptionalAction)
    parser.add_argument('--skip',required=False,help='Skip existing output file.\n ',
                        default=False,action=argparse.BooleanOptionalAction)
    parser.add_argument('--gos',required=False,help='Auto single-grid odd res and subsampled images if grid isn\'t specified and effective. \nThis script does "pad and set res" anyway, but for some weird reason add a single-grid \nmake more software to recognize the specified res. Default may change in the future.\n ',
                        default=True,action=argparse.BooleanOptionalAction)
    parser.add_argument('-j',type=int,required=False,help='Parallel jobs, default 1. This will make programs\' info output a scramble.\n ',
                        default=1)
    parser.add_argument('-tmb',type=int,required=False,help='Create thumbnail for image, set number for auto-scale thumbnail width(px), 0 to disable. \nDefault 0. This differs from sequence thumnail.\n ',
                        default=0)
    parser.add_argument('-qtm',type=str,required=False,help='Sequence image thumbnail quality. Experimental. Default q+6.\n ',
                        default=None)
    parser.add_argument('-tmpf',type=str,required=False,help='Temp folder location. Default automatic find system temp folder.\n ',
                        default=None)
    parser.add_argument('-alpbl','--alphablend',type=int,required=False,help='Alphablend when encoding rgb channels of transparent image, default 0.\n ',
                        default=0)
    parser.add_argument('--lpbo',required=False,help='Use libplacebo to handle the color space conversion, default false.\n ',
                        default=False,action=argparse.BooleanOptionalAction)
    parser.add_argument('-scale',type=str,required=False,help='Scale factor, can be a number for both W&H or comma seperated two numbers for each (W,H).\n Range is 0~1, Default 1,1.\n ',
                        default='1,1')
    parser.add_argument('-hwenc',type=str,required=False,help='Seriously? Don\'t.\n ',
                        default='none')
    parser.add_argument('-e','--exiftr',type=int,required=False,help='Transfer EXIF, set 1/0 for on/off, default 0(off).\n ',
                        default=0)
    parser.add_argument('--fast',required=False,help='Some x265 parameter tweaks, will affect compression ratio, \nbut make encoding faster up to 6 times than default.\n ',
                        default=False,action=argparse.BooleanOptionalAction)
    parser.add_argument('-st','--seqtrim',type=str,required=False,help='Trim input when encoding sequence. For example "60,65" means encode 60s to 65s of input.\n ',
                        default='')
    parser.add_argument('INPUTFILE',type=str,help='Input file(s) or folder(s).',nargs='+')
    args=parser.parse_args(sys.argv[1:])
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
    args.scale = [float(x) for x in args.scale.split(',')]
    args.scale.append(args.scale[0])
    args.icc = not args.icc
    if args.fast:
        args.x265_params = args.x265_params + ':rdoq-level=0:min-cu-size=32:max-tu-size=8'
    if args.q == -1:
        args.x265_params = args.x265_params + ':lossless=1'
    if args.x265_params != '':
        if args.x265_params[0] != ':':
            args.x265_params = ':' + args.x265_params
    args.seqtrim = args.seqtrim.split(',')
    if len(args.seqtrim)!=2:
        args.seqtrim=[]

    i=0
    jobs=[]
    for in_fp in args.INPUTFILE:
        in_fp = os.path.abspath(in_fp)
        if os.path.isdir(in_fp):
            dirp=pathlib.Path(in_fp)
            if args.sf:
                files=[path for path in dirp.rglob('*') if os.path.isfile(path)]
                subdirs=[path for path in dirp.rglob('*') if os.path.isdir(path)]
            else:
                files=[path for path in dirp.glob('*') if os.path.isfile(path)]
                subdirs=[]

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
                if args.skip and os.path.exists(out_fp_sf):
                    continue
                jobs.append([in_fp_sf,out_fp_sf,args.q,args.delete_src,args.sws,args.alpha,args.no_alpha,args.alphaq,args.icc,args.mat,args.depth,args.sample,args.g,None,args.sao,args.coffs,args.psy_rdoq,args.x265_params,args.gos,args.tmpf,args.qtm,args.alphablend,args.lpbo,args.scale,args.hwenc,args.exiftr,args.tmb,args.seqtrim,args.rgb_color])

        else:
            if args.o == None:
                out_fp = in_fp + '.heic'
            else:
                out_fp = args.o[i]
                i+=1
            out_fp = os.path.abspath(out_fp)
            if args.skip and os.path.exists(out_fp):
                continue
            jobs.append([in_fp,out_fp,args.q,args.delete_src,args.sws,args.alpha,args.no_alpha,args.alphaq,args.icc,args.mat,args.depth,args.sample,args.g,None,args.sao,args.coffs,args.psy_rdoq,args.x265_params,args.gos,args.tmpf,args.qtm,args.alphablend,args.lpbo,args.scale,args.hwenc,args.exiftr,args.tmb,args.seqtrim,args.rgb_color])

    if args.j>1 and len(jobs):
        with Pool(processes=args.j,initializer=pool_init) as pool:
            try:
                for x in pool.imap_unordered(makeheic_wrapper,jobs):
                    pass
            except KeyboardInterrupt:
                pass
    elif len(jobs):
        for x in map(makeheic_wrapper,jobs):
            pass

    if args.delete_src:
        for in_fp in args.INPUTFILE:
            in_fp = os.path.abspath(in_fp)
            if os.path.isdir(in_fp):
                dirp=pathlib.Path(in_fp)
                subdirs=[path for path in dirp.rglob('*') if os.path.isdir(path)] if args.sf else []
                for subdir in subdirs[::-1]:
                    try:
                        os.rmdir(subdir)
                    except:
                        pass
                try:
                    os.rmdir(in_fp)
                except:
                    pass

    print(fail,'conversion(s) failed.')
    # if not args.s:
    #     input('enter to exit.')
