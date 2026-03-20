# AMT_Scale_Fix
This is a Windows app that moves the scaling factors from the AMT tag location to the standard .tif locations that can be read by ImageJ and other programs

## Prerequisites

1. This script was written for compatibility with Windows 7. Future versions of Windows should be compatible.
2. You must have a version of Python accessible. The last version of Python compatible with Windows 7 is Python 3.8.10 (https://www.python.org/downloads/release/python-3810/), so that is what we have on our computer. When you install, you must check **Add Python 3.8 to PATH** and ensure that **pip** is also being installed. 
3. Your .tif (or .tiff) files must have been written by the AMT camera software. You must not wish to use the original tags (XResolution [282], YResolution [283], and ResolutionUnit [296]) for other purposes as they will be overwritten. 

## Getting Started

1. Your Python must have tifffile and numpy installed. If you just installed Python, run the following commands in cmd or PowerShell:
   ```cmd
   python -m pip install tifffile numpy
   ```
  
2. Before you start, in amt_tiff_scale_fix.py, change
   ```python
   BASE = Path(r"C:\Users\amt\Desktop\Individual Folders")
   ```
   to whatever your base directory where you save images is. If you save in multiple locations, choose a directory upstream of all potential locations.

3. If you do not want the script to recurse through subdirectories (and thus only convert .tif files that are located directly in the chosen directory), change the following line to contain two instances of **glob** instead of **rglob**:
   ```python
   tifs = sorted(list(folder.rglob("*.tif")) + list(folder.rglob("*.tiff)))
   ```

## Running the Program

1. Double-click on the script on the Desktop or in the File Explorer, or in cmd run (while standing in the directory you have the script):
   ```cmd
   python amt_tiff_scale_fix.py
   ```
2. Click Browse to choose a directory containing .tifs that you wish to update scale tags on. **Any .tif files in this directory and in all subdirectories will be converted.**
3. Choose if you want to overwrite the original files or generate a copy of the original saved with the suffix *_fixed.tif. If you overwrite the original files, you can choose to save them as *.bak files or do a simple overwrite.
4. Click run
5. Wait for the run to complete. Your images are now ready to be imported into ImageJ or other programs!

## Example Images

<img width="430" height="303" alt="app" src="https://github.com/user-attachments/assets/ca9e2dce-fd39-452c-8a4e-bece17ec4718" />

<img width="430" height="303" alt="warning" src="https://github.com/user-attachments/assets/de717798-9b26-4887-810f-6a3e014fbe59" />

<img width="430" height="300" alt="done" src="https://github.com/user-attachments/assets/d219e44a-6214-4827-841f-8bd543c1c4de" />

___

Original image on left, "fixed" image on right; correct scale and units automatically detected by ImageJ

<img width="1535" height="730" alt="image" src="https://github.com/user-attachments/assets/59a1010d-bdb0-4f54-a7fe-29ecc30ebc43" />
_
This script was generated with the assistance of GPT4DFCI, a private, HIPAA-secure endpoint to GPT-4o provided by Dana-Farber Cancer Institute_
