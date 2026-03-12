import os
import sys
import shutil
import time
import subprocess
from urllib.parse import urlparse

try:
    from colorama import init, Fore, Back, Style
    init(autoreset=True)
except ImportError:
    class _Noop:
        def getattr(self, _): pass
    Fore = Back = Style = _Noop()

def ok(msg): print(f"  {Fore.GREEN}✓{Style.RESET_ALL} {msg}")
def err(msg): print(f"  {Fore.RED}✗{Style.RESET_ALL} {msg}")
def info(msg): print(f"  {Fore.CYAN}ℹ{Style.RESET_ALL} {msg}")
def warn(msg): print(f"  {Fore.YELLOW}⚠{Style.RESET_ALL} {msg}")

def run_git_command(args, cwd, hide_output=True):
    """Menjalankan perintah git dan mengembalikan stdout (str) dan success (bool)."""
    try:
        res = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False
        )
        if res.returncode == 0:
            return res.stdout.strip(), True
        else:
            return res.stderr.strip(), False
    except Exception as e:
        return str(e), False

def is_valid_github_url(url: str) -> bool:
    """Validasi dasar URL GitHub"""
    if "github.com" not in url.lower():
        return False
    # Bersihkan URL jika diisi utuh
    url = url.strip()
    return True

def format_github_url(url: str) -> str:
    """Pastikan URL berakhiran .git dan dibersihkan dari trailing slashes"""
    url = url.strip().rstrip("/")
    if not url.endswith(".git"):
         url += ".git"
    return url

def force_rmtree(action, name, exc):
    """Callback for shutil.rmtree to forcefully remove read-only files (.git on Windows)"""
    import stat
    os.chmod(name, stat.S_IWRITE)
    os.remove(name)

