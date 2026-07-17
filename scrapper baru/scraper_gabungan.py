import requests
import json
import time
import base64
import os
import threading
import random
import queue
from datetime import datetime

# --- KONFIGURASI ---
KEYWORDS = ["cimory", "kanzler"]
API_SEARCH = "https://webcommerce-gw.alfagift.id/v2/products/searches"
GAS_URL = os.environ.get("GAS_URL", "https://script.google.com/macros/s/AKfycbxSzFYvsHRR0wwh0HPgKjbbN5YrMnNiHrTe0yTdVHAvyHsMGbHU6k7ZTYXkbWevlCcXew/exec")

STATIC_HEADERS = {
    'accept': 'application/json',
    'accept-language': 'id',
    'devicemodel': 'chrome',
    'devicetype': 'Web',
    'fingerprint': 'Sk7dUS6Ek63RUgn46AFTdWBcntIddFBw8PwBE+loQUL8EhnB3yHzMbd0A+h96yMD',
    'origin': 'https://alfagift.id',
    'priority': 'u=1, i',
    'referer': 'https://alfagift.id/',
    'sec-ch-ua': '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"macOS"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
    'trxid': str(int(time.time() * 1000))[:10],
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'
}

# --- LOCKS & GLOBAL EVENTS ---
file_lock = threading.Lock()
progress_lock = threading.Lock()
stop_event = threading.Event()

def alfagift_login(username, password):
    url = "https://webcommerce-gw.alfagift.id/v1/account/member/login"
    payload = {"login": username, "loginType": "mobile", "password": password, "requestPosition": "LOGIN"}
    try:
        res = requests.post(url, headers=STATIC_HEADERS, json=payload, timeout=10)
        if res.status_code == 200:
            data = res.json()
            return data.get('status', {}).get('token') or data.get('member', {}).get('webToken')
    except Exception as e:
        print(f"[-] Gagal login {username}: {e}")
    return None

def encode_header(data):
    return base64.b64encode(json.dumps(data, separators=(',', ':')).encode('utf-8')).decode('utf-8')

def get_master_data():
    print("[*] Narik master data dari Google Sheet...")
    try:
        res = requests.get(GAS_URL)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"[-] Gagal narik data dari GAS: {e}")
        return None

def get_scraped_store_codes(file_path='final_data.json'):
    if not os.path.exists(file_path):
        return set()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        if data and isinstance(data, list):
            first_entry = data[0]
            last_updated = first_entry.get('last_updated')
            current_date = datetime.now().strftime('%Y-%m-%d')
            
            # Jika tanggal data lama berbeda dengan tanggal hari ini, reset!
            if last_updated and last_updated != current_date:
                print(f"[!] Terdeteksi pergantian hari ({last_updated} -> {current_date}). Mereset file {file_path}...")
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"[-] Gagal menghapus file progress lama: {e}")
                return set()
                
            return {item.get('store_code') for item in data if item.get('store_code')}
    except Exception as e:
        print(f"[-] Gagal membaca history progress: {e}. Mulai ulang dari awal.")
        return set()
    return set()

def save_store_data(store_data, file_path='final_data.json'):
    with file_lock:
        data = []
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = []
        
        # Simpan/tambahkan data toko baru
        data.append(store_data)
        
        # Tulis secara atomik biar gak corrupt kalau di-interupsi
        temp_file = file_path + '.tmp'
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(temp_file, file_path)
        except Exception as e:
            print(f"\n[-] Gagal menyimpan data ke {file_path}: {e}")

def scrap_single_store(store, token, prod_master):
    current_date = datetime.now().strftime('%Y-%m-%d')
    store_data = {
        "store_code": store.get('store_code', ''),
        "store_name": store.get('store_name', ''),
        "fc_code": store.get('fc_code', ''),
        "branch_name": store.get('branch_name', ''),
        "mds_name": store.get('mds_name', ''),
        "latitude": store.get('latitude', ''),
        "longitude": store.get('longitude', ''),
        "tipe_toko": store.get('tipe_toko', ''),
        "last_updated": current_date,
        "products": []
    }

    headers = STATIC_HEADERS.copy()
    headers['token'] = token
    headers['fccode'] = encode_header({"seller_id": "1", "fc_code": store.get('fc_code', '')})
    headers['storecode'] = encode_header({
        "store_code": store.get('store_code', ''), "delivery": True, "sapa": True,
        "store_method": 1, "blacklist_tags": [], "distance": 13876508.5,
        "maxDistance": None, "flagRoute": store.get('flagroute', ''), "depo_id": ""
    })

    for kw in KEYWORDS:
        if stop_event.is_set():
            break
        try:
            res = requests.get(API_SEARCH, headers=headers, params={'keyword': kw, 'start': 0, 'limit': 60}, timeout=15)
            if res.status_code == 200:
                api_res = res.json()
                
                for p in api_res.get('products', []):
                    name = p.get('productName')
                    
                    if name in prod_master:
                        base_price = p.get('basePrice', 0)
                        final_price = p.get('finalPrice', 0)
                        stock = p.get('stock', 0)
                        
                        store_data['products'].append({
                            "name": name,
                            "barcode": prod_master[name].get('barcode', ''),
                            "normal": base_price,
                            "promo": final_price if final_price < base_price else "",
                            "jenis_promo": prod_master[name].get('jenis_promo', ''),
                            "mulai_promo": prod_master[name].get('mulai_promo', ''),
                            "akhir_promo": prod_master[name].get('akhir_promo', ''),
                            "stock": stock
                        })
        except Exception as e:
            print(f"\n[-] Error nge-hit {kw} buat toko {store.get('store_code', '')}: {e}")
        
        # Jeda acak antar keyword biar alami (0.8 - 1.8 detik)
        time.sleep(random.uniform(0.8, 1.8))
        
    return store_data

