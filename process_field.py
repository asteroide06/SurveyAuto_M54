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

def fast_bin2_sum(input_path, output_path, new_obj_name):
    """Binning 2x2 Sum + Injection du nom de l'objet dans le header."""
    try:
        with fits.open(input_path) as hdul:
            data = hdul[0].data.astype(np.float32)
            header = hdul[0].header
            
            # --- MISE À JOUR DU HEADER ---
            header['OBJECT'] = new_obj_name
            
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
        logging.error(f"Erreur binning/header {input_path.name}: {e}")

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
        
        # 1. Identification du type
        is_confirm = (image_type.upper() == "CONFIRM")

        # 2. Dossiers Sources
        parent_dir = DRIVE_LOCAL / f"NightImages/{night_date}/{image_type}"
        if not parent_dir.exists(): parent_dir = DRIVE_LOCAL / f"NightImages/{night_date}/LIGHT"
        
        src_field_dir = parent_dir / target_name

        # Rattrapage fichiers orphelins
        orphans = list(parent_dir.glob(f"{target_name}*.fits"))
        if orphans:
            src_field_dir.mkdir(parents=True, exist_ok=True)
            for f in orphans: shutil.move(str(f), str(src_field_dir / f.name))

        fits_files = list(src_field_dir.glob("*.fits"))
        if not fits_files:
            logging.error(f"Aucun fichier FITS trouvé dans {src_field_dir}")
            return

        # 3. Récupération des infos Header & Calcul du Code Survey
        with fits.open(fits_files[0]) as hdul:
            hdr = hdul[0].header
            field_tag = deg_to_hms_dms(hdr.get('RA', 0.0), hdr.get('DEC', 0.0))
            header_object = hdr.get('OBJECT', target_name).strip().replace(" ", "_")

        # LOGIQUE DE NOMMAGE HARMONISÉE
        if is_confirm:
            # Pour une confirmation, la vérité est le nom dans le Header (ex: 81011)
            final_target_id = header_object
            field_code = "CONFIRM" 
        else:
            # Pour un Survey, on génère un code FEFAEJ
            try:
                field_code = subprocess.check_output(["python", str(DESIGN_PY), "--next-field", str(year), str(month), str(day)], text=True).strip()
            except:
                field_code = "UNKNOWN"
            final_target_id = field_code

        logging.info(f"Nom final retenu pour Tycho : {final_target_id}")

        bin1_dir, bin2_dir = src_field_dir / "bin1", src_field_dir / "bin2"
        for d in [bin1_dir, bin2_dir]: d.mkdir(exist_ok=True)

        # 4. Traitement Binning & Mise à jour Header
        for i, f in enumerate(fits_files):
            new_name = f"{final_target_id}_{field_tag}_{i:04d}.fits"
            dest_b1 = bin1_dir / new_name
            
            # Déplacement vers bin1
            shutil.move(str(f), str(dest_b1))
            # Binning vers bin2 + Injection du nom final dans le header OBJECT
            fast_bin2_sum(dest_b1, bin2_dir / new_name, final_target_id)



        # 5. TRANSFERTS
        if is_confirm:
            remote_root = JIM_PC / f"confsync/{night_date}"
            u_name = get_unique_target_name(remote_root, final_target_id)
            base_remote = remote_root / u_name
            base_archive = DRIVE_ARCHIVE / f"NightImages/{night_date}/CONFIRM/{u_name}"
            base_nas = NAS / f"{night_date}/CONFIRM/{u_name}"
        else:
            base_remote = JIM_PC / f"{night_date}/{image_type}/{final_target_id}"
            base_archive = DRIVE_ARCHIVE / f"NightImages/{night_date}/{image_type}/{final_target_id}"
            base_nas = NAS / f"{night_date}/{image_type}/{final_target_id}"

        # A. PRIORITÉ BIN2 -> JIM-PC (SÉCURISÉ SI JIM-PC EST ÉTEINT)
        try:
            dest_remote_bin2 = base_remote / "bin2"
            dest_remote_bin2.mkdir(parents=True, exist_ok=True)
            for f in bin2_dir.glob("*.fits"):
                shutil.copy2(str(f), str(dest_remote_bin2 / f.name))
            logging.info("Copie BIN2 sur JIM-PC réussie.")
        except Exception as e:
            logging.error(f"JIM-PC inaccessible pour le BIN2 (PC éteint ?). Erreur : {e}")

        # B. SIGNAL TYCHO (DUPLIQUÉ SUR JIM-PC, DRIVE_ARCHIVE ET NAS)
        sync_destinations = [
            ("JIM-PC", JIM_PC),                            
            ("ARCHIVE_E", DRIVE_ARCHIVE / "NightImages"),   
            ("NAS_Z", NAS)                                  
        ]

        for label, root_sync in sync_destinations:
            try:
                if is_confirm:
                    todo_path = root_sync / "confsync" / "todo.txt"
                    todo_path.parent.mkdir(parents=True, exist_ok=True)
                    with todo_path.open("a", encoding='utf-8') as f_todo:
                        f_todo.write(f"{u_name}\n")
                else:
                    path_for_tycho = f"H:/NightImages/{night_date}/{image_type}/{final_target_id}/bin2"
                    sync_file = root_sync / "sync" / f"bin2_{final_target_id}.txt"
                    sync_file.parent.mkdir(parents=True, exist_ok=True)
                    sync_file.write_text(path_for_tycho)
                logging.info(f"Signal synchronisé sur {label}")
            except Exception as e:
                logging.warning(f"Echec synchro signal sur {label} (Normal si PC distant éteint) : {e}")

        # C. SAUVEGARDES BIN1 ET ARCHIVES
        if not only_bin2:
            try:
                (base_remote / "bin1").mkdir(parents=True, exist_ok=True)
                for f in bin1_dir.glob("*.fits"):
                    shutil.copy2(str(f), str(base_remote / "bin1" / f.name))
                logging.info("Copie BIN1 sur JIM-PC réussie.")
            except Exception as e:
                logging.error(f"JIM-PC inaccessible pour le BIN1 : {e}")
        
        # Sauvegardes locales (E:) et réseau (NAS Z:) indépendantes
        for root_dest in [base_archive, base_nas]:
            if root_dest:
                try:
                    subs = ["bin2"] if only_bin2 else ["bin1", "bin2"]
                    for sub in subs:
                        (root_dest / sub).mkdir(parents=True, exist_ok=True)
                        src_d = bin1_dir if sub == "bin1" else bin2_dir
                        for f in src_d.glob("*.fits"):
                            shutil.copy2(str(f), str(root_dest / sub / f.name))
                    logging.info(f"Sauvegarde réussie vers {root_dest}")
                except Exception as e:
                    logging.warning(f"Sauvegarde vers {root_dest} incomplète ou impossible : {e}")
                    
                    
                    
        # 6. NETTOYAGE FINAL (RÉTABLI ET ALIGNÉ SUR LE BLOC TRY PRINCIPAL)
        check_folder = base_archive / ("bin2" if only_bin2 else "bin1")
        count_src = len(list((bin2_dir if only_bin2 else bin1_dir).glob("*.fits")))
        count_arch = len(list(check_folder.glob("*.fits")))

        if count_src > 0 and count_src == count_arch:
            shutil.rmtree(str(src_field_dir))
            logging.info(f"Nettoyage OK : {target_name} supprimé de C:.")
        else:
            logging.warning(f"Nettoyage annulé : Source {count_src} != Archive {count_arch}")

    except Exception as e:
        logging.error(f"Erreur critique : {e}", exc_info=True)

