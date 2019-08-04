import os
import argparse
import shutil
import subprocess

import ffmpeg
import numpy as np
from tqdm import tqdm

from fisheye import FisheyeToEquirectangular
from utils.imutil import imresize

def get_tmp_audio(tmp_folder, fn):
    os.makedirs(tmp_folder, exist_ok=True)
    basename = os.path.basename(fn)
    return os.path.join(tmp_folder, f'{basename}.wav')

def get_tmp_video(tmp_folder, fn):
    os.makedirs(tmp_folder, exist_ok=True)
    basename = os.path.basename(fn)
    return os.path.join(tmp_folder, basename)

def print_meta(fn, meta):
    print(fn)
    print(f'  {meta["width"]}x{meta["height"]} @ {meta["avg_frame_rate"]}')
    for key in 'duration start_time'.split(' '):
        print(f'  {key}: {meta[key]}')

def get_meta(fn):
    return ffmpeg.probe(fn)['streams'][0]

def get_input_process(fn, width, height, fps, target_width, target_height, target_fps, vframes):
    process = ffmpeg.input(fn)
    if fps != target_fps:
        process = process.filter('fps', fps=24)
    if width != target_width or height != target_height:
        process = process.filter('scale', target_width, target_height)
    extra = {}
    if vframes:
        extra['vframes'] = vframes
    process = (
        process
        .output('pipe:', format='rawvideo', pix_fmt='rgb24', **extra)
        .global_args('-hide_banner', '-nostats', '-loglevel', 'panic')
        .run_async(pipe_stdout=True)
    )
    return process

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        epilog='Usage: python unwarp.py -l ch01.mp4 -r ch02.mp4 -d 10 -o warped.mp4'
    )

    parser.add_argument('-l', '--left_video', type=str,
        help='Left video filename', required=True)
    parser.add_argument('--skip_left', type=int,
        help='Left video frames to skip', default=0)
    parser.add_argument('-r', '--right_video', type=str,
        help='Right video filename', required=True)
    parser.add_argument('--skip_right', type=int,
        help='Right video frames to skip', default=0)
    parser.add_argument('-o', '--output', type=str,
        help='Output video filename', required=True)
    parser.add_argument('--height', type=int,
        help='Output video height', default=2048)
    parser.add_argument('--frame_rate', type=int,
        help='Output video frame rate', default=24)
    parser.add_argument('--blending', type=int,
        help='Blending area in pixels', default=16)
    parser.add_argument('--aperture', type=float,
        help='Ratio of the camera FOV to image size', default=1)
    parser.add_argument('--preset', type=str,
        help='ffmpeg output video codec preset', default='ultrafast')
    parser.add_argument('-d', '--duration', type=float,
        help='Duration in seconds, uses entire video if ommitted')
    parser.add_argument('--vcodec', type=str,
        help='ffmpeg output video codec', default='libx264')
    parser.add_argument('--fisheye', action='store_true',
        help='Output raw fisheye pair, do not unwarp')
    parser.add_argument('--tmp_folder', type=str,
        help='Location of temp folder.', default='.tmp')
    parser.add_argument('-v', '--verbose', action='store_true')

    args = parser.parse_args()

    left_meta = get_meta(args.left_video)
    left_width, left_height = left_meta['width'], left_meta['height']
    left_fps = left_meta['avg_frame_rate']

    right_meta = get_meta(args.right_video)
    right_width, right_height = right_meta['width'], right_meta['height']
    right_fps = right_meta['avg_frame_rate']

    if args.verbose:
        print_meta(args.left_video, left_meta)
        print_meta(args.right_video, right_meta)

    n_frames = int(args.frame_rate * args.duration) if args.duration else None
    target_fps = f'{args.frame_rate}/1'
    input_width = max(left_width, right_width)
    input_height = max(left_height, right_height)

    left_process = get_input_process(args.left_video,
        left_width, left_height, left_fps,
        input_width, input_height, target_fps,
        args.skip_left + n_frames if n_frames else None)
    
    right_process = get_input_process(args.right_video,
        right_width, right_height, right_fps,
        input_width, input_height, target_fps,
        args.skip_right + n_frames if n_frames else None)

    out_process = (
        ffmpeg
        .input('pipe:', format='rawvideo', pix_fmt='rgb24', s=f'{args.height*2}x{args.height}')
        .output(get_tmp_video(args.tmp_folder, args.output), preset=args.preset, pix_fmt='yuv420p', vcodec=args.vcodec)
        .global_args('-hide_banner', '-nostats', '-loglevel', 'panic')
        .overwrite_output()
        .run_async(pipe_stdin=True)
    )

    left_byte_count = left_width * left_height * 3
    right_byte_count = right_width * right_height * 3

    unwarp = FisheyeToEquirectangular(args.height, input_width, args.blending)

    if args.verbose:
        print(f'Skipping frames: left {args.skip_left} / right {args.skip_right}')
    skip_max = max(args.skip_left, args.skip_right)
    for i in tqdm(range(skip_max)):
        if i < args.skip_left:
            left_process.stdout.read(left_byte_count)
        if i < args.skip_right:
            right_process.stdout.read(right_byte_count)

    if args.verbose:
        print(f'Warping frames: {n_frames}')

    for i in tqdm(range(n_frames)):
        left_bytes = left_process.stdout.read(left_byte_count)
        right_bytes = right_process.stdout.read(right_byte_count)

        if not left_bytes:
            if args.verbose:
                print(f'Reached end of {args.left_video}')
            break
            
        if not right_bytes:
            if args.verbose:
                print(f'Reached end of {args.right_video}')
            break
            
        left_frame = (
            np
            .frombuffer(left_bytes, np.uint8)
            .reshape([left_height, left_width, 3])
        )
        
        right_frame = (
            np
            .frombuffer(right_bytes, np.uint8)
            .reshape([right_height, right_width, 3])
        )
        
        if args.fisheye:
            out_frame = np.hstack((
                imresize(left_frame, output_wh=(args.height, args.height)),
                imresize(right_frame, output_wh=(args.height, args.height))
            ))
        else:
            out_frame = unwarp.unwarp_pair(left_frame, right_frame)

        out_process.stdin.write(
            out_frame
            .astype(np.uint8)
            .tobytes()
        )

    left_process.wait()
    right_process.wait()
    out_process.stdin.close()
    out_process.wait()

    for fn in [args.left_video, args.right_video]:
        tmp_fn = get_tmp_audio(args.tmp_folder, fn)
        if args.verbose:
            print('Re-encoding audio from', fn, 'to', tmp_fn)
        (
            ffmpeg
            .input(fn)
            .output(tmp_fn)
            .global_args('-hide_banner', '-nostats', '-loglevel', 'panic')
            .overwrite_output()
            .run()
        )

    skip_left_seconds = args.skip_left / args.frame_rate
    skip_right_seconds = args.skip_right / args.frame_rate

    left_tmp = get_tmp_audio(args.tmp_folder, args.left_video)
    in_audio_left = (
        ffmpeg
        .input(left_tmp)
        .filter('atrim', start=skip_left_seconds)
        .filter('asetpts', 'PTS-STARTPTS')
    )

    right_tmp = get_tmp_audio(args.tmp_folder, args.right_video)
    in_audio_right = (
        ffmpeg
        .input(right_tmp)
        .filter('atrim', start=skip_right_seconds)
        .filter('asetpts', 'PTS-STARTPTS')
    )

    video_tmp = get_tmp_video(args.tmp_folder, args.output)
    in_video = ffmpeg.input(video_tmp)

    if args.verbose:
        print('Merging input:')
        print('  ', left_tmp)
        print('  ', right_tmp)
        print('  ', video_tmp)
        print('Output:')
        print('  ', args.output)
        
    (
        ffmpeg
        .filter((in_audio_left, in_audio_right), 'join', inputs=2, channel_layout='stereo')
        .output(in_video.video, args.output, shortest=None, vcodec='copy')
        .global_args('-hide_banner', '-nostats', '-loglevel', 'panic')
        .overwrite_output()
        .run()
    )

    if args.verbose:
        print('Finished encoding')

    if args.verbose:
        print('Removing folder', args.tmp_folder)

    if os.path.exists(args.tmp_folder):
        shutil.rmtree(args.tmp_folder)

    # https://github.com/kkroening/ffmpeg-python/issues/108
    subprocess.run(['stty', 'echo'])