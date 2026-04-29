import os
import shutil
import subprocess
import logging
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from astropy.io import fits
from astropy.coordinates import SkyCoord
import astropy.units as u

# --------------------------------------------------------------------------
# 0. CONFIGURATION
# --------------------------------------------------------------------------
DRIVE_LOCAL = Path("C:/")
DRIVE_ARCHIVE = Path("E:/")
# Utilisation du format raw string (r) pour éviter les problèmes de slashs réseau
JIM_PC = Path(r"\\JIM-PC\NightImages")
NAS = Path("Z:/")

LOG_FILE = DRIVE_LOCAL / "NightImages/Scripts/process_field.log"
DESIGN_PY = DRIVE_LOCAL / "NightImages/Scripts/neocp_designation.py"

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format='%(asctime)s : %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    encoding='utf-8' 
)

# --------------------------------------------------------------------------
# FONCTIONS OUTILS
# --------------------------------------------------------------------------
def deg_to_hms_dms(ra_deg, dec_deg):
    """Convertit les degrés décimaux en format 11h36m28s_+39d59m56s."""
    try:
        c = SkyCoord(ra=ra_deg*u.degree, dec=dec_deg*u.degree)
        ra_hms = c.ra.to_string(unit=u.hour, sep=('h', 'm', 's'), precision=0, pad=True)
        dec_dms = c.dec.to_string(unit=u.degree, sep=('d', 'm', 's'), precision=0, pad=True, alwayssign=True)
        return f"{ra_hms}_{dec_dms}"
    except:
        return f"RA{ra_deg:.2f}_DEC{dec_deg:.2f}"

