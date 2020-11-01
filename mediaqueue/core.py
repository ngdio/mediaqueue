import click
import json
from pathlib import Path
from PIL import Image
import pycountry
import re
import shlex
import subprocess
import time
import traceback
import youtube_dl

SUB_LANGUAGES = ['en', 'en-US', 'en-UK', 'en-us', 'en-uk', 'de', 'de-DE', 'de-de', 'un']

ytops = {
    'outtmpl': '{}.%(ext)s',
    'hls_prefer_native': True,
    'nocheckcertificate': True,
    'writesubtitles': True,
    'subtitleslangs': SUB_LANGUAGES,
    'subtitlesformat': 'srt/vtt',
    'keepvideo': True,
    'skip_unavailable_fragments': False,
    'writethumbnail': True,
    'fixup': 'never',
    'socket_timeout': 10,
    'postprocessors': [
        {
            'key': 'FFmpegSubtitlesConvertor',
            'format': 'srt',
        },
    ],
}

ytdl = youtube_dl.YoutubeDL(ytops)

@click.command()
@click.argument('file', type=click.Path(exists=True))
@click.option('-v', '--verbose', is_flag=True)
def main(file, verbose):
    file_path = Path(file)
    with file_path.open('r') as f:
        links = f.read().splitlines()

    done_path = file_path.with_suffix('.done')
    if not done_path.is_file():
        done_path.touch()

    with done_path.open('r') as f:
        done = f.read().splitlines()
    done = [int(i) for i in done if i.isdigit()]

    path_forced_info = file_path.with_suffix('.forced.json')
    if path_forced_info.is_file():
        with path_forced_info.open('r') as f:
            forced_info = json.load(f)
    else:
        forced_info = {}

    for index, link in enumerate(links):
        if index in done:
            continue
        if not link or not link.startswith('http'):
            continue

        print('[Queue] Processing link #{}'.format(index))

        # path_video = Path('{}.mp4'.format(index))
        # path_subs = Path('{}.en.srt'.format(index))
        # path_thumb_jpg = Path('{}.jpg'.format(index))
        # path_thumb_png = Path('{}.png'.format(index))
        # if path_video.is_file() and path_subs.is_file() and (path_thumb_jpg.is_file() or path_thumb_png.is_file()):
        #     print('[Queue] All files for #{} already exist, proceed to muxing')
        # else:
        
        result = False
        while not result:
            info = download(index, link, verbose)
            if info:
                info = {**info, **forced_info}
                result = mux(index, info)
                if result:
                    with done_path.open('a+') as f:
                        f.write(str(index) + '\n')

                # source_files = Path('.').glob('{}.*'.format(id))
                # for file in source_files:
                #     file.unlink()


def download(id, url, verbose=False, rewrite_info=False):
    ytdl = youtube_dl.YoutubeDL(ytops)
    ytdl.params['outtmpl'] = ytops['outtmpl'].format(id)
    try:
        info_path = Path('{}.info.json'.format(id))
        if not rewrite_info and info_path.is_file():
            with info_path.open('r') as f:
                info = json.load(f)
        else:
            info = ytdl.extract_info(url, download=False)
            with info_path.open('w') as f:
                json.dump(info, f)

        ytdl.process_info(info)
    except:
        if verbose:
            traceback.print_exc()
        print("[Queue] Download of item #{} failed. Try again in 30".format(id))
        time.sleep(30)
        return None
    return info

def alpha3(alpha2):
    return pycountry.languages.get(alpha_2=alpha2[0:2]).alpha_3

