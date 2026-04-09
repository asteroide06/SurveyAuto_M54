# session_init.py
# Archivage de conflist.txt et lastconfirm.txt au debut de chaque session

import sys
import os
import datetime
import shutil

def main():
    if len(sys.argv) < 2:
        print("Usage: session_init.py <confirm_dir>")
        sys.exit(1)

    confirm_dir = sys.argv[1]
    conflist    = os.path.join(confirm_dir, "conflist.txt")
    lastconfirm = os.path.join(confirm_dir, "lastconfirm.txt")
    archive_dir = os.path.join(confirm_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)

    date_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # Archiver conflist.txt s'il existe et n'est pas vide
    if os.path.exists(conflist) and os.path.getsize(conflist) > 0:
        shutil.copy(conflist, os.path.join(archive_dir, f"conflist_{date_str}.txt"))
        print(f"conflist.txt archivé -> conflist_{date_str}.txt")

    # Archiver lastconfirm.txt s'il existe
    if os.path.exists(lastconfirm) and os.path.getsize(lastconfirm) > 0:
        shutil.copy(lastconfirm, os.path.join(archive_dir, f"lastconfirm_{date_str}.txt"))
        print(f"lastconfirm.txt archivé -> lastconfirm_{date_str}.txt")

    # Remettre à zéro
    with open(conflist, "w") as f:
        f.write("")
    with open(lastconfirm, "w") as f:
        f.write("0")

    print("Session initialisée : conflist.txt vide, lastconfirm.txt = 0")
    sys.exit(0)

if __name__ == "__main__":
    main()