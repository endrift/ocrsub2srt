import os
import sys
import subprocess
import tempfile

FFMPEG = 'ffmpeg'
FFPROBE = 'ffprobe'
TESSERACT = 'tesseract'

FOOTER = b'\0\0\0\0IEND\xae\x42\x60\x82'

tesseract_command = [TESSERACT, '-l', 'eng', '--dpi', '200', '--oem', '0', 'pnglist.txt', 'frames']
rate = (20, 1)

def frames_to_time(frame):
    ms = (frame * 1000 * rate[1] // rate[0]) % 1000
    s = (frame * rate[1] // rate[0]) % 60
    m = (frame * rate[1] // rate[0] // 60) % 60
    h = frame * rate[1] // rate[0] // 3600
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'


def process_frame_list(frame_list, srt, seq, text, text_start):
    with open('pnglist.txt', 'wt') as f:
        for i in frame_list:
            print(f'frame{i:06d}.png', file=f)

    out = subprocess.run(tesseract_command, input=png, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for i in frame_list:
        os.remove(f'frame{i:06d}.png')
    os.remove('pnglist.txt')

    with open('frames.txt', 'rt') as f:
        out = f.read()
        lines = out.split('\f')
        for i, line in zip(frame_list, lines):
            if line != text:
                if text:
                    print(seq, file=srt)
                    seq += 1
                    print(frames_to_time(text_start), '-->', frames_to_time(i - 1), file=srt)
                    print(text, file=srt)
                text = line
                text_start = i

    os.remove('frames.txt')
    srt.flush()
    return seq, text, text_start


for fname in sys.argv[1:]:
    ffprobe_command = [FFPROBE, '-of', 'default=nk=1:nw=1', '-show_entries', 'format=duration', fname]
    out = subprocess.run(ffprobe_command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    time = out.stdout.decode().strip()
    ffmpeg_command = [FFMPEG,
                      '-i', fname,
                      '-f', 'lavfi',
                      '-t', time,
                      '-r', f'{rate[0]}/{rate[1]}',
                      '-i', f'color=color=black:size=1280x720:r={rate[0]}/{rate[1]},format=rgb24',
                      '-filter_complex', '[0:s]scale=w=1280:h=-1[s];[1:v][s]overlay=eof_action=endall,format=rgb24[v]',
                      '-map', '[v]',
                      '-an',
                      '-c:v', 'png',
                      '-compression_level', '1',
                      '-f', 'rawvideo',
                      'pipe:1']

    proc = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    buffer = b''
    frame = 0
    seq = 1
    text = ''
    text_start = None
    frame_list = []
    last_png = None

    with open(os.path.splitext(fname)[0] + '.srt', 'wt') as srt:
        while proc.poll() is None:
            eof = buffer.find(FOOTER)
            if eof < 0:
                buffer += proc.stdout.read(4096)
                continue
            png = buffer[:eof + len(FOOTER)]
            buffer = buffer[eof + len(FOOTER):]
            if png != last_png:
                frame_list.append(frame)
                last_png = png
                with open(f'frame{frame:06d}.png', 'wb') as f:
                    f.write(png)
            frame += 1

            if len(frame_list) >= 50:
                seq, text, text_start = process_frame_list(frame_list, srt, seq, text, text_start)
                print(frames_to_time(frame), file=sys.stderr)
                frame_list = []

        if frame_list:
            process_frame_list(frame_list, srt, seq, text, text_start)
