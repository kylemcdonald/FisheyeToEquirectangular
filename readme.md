# FisheyeToEquirectangular

Scripts for converting pairs of Hikvision fisheye videos to equirectangular videos.

# Install

Install ffmpeg, OpenCV, and a few Python libraries.

```
$ brew install ffmpeg
$ brew install python3
$ brew tap homebrew/science
$ brew install opencv3 --with-contrib --with-python3
$ pip3 install numpy tqdm ffmpeg-python
```

This might be easier with [Anaconda](https://www.anaconda.com/distribution/) which comes with Python3 and numpy already.

You also need some Python utils:

```
$ git clone git@github.com:kylemcdonald/python-utils.git utils
```

# Usage

Searching for files:

```
$ python find.py -i /media/kyle/EXPORT/ -t "6/26/2019 18:23:00" -c 3 4
/media/kyle/EXPORT/ch03_20190626181035.mp4 +745 seconds
/media/kyle/EXPORT/ch04_20190626181114.mp4 +706 seconds
Extract near beginning of files:
  -l /media/kyle/EXPORT/ch03_20190626181035.mp4 --skip_left 936 -r /media/kyle/EXPORT/ch04_20190626181114.mp4 --skip_right 0
Extract from 6/26/2019 18:23:00:
  -l /media/kyle/EXPORT/ch03_20190626181035.mp4 --skip_left 17880 -r /media/kyle/EXPORT/ch04_20190626181114.mp4 --skip_right 16944
```

These parameters can be pasted into the unwarper:

```
python unwarp.py \
    -o out.mp4 \
    -l /media/kyle/EXPORT/ch03_20190626181035.mp4 --skip_left 936 \
    -r /media/kyle/EXPORT/ch04_20190626181114.mp4 --skip_right 0 \
    -d 10
```

This will output a 10 second clip from near the beginning of the file.

If the audio isn't perfectly synced, you might need to open the clip in an audio editor and find how many frames offset the audio is. Then adjust the skip amounts accordingly.