import requests
import json

base_url = "https://raw.githubusercontent.com/raynaldoanantawijaya/emas/main"
files = [
    "galeri24_co_id_1773287359.json",
    "harga-emas_org_1773287342.json",
    "logammulia_com_1773287304.json"
]

for f in files:
    url = f"{base_url}/{f}"
    print(f"--- Checking {f} ---")
    res = requests.get(url)
    if res.status_code == 200:
        try:
            data = res.json()
            source = data.get("metadata", {}).get("source", "Unknown")
            tables = data.get("data", {}).get("tables", [])
            print(f"Source: {source}")
            print(f"Number of tables: {len(tables)}")
            
            # Print a few table titles and lengths to verify completeness
            for i, t in enumerate(tables[:3]):
                num_rows = len(t.get('rows', []))
                print(f"  Table {i+1}: {t.get('title', 'Unknown')} ({num_rows} rows)")
        except Exception as e:
            print(f"Error parsing JSON: {e}")
    else:
        print(f"Failed to fetch {url}. Status code: {res.status_code}")
    print()
