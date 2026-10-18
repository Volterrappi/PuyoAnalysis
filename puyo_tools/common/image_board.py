"""Best-effort screenshot-to-board recognition, with manually selected crop.

The screenshot may show 12 visible rows or all 13. Classify the colored
*body* of each puyo, avoiding the white eyes in the upper half of the cell.
"""
import colorsys
from collections import Counter
from statistics import median

# HSV hue references. In Puyo eSports yellow bodies are orange-yellow,
# typically hue 0.09..0.15 (rather than pure yellow at 0.167).
HUES = {'R': 0.0, 'Y': 0.12, 'G': 0.32, 'B': 0.59, 'P': 0.77}


def classify_rgb(rgb):
    """Classify a single RGB pixel; useful for synthetic tests and fallbacks."""
    r, g, b = (int(v) / 255 for v in rgb[:3])
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if v < 0.20:
        return '.'
    if s < 0.18:
        return 'O' if v > 0.48 else '.'
    if v < 0.28:
        return '.'
    # Explicit orange-yellow boundary; the old nearest-hue boundary at .075
    # incorrectly assigned orange shadows of yellow puyos to red.
    if 0.055 <= h < 0.22:
        return 'Y'
    return min(HUES, key=lambda c: min(abs(h - HUES[c]), 1 - abs(h - HUES[c])))


def _sample_cell(rgb, left, top, right, bottom):
    """Vote on saturated body pixels, avoiding eyes, borders and background."""
    w, h = right - left, bottom - top
    votes = Counter()
    # Most reliable eSports body colors occur just below the white eyes.
    # Include several horizontal offsets for cells with mouth/shine details.
    for fy in (0.58, 0.66, 0.73, 0.80):
        for fx in (0.28, 0.39, 0.50, 0.61, 0.72):
            x = max(0, min(rgb.width - 1, int(left + fx * w)))
            y = max(0, min(rgb.height - 1, int(top + fy * h)))
            p = rgb.getpixel((x, y))
            hh, ss, vv = colorsys.rgb_to_hsv(*(k / 255 for k in p))
            if vv < .25 or ss < .30:
                continue
            label = classify_rgb(p)
            if label in HUES:
                votes[label] += 1
    if votes:
        return votes.most_common(1)[0][0]
    # No colorful pixels: neutral ojama or dark empty cell. The median over
    # a small central patch avoids single white pixels from highlights.
    pixels = []
    for fy in (.40, .50, .60):
        for fx in (.38, .50, .62):
            x = max(0, min(rgb.width - 1, int(left + fx * w)))
            y = max(0, min(rgb.height - 1, int(top + fy * h)))
            pixels.append(rgb.getpixel((x, y)))
    med = tuple(median(p[k] for p in pixels) for k in range(3))
    return classify_rgb(med)