def push_to_github(repo_url: str, files_to_copy: list):
    """
    Meng-clone repo, copy multiple file scrape ke repo, commit, lalu push back.
    files_to_copy adalah list of dict: [{"source": "path", "target": "filename.json", "category": "saham"}, ...]
    """
    
    if not files_to_copy:
        err("Daftar file kosong.")
        return False
        
    for fobj in files_to_copy:
        if not os.path.exists(fobj["source"]):
            err(f"File sumber tidak ditemukan: {fobj['source']}")
            return False
            
    if not is_valid_github_url(repo_url):
        err("URL tidak valid. Pastikan itu adalah URL repository GitHub (misal: https://github.com/user/repo).")
        return False
        
    clean_repo_url = format_github_url(repo_url)
    
    # ── 1. SETUP TEMP WOKRSPACE ──
    tmp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tmp_git_push")
    if os.path.exists(tmp_dir):
        # Bersihkan folder temp sisa push sebelumnya jika ada
        shutil.rmtree(tmp_dir, onerror=force_rmtree)
        time.sleep(0.5)
        
    os.makedirs(tmp_dir, exist_ok=True)
    
    try:
        info(f"Mempersiapkan repository target: {Fore.CYAN}{clean_repo_url}{Style.RESET_ALL}")
        
        # ── 2. CLONE (SHALLOW) ──
        warn("Melakukan git clone (depth=1) untuk kecepatan...")
        # Note: 'repo' adalah nama subfolder dalam .tmp_git_push
        stdout, success = run_git_command(["clone", "--depth", "1", clean_repo_url, "repo"], tmp_dir)
        if not success:
            err(f"Gagal clone repository. Pastikan URL benar dan Anda punya akses (berupa public repo atau auth tersetting).\nGit Error: {stdout}")
            return False
            
        repo_dir = os.path.join(tmp_dir, "repo")
        
        # Cari branch utama (bisa main atau master)
        branch_out, success = run_git_command(["branch", "--show-current"], repo_dir)
        current_branch = branch_out if success and branch_out else "main"
        
        # ── 2.5 CLEAR EXISTING REPO FILES ──
        warn("Membersihkan file lama dari repository untuk menghindari penumpukan...")
        for item in os.listdir(repo_dir):
            if item == ".git":
                continue
            item_path = os.path.join(repo_dir, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path, onerror=force_rmtree)
            else:
                try:
                    os.chmod(item_path, stat.S_IWRITE)
                    os.remove(item_path)
                except:
                    pass
        
        # ── 3. COPY FILE ──
        for fobj in files_to_copy:
            target_file_path = os.path.join(repo_dir, fobj["target"])
            info(f"Menyalin hasil scrape ke: {Fore.CYAN}{fobj['target']}{Style.RESET_ALL}")
            shutil.copy2(fobj["source"], target_file_path)
            
            if not os.path.exists(target_file_path):
                 err(f"Gagal memindah file JSON {fobj['target']} ke dalam folder repository.")
                 return False
             
        # ── 3.5 VERCEL BOILERPLATE INJECTION ──
        vercel_json_path = os.path.join(repo_dir, "vercel.json")
        has_vercel_json_already = os.path.exists(vercel_json_path)
        if not has_vercel_json_already:
             warn("Membuat vercel.json untuk mengizinkan akses CORS lintas domain...")
             import json
             vercel_config = {
               "headers": [
                 {
                   "source": "/(.*)",
                   "headers": [
                     { "key": "Access-Control-Allow-Origin", "value": "*" },
                     { "key": "Access-Control-Allow-Methods", "value": "GET, OPTIONS" }
                   ]
                 }
               ]
             }
             with open(vercel_json_path, "w", encoding="utf-8") as vf:
                 json.dump(vercel_config, vf, indent=2)
             
        # ── 3.6 STANDALONE REPO INJECTION ──
        warn("Menginjeksi kode scraper & GitHub Actions...")
        import glob
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Copy requirements.txt
        req_src = os.path.join(base_dir, "requirements.txt")
        if os.path.exists(req_src):
            shutil.copy2(req_src, os.path.join(repo_dir, "requirements.txt"))
            
        # Copy all python files in root
        for py_file in glob.glob(os.path.join(base_dir, "*.py")):
            if not os.path.basename(py_file).startswith("test_") and not os.path.basename(py_file).startswith("."):
                shutil.copy2(py_file, os.path.join(repo_dir, os.path.basename(py_file)))
        
        # Copy essential subdirectories (config, modules, api)
        essential_dirs = ["config", "modules", "api"]
        for subdir in essential_dirs:
            src_dir = os.path.join(base_dir, subdir)
            dst_dir = os.path.join(repo_dir, subdir)
            if os.path.isdir(src_dir):
                shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
                
        # Determine categories based on files_to_copy
        categories = list(set([fobj["category"] for fobj in files_to_copy]))
        combo_name = "Gabungan" if len(categories) > 1 else categories[0]
        
        # Create .github/workflows/auto_scrape.yml
        workflows_dir = os.path.join(repo_dir, ".github", "workflows")
        os.makedirs(workflows_dir, exist_ok=True)
        yml_path = os.path.join(workflows_dir, "auto_scrape.yml")
        
        fetch_proxies_step = ""
        needs_proxy = any(c in ["saham", "crypto", "forex"] for c in categories)
        if needs_proxy:
            fetch_proxies_step = """
      - name: Hunt Fresh Working Proxies
        run: python fetch_proxies.py"""
        
        scrape_steps = ""
        for cat in categories:
            scrape_steps += f"""
      - name: Run Scraper ({cat.upper()})
        run: python menu.py --{cat}"""
        
        yml_content = f"""name: Standalone Scraper ({combo_name})

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

on:
  schedule:
    - cron: '0 */4 * * *'
  workflow_dispatch:

jobs:
  scrape_and_commit:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    env:
      TZ: "Asia/Jakarta"
      
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'
          cache: 'pip'
          
      - name: Install dependencies
        run: pip install -r requirements.txt
        
      - name: Install Playwright
        run: playwright install chromium --with-deps{fetch_proxies_step}{scrape_steps}
        
      - name: Commit & Push New JSON Data
        run: |
          git config --global user.name 'github-actions[bot]'
          git config --global user.email '41898282+github-actions[bot]@users.noreply.github.com'
"""
        import re
        for i, fobj in enumerate(files_to_copy):
            cat = fobj["category"]
            tgt = fobj["target"]
            src_file = os.path.basename(fobj["source"])
            # Remove trailing timestamps (e.g. galeri24_co_id_1773010101.json -> galeri24_co_id)
            base_pattern = re.sub(r'_[0-9]+\.json$', '', src_file)
            if base_pattern == src_file: 
                base_pattern = src_file.replace('.json', '')
            
            yml_content += f"""
          echo "Processing {tgt}..."
          new_file_{i}=$(ls -t hasil_scrape/{cat}/*{base_pattern}*.json 2>/dev/null | head -1 || true)
          if [ -z "$new_file_{i}" ]; then
              new_file_{i}=$(ls -t hasil_scrape/*/*{base_pattern}*.json 2>/dev/null | head -1 || true)
          fi
          if [ -z "$new_file_{i}" ]; then
              # Ultimate fallback: category newest
              new_file_{i}=$(ls -t hasil_scrape/{cat}/*.json 2>/dev/null | head -1 || true)
          fi
          
          if [ -n "$new_file_{i}" ] && [ -f "$new_file_{i}" ]; then
             echo "Updating {tgt} with $new_file_{i}"
             cp "$new_file_{i}" "{tgt}"
             git add "{tgt}"
          else
             echo "Warning: Could not find output for pattern '{base_pattern}'"
          fi
"""
        
        yml_content += f"""
          git diff --quiet && git diff --staged --quiet || (git commit -m "bot: Auto-update {combo_name} API endpoints" && git push)
"""
        with open(yml_path, "w", encoding="utf-8") as f:
            f.write(yml_content)

        # ── 4. COMMIT & PUSH ──
        warn("Menyiapkan commit...")
        # Add EVERYTHING since we inject standalone codebase
        _, success = run_git_command(["add", "."], repo_dir)
        if not success:
            err("Gagal git add pada file-file standalone repo.")
            return False
            
        # Check jika ada perubahan
        status_out, _ = run_git_command(["status", "--porcelain"], repo_dir)
        if not status_out.strip():
            target_display = files_to_copy[0]['target'] if len(files_to_copy) == 1 else "Gabungan File"
            ok(f"File {target_display} sudah up-to-date di repository. Tidak ada push yang diperlukan.")
            return True
            
        # Commit
        commit_msg = f"Auto-update API endpoints: {combo_name} [{int(time.time())}]"
        stdout, success = run_git_command(["commit", "-m", commit_msg], repo_dir)
        if not success:
            err(f"Gagal melakukan commit.\nGit Error: {stdout}")
            return False
            
        # Push!
        info(f"Melakukan push otomatis ke branch '{current_branch}'...")
        stdout, success = run_git_command(["push", "origin", current_branch], repo_dir)
        
        if success:
            ok("Push berhasil!")
            print(f"\n  {Fore.GREEN}Endpoint JSON Anda sudah siap di GitHub!{Style.RESET_ALL}")
            
            try:
                path_parts = urlparse(clean_repo_url).path.strip("/").replace(".git", "")
                for fobj in files_to_copy:
                    raw_url = f"https://raw.githubusercontent.com/{path_parts}/refs/heads/{current_branch}/{fobj['target']}"
                    print(f"  {Fore.CYAN}🔗 {fobj['target']} Raw/API Link{Style.RESET_ALL} : {Fore.BLUE}{Style.BRIGHT}{raw_url}{Style.RESET_ALL}")
                print(f"  {Fore.CYAN}🔗 GitHub Link{Style.RESET_ALL}                  : {Fore.BLUE}{Style.BRIGHT}https://github.com/{path_parts}{Style.RESET_ALL}")
            except Exception as e:
                pass
                
            return True
        else:
            err(f"Gagal melakukan push.\nGit Error: {stdout}")
            return False

    except Exception as e:
        err(f"Terjadi kesalahan saat push ke GitHub: {e}")
        return False


