import glob
import shutil
import sys
from pathlib import Path

output_base = sys.argv[2]

for f in glob.glob(sys.argv[1] + '/*.png'):
    res = f.split('/')[-1].split('.')[0]
    dest_dir = output_base + '/' + res + '/apps'

    Path(dest_dir).mkdir(parents=True, exist_ok=True)

    shutil.copy(f, dest_dir + '/bauh.png')