def _sample_board_cell(rgb,left,top,right,bottom,cross_cell=False):
    """Require a body-sized foreground patch, rather than a few colored pixels.

    Estimate the local background from cell corners. The denser lower-body
    grid rejects thin X marks and leaves NEXT's existing sampler unchanged.
    """
    w,h=right-left,bottom-top
    def pixel(fx,fy):
        x=max(0,min(rgb.width-1,int(left+fx*w)))
        y=max(0,min(rgb.height-1,int(top+fy*h)))
        return rgb.getpixel((x,y))
    corners=[pixel(x,y) for x,y in ((.07,.07),(.93,.07),(.07,.93),(.93,.93),
                                   (.07,.20),(.93,.20),(.07,.80),(.93,.80))]
    background=tuple(median(p[k] for p in corners) for k in range(3))
    labels=[];votes=Counter()
    for fy in (.42,.50,.58,.66,.74,.82):
        line=[]
        for fx in (.20,.30,.40,.50,.60,.70,.80):
            p=pixel(fx,fy)
            label=classify_rgb(p) if max(abs(p[k]-background[k]) for k in range(3))>=30 else '.'
            line.append(label)
            if label!='.':votes[label]+=1
        labels.append(line)
    # Require several filled 2x2 patches: eyes/highlights may interrupt a body,
    # while an isolated pixel or a narrow diagonal must not become a puyo.
    for label,amount in votes.most_common():
        blocks=sum(all(labels[y+dy][x+dx]==label for dy in (0,1) for dx in (0,1))
                   for y in range(5) for x in range(6))
        wide_body=False
        for line in labels[3:]:
            run=0
            for value in line:
                run=run+1 if value==label else 0
                if run>=4:wide_body=True
        if amount>=9 and blocks>=3 and wide_body:
            if cross_cell and label=='R':
                # The rotating death marker can be as broad as a red puyo.
                # At column3/row12 alone, require positive eye/highlight
                # evidence on the upper body; uncertain red stays empty.
                # Do not inspect the top border or the neighboring cell.
                whites=[]
                for fy in (.20,.26,.32,.38,.44,.50):
                    line=[]
                    for fx in (.25,.3125,.375,.4375,.50,.5625,.625,.6875,.75):
                        p=pixel(fx,fy)
                        _,sat,value=colorsys.rgb_to_hsv(*(channel/255 for channel in p))
                        line.append(min(p)>=170 and sat<=.30 and value>=.72)
                    whites.append(line)
                white_count=sum(sum(line) for line in whites)
                adjacent=any(line[x] and line[x+1] for line in whites for x in range(8))
                if white_count<3 or not adjacent:return '.'
            return label
    return '.'


def recognize_board(image, crop, visible_rows=12):
    """Return 13x6 character rows from PIL image and crop (l,t,r,b)."""
    if visible_rows not in (12, 13):
        raise ValueError('visible_rows must be 12 or 13')
    left, top, right, bottom = map(int, crop)
    if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
        raise ValueError('Crop must be within image bounds and have positive area')
    if right - left < 12 or bottom - top < visible_rows * 2:
        raise ValueError('Crop is too small')
    rgb = image.convert('RGB')
    rows = [['.'] * 6 for _ in range(13)]
    offset = 13 - visible_rows
    for r in range(visible_rows):
        for c in range(6):
            x0 = left + c * (right - left) / 6
            x1 = left + (c + 1) * (right - left) / 6
            y0 = top + r * (bottom - top) / visible_rows
            y1 = top + (r + 1) * (bottom - top) / visible_rows
            rows[r + offset][c] = _sample_board_cell(rgb, x0, y0, x1, y1,
                                                   cross_cell=(r+offset==1 and c==2))
    return [''.join(row) for row in rows]


def recognize_esports_next(image, crop, player='1P'):
    """Read NEXT and DOUBLE NEXT on the standard Puyo Puyo eSports layout.

    The 1P previews lie to the right of its field; 2P previews to the left.
    Return [NEXT, DOUBLE NEXT], each encoded axis (lower) then child (upper).
    Coordinates were calibrated from a 1649x928 eSports screenshot and scale
    with the selected field's six-column width and visible-row height.
    """
    left, top, right, bottom = map(float, crop)
    width = (right-left)/6
    height = (bottom-top)/12  # normal eSports visible field is 12 rows
    if width <= 0 or height <= 0 or player not in ('1P','2P'):
        return ['..','..']
    sign = 1 if player == '1P' else -1
    rgb = image.convert('RGB')
    pairs=[]
    # First pair: near upper side; second: stepped toward the centre.
    # Relative offsets measured from the top-right/top-left field corner.
    for xoff, upper_y, lower_y, diameter in (
        (1.30, 0.53, 1.55, 0.75),
        (2.02, 2.63, 3.45, 0.68),
    ):
        cx = (right if sign == 1 else left) + sign*xoff*width
        labels=[]
        for yoff in (lower_y, upper_y):
            cy = top + yoff*height
            radius = min(width,height)*diameter/2
            if cx-radius < 0 or cx+radius >= rgb.width or cy-radius < 0 or cy+radius >= rgb.height:
                labels.append('.')
            else:
                label = _sample_cell(rgb,cx-radius,cy-radius,cx+radius,cy+radius)
                labels.append(label if label in HUES else '.')
        pairs.append(''.join(labels))
    return pairs
