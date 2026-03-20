# AMT TIFF scale fix (Windows 7 friendly, ASCII-only source)
# Writes standard TIFF resolution tags in CENTIMETERS (ResolutionUnit=3)

import os
import re
import shutil
import threading
from pathlib import Path

import tifffile

UNIT_TO_M = {
    "m": 1.0,
    "cm": 1e-2,
    "mm": 1e-3,
    "um": 1e-6,
    "nm": 1e-9,
    "in": 0.0254,
    "inch": 0.0254,
    "inches": 0.0254,
}

FLOAT_RE = r"([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)"

def get_desktop_folder():
    import ctypes
    from ctypes import wintypes

    CSIDL_DESKTOPDIRECTORY = 0x10
    SHGFP_TYPE_CURRENT = 0

    buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
    ctypes.windll.shell32.SHGetFolderPathW(
        None, CSIDL_DESKTOPDIRECTORY, None, SHGFP_TYPE_CURRENT, buf
    )
    return Path(buf.value)

def _decode_description(value):
    """Return description as str (best-effort)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        # Try UTF-8 first, then Windows-1252, then Latin-1 as last resort
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                return value.decode(enc)
            except Exception:
                pass
        return value.decode("latin-1", errors="replace")
    return str(value)

def parse_amt_description(desc):
    """Return (xpixcal, ypixcal, unit) or None."""
    desc = _decode_description(desc)
    if not desc:
        return None

    # AMT often uses CR separators and may include NULs
    desc = desc.replace("\x00", "")
    desc = desc.replace("\r\n", "\n").replace("\r", "\n")

    # XpixCal/YpixCal
    x = re.search(rf"\bXpixCal\s*=\s*{FLOAT_RE}\b", desc, re.IGNORECASE)
    y = re.search(rf"\bYpixCal\s*=\s*{FLOAT_RE}\b", desc, re.IGNORECASE)

    # Unit (allow micro sign via \u00b5 without putting it literally in the file)
    u = re.search(r"\bUnit\s*=\s*([A-Za-z]|[\u00b5])+\b", desc, re.IGNORECASE)

    if not (x and y and u):
        return None

    unit = u.group(0)
    # unit match includes "Unit=..." potentially; extract after "=" robustly
    unit = unit.split("=", 1)[-1].strip()

    return float(x.group(1)), float(y.group(1)), unit

def px_per_cm_from_px_per_unit(px_per_unit_value, unit):
    """
    AMT definition: XpixCal/YpixCal = PixelPerUnit
    Convert to pixels per centimeter for standard TIFF tags.
    """
    unit_key = (unit or "").strip().lower()

    # Normalize micro sign to 'u' without embedding it literally
    unit_key = unit_key.replace("\u00b5", "u")

    if unit_key not in UNIT_TO_M:
        raise ValueError("Unknown Unit={!r}".format(unit))

    unit_m = UNIT_TO_M[unit_key]
    units_per_cm = 1e-2 / unit_m  # number of 'unit' in 1 cm
    return px_per_unit_value * units_per_cm


def _best_effort_compression_name(page):
    """Return a compression name that tifffile might be able to WRITE, or None."""
    try:
        if page.compression is None:
            return None
        name = page.compression.name
        # Don't try to re-encode JPEG-compressed TIFF pages here
        if name in ("JPEG", "OJPEG"):
            return None
        return name
    except Exception:
        return None

def fix_one_tiff(path, overwrite, make_backup, log=print):
    try:
        with tifffile.TiffFile(path) as tif:
            desc_tag = tif.pages[0].tags.get("ImageDescription")
            desc_val = desc_tag.value if desc_tag is not None else None

            parsed = parse_amt_description(desc_val)
            if not parsed:
                log("SKIP: {} (no XpixCal/YpixCal/Unit found)".format(path.name))
                return False

            xpixcal, ypixcal, unit = parsed
            xres = px_per_cm_from_px_per_unit(xpixcal, unit)
            yres = px_per_cm_from_px_per_unit(ypixcal, unit)

            tmp_path = path.with_suffix(path.suffix + ".tmp")

            with tifffile.TiffWriter(tmp_path, bigtiff=tif.is_bigtiff) as tw:
                for page in tif.pages:
                    data = page.asarray()

                    pdesc_tag = page.tags.get("ImageDescription")
                    pdesc_val = pdesc_tag.value if pdesc_tag is not None else None
                    pdesc_val = _decode_description(pdesc_val)

                    comp = _best_effort_compression_name(page)

                    # Try to preserve compression; if writing fails, fall back to none.
                    try:
                        tw.write(
                            data,
                            description=pdesc_val,
                            resolution=(xres, yres),
                            resolutionunit="CENTIMETER",
                            compression=comp,
                            metadata=None,
                        )
                    except Exception as e:
                        log("WARN: {} could not write compression {} ({}). Writing uncompressed."
                            .format(path.name, comp, e))
                        tw.write(
                            data,
                            description=pdesc_val,
                            resolution=(xres, yres),
                            resolutionunit="CENTIMETER",
                            compression=None,
                            metadata=None,
                        )

        if overwrite:
            if make_backup:
                bak = path.with_suffix(path.suffix + ".bak")
                if not bak.exists():
                    shutil.copy2(path, bak)
            os.replace(tmp_path, path)
            outname = path.name
        else:
            out = path.with_name(path.stem + "_fixed" + path.suffix)
            os.replace(tmp_path, out)
            outname = out.name

        log("OK: {} -> X/YResolution={:.10g}, {:.10g} px/cm (Unit in note: {})"
            .format(outname, xres, yres, unit))
        return True

    except Exception as e:
        log("ERR: {}: {}".format(path.name, e))
        try:
            tmp = path.with_suffix(path.suffix + ".tmp")
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return False

def fix_folder(folder, overwrite, make_backup, log=print):
    tifs = sorted(list(folder.rglob("*.tif")) + list(folder.rglob("*.tiff")))
    if not tifs:
        log("No .tif/.tiff files found.")
        return

    log("Found {} TIFF(s) in: {}".format(len(tifs), folder))
    changed = 0
    for p in tifs:
        if fix_one_tiff(p, overwrite=overwrite, make_backup=make_backup, log=log):
            changed += 1
    log("Done. Modified {} file(s).".format(changed))

def run_gui():
    import tkinter as tk
    from tkinter import filedialog, scrolledtext, messagebox

    BASE = get_desktop_folder() / "Individual Folders"

    if not BASE.is_dir():
        messagebox.showerror("Missing folder", "BASE folder does not exist:\n\n{}".format(BASE))

    root = tk.Tk()
    root.title("AMT TIFF Scale Fix (writes Resolution tags in cm)")

    # Start at BASE; user must pick a subfolder to enable Run
    folder_var = tk.StringVar(value=str(BASE))
    overwrite_var = tk.BooleanVar(value=True)
    backup_var = tk.BooleanVar(value=True)

    logbox = scrolledtext.ScrolledText(root, width=100, height=25, state="disabled")

    def log(msg):
        logbox.configure(state="normal")
        logbox.insert("end", msg + "\n")
        logbox.see("end")
        logbox.configure(state="disabled")

    def is_allowed_selection(p: Path) -> bool:
        # Must be inside BASE (at any depth), but not BASE itself
        base = os.path.normcase(os.path.abspath(str(BASE)))
        sel = os.path.normcase(os.path.abspath(str(p)))

        return sel != base and sel.startswith(base + os.sep)

    def update_run_state(*_):
        p = Path(folder_var.get())
        ok = is_allowed_selection(p)
        run_btn.configure(state=("normal" if ok else "disabled"))

    def browse():
        # Prefer current entry if it exists; else BASE; else C:\
        current = folder_var.get().strip()
        if current and os.path.isdir(current):
            start_dir = current
        elif os.path.isdir(str(BASE)):
            start_dir = str(BASE)
        else:
            start_dir = r"C:\\"

        d = filedialog.askdirectory(parent=root, initialdir=start_dir, mustexist=True)
        if d:
            folder_var.set(d)

    def start():
        folder = Path(folder_var.get())
        if not is_allowed_selection(folder):
            messagebox.showerror(
                "Select a subfolder",
                "Please browse to a folder inside:\n\n{}".format(str(BASE)),
            )
            return

        overwrite = overwrite_var.get()
        make_backup = backup_var.get()

        if overwrite and not messagebox.askyesno(
            "Confirm overwrite",
            "This will overwrite TIFFs in the selected folder (and subfolders).\n\nContinue?",
        ):
            return

        def worker():
            fix_folder(folder, overwrite=overwrite, make_backup=make_backup, log=log)

        threading.Thread(target=worker, daemon=True).start()

    frm = tk.Frame(root, padx=10, pady=10)
    frm.pack(fill="x")

    tk.Label(frm, text="Folder:").grid(row=0, column=0, sticky="w")
    tk.Entry(frm, textvariable=folder_var, width=80).grid(row=0, column=1, sticky="we", padx=5)
    tk.Button(frm, text="Browse...", command=browse).grid(row=0, column=2, sticky="e")
    frm.grid_columnconfigure(1, weight=1)

    opts = tk.Frame(root, padx=10)
    opts.pack(fill="x")
    tk.Checkbutton(opts, text="Overwrite original files", variable=overwrite_var).pack(anchor="w")
    tk.Checkbutton(opts, text="Make .bak backup (only when overwriting)", variable=backup_var).pack(anchor="w")

    run_btn = tk.Button(root, text="Run", command=start, padx=20, pady=5)
    run_btn.pack(pady=8)

    logbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    # Enable/disable Run based on selection
    try:
        folder_var.trace_add("write", update_run_state)
    except AttributeError:
        folder_var.trace("w", update_run_state)
    update_run_state()

    root.mainloop()

def main():
    import argparse

    ap = argparse.ArgumentParser(
        description="Fix AMT TIFF calibration by writing standard TIFF resolution tags (cm)."
    )
    ap.add_argument("folder", nargs="?", help="Folder of TIFFs. If omitted, launches GUI.")
    ap.add_argument("--no-overwrite", action="store_true", help="Write *_fixed.tif instead of overwriting.")
    ap.add_argument("--no-backup", action="store_true", help="Do not create .bak when overwriting.")
    args = ap.parse_args()

    if not args.folder:
        run_gui()
        return

    folder = Path(args.folder)
    fix_folder(
        folder,
        overwrite=(not args.no_overwrite),
        make_backup=(not args.no_backup),
        log=print,
    )

if __name__ == "__main__":
    main()



