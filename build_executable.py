import PyInstaller.__main__
import os
import platform

# Ensure React dist_frontend and bin folder are included in the build
separator = ';' if platform.system() == 'Windows' else ':'
add_data = [
    f"dist_frontend{separator}dist_frontend",
    f"bin{separator}bin"
]

data_args = []
for item in add_data:
    data_args.append(f'--add-data={item}')

PyInstaller.__main__.run([
    'app_server.py',
    '--onefile',
    '--name=fypd',
    *data_args,
    '--hidden-import=uvicorn.logging',
    '--hidden-import=uvicorn.loops',
    '--hidden-import=uvicorn.loops.auto',
    '--hidden-import=uvicorn.protocols',
    '--hidden-import=uvicorn.protocols.http',
    '--hidden-import=uvicorn.protocols.http.auto',
    '--hidden-import=uvicorn.protocols.websockets',
    '--hidden-import=uvicorn.protocols.websockets.auto',
    '--hidden-import=uvicorn.lifespan',
    '--hidden-import=uvicorn.lifespan.on',
    '--hidden-import=whisper',
    '--hidden-import=moviepy',
    '--hidden-import=yt_dlp',
    '--hidden-import=textwrap3',
    '--hidden-import=viral_clipper',
    '--collect-all=whisper',
    '--collect-all=moviepy',
    '--collect-all=yt_dlp',
    '--collect-all=fastapi',
    '--collect-all=uvicorn',
    '--collect-all=imageio',
    '--collect-all=imageio_ffmpeg',
    '--collect-all=decorator',
    '--clean',
])

print("\n[+] Build Complete! Your executable is in the 'dist' folder.")
print("[!] Standalone Mode: If you placed portable magick.exe/ffmpeg.exe in 'bin/', the app is now fully independent!")
print("[!] Otherwise, users will still need system-wide FFmpeg and ImageMagick.")
