"""Conservative source-image aspect ratio based field suggestions.
All rectangles use original image pixels; users can override them.
"""
def suggest(width, height):
    if width <= 0 or height <= 0: return {}
    ratio = width / height
    def rect(fracs):
        return tuple(round(x * width if i % 2 == 0 else x * height) for i,x in enumerate(fracs))
    # Standalone board: 6 columns x 12 or 13 rows, often cropped tightly.
    if 0.43 <= ratio <= 0.61:
        return {"1P": (rect((0.02,0.02,0.98,0.98)), 12, "盤面単体に近い縦横比")}
    # 16:9 entire Puyo Puyo eSports playfield, approximate on purpose.
    if 1.65 <= ratio <= 1.92:
        return {
            "1P": (rect((0.14,0.18,0.365,0.885)), 12, "16:9ゲーム画面の1P候補"),
            "2P": (rect((0.635,0.18,0.86,0.885)), 12, "16:9ゲーム画面の2P候補"),
        }
    return {}