def clear_github_repo(repo_url: str):
    """
    Meng-clone repo, menghapus seluruh file (kecuali .git), commit, lalu push back
    untuk membersihkan repository secara total.
    """
    if not is_valid_github_url(repo_url):
        err("URL tidak valid. Pastikan itu adalah URL repository GitHub (misal: https://github.com/user/repo).")
        return False
        
    clean_repo_url = format_github_url(repo_url)
    
    # ── 1. SETUP TEMP WOKRSPACE ──
    tmp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tmp_git_push")
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir, onerror=force_rmtree)
        time.sleep(0.5)
        
    os.makedirs(tmp_dir, exist_ok=True)
    
    try:
        info(f"Mempersiapkan penghapusan untuk repository target: {Fore.CYAN}{clean_repo_url}{Style.RESET_ALL}")
        
        # ── 2. CLONE (SHALLOW) ──
        warn("Melakukan git clone (depth=1) untuk kecepatan...")
        stdout, success = run_git_command(["clone", "--depth", "1", clean_repo_url, "repo"], tmp_dir)
        if not success:
            err(f"Gagal clone repository. Pastikan URL benar dan Anda punya akses.\nGit Error: {stdout}")
            return False
            
        repo_dir = os.path.join(tmp_dir, "repo")
        
        branch_out, success = run_git_command(["branch", "--show-current"], repo_dir)
        current_branch = branch_out if success and branch_out else "main"
        
        # ── 3. WIPE FILES ──
        warn("Menghapus seluruh file dan folder di dalam repository...")
        deleted_count = 0
        for item in os.listdir(repo_dir):
            if item == ".git":
                continue
            item_path = os.path.join(repo_dir, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path, onerror=force_rmtree)
                deleted_count += 1
            else:
                try:
                    import stat
                    os.chmod(item_path, stat.S_IWRITE)
                    os.remove(item_path)
                    deleted_count += 1
                except:
                    pass
                    
        if deleted_count == 0:
            ok("Repository sudah dalam keadaan kosong. Tidak ada yang perlu dihapus.")
            return True

        # ── 4. COMMIT & PUSH ──
        warn("Menyiapkan commit untuk penghapusan massal...")
        _, success = run_git_command(["add", "-u"], repo_dir)
        _, success2 = run_git_command(["add", "."], repo_dir)
        
        status_out, _ = run_git_command(["status", "--porcelain"], repo_dir)
        if not status_out.strip():
            ok("Repository sudah up-to-date (sudah kosong).")
            return True
            
        commit_msg = f"bot: Clear repository [{int(time.time())}]"
        stdout, success = run_git_command(["commit", "-m", commit_msg], repo_dir)
        if not success:
            err(f"Gagal melakukan commit.\nGit Error: {stdout}")
            return False
            
        info(f"Melakukan push penghapusan ke branch '{current_branch}'...")
        stdout, success = run_git_command(["push", "origin", current_branch], repo_dir)
        
        if success:
            ok("Pembersihan berhasil! Repository sekarang kosong.")
            return True
        else:
            err(f"Gagal melakukan push.\nGit Error: {stdout}")
            return False

    except Exception as e:
        err(f"Terjadi kesalahan saat membersihkan GitHub repo: {e}")
        return False

            
    finally:
        # ── 5. TEMPORARY FOLDER CLEANUP ──
        if os.path.exists(tmp_dir):
             # Paksa lepas read-only files (seperti .git objects) sebelum rmtree di Windows
             # Folder temp mungkin error di lock oleh windows OS sebentar, abaikan saja
             pass
