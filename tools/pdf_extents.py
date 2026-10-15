"""Report page count and lowest text position per page (dev aid for fitting copy without shrinking fonts)."""
import sys
import pymupdf

for f in sys.argv[1:]:
    d = pymupdf.open(f)
    print(f, "pages:", len(d))
    for i, p in enumerate(d):
        body = [b for b in p.get_text("blocks") if b[3] < p.rect.height - 48 and b[1] > 48]
        print(f"  p{i+1}: lowest body text y={max((b[3] for b in body), default=0):.0f} of limit {p.rect.height-50:.0f}; blocks={len(body)}")
