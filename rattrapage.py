import shutil
from pathlib import Path
from astropy.io import fits

# --- CONFIGURATION À ADAPTER ---
NIGHT_DATE = "2026-05-21"       # La date de la nuit concernée (format AAAA-MM-JJ)
IMAGE_TYPE = "Survey"           # "Survey" ou "Confirm"
DOSSIERS_SOURCE = ["Field_0", "Field_1"] # Les dossiers d'origine actuellement sur C:

JIM_PC = Path(r"\\JIM-PC\NightImages")
DRIVE_LOCAL = Path("C:/")

# Racine source sur C:
src_root = DRIVE_LOCAL / f"NightImages/{NIGHT_DATE}/{IMAGE_TYPE}"
# Si tes dossiers sont encore dans "LIGHT", décommente la ligne suivante :
# src_root = DRIVE_LOCAL / f"NightImages/{NIGHT_DATE}/LIGHT"

for folder in DOSSIERS_SOURCE:
    src_field = src_root / folder
    if not src_field.exists():
        print(f"❌ Dossier introuvable sur C: {src_field}")
        continue

    bin2_dir = src_field / "bin2"
    bin1_dir = src_field / "bin1"

    # On cherche un fichier FITS pour lire le vrai nom de l'objet dans le Header
    sample_fits = next(bin2_dir.glob("*.fits"), None) or next(bin1_dir.glob("*.fits"), None)
    
    if not sample_fits:
        print(f"⚠️ Aucun fichier FITS trouvé dans {folder}, saut de ce dossier.")
        continue

    # Lecture du vrai nom du champ (ex: FEUAGT) via le mot-clé OBJECT mis à jour par le script
    try:
        with fits.open(sample_fits) as hdul:
            final_target_id = hdul[0].header.get('OBJECT', folder).strip()
    except Exception as e:
        # En cas de problème de lecture, on extrait le début du nom du fichier FITS
        final_target_id = sample_fits.name.split('_')[0]

    print(f"\nProcessing {folder} ➡️ Nom réel détecté : {final_target_id}")

    # 1. Définition du chemin cible sur JIM-PC avec le bon nom
    dest_remote = JIM_PC / f"{NIGHT_DATE}/{IMAGE_TYPE}/{final_target_id}"

    # 2. Copie des répertoires bin1 et bin2 vers JIM-PC
    for sub in ["bin1", "bin2"]:
        src_sub = src_field / sub
        dest_sub = dest_remote / sub
        if src_sub.exists():
            dest_sub.mkdir(parents=True, exist_ok=True)
            for f in src_sub.glob("*.fits"):
                shutil.copy2(str(f), str(dest_sub / f.name))
            print(f"  └── Copie du sous-dossier {sub} sur JIM-PC réussie.")

    # 3. Génération du fichier signal Tycho (Survey ou Confirm)
    try:
        if IMAGE_TYPE.upper() == "CONFIRM":
            todo_file = JIM_PC / "confsync" / "todo.txt"
            todo_file.parent.mkdir(parents=True, exist_ok=True)
            with todo_file.open("a", encoding='utf-8') as f_todo:
                f_todo.write(f"{final_target_id}\n")
            print(f"  └── Signal de Confirmation ajouté dans todo.txt")
        else:
            path_for_tycho = f"H:/NightImages/{NIGHT_DATE}/{IMAGE_TYPE}/{final_target_id}/bin2"
            sync_file = JIM_PC / f"sync/bin2_{final_target_id}.txt"
            sync_file.parent.mkdir(parents=True, exist_ok=True)
            sync_file.write_text(path_for_tycho)
            print(f"  └── Fichier signal créé : bin2_{final_target_id}.txt")
            
    except Exception as e:
        print(f"  ❌ Erreur lors de la création du signal pour {final_target_id} : {e}")