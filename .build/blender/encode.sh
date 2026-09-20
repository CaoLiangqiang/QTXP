#!/bin/bash
# 把 Blender 渲出的帧序列合成为 mp4 / GIF，并把效果图转成适合网页与仓库的 JPEG。
# 用法：bash .build/blender/encode.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$ROOT/.build/renders"
OUT="$ROOT/renders"
mkdir -p "$OUT"

# 字体路径含空格，ffmpeg 滤镜里转义麻烦，先复制到无空格路径
FONT=/tmp/qtxp_cjk.ttc
cp "/System/Library/Fonts/Hiragino Sans GB.ttc" "$FONT"

# 注意：drawtext 的 text 里不能出现未转义的冒号，它会被当成选项分隔符，
# 所以这里用等号代替（11→8 = 42m 而不是 11→8:42m）
NOTE="上海 冬至 9-15时 ｜ 楼间距由日照数据反推 11→8 = 42m、8→5 = 30m ｜ 示意模型"

echo "=== 1/4 日照动画 mp4 ==="
# 时间标签由帧号算出：9 时起、每帧 5 分钟
ffmpeg -hide_banner -loglevel error -y -framerate 12 -i "$SRC/sun/%04d.png" \
  -vf "drawtext=fontfile=$FONT:text='冬至日照 %{eif\:9+floor(n*5/60)\:d\:2}\:%{eif\:mod(n*5\,60)\:d\:2}':fontcolor=white:fontsize=44:borderw=3:bordercolor=black@0.7:x=36:y=30,\
drawtext=fontfile=$FONT:text='$NOTE':fontcolor=white@0.82:fontsize=22:borderw=2:bordercolor=black@0.6:x=36:y=h-46,\
format=yuv420p" \
  -c:v libx264 -crf 20 -preset slow -movflags +faststart "$OUT/冬至日照动画.mp4"

echo "=== 2/4 日照动画 gif ==="
ffmpeg -hide_banner -loglevel error -y -framerate 12 -i "$SRC/sun/%04d.png" \
  -vf "drawtext=fontfile=$FONT:text='冬至 %{eif\:9+floor(n*5/60)\:d\:2}\:%{eif\:mod(n*5\,60)\:d\:2}':fontcolor=white:fontsize=40:borderw=3:bordercolor=black@0.7:x=28:y=24,\
scale=900:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=192[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3" \
  -loop 0 "$OUT/冬至日照动画.gif"

echo "=== 3/4 环绕 mp4 + gif ==="
ffmpeg -hide_banner -loglevel error -y -framerate 24 -i "$SRC/turn/%04d.png" \
  -vf "format=yuv420p" -c:v libx264 -crf 20 -preset slow -movflags +faststart "$OUT/环绕.mp4"
ffmpeg -hide_banner -loglevel error -y -framerate 20 -i "$SRC/turn/%04d.png" \
  -vf "scale=760:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=160[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3" \
  -loop 0 "$OUT/环绕.gif"

echo "=== 4/4 效果图转 JPEG ==="
# 匹配所有「两位数字_名字.png」的成品，既含 01..05 分析图也含 10..12 气氛图
for f in "$SRC"/[0-9][0-9]_*.png; do
  b="$(basename "$f" .png)"
  ffmpeg -hide_banner -loglevel error -y -i "$f" -vf "scale=1920:-1:flags=lanczos" -q:v 3 "$OUT/$b.jpg"
done

rm -f "$FONT"
echo
ls -lh "$OUT"
