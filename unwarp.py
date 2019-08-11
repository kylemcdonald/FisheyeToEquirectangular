import os
import argparse
import shutil
import errno

import ffmpeg
import numpy as np
from tqdm import tqdm

from fisheye import FisheyeToEquirectangular
from utils.imutil import imresize, imwrite

def get_tmp_audio(tmp_folder, fn):
    os.makedirs(tmp_folder, exist_ok=True)
    basename = os.path.basename(fn)
    return os.path.join(tmp_folder, f'{basename}.wav')

def get_tmp_video(tmp_folder, fn):
    os.makedirs(tmp_folder, exist_ok=True)
    basename = os.path.basename(fn)
    return os.path.join(tmp_folder, basename)

def print_meta(fn, meta):
    video_stream = get_stream(meta, 'video')
    audio_stream = get_stream(meta, 'audio')
    print(fn)
    print(f'  video: {video_stream["width"]}x{video_stream["height"]} @ {video_stream["avg_frame_rate"]}')
    print('  audio: ' + ('yes' if audio_stream else 'no'))
    for key in 'duration start_time'.split(' '):
        print(f'  {key}: {video_stream[key]}')

def get_meta(fn):
    if not os.path.exists(fn):
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), fn)
    return ffmpeg.probe(fn)

def get_stream(meta, codec_type):
    for stream in meta['streams']:
        if stream['codec_type'] == codec_type:
            return stream
    return None

def get_input_process(fn, width, height, fps, target_width, target_height, target_fps, vframes):
    process = ffmpeg.input(fn)
    if fps != f'{target_fps}/1':
        process = process.filter('fps', fps=target_fps)
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

def main():
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
    parser.add_argument('--preview', action='store_true',
        help='Save a .png of the first frame for reference.')
    parser.add_argument('-v', '--verbose', action='store_true')

    args = parser.parse_args()

    left_meta = get_meta(args.left_video)
    left_video_stream = get_stream(left_meta, 'video')
    left_width, left_height = left_video_stream['width'], left_video_stream['height']
    left_fps = left_video_stream['avg_frame_rate']

    right_meta = get_meta(args.right_video)
    right_video_stream = get_stream(right_meta, 'video')
    right_width, right_height = right_video_stream['width'], right_video_stream['height']
    right_fps = right_video_stream['avg_frame_rate']

    if args.verbose:
        print_meta(args.left_video, left_meta)
        print_meta(args.right_video, right_meta)

    left_duration = float(left_video_stream['duration']) - args.skip_left / args.frame_rate
    right_duration = float(right_video_stream['duration']) - args.skip_right / args.frame_rate
    max_duration = min(left_duration, right_duration)
    
    if args.duration is None:
        if args.verbose:
            print(f'No duration specified. Using maximum duration {max_duration} seconds')
        args.duration = max_duration

    if args.duration > max_duration:
        if args.verbose:
            print(f'Duration {args.duration} seconds is too long, using maximum duration {max_duration} seconds')
        args.duration = max_duration

    n_frames = int(args.frame_rate * args.duration)
    input_width = max(left_width, right_width)
    input_height = max(left_height, right_height)

    left_process = get_input_process(args.left_video,
        left_width, left_height, left_fps,
        input_width, input_height, args.frame_rate,
        args.skip_left + n_frames)
    
    right_process = get_input_process(args.right_video,
        right_width, right_height, right_fps,
        input_width, input_height, args.frame_rate,
        args.skip_right + n_frames)

    out_process = (
        ffmpeg
        .input('pipe:', format='rawvideo', pix_fmt='rgb24', s=f'{args.height*2}x{args.height}')
        .output(get_tmp_video(args.tmp_folder, args.output), preset=args.preset, pix_fmt='yuv420p', vcodec=args.vcodec)
        .global_args('-hide_banner', '-nostats', '-loglevel', 'panic')
        .overwrite_output()
        .run_async(pipe_stdin=True)
    )

    byte_count = input_width * input_height * 3

    unwarp = FisheyeToEquirectangular(args.height, input_width, args.blending)

    if args.skip_left:
        if args.verbose:
            print(f'Skipping left frames: {args.skip_left}')
        for i in tqdm(range(args.skip_left)):
            left_process.stdout.read(byte_count)

    if args.skip_right:
        if args.verbose:
            print(f'Skipping right frames: {args.skip_right}')
        for i in tqdm(range(args.skip_right)):
            right_process.stdout.read(byte_count)

    if args.verbose:
        print(f'Warping frames: {n_frames}')

    for i in tqdm(range(n_frames)):
        left_bytes = left_process.stdout.read(byte_count)
        right_bytes = right_process.stdout.read(byte_count)

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
            .reshape([input_height, input_width, 3])
        )
        
        right_frame = (
            np
            .frombuffer(right_bytes, np.uint8)
            .reshape([input_height, input_width, 3])
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

        if args.preview and i == 0:
            if args.verbose:
                print('Saving preview frame...')
            imwrite(args.output + '.png', out_frame)

    if args.verbose:
        print('Closing all processes...')
    left_process.stdout.close()
    right_process.stdout.close()
    out_process.stdin.close()
    if args.verbose:
        print('Waiting for all processes to finish...')
    left_process.wait()
    right_process.wait()
    out_process.wait()

    filenames = [args.left_video, args.right_video]
    metas = [left_meta, right_meta]
    skips = [args.skip_left, args.skip_right]
    in_audio = []
    for fn, meta, skip in zip(filenames, metas, skips):
        if not get_stream(meta, 'audio'):
            if args.verbose:
                print('No audio from', fn)
            continue

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

        skip_seconds = skip / args.frame_rate
        in_audio.append(
            ffmpeg
            .input(tmp_fn)
            .filter('atrim', start=skip_seconds)
            .filter('asetpts', 'PTS-STARTPTS')
        )

    video_tmp = get_tmp_video(args.tmp_folder, args.output)
    in_video = ffmpeg.input(video_tmp)

    if len(in_audio) == 0:
        if args.verbose:
            print('No audio channels, using video directly.')
        shutil.copy(video_tmp, args.output)

    if len(in_audio) == 1:
        if args.verbose:
            print('Merging video and single audio channel into', args.output)
            
        (
            ffmpeg
            .output(in_video.video, in_audio[0], args.output, shortest=None, vcodec='copy')
            .global_args('-hide_banner', '-nostats', '-loglevel', 'panic')
            .overwrite_output()
            .run()
        )

    if len(in_audio) == 2:
        if args.verbose:
            print('Merging video and two audio channels into', args.output)
            
        (
            ffmpeg
            .filter(in_audio, 'join', inputs=2, channel_layout='stereo')
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

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        # https://github.com/kkroening/ffmpeg-python/issues/108
        os.system('stty echo')