def mux(id, info):
    fix_aac = False

    paths_video = []
    paths_audio = []
    if 'requested_formats' in info and info['requested_formats']:
        for format in info['requested_formats']:
            path = Path('{}.f{}.{}'.format(id, format['format_id'], format['ext']))
            if format['vcodec'] != 'none':
                paths_video.append(path)
            if format['acodec'] != 'none':
                lang = format.get('language') or info.get('language') or 'en'
                paths_audio.append((path if path not in paths_video else None, alpha3(lang)))
                if format['acodec'].startswith('mp4a'):
                    fix_aac = True
    else:
        paths_video.append(Path('{}.{}'.format(id, info['ext'])))
        paths_audio.append((None, info.get('language') or 'en'))
        if 'acodec' in info and info['acodec'].startswith('mp4a'):
            fix_aac = True

    if not paths_video and not paths_audio:
        print('[Queue] Muxing failed because no video/audio files were found.')
        return False

    # Determine which subtitles are available for muxing
    available_subs = [i for i in info['subtitles'] if i in SUB_LANGUAGES] if 'subtitles' in info else []

    paths_sub = []
    for lang in available_subs:
        path_sub = Path('{}.{}.vtt'.format(id, lang))
        if not path_sub.is_file():
            path_sub = Path('{}.{}.srt'.format(id, lang))
            if path_sub.is_file():
                pass #fix_srt(path_sub)
            else:
                path_sub = None
        if path_sub:
            if lang == 'un':
                lang = 'en'
            paths_sub.append((path_sub, alpha3(lang)))

    # Check if thumbnail was downloaded
    orig_path_thumb = Path('{}.jpg'.format(id))
    if not orig_path_thumb.is_file():
        orig_path_thumb = Path('{}.png'.format(id))
        if not orig_path_thumb.is_file():
            orig_path_thumb = None
    
    # Check if the thumbnail's resolution is high enough
    if orig_path_thumb:
        with Image.open(orig_path_thumb) as img:
            if img.size[1] < 480:
                orig_path_thumb = None

    # Determine mime type of thumbnail
    if orig_path_thumb:
        if orig_path_thumb.suffix == '.jpg':
            thumb_mime = 'image/jpeg'
        elif orig_path_thumb.suffix == '.png':
            thumb_mime = 'image/png'
        else:
            orig_path_thumb = None

    # Rename thumbnail file to 'thumbnail'
    if orig_path_thumb:
        path_thumb = Path('thumbnail{}'.format(orig_path_thumb.suffix))
        orig_path_thumb.rename(path_thumb)
    else:
        path_thumb = None

    if 'movie' in info and info['movie'] == True:
        title = info['title']
        path_final = Path('{}.mkv'.format(title))
    else:
        if 'episode' not in info or not info['episode']:
            if 'title' in info and info['title']:
                info['episode'] = info['title']
            else:
                info['episode'] = 'EPISODE'
        if 'season_number' not in info or not info['season_number']:
            print('\a')
            info['season_number'] = click.prompt(
                'No season number found. Please specify for episode "{}"'.format(info['episode']),
                default=0)
        r = re.match(r'(?:(?:Episode|Folge|Part) )*(?P<nr>\d+)(?:/\d)*', info['episode'])
        if r and info['title'] != info['episode']:
            info['episode'] = info['title']
        if 'series' not in info or not info['series']:
            info['series'] = 'SERIES'

        info['episode'] = re.sub(r'( \(?\d+/\d+\)?)$', '', info['episode'])
        info['episode'] = info['episode'].replace('Season {}'.format(info['season_number']), '')
        info['episode'] = info['episode'].replace(info['series'], '')
        info['episode'] = info['episode'].replace(' - ', '')
        info['episode'] = info['episode'].strip()

        if 'episode_number' not in info or not info['episode_number']:
            if r and r['nr'].isdigit():
                info['episode_number'] = int(r['nr'])
            else:
                print('\a')
                info['episode_number'] = click.prompt(
                    'No episode number found. Please specify for episode "{}"'.format(info['episode']),
                    default=100 + id)
        if 'episode_offset' in info and info['episode_offset'] is not None:
            info['episode_number'] += info['episode_offset']

        title = '{series} - {season_number}x{episode_number:02d} - {episode}'.format(**info)
        path_final = Path('{}/{}.mkv'.format(info['season_number'], title))

    if path_final.is_file():
        path_final.unlink()
    path_final.parent.mkdir(exist_ok=True)

    cmd = 'ffmpeg'
    for path_video in paths_video:
        cmd += ' -i {}'.format(shlex.quote(str(path_video.absolute())))
    for path_audio in paths_audio:
        if path_audio[0]:
            cmd += ' -i {}'.format(shlex.quote(str(path_audio[0].absolute())))
    if paths_sub:
        for path_sub in paths_sub:
            cmd += ' -i {}'.format(shlex.quote(str(path_sub[0].absolute())))
            
    chapters = info.get('chapters', [])
    if chapters:
        path_chapters = Path('{}.meta'.format(id))
        with path_chapters.open('w') as f:
            def ffmpeg_escape(txt):
                return re.sub(r'(=|;|#|\\|\n)', r'\\\1', txt)

            metadata_file_content = ';FFMETADATA1\n'
            for chapter in chapters:
                metadata_file_content += '[CHAPTER]\nTIMEBASE=1/1000\n'
                metadata_file_content += 'START=%d\n' % (chapter['start_time'] * 1000)
                metadata_file_content += 'END=%d\n' % (chapter['end_time'] * 1000)
                chapter_title = chapter.get('title')
                if chapter_title:
                    metadata_file_content += 'title=%s\n' % ffmpeg_escape(chapter_title)
            f.write(metadata_file_content)
            cmd += ' -i "{}" -map_metadata 1'.format(path_chapters.absolute())

    cmd += ' -c:v copy -bsf:v "filter_units=remove_types=6" -c:a copy'
    if fix_aac:
        cmd += ' -bsf:a aac_adtstoasc'
    if paths_sub:
        cmd += ' -c:s copy'
    for index, path_video in enumerate(paths_video):
        cmd += ' -disposition:v:{} +default'.format(index)
    for index, path_audio in enumerate(paths_audio):
        cmd += ' -metadata:s:a:{} language={}'.format(index, path_audio[1])
        cmd += ' -disposition:a:{} +default'.format(index)
    if paths_sub:
        for index, path_sub in enumerate(paths_sub):
            cmd += ' -metadata:s:s:{} language={}'.format(index, path_sub[1])
    if path_thumb:
        cmd += ' -attach {} -metadata:s:t mimetype={}'.format(shlex.quote(str(path_thumb.absolute())), thumb_mime)
    cmd += ' -metadata title={}'.format(shlex.quote(title))
    if 'description' in info:
        cmd += ' -metadata description={}'.format(shlex.quote(info['description']))
        cmd += ' -metadata comment={}'.format(shlex.quote(info['description']))
        cmd += ' -metadata summary={}'.format(shlex.quote(info['description']))
        cmd += ' -metadata synopsis={}'.format(shlex.quote(info['description']))
            
    cmd += ' -y {}'.format(shlex.quote(str(path_final.absolute())))

    print('[Queue] Mux #{}: "{}"'.format(id, cmd))

    proc = subprocess.run(cmd, shell=True)

    if path_thumb:
        path_thumb.rename(orig_path_thumb)

    if proc.returncode != 0:
        print('[Queue]] Muxing #{} failed.'.format(id))
        return False
    
    print('[Queue] #{} successfully muxed.'.format(id))
    return True


def fix_srt(path):
    print("[Queue] Fix corrupted SRT conversion")
    with path.open('r', encoding='utf-8-sig') as f:
        srt = f.read().split('\n')

    i = 0
    while i < len(srt):
        if srt[i]:
            if srt[i].isdigit():
                i += 1
                if re.match(r'[0-9][0-9]:[0-9][0-9]:[0-9][0-9],[0-9][0-9][0-9] --> [0-9][0-9]:[0-9][0-9]:[0-9][0-9],[0-9][0-9][0-9]', srt[i]):
                    i += 1
                    while srt[i+1]:
                        srt[i] += '<br />' + srt[i+1]
                        del srt[i+1]
        i += 1
    
    with path.open('w', encoding='utf-8-sig') as f:
        f.write('\n'.join(srt))
