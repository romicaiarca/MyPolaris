import requests
from datetime import datetime

class MyPolarisAPI:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "HomeAssistant-MyPolaris/2.0 (@romicaiarca)"
        })

    def login(self):
        try:
            self.session.get("https://my.polaris.ro/Login.aspx", timeout=10)
            payload = {
                "Email": self.email,
                "Parola": self.password,
                "Cod": "",
                "token": "bypass-ha"
            }
            r = self.session.post(
                "https://my.polaris.ro/Login.aspx/Autentificare",
                json=payload,
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=15
            )
            result = r.json()["d"]
            if result.get("Login2Steps"):
                raise Exception("2FA activat – intră o dată manual în browser")
            return result["EsteOK"]
        except Exception as e:
            print(f"[MyPolaris] Login error: {e}")
            return False

    def call(self, method, data=None):
        if data is None: data = {}
        try:
            r = self.session.post(
                f"https://my.polaris.ro/{method}",
                json=data,
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=15
            )
            return r.json()["d"]
        except:
            return {}

    def fetch_all_data(self):
        if not self.login():
            return None

        # 1. Nume contract
        pdl = self.call("InvoicesAndPayments.aspx/LoadPuncteDeLucru")
        denumire = pdl.get("lista", [{}])[0].get("Denumire", "Necunoscut")

        # 2. Sold + Facturi
        facturi_resp = self.call("InvoicesAndPayments.aspx/LoadFacturi")
        sold = facturi_resp.get("Sold", "0,00")
        facturi_raw = facturi_resp.get("Facturi", [])

        # 3. Plăți
        plati_raw = self.call("InvoicesAndPayments.aspx/LoadPlati").get("Plati", [])

        # === FACTURI PE ANI ===
        facturi_by_year = {}
        for f in facturi_raw:
            try:
                year = datetime.strptime(f["DataDocument_Proxy"], "%d.%m.%Y").year
            except:
                continue
            if year not in facturi_by_year:
                facturi_by_year[year] = []
            facturi_by_year[year].append({
                "Nr": f["NrDocument"],
                "Data": f["DataDocument_Proxy"],
                "Scadenta": f["DataScadenta_Proxy"],
                "Valoare": f["Valoare_Proxy"] + " RON",
                "DePlata": "Da" if f.get("DePlata") else "Nu",
                "IdFactura": f["IdFactura"],
                "IdContract": f["IdContract"],
                "Moneda": f["MonedaCod"]
            })

        # === PLĂȚI PE ANI ===
        plati_by_year = {}
        for p in plati_raw:
            try:
                year = datetime.strptime(p["DataDoc_Proxy"], "%d.%m.%Y").year
            except:
                continue
            if year not in plati_by_year:
                plati_by_year[year] = []
            plati_by_year[year].append({
                "Tip": p["TipDoc"],
                "Data": p["DataDoc_Proxy"],
                "Suma": p["Suma_Proxy"] + " RON",
                "NrDoc": p["NrDoc"],
                "Moneda": p["MonedaCod"]
            })

        return {
            "denumire": denumire,
            "sold": sold,
            "facturi_by_year": facturi_by_year,
            "plati_by_year": plati_by_year,
            "last_update": datetime.now().strftime("%d.%m.%Y %H:%M")
        }