def worker(store_queue, token, account_name, total_stores, completed_counter, start_time, prod_master):
    while not store_queue.empty() and not stop_event.is_set():
        try:
            store = store_queue.get_nowait()
        except queue.Empty:
            break
        
        try:
            store_data = scrap_single_store(store, token, prod_master)
            
            if stop_event.is_set():
                store_queue.task_done()
                break
                
            save_store_data(store_data)
            
            with progress_lock:
                completed_counter[0] += 1
                idx = completed_counter[0]
                
                elapsed = time.time() - start_time
                avg_time = elapsed / idx
                remaining = total_stores - idx
                est_seconds = avg_time * remaining
                
                if est_seconds > 60:
                    est_str = f"{int(est_seconds // 60)}m {int(est_seconds % 60)}s"
                else:
                    est_str = f"{int(est_seconds)}s"
                    
                print(f"[Progress: {idx}/{total_stores}] [Akun: {account_name}] Selesai Toko {store.get('store_code', '')} (Sisa estimasi: {est_str})")
        except Exception as e:
            print(f"\n[-] Gagal memproses Toko {store.get('store_code', '')}: {e}")
        finally:
            store_queue.task_done()
            
        # Jeda acak antar toko (2.0 - 3.5 detik) dengan pengecekan stop_event berkala
        sleep_time = random.uniform(2.0, 3.5)
        step = 0.5
        slept = 0
        while slept < sleep_time and not stop_event.is_set():
            time.sleep(min(step, sleep_time - slept))
            slept += step

def main():
    accounts_env = os.environ.get("ACCOUNTS_JSON")
    if accounts_env:
        try:
            accounts = json.loads(accounts_env)
            print("[*] Memuat akun dari environment variable...")
        except Exception as e:
            print(f"[-] Gagal memparsing ACCOUNTS_JSON dari environment: {e}")
            return
    else:
        if not os.path.exists('accounts.json'):
            print("[-] File accounts.json ga ketemu dan ACCOUNTS_JSON env tidak diset!")
            return
        with open('accounts.json', 'r') as f:
            accounts = json.load(f)
        
    active_accounts = []
    print("[*] Proses login akun Alfagift...")
    for acc in accounts:
        t = alfagift_login(acc['username'], acc['password'])
        if t: 
            active_accounts.append({"token": t, "name": acc['name']})
            print(f"[+] Login sukses: {acc['name']}")
        time.sleep(1)
        
    if not active_accounts:
        print("[-] Ga ada token yang aktif. Stop.")
        return

    master = get_master_data()
    if not master or 'stores' not in master: 
        print("[-] Data master kosong atau error.")
        return
    
    stores = master['stores']
    prod_master = master['products']
    
    # Deteksi progress yang sudah berhasil disimpan sebelumnya
    scraped_codes = get_scraped_store_codes()
    stores_to_scrap = [s for s in stores if s.get('store_code') not in scraped_codes]
    
    total_total = len(stores)
    total_scraped_before = len(scraped_codes)
    total_to_scrap = len(stores_to_scrap)
    
    print(f"[*] Total Toko: {total_total}")
    if total_scraped_before > 0:
        print(f"[+] Terdeteksi progress lama! {total_scraped_before} toko sudah sukses di-scrap.")
    print(f"[*] Toko yang tersisa untuk di-scrap: {total_to_scrap}")
    
    if total_to_scrap == 0:
        print("[!] Semua toko sudah sukses di-scrap!")
        return

    store_queue = queue.Queue()
    for store in stores_to_scrap:
        store_queue.put(store)

    completed_counter = [0]
    start_time = time.time()
    
    num_threads = len(active_accounts)
    print(f"[*] Menjalankan {num_threads} thread worker paralel...")
    
    threads = []
    for i in range(num_threads):
        acc = active_accounts[i]
        t = threading.Thread(
            target=worker,
            args=(store_queue, acc['token'], acc['name'], total_to_scrap, completed_counter, start_time, prod_master),
            daemon=True
        )
        t.start()
        threads.append(t)
        
    try:
        while not store_queue.empty():
            time.sleep(0.5)
            if not any(t.is_alive() for t in threads):
                break
                
        for t in threads:
            t.join(timeout=1.0)
            
        if stop_event.is_set():
            print("\n[!] Scraping dihentikan secara paksa oleh user. Data yang selesai telah tersimpan aman.")
        else:
            print("\n[!] Scraping selesai secara utuh! Cek file final_data.json")
            
    except KeyboardInterrupt:
        print("\n[!] Menerima sinyal keluar (Ctrl+C). Menghentikan scraper dengan aman...")
        stop_event.set()
        for t in threads:
            t.join(timeout=5.0)
        print("[!] Semua thread telah berhenti. Data aman disimpan di final_data.json.")

if __name__ == "__main__":
    main()