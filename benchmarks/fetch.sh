#!/usr/bin/env bash
# Download the benchmark footage and music (free licences, archive.org) into $1 (default: bench_data).
# Licences: see benchmarks/HISTORY_FA.md. Needs curl and ffmpeg.
set -e
D=${1:-bench_data}; mkdir -p "$D/src" "$D/ref"; cd "$D"
A=https://archive.org/download
get() { [ -s "$2" ] || curl -sL --fail -o "$2" "$1"; }
# Set 1 (tuning set): snowboard (CC0, minute 5:00-7:30) + parkour POV (CC BY 3.0)
[ -s src/snow.mp4 ] || ffmpeg -v error -ss 300 -t 150 -i "$A/the-univited-three-snowboarding/The%20Uninvited.mp4" -c copy src/snow.mp4
get "$A/youtube-qCmCHokphb4/qCmCHokphb4.mp4" src/parkour.mp4
# Velocity references (Public Domain Mark)
for f in "Speed Ramp Velocity" "Velocity capcut template" "Fire Velocity capcut template " "Speed Velocity Capcut Template"; do
  n=$(echo "$f" | tr -d ' '); get "$A/car-edit-velocity/$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$f.mp4")" "ref/$n.mp4"
done
# Set 2 (new footage, never used for tuning): lion dance + surf (CC BY 2.0), BMX 15 fps (CC BY 2.0), skate (CC BY-SA 3.0)
get "$A/Flickr-8011137199/$(curl -s https://archive.org/metadata/Flickr-8011137199 | python3 -c 'import sys,json;print([x["name"] for x in json.load(sys.stdin)["files"] if x["name"].lower().endswith(".mp4")][0])')" src/Flickr-8011137199.mp4
get "$A/Flickr-4875043276/2010_US_Open_of_Surfing_-_Final_Heat-4875043276.mp4" src/Flickr-4875043276.mp4
get "$A/Flickr-4103865318/$(curl -s https://archive.org/metadata/Flickr-4103865318 | python3 -c 'import sys,json;print([x["name"] for x in json.load(sys.stdin)["files"] if x["name"].lower().endswith(".mp4")][0])')" src/Flickr-4103865318.mp4
get "$A/RandolfeWicker-BMXFLATLANDACTION258/RandolfeWicker-BMXFLATLANDACTION258_512kb.mp4" src/bmx.mp4
get "$A/gagepresidioskate1/gagepresidioskate1.mov" src/skate.mov
# Music: 104 BPM (from SpeedVelocity) and ~140 BPM (from Fire)
[ -s music104.wav ] || ffmpeg -v error -i ref/SpeedVelocityCapcutTemplate.mp4 -vn -ac 2 -ar 44100 music104.wav
[ -s music140.wav ] || ffmpeg -v error -i ref/FireVelocitycapcuttemplate.mp4 -vn -ac 2 -ar 44100 music140.wav
echo "data in $D"
