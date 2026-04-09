import requests

def test_nina_v2(target_name):
    # Route basée sur votre lien doc : /v2/api/sequence/set-target
    # Le port reste 1888 comme sur votre capture
    url = "http://localhost:1888/v2/api/sequence/set-target"
    
    # Structure JSON requise par la v2
    payload = {
        "Name": target_name,
        "RA": 0,
        "Dec": 0,
        "Rotation": 0
    }
    
    print(f"Tentative v2 vers {url}...")
    
    try:
        r = requests.get(url, params=payload, timeout=5) # La doc v2 semble utiliser GET avec paramètres
        if r.status_code == 200:
            print("✅ SUCCÈS : Cible mise à jour dans NINA.")
        else:
            # Si GET échoue, on tente en POST (certaines API v2 acceptent les deux)
            r = requests.post(url, json=payload, timeout=5)
            if r.status_code == 200:
                print("✅ SUCCÈS (via POST) : Cible mise à jour.")
            else:
                print(f"❌ ERREUR : Code {r.status_code} - {r.text}")
    except Exception as e:
        print(f"❌ CONNEXION IMPOSSIBLE : {e}")

if __name__ == "__main__":
    test_nina_v2("ASTEROID-V2-TEST")