def fast_bin2_sum(input_path, output_path):
    """Binning 2x2 Sum exporté en 16-bits (8Mo)."""
    try:
        with fits.open(input_path) as hdul:
            data = hdul[0].data.astype(np.float32)
            header = hdul[0].header
            y, x = data.shape
            y_t, x_t = y - (y % 2), x - (x % 2)
            data = data[:y_t, :x_t]
            binned = data.reshape(y_t // 2, 2, x_t // 2, 2).sum(axis=(1, 3))
            binned = np.clip(binned, 0, 65535).astype(np.uint16)
            header['NAXIS1'] = x_t // 2
            header['NAXIS2'] = y_t // 2
            header['BITPIX'] = 16 
            fits.writeto(output_path, binned, header, overwrite=True)
    except Exception as e:
        logging.error(f"Erreur binning {input_path.name}: {e}")

def get_unique_target_name(base_path, target_name):
    final_path = base_path / target_name
    if not final_path.exists(): return target_name
    i = 2
    while (base_path / f"{target_name}_{i}").exists(): i += 1
    return f"{target_name}_{i}"

# --------------------------------------------------------------------------
# CORPS DU SCRIPT
# --------------------------------------------------------------------------
def process_field(year, month, day, hour, minute, second, image_type, target_name, only_bin2=False):
    logging.info(f"--- Début Session : {target_name} ({image_type}) ---")
    try:
        dt = datetime(year, month, day, hour, minute, second)
        night_date = (dt - timedelta(hours=12)).strftime("%Y-%m-%d")
        
        # 1. Code champ
        try:
            field_code = subprocess.check_output(["python", str(DESIGN_PY), "--next-field", str(year), str(month), str(day)], text=True).strip()
        except:
            field_code = "UNKNOWN"
            logging.warning("Désignation impossible, utilisation de UNKNOWN")

        is_confirm = (image_type.upper() == "CONFIRM")

        # 2. Dossiers Sources
        parent_dir = DRIVE_LOCAL / f"NightImages/{night_date}/{image_type}"
        if not parent_dir.exists(): parent_dir = DRIVE_LOCAL / f"NightImages/{night_date}/LIGHT"
        
        src_field_dir = parent_dir / target_name

        # Rattrapage fichiers orphelins (si Field_4 est à la racine de LIGHT)
        orphans = list(parent_dir.glob(f"{target_name}*.fits"))
        if orphans:
            src_field_dir.mkdir(parents=True, exist_ok=True)
            for f in orphans: shutil.move(str(f), str(src_field_dir / f.name))

        fits_files = list(src_field_dir.glob("*.fits"))
        if not fits_files:
            logging.error(f"Aucun fichier FITS trouvé dans {src_field_dir}")
            return

        # 3. Header & Dossiers Bin
        with fits.open(fits_files[0]) as hdul:
            hdr = hdul[0].header
            field_tag = deg_to_hms_dms(hdr.get('RA', 0.0), hdr.get('DEC', 0.0))

        bin1_dir, bin2_dir = src_field_dir / "bin1", src_field_dir / "bin2"
        for d in [bin1_dir, bin2_dir]: d.mkdir(exist_ok=True)

        # 4. Traitement Binning
        for i, f in enumerate(fits_files):
            prefix = target_name if is_confirm else field_code
            new_name = f"{prefix}_{field_tag}_{i:04d}.fits"
            dest_b1 = bin1_dir / new_name
            shutil.move(str(f), str(dest_b1))
            fast_bin2_sum(dest_b1, bin2_dir / new_name)

        # 5. TRANSFERTS
        if is_confirm:
            remote_root = JIM_PC / f"confsync/{night_date}"
            u_name = get_unique_target_name(remote_root, target_name)
            base_remote = remote_root / u_name
            base_archive = DRIVE_ARCHIVE / f"NightImages/{night_date}/CONFIRM/{u_name}"
            base_nas = None
        else:
            base_remote = JIM_PC / f"{night_date}/{image_type}/{field_code}"
            base_archive = DRIVE_ARCHIVE / f"NightImages/{night_date}/{image_type}/{field_code}"
            base_nas = NAS / f"{night_date}/{image_type}/{field_code}"

        # A. PRIORITÉ BIN2 -> JIM-PC (Essentiel pour Tycho)
        dest_remote_bin2 = base_remote / "bin2"
        dest_remote_bin2.mkdir(parents=True, exist_ok=True)
        
        for f in bin2_dir.glob("*.fits"):
            shutil.copy2(str(f), str(dest_remote_bin2 / f.name))
        logging.info(f"Transfert BIN2 terminé vers {dest_remote_bin2}")

        # B. SIGNAL TYCHO (Maintenant que les fichiers sont copiés !)
        if is_confirm:
            with (JIM_PC / "confsync/todo.txt").open("a", encoding='utf-8') as f_todo:
                f_todo.write(f"{u_name}\n")
        else:
            path_for_tycho = f"H:/NightImages/{night_date}/{image_type}/{field_code}/bin2"
            sync_file = JIM_PC / f"sync/bin2_{field_code}.txt"
            sync_file.parent.mkdir(exist_ok=True)
            sync_file.write_text(path_for_tycho)
        logging.info("Signal Tycho envoyé.")

        # C. SAUVEGARDES BIN1 et ARCHIVES
        if not only_bin2:
            (base_remote / "bin1").mkdir(parents=True, exist_ok=True)
            for f in bin1_dir.glob("*.fits"):
                shutil.copy2(str(f), str(base_remote / "bin1" / f.name))
        
        # Archive E: et NAS Z:
        for root_dest in [base_archive, base_nas]:
            if root_dest and (root_dest.drive or str(root_dest).startswith('\\')):
                try:
                    # On définit les sous-dossiers à traiter
                    subs = ["bin2"] if only_bin2 else ["bin1", "bin2"]
                    for sub in subs:
                        (root_dest / sub).mkdir(parents=True, exist_ok=True)
                        src_d = bin1_dir if sub == "bin1" else bin2_dir
                        for f in src_d.glob("*.fits"):
                            shutil.copy2(str(f), str(root_dest / sub / f.name))
                except:
                    logging.warning(f"Sauvegarde vers {root_dest} incomplète.")

        # 6. NETTOYAGE FINAL (Vérification par comptage)
        # On choisit quel dossier vérifier pour valider le transfert
        if only_bin2:
            # Si on ne garde que le BIN2, on vérifie les fichiers BIN2
            count_src = len(list(bin2_dir.glob("*.fits")))
            count_arch = len(list((base_archive / "bin2").glob("*.fits")))
            check_type = "BIN2"
        else:
            # Sinon, on vérifie classiquement sur le BIN1
            count_src = len(list(bin1_dir.glob("*.fits")))
            count_arch = len(list((base_archive / "bin1").glob("*.fits")))
            check_type = "BIN1"

        if count_src > 0 and count_src == count_arch:
            shutil.rmtree(str(src_field_dir))
            logging.info(f"Nettoyage OK ({check_type}) : {target_name} supprimé de C:.")
        else:
            logging.warning(f"Nettoyage annulé : Source {check_type} ({count_src}) != Archive ({count_arch})")

if __name__ == "__main__":
    import sys
    # Vérifie si le flag --only-bin2 est présent dans les arguments
    only_bin2 = "--only-bin2" in sys.argv
    # On retire le flag de la liste pour ne pas perturber le comptage des arguments positionnels
    args = [a for a in sys.argv if a != "--only-bin2"]
    
    if len(args) > 8:
        process_field(int(args[1]), int(args[2]), int(args[3]), 
                      int(args[4]), int(args[5]), int(args[6]), 
                      args[7], args[8], only_bin2=only_bin2)