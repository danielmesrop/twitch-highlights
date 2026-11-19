---
name: twitch-highlights
description: Find and cut highlight clips from a Twitch or Kick streamer's VODs (rage, screaming, laughing, big reactions) and render them as 9:16 facecam-over-gameplay shorts with captions. Use when the user gives a Twitch or Kick channel or VOD link, or asks to clip Twitch/Kick streams or streamer highlights.
---

# Twitch & Kick Highlights

Pipeline: VOD audio → loudness peaks → transcribe candidates → user picks → cut video → 9:16 stack → captions.
Needs yt-dlp, ffmpeg, whisper, and the clipify skill (for `build_ass.py`). Work in `/tmp/twitch/`.

## 1. Pick the VOD
Channel given → list recent VODs and let the user choose (ask Twitch or Kick if unclear):
- Twitch: `yt-dlp --flat-playlist -I 1:5 --print "%(url)s | %(duration_string)s | %(title).70s" "https://www.twitch.tv/CHANNEL/videos?filter=archive&sort=time"`
- Kick: same command with `"https://kick.com/CHANNEL/videos"`. Strip the `#__youtubedl_smuggle...` tail from the printed URLs.
VOD links look like `https://www.twitch.tv/videos/ID` or `https://kick.com/CHANNEL/videos/UUID`. Subscriber-only VODs won't download; say so.
Everything below is identical for both sites. Ignore yt-dlp's "impersonation" and "subtitle tracks" warnings on Kick.

## 2. Find candidates from the audio
```bash
yt-dlp -q -f Audio_Only/160p/worst -o /tmp/twitch/audio.%(ext)s "$VOD"   # Kick has no audio-only, so 160p; ~1-3 min per 4 h; add --download-sections "*1:00:00-2:00:00" for a range, then pass --offset 3600
python3 <skill-dir>/scripts/find_peaks.py /tmp/twitch/audio.mp4 --top 15 > /tmp/twitch/peaks.json
```
Peaks = moments much louder than the surrounding 3 minutes. Each is `{peak, start, end, score}` in VOD seconds (default 20 s build-up + 10 s reaction).

## 3. Check what's actually happening
For each candidate, cut its audio from audio.mp4 (`ffmpeg -ss START -t DUR`) and run `whisper --model tiny.en --output_format txt`. Drop music, alerts/donation sounds, ads and silence. Keep rage, screams, laughs, funny lines. Show the user a short list: time, score, one-line quote, suggested title. Let them pick and adjust start/end.

## 4. Cut the video (only the chosen sections)
```bash
yt-dlp -q -f 720p60/720p/best --download-sections "*START-END" -o /tmp/twitch/clip_N.%(ext)s "$VOD"
```

## 5. Vertical layout: facecam on top, gameplay below
Grab one frame, find the facecam box (x,y,w,h in source pixels), and verify it with `drawbox` (two tries max). Avoid the chat overlay.
```bash
ffmpeg -y -i clip_N.mp4 -filter_complex "[0:v]split=2[a][b];[a]crop=CW:CH:CX:CY,scale=1080:-2,crop=1080:min(ih\,826)[cam];[b]crop=ih*1080/1094:ih:(iw-ih*1080/1094)/2:0,scale=1080:1094[game];[cam]pad=1080:826:0:(oh-ih)/2[c2];[c2][game]vstack,fps=30[v]" -map "[v]" -map 0:a -c:v libx264 -preset fast -crf 20 -pix_fmt yuv420p -c:a aac -b:a 160k stacked_N.mp4
```
No facecam → plain center crop to 9:16 (`crop=ih*9/16:ih,scale=1080:1920`). If the action is off-center, shift the gameplay crop's x.

## 6. Captions
```bash
whisper stacked_N.mp4 --model tiny.en --word_timestamps True --output_format json --output_dir /tmp/twitch --language en
python3 ~/.claude/skills/clipify/scripts/build_ass.py /tmp/twitch/stacked_N.json /tmp/twitch/cap_N.ass opus
sed -i 's/,280,1$/,860,1/' /tmp/twitch/cap_N.ass   # put captions on the seam between cam and game
ffmpeg -y -i stacked_N.mp4 -vf "subtitles=/tmp/twitch/cap_N.ass" -c:v libx264 -preset fast -crf 20 -c:a copy OUT.mp4
```

## 7. Deliver
Save to `./stream_clips/CHANNEL_VODID/` with readable names. One line per clip: title, length, why it's good. Check a frame of each output before saying it's done.
Remind the user once: posting another streamer's clips needs their permission (many have clipping programs). Never upload anything yourself.

## Limits
Chat-based detection isn't available; this uses audio only. Quiet funny moments get missed, so offer to transcribe a whole range when the user wants a specific bit.
