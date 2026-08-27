"""
Dev-only helper: renders PPTX slides to PNG using local PowerPoint via COM
automation, so slide layout/overlap issues can be visually inspected
without a human opening the file. Not part of the health check tool
itself - just a verification aid.

Usage:
    python tools/render_preview.py <path-to-pptx> [output_dir] [--slides 1,2,5]
"""
import sys
import os

import win32com.client


def render(pptx_path: str, out_dir: str, slide_numbers=None, width=1600, height=900):
    pptx_path = os.path.abspath(pptx_path)
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    # DispatchEx launches a separate PowerPoint process instead of attaching
    # to (and later quitting) any PowerPoint instance the user already has open.
    app = win32com.client.DispatchEx("PowerPoint.Application")
    try:
        presentation = app.Presentations.Open(pptx_path, WithWindow=False)
        try:
            if slide_numbers:
                for n in slide_numbers:
                    slide_path = os.path.join(out_dir, f"slide_{n:03d}.png")
                    presentation.Slides(n).Export(slide_path, "PNG", width, height)
                    print(slide_path)
            else:
                presentation.Export(out_dir, "PNG", width, height)
                print(f"Exported all slides to {out_dir}")
        finally:
            presentation.Close()
    finally:
        app.Quit()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    pptx_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else os.path.splitext(pptx_path)[0] + "_preview"
    slide_numbers = None
    for arg in sys.argv[2:]:
        if arg.startswith("--slides"):
            slide_numbers = [int(x) for x in arg.split("=", 1)[1].split(",")]
    render(pptx_path, out_dir, slide_numbers)
