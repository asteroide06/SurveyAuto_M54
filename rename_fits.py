import os

# --- CONFIGURATION ---
directory = r'C:\NightImages\2026-04-08\LIGHT'
field_name = 'ChampTest'
# ---------------------

def rename_files():
    count = 0
    if not os.path.exists(directory):
        print(f"Erreur : Le dossier {directory} n'existe pas.")
        return

    for filename in os.listdir(directory):
        # On cible les fichiers qui commencent par l'underscore de la date
        if filename.startswith("_2026") and filename.lower().endswith(".fits"):
            old_path = os.path.join(directory, filename)
            
            # Nouveau nom : ChampTest_2026...
            new_name = f"{field_name}{filename}"
            new_path = os.path.join(directory, new_name)
            
            os.rename(old_path, new_path)
            print(f"Renommé : {filename} -> {new_name}")
            count += 1
            
    print(f"\nTerminé ! {count} fichiers renommés.")

if __name__ == "__main__":
    rename_files()