from PyInstaller.utils.hooks import collect_data_files

# This ensures PyInstaller bundles the model files needed by faster-whisper
datas = collect_data_files('faster_whisper') 