# L'EXÉCUTION DU SCRIPT (À LA RACINE DU FICHIER)
if __name__ == "__main__":
    import sys
    only_bin2_flag = "--only-bin2" in sys.argv
    args = [a for a in sys.argv if a != "--only-bin2"]
    
    if len(args) > 8:
        process_field(int(args[1]), int(args[2]), int(args[3]), 
                      int(args[4]), int(args[5]), int(args[6]), 
                      args[7], args[8], only_bin2=only_bin2_flag)                      



#Ancienne version de la section 5 conservée ici, car Gemini a du mal à ne pas détruire ce qui existait... 


        # # 5. TRANSFERTS
        # if is_confirm:
            # remote_root = JIM_PC / f"confsync/{night_date}"
            # u_name = get_unique_target_name(remote_root, final_target_id)
            # base_remote = remote_root / u_name
            # base_archive = DRIVE_ARCHIVE / f"NightImages/{night_date}/CONFIRM/{u_name}"
            # base_nas = None
        # else:
            # base_remote = JIM_PC / f"{night_date}/{image_type}/{final_target_id}"
            # base_archive = DRIVE_ARCHIVE / f"NightImages/{night_date}/{image_type}/{final_target_id}"
            # base_nas = NAS / f"{night_date}/{image_type}/{final_target_id}"

        # # A. PRIORITÉ BIN2 -> JIM-PC
        # dest_remote_bin2 = base_remote / "bin2"
        # dest_remote_bin2.mkdir(parents=True, exist_ok=True)
        # for f in bin2_dir.glob("*.fits"):
            # shutil.copy2(str(f), str(dest_remote_bin2 / f.name))

        # # B. SIGNAL TYCHO (Cohérent avec final_target_id)
        # if is_confirm:
            # with (JIM_PC / "confsync/todo.txt").open("a", encoding='utf-8') as f_todo:
                # f_todo.write(f"{u_name}\n")
        # else:
            # path_for_tycho = f"H:/NightImages/{night_date}/{image_type}/{final_target_id}/bin2"
            # sync_file = JIM_PC / f"sync/bin2_{final_target_id}.txt"
            # sync_file.parent.mkdir(exist_ok=True)
            # sync_file.write_text(path_for_tycho)
        # logging.info(f"Signal Tycho envoyé pour {final_target_id}.")

        # # C. SAUVEGARDES BIN1 et ARCHIVES
        # if not only_bin2:
            # (base_remote / "bin1").mkdir(parents=True, exist_ok=True)
            # for f in bin1_dir.glob("*.fits"):
                # shutil.copy2(str(f), str(base_remote / "bin1" / f.name))
        
        # for root_dest in [base_archive, base_nas]:
            # if root_dest and (root_dest.drive or str(root_dest).startswith('\\')):
                # try:
                    # subs = ["bin2"] if only_bin2 else ["bin1", "bin2"]
                    # for sub in subs:
                        # (root_dest / sub).mkdir(parents=True, exist_ok=True)
                        # src_d = bin1_dir if sub == "bin1" else bin2_dir
                        # for f in src_d.glob("*.fits"):
                            # shutil.copy2(str(f), str(root_dest / sub / f.name))
                # except:
                    # logging.warning(f"Sauvegarde vers {root_dest} incomplète.")

