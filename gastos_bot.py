#!/usr/bin/env python3
"""Bot financiero B1G J4cK  ->  Notion.  Menu con submenus, pagos fijos con
frecuencia y recordatorios a Telegram, KM/combustible y saldo DiDi."""
import os
import re
import time
import datetime as dt
import requests
from dotenv import load_dotenv

load_dotenv()
AQUI = os.path.dirname(os.path.abspath(__file__))

TG_TOKEN        = os.getenv("TELEGRAM_TOKEN", "").strip()
NOTION_TOKEN    = os.getenv("NOTION_TOKEN", "").strip()
NOTION_DB       = os.getenv("NOTION_DB_ID", "").strip()
NOTION_KM_DB    = os.getenv("NOTION_KM_DB", "").strip()
NOTION_FIJOS_DB = os.getenv("NOTION_FIJOS_DB", "").strip()
SOLO_CHAT       = os.getenv("ALLOWED_CHAT_ID", "").strip()

TG_API = f"https://api.telegram.org/bot{TG_TOKEN}"
NOTION_API = "https://api.notion.com/v1"
NOTION_HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}",
                  "Notion-Version": "2022-06-28", "Content-Type": "application/json"}

METODOS = {
    "efectivo": "Efectivo", "cash": "Efectivo", "nequi": "Nequi",
    "bancolombia": "Bancolombia", "banco": "Bancolombia", "daviplata": "Daviplata",
    "binance": "Binance", "debito": "Tarjeta Débito", "débito": "Tarjeta Débito",
    "credito": "Tarjeta Crédito", "crédito": "Tarjeta Crédito", "tarjeta": "Tarjeta Débito",
}

GRUPOS = {
    "ingreso": [
        ("🏢 Empresas", ["GravitaX", "Sigm4", "Ap3x Motors", "White Box", "Alph4 Jet", "Construcciones"]),
        ("💵 Otros ingresos", ["Otros ingresos", "Comisión IB", "Ahorro", "Inversión"]),
        ("🤝 Préstamo recibido", ["Préstamo recibido"]),
        ("🚕 DiDi / Uber (saldo)", ["__didi__"]),
    ],
    "gasto": [
        ("🟠 Personal", ["Alimentación", "Mercado", "Paradas", "Ocio", "Servicios", "Salud", "Deudas", "Otros"]),
        ("🔵 Vehículo", ["Gasolina", "Gas", "Lavado", "Parqueadero", "Peajes", "Multas"]),
        ("🗓️ Vehículo (anual)", ["SOAT", "Tecnomecanica", "Llantas", "Aceite", "Mantenimiento", "Repuestos"]),
        ("🟣 Trading", ["Vps", "TradingView", "Prop Firms", "Brokers", "Otros Trading"]),
        ("🤝 Préstamo dado", ["Préstamo dado"]),
    ],
}
CAT_UBER = {"Gasolina", "Gas", "Lavado", "Mantenimiento", "Llantas", "Aceite", "Repuestos",
            "Parqueadero", "Peajes", "Multas", "SOAT", "Tecnomecanica", "Comisión Uber", "Otros Uber"}
CAT_TRADING = {"Vps", "TradingView", "Software", "Prop Firms", "Brokers", "Otros Trading", "Comisión IB"}
CATEGORIAS = [
    ("Alimentación", ["almuerzo","comida","cena","desayuno","restaurante","cafe","café","domicilio"]),
    ("Mercado", ["mercado","ara","d1","exito","éxito"]),
    ("Paradas", ["parada","chicle","agua","antojo","gaseosa","snack","mecato","dulce"]),
    ("Gas", [" gas ","gnv","glp"]),
    ("Gasolina", ["gasolina","combustible","tanqueada"]),
    ("Transporte", ["transporte","bus","taxi","pasaje"]),
    ("Salud", ["salud","eps","medico","médico","droga","farmacia"]),
    ("Ocio", ["cine","fiesta","cerveza","netflix"]),
    ("Internet Casa", ["internet","wifi","fibra"]),
    ("Servicios", ["luz","agua","energia","energía","servicios"]),
    ("Deudas", ["deuda","cuota","prestamo","préstamo"]),
    ("TradingView", ["tradingview"]),
    ("Software", ["software","licencia","suscripcion","suscripción"]),
    ("Otros ingresos", ["sueldo","salario","nomina","nómina","venta"]),
]
FRECUENCIAS = {"mensual": "Mensual", "bimestral": "Bimestral", "dos meses": "Bimestral",
               "trimestral": "Trimestral", "trimestre": "Trimestral",
               "semestral": "Semestral", "semestre": "Semestral", "anual": "Anual", "año": "Anual"}
PERIODO = {"Mensual": 1, "Bimestral": 2, "Trimestral": 3, "Semestral": 6, "Anual": 12}

MODO = {}          # chat_id -> "ingreso"|"gasto"
PENDIENTE = {}     # chat_id -> estado conversacional
RASTRO = {}        # chat_id -> [message_ids del flujo actual, para limpiar al terminar]
CHAT_FILE = os.path.join(AQUI, "chat_id.txt")


# ---------- utilidades ----------
def fmt(n):
    return f"${n:,.0f}".replace(",", ".")


def mes_actual():
    return dt.datetime.now().strftime("%Y-%m")


def meses_entre(ym1, ym2):
    y1, m1 = map(int, ym1.split("-")); y2, m2 = map(int, ym2.split("-"))
    return (y2 - y1) * 12 + (m2 - m1)


def parsear_monto(txt):
    m = re.search(r"(\d[\d\.\, ]*)\s*(k|mil)?", txt.lower())
    if not m:
        return None, txt
    limpio = m.group(1).replace(".", "").replace(",", "").replace(" ", "")
    if not limpio.isdigit():
        return None, txt
    v = int(limpio)
    if m.group(2) in ("k", "mil"):
        v *= 1000
    return v, (txt[:m.start()] + " " + txt[m.end():]).strip()


def separar_por_metodo(palabras):
    for i, p in enumerate(palabras):
        if p.lower().strip(".,") in METODOS:
            return (METODOS[p.lower().strip(".,")],
                    " ".join(palabras[:i]).strip(), " ".join(palabras[i+1:]).strip())
    return None, " ".join(palabras).strip(), ""


def metodo_y_nota(palabras):
    metodo, resto = None, []
    for p in palabras:
        k = p.lower().strip(".,")
        if metodo is None and k in METODOS:
            metodo = METODOS[k]
        else:
            resto.append(p)
    return metodo, " ".join(resto).strip()


def adivinar_categoria(desc, modo):
    d = " " + desc.lower() + " "
    for cat, claves in CATEGORIAS:
        for c in claves:
            if c in d:
                return cat
    return "Otros ingresos" if modo == "ingreso" else "Otros"


def tipo_de(categoria, modo):
    if modo == "ingreso":
        return "Ingreso"
    if categoria in CAT_TRADING:
        return "Gasto Trading"
    if categoria in CAT_UBER:
        return "Gasto Uber"
    return "Gasto Personal"


# ---------- Notion: Movimientos ----------
def notion_crear(descripcion, valor=None, categoria=None, metodo=None,
                 tipo=None, didi=None, notas=None):
    props = {"descripcion": {"title": [{"text": {"content": (descripcion or "—")[:200]}}]},
             "fecha": {"date": {"start": dt.datetime.now().astimezone().isoformat()}}}
    if valor is not None: props["valor"] = {"number": float(valor)}
    if categoria:         props["categoria"] = {"select": {"name": categoria}}
    if metodo:            props["metodo"] = {"select": {"name": metodo}}
    if tipo:              props["tipo"] = {"select": {"name": tipo}}
    if didi is not None:  props["DiDi"] = {"number": float(didi)}
    if notas:             props["notas"] = {"rich_text": [{"text": {"content": notas[:200]}}]}
    r = requests.post(f"{NOTION_API}/pages", headers=NOTION_HEADERS,
                      json={"parent": {"database_id": NOTION_DB}, "properties": props}, timeout=20)
    if r.status_code >= 300:
        raise RuntimeError(f"Notion {r.status_code}: {r.text[:300]}")
    return r.json().get("id")


def notion_agregar_nota(page_id, nota):
    r = requests.patch(f"{NOTION_API}/pages/{page_id}", headers=NOTION_HEADERS,
                       json={"properties": {"notas": {"rich_text": [{"text": {"content": nota[:200]}}]}}},
                       timeout=20)
    if r.status_code >= 300:
        raise RuntimeError(f"Notion {r.status_code}: {r.text[:300]}")


def notion_saldo_didi():
    total, cursor = 0.0, None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r = requests.post(f"{NOTION_API}/databases/{NOTION_DB}/query",
                          headers=NOTION_HEADERS, json=body, timeout=20)
        if r.status_code >= 300:
            raise RuntimeError(f"Notion {r.status_code}: {r.text[:300]}")
        d = r.json()
        for pg in d.get("results", []):
            v = pg.get("properties", {}).get("DiDi", {}).get("number")
            if v:
                total += v
        if not d.get("has_more"):
            break
        cursor = d.get("next_cursor")
    return total


# ---------- Notion: KM ----------
def notion_km_todos():
    filas, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r = requests.post(f"{NOTION_API}/databases/{NOTION_KM_DB}/query",
                          headers=NOTION_HEADERS, json=body, timeout=20)
        if r.status_code >= 300:
            raise RuntimeError(f"Notion {r.status_code}: {r.text[:300]}")
        d = r.json()
        for pg in d.get("results", []):
            pr = pg.get("properties", {})
            filas.append({"odometro": (pr.get("odometro", {}) or {}).get("number"),
                          "combustible": ((pr.get("combustible", {}) or {}).get("select") or {}).get("name"),
                          "recorrido": (pr.get("recorrido_km", {}) or {}).get("number") or 0,
                          "costo": (pr.get("costo", {}) or {}).get("number") or 0})
        if not d.get("has_more"):
            break
        cursor = d.get("next_cursor")
    return filas


def notion_km_crear(odometro, combustible, recorrido, costo, nota):
    props = {"Registro": {"title": [{"text": {"content": f"{combustible} · {int(odometro)} km"}}]},
             "fecha": {"date": {"start": dt.datetime.now().astimezone().isoformat()}},
             "odometro": {"number": float(odometro)}, "combustible": {"select": {"name": combustible}},
             "recorrido_km": {"number": float(recorrido)}}
    if costo: props["costo"] = {"number": float(costo)}
    if nota:  props["nota"] = {"rich_text": [{"text": {"content": nota[:200]}}]}
    r = requests.post(f"{NOTION_API}/pages", headers=NOTION_HEADERS,
                      json={"parent": {"database_id": NOTION_KM_DB}, "properties": props}, timeout=20)
    if r.status_code >= 300:
        raise RuntimeError(f"Notion {r.status_code}: {r.text[:300]}")


def parsear_km(texto):
    low = texto.lower()
    comb = "Gasolina" if "gasolina" in low else ("Gas" if ("gas" in low or "gnv" in low or "glp" in low) else None)
    nums = [int(n.replace(".", "").replace(",", "")) for n in re.findall(r"\d[\d\.\,]*", texto)]
    odo = nums[0] if nums else None
    costo = nums[1] if len(nums) > 1 else None
    pal = [p for p in texto.split() if not re.match(r"^\d", p) and p.lower() not in ("gas","gasolina","gnv","glp")]
    return odo, comb, costo, " ".join(pal).strip()


def registrar_km(chat_id, texto):
    odo, comb, costo, nota = parsear_km(texto)
    if odo is None or comb is None:
        responder(chat_id, "Formato: <b>odómetro combustible [costo]</b>\nEj: <code>45200 gas 30000</code>")
        return False
    filas = notion_km_todos()
    ult = max((f["odometro"] for f in filas if f["odometro"] is not None), default=None)
    rec = (odo - ult) if (ult is not None and odo >= ult) else 0
    notion_km_crear(odo, comb, rec, costo, nota)
    filas.append({"combustible": comb, "recorrido": rec, "costo": costo or 0})
    kg = sum(f["recorrido"] for f in filas if f["combustible"] == "Gas")
    kn = sum(f["recorrido"] for f in filas if f["combustible"] == "Gasolina")
    cg = sum(f["costo"] for f in filas if f["combustible"] == "Gas")
    cn = sum(f["costo"] for f in filas if f["combustible"] == "Gasolina")
    cpk = lambda c, k: (f"{fmt(c/k)}/km" if k else "—")
    finalizar(chat_id,
        f"🚗 Odómetro <b>{int(odo)}</b> · {comb}" + (f" · {fmt(costo)}" if costo else "") + "\n" +
        (f"📏 <b>{int(rec)} km</b> desde la última\n" if rec else "📏 Primera lectura\n") +
        f"\n<b>Acumulado</b>\n🔵 Gas: {int(kg)} km · {cpk(cg,kg)}\n🟠 Gasolina: {int(kn)} km · {cpk(cn,kn)}\n\n¿Algo más? 👇")
    return True


# ---------- Notion: Pagos fijos ----------
def _rt(pr, key):
    a = (pr.get(key, {}) or {}).get("rich_text") or []
    return a[0]["plain_text"] if a else ""


def notion_fijos_listar():
    filas, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r = requests.post(f"{NOTION_API}/databases/{NOTION_FIJOS_DB}/query",
                          headers=NOTION_HEADERS, json=body, timeout=20)
        if r.status_code >= 300:
            raise RuntimeError(f"Notion {r.status_code}: {r.text[:300]}")
        d = r.json()
        for pg in d.get("results", []):
            pr = pg.get("properties", {})
            tit = (pr.get("Nombre", {}) or {}).get("title") or []
            filas.append({
                "id": pg["id"], "nombre": tit[0]["plain_text"] if tit else "—",
                "inmueble": _rt(pr, "inmueble"), "categoria": _rt(pr, "categoria") or "Otros",
                "metodo": _rt(pr, "metodo"), "ultimo_pago": _rt(pr, "ultimo_pago"),
                "frecuencia": ((pr.get("frecuencia", {}) or {}).get("select") or {}).get("name") or "Mensual",
                "monto": (pr.get("monto", {}) or {}).get("number") or 0,
                "monto_pronto_pago": (pr.get("monto_pronto_pago", {}) or {}).get("number") or 0,
                "dia_limite_descuento": (pr.get("dia_limite_descuento", {}) or {}).get("number") or 0,
                "estado_mes": ((pr.get("estado_mes", {}) or {}).get("select") or {}).get("name") or "",
                "dia": (pr.get("dia", {}) or {}).get("number") or 1,
                "activo": (pr.get("activo", {}) or {}).get("checkbox", False),
                "notificar": (pr.get("notificar", {}) or {}).get("checkbox", True)})
        if not d.get("has_more"):
            break
        cursor = d.get("next_cursor")
    return filas


def notion_fijo_crear(nombre, inmueble, categoria, monto, dia, frecuencia, metodo):
    def _t(v):
        return {"rich_text": [{"text": {"content": str(v)[:100]}}]} if v else {"rich_text": []}
    props = {"Nombre": {"title": [{"text": {"content": nombre[:100]}}]},
             "inmueble": _t(inmueble), "categoria": _t(categoria), "metodo": _t(metodo),
             "monto": {"number": float(monto or 0)}, "dia": {"number": float(dia or 1)},
             "frecuencia": {"select": {"name": frecuencia}}, "activo": {"checkbox": True},
             "notificar": {"checkbox": True}, "ultimo_pago": {"rich_text": []}}
    r = requests.post(f"{NOTION_API}/pages", headers=NOTION_HEADERS,
                      json={"parent": {"database_id": NOTION_FIJOS_DB}, "properties": props}, timeout=20)
    if r.status_code >= 300:
        raise RuntimeError(f"Notion {r.status_code}: {r.text[:300]}")


def notion_fijo_marcar_pagado(page_id, mes):
    r = requests.patch(f"{NOTION_API}/pages/{page_id}", headers=NOTION_HEADERS,
                       json={"properties": {
                           "ultimo_pago": {"rich_text": [{"text": {"content": mes}}]},
                           "estado_mes": {"select": {"name": "Pagado"}}}}, timeout=20)
    if r.status_code >= 300:
        raise RuntimeError(f"Notion {r.status_code}: {r.text[:300]}")


def monto_efectivo(f):
    """Devuelve (monto, con_descuento). Si el fijo tiene pronto pago y hoy es
    <= día límite, aplica el monto con descuento."""
    normal = f.get("monto") or 0
    pp = f.get("monto_pronto_pago") or 0
    lim = f.get("dia_limite_descuento") or 0
    if pp and lim and dt.datetime.now().day <= int(lim):
        return pp, True
    return normal, False


def esta_pendiente(f):
    if not f["activo"]:
        return False
    per = PERIODO.get(f.get("frecuencia") or "Mensual", 1)
    up = f["ultimo_pago"]
    if not up:
        return True
    return meses_entre(up, mes_actual()) >= per


def vencido(f):
    """Vencido = atrasado de un periodo ANTERIOR (no solo porque pasó el día de este mes)."""
    up = f["ultimo_pago"]
    if not up:
        return False
    per = PERIODO.get(f.get("frecuencia") or "Mensual", 1)
    return meses_entre(up, mes_actual()) > per


def pendientes_lista():
    return sorted([f for f in notion_fijos_listar() if esta_pendiente(f)], key=lambda f: f["dia"])


# ---------- Resumen colorido del mes ----------
CAT_EMOJI = {"Gasolina": "⛽", "Gas": "🔥", "Paradas": "🥤", "Alimentación": "🍔",
             "Mercado": "🛒", "Ocio": "🎉", "Servicios": "🏠", "Deudas": "💳",
             "Salud": "🩺", "Uber": "🚕", "Trading": "📈", "Lavado": "🧼",
             "Parqueadero": "🅿️", "Peajes": "🛣️", "Multas": "🚨", "Otros": "➕"}


def notion_gastos_desde(desde_iso):
    """Suma los gastos (no ingresos/transferencias) desde una fecha por categoría."""
    filtro = {"and": [
        {"property": "fecha", "date": {"on_or_after": desde_iso}},
        {"property": "tipo", "select": {"does_not_equal": "Ingreso"}},
        {"property": "tipo", "select": {"does_not_equal": "Transferencia"}}]}
    agg, total, cursor = {}, 0.0, None
    while True:
        body = {"page_size": 100, "filter": filtro}
        if cursor:
            body["start_cursor"] = cursor
        r = requests.post(f"{NOTION_API}/databases/{NOTION_DB}/query",
                          headers=NOTION_HEADERS, json=body, timeout=20)
        if r.status_code >= 300:
            raise RuntimeError(f"Notion {r.status_code}: {r.text[:300]}")
        d = r.json()
        for pg in d.get("results", []):
            pr = pg.get("properties", {})
            val = (pr.get("valor", {}) or {}).get("number") or 0
            cat = ((pr.get("categoria", {}) or {}).get("select") or {}).get("name") or "Otros"
            agg[cat] = agg.get(cat, 0) + val
            total += val
        if not d.get("has_more"):
            break
        cursor = d.get("next_cursor")
    return total, agg


def _resumen_texto(desde_iso, titulo):
    total, agg = notion_gastos_desde(desde_iso)
    if total <= 0:
        return f"📅 Aún no hay gastos registrados en {titulo.lower()}."
    filas = sorted(agg.items(), key=lambda x: -x[1])[:8]
    lineas = []
    for cat, val in filas:
        pct = val / total * 100
        barras = "█" * max(1, min(10, round(pct / 10)))
        em = CAT_EMOJI.get(cat, "•")
        lineas.append(f"{em} <b>{cat}</b>  {barras}  {fmt(val)} ({pct:.0f}%)")
    return (f"📅 <b>{titulo}</b>\n💸 Total gastado: <b>{fmt(total)}</b>\n\n" + "\n".join(lineas))


def resumen_mes_texto():
    return _resumen_texto(mes_actual() + "-01", f"Resumen del mes ({mes_actual()})")


def resumen_semana_texto():
    hoy = dt.date.today()
    lunes = hoy - dt.timedelta(days=hoy.weekday())  # lunes de esta semana
    return _resumen_texto(lunes.isoformat(), f"Resumen de la semana (desde {lunes.strftime('%d/%m')})")


# ---------- Telegram ----------
def _kb(rows):
    return {"inline_keyboard": rows}


def kb_tipo():
    return _kb([[{"text": "💰 Ingresos", "callback_data": "T|ingreso"},
                 {"text": "🧾 Pagos", "callback_data": "T|gasto"}],
                [{"text": "➕ Otro", "callback_data": "T|otro"}],
                [{"text": "📅 Resumen", "callback_data": "T|resumen"},
                 {"text": "📌 Pendientes", "callback_data": "P|ver"}]])


def kb_resumen():
    return _kb([[{"text": "📅 Mes", "callback_data": "RSM|mes"},
                 {"text": "🗓️ Semana", "callback_data": "RSM|semana"}],
                [{"text": "⬅️ Atrás", "callback_data": "T|inicio"}]])


def kb_otro():
    return _kb([
        [{"text": "🚗 KM", "callback_data": "O|km"},
         {"text": "📄 Pagos fijos", "callback_data": "P|ver"}],
        [{"text": "➕ Nuevo pago fijo", "callback_data": "F|nuevo"}],
        [{"text": "💸 Saldo a retirar (DiDi)", "callback_data": "O|retiromenu"}],
        [{"text": "🚕 Registrar DiDi/Uber", "callback_data": "O|didi"}],
        [{"text": "⬅️ Atrás", "callback_data": "T|inicio"}]])


def kb_retiro():
    return _kb([[{"text": "💸 Retirar TODO", "callback_data": "R|todo"},
                 {"text": "✏️ Otra cantidad", "callback_data": "R|parcial"}],
                [{"text": "⬅️ Atrás", "callback_data": "T|otro"}]])


def kb_grupos(modo):
    rows = [[{"text": g, "callback_data": f"G|{modo}|{i}"}] for i, (g, _) in enumerate(GRUPOS[modo])]
    rows.append([{"text": "⬅️ Atrás", "callback_data": "T|inicio"}])
    return _kb(rows)


def kb_categorias(modo, gi):
    _, cats = GRUPOS[modo][gi]
    fila, rows = [], []
    for c in cats:
        if c == "__didi__":
            continue
        fila.append({"text": c, "callback_data": f"C|{modo}|{c}"})
        if len(fila) == 2:
            rows.append(fila); fila = []
    if fila:
        rows.append(fila)
    rows.append([{"text": "⬅️ Atrás", "callback_data": f"B|{modo}"}])
    return _kb(rows)


def responder(chat_id, texto, markup=None, track=True):
    payload = {"chat_id": chat_id, "text": texto, "parse_mode": "HTML"}
    if markup:
        payload["reply_markup"] = markup
    try:
        r = requests.post(f"{TG_API}/sendMessage", json=payload, timeout=20)
        mid = r.json().get("result", {}).get("message_id")
        if track and mid:
            RASTRO.setdefault(chat_id, []).append(mid)
    except Exception as e:
        print("sendMessage err:", e)


def editar(chat_id, mid, texto, markup=None):
    """Edita el mensaje existente (fluido: el menú cambia en el sitio, sin mandar uno nuevo)."""
    payload = {"chat_id": chat_id, "message_id": mid, "text": texto, "parse_mode": "HTML"}
    if markup:
        payload["reply_markup"] = markup
    try:
        requests.post(f"{TG_API}/editMessageText", json=payload, timeout=20)
    except Exception as e:
        print("editMessageText err:", e)


def borrar(chat_id, mid):
    try:
        requests.post(f"{TG_API}/deleteMessage", json={"chat_id": chat_id, "message_id": mid}, timeout=15)
    except Exception:
        pass


def limpiar(chat_id):
    for mid in RASTRO.get(chat_id, []):
        borrar(chat_id, mid)
    RASTRO[chat_id] = []


def kb_fin(page_id=None):
    rows = []
    if page_id:
        rows.append([{"text": "🗒️ Agregar nota", "callback_data": f"N|{page_id}"}])
    rows += [[{"text": "💰 Ingresos", "callback_data": "T|ingreso"},
              {"text": "🧾 Pagos", "callback_data": "T|gasto"}],
             [{"text": "➕ Otro", "callback_data": "T|otro"}]]
    return _kb(rows)


def finalizar(chat_id, texto, page_id=None):
    """Borra los mensajes del flujo y deja SOLO el resultado + el menú de inicio."""
    limpiar(chat_id)
    responder(chat_id, texto, kb_fin(page_id))


def menu(chat_id):
    MODO.pop(chat_id, None)
    limpiar(chat_id)
    responder(chat_id, "¿Qué vas a registrar? 👇", kb_tipo())


# ---------- Registros ----------
def registrar_con_categoria(chat_id, texto, categoria, modo):
    valor, resto = parsear_monto(texto)
    if valor is None:
        responder(chat_id, "No leí el monto. Ej: <code>20000 efectivo papa</code>"); return False
    metodo, nota = metodo_y_nota(resto.split())
    tipo = tipo_de(categoria, modo)
    pid = notion_crear(nota or categoria, valor, categoria, metodo, tipo, notas=nota or None)
    et = "💰 Ingreso" if modo == "ingreso" else "🧾 Pago"
    finalizar(chat_id,
        f"✅ {et}: <b>{fmt(valor)}</b>\n🏷️ {categoria} · {tipo}\n💳 {metodo or '—'}" +
        (f"\n🗒️ {nota}" if nota else "") + "\n\n¿Algo más? 👇", pid)
    return True


def registrar_rapido(chat_id, texto, modo):
    valor, resto = parsear_monto(texto)
    if valor is None:
        responder(chat_id, "No encontré el valor. Usa /menu o: <code>15000 almuerzo nequi</code>"); return
    metodo, desc, nota = separar_por_metodo(resto.split())
    if not desc:
        desc = "Ingreso" if modo == "ingreso" else "Pago"
    categoria = adivinar_categoria(desc + " " + nota, modo)
    tipo = tipo_de(categoria, modo)
    pid = notion_crear(desc, valor, categoria, metodo, tipo, notas=nota or None)
    et = "💰 Ingreso" if modo == "ingreso" else "🧾 Pago"
    finalizar(chat_id,
        f"✅ {et}: <b>{fmt(valor)}</b>\n📝 {desc}\n🏷️ {categoria} · {tipo}\n💳 {metodo or '—'}\n\n¿Algo más? 👇", pid)


def registrar_fijo(chat_id, texto):
    partes = [x.strip() for x in texto.split(";")]
    if len(partes) < 4:
        responder(chat_id, "Formato: <b>nombre ; inmueble ; monto ; día ; frecuencia</b>\n"
                           "Ej: <code>Internet Casa ; Apto 1305 ; 80000 ; 10 ; mensual</code>\n"
                           "<i>Frecuencia: mensual, bimestral, trimestral, semestral, anual. Monto variable = 0.</i>\n"
                           "<i>El medio de pago lo eliges cuando lo pagues.</i>")
        return False
    nombre, inmueble = partes[0], partes[1]
    monto, _ = parsear_monto(partes[2])
    dia, _ = parsear_monto(partes[3])
    frec = FRECUENCIAS.get(partes[4].lower().strip(), "Mensual") if len(partes) > 4 else "Mensual"
    categoria = adivinar_categoria(nombre, "gasto")
    notion_fijo_crear(nombre, inmueble, categoria, monto or 0, int(dia or 1), frec, "")
    finalizar(chat_id,
        f"✅ Pago fijo guardado:\n<b>{nombre}</b>" + (f" · {inmueble}" if inmueble else "") + "\n"
        f"💵 {fmt(monto) if monto else 'variable'} · vence el <b>{int(dia or 1)}</b> · {frec}\n"
        f"🔔 Te avisaré 1-2 días antes.\n\n¿Algo más? 👇")
    return True


def _out(chat_id, mid, txt, mk=None):
    if mid:
        editar(chat_id, mid, txt, mk)
    else:
        responder(chat_id, txt, mk)


def mostrar_pendientes(chat_id, mid=None):
    pend = pendientes_lista()
    if not pend:
        _out(chat_id, mid, "🎉 No tienes pagos fijos pendientes.", kb_fin()); return
    total = sum(f["monto"] for f in pend)
    lineas, botones = [], []
    for f in pend:
        d = int(f["dia"])
        alerta = " ⚠️ Vencido" if vencido(f) else ""
        lineas.append(f"• <b>{f['nombre']}</b>" + (f" ({f['inmueble']})" if f['inmueble'] else "") +
                      f" — {fmt(f['monto']) if f['monto'] else 'variable'} · vence {d} · {f['frecuencia']}{alerta}")
        botones.append([{"text": f"✅ Pagar {f['nombre']}", "callback_data": f"PAY|{f['id']}"}])
    botones.append([{"text": "⬅️ Menú", "callback_data": "T|inicio"}])
    _out(chat_id, mid, "📄 <b>Pagos fijos pendientes</b>\n" + "\n".join(lineas) +
         f"\n\nTotal: <b>{fmt(total)}</b>", _kb(botones))


def _pagar(chat_id, f, monto, metodo=None):
    tipo = tipo_de(f["categoria"], "gasto")
    notion_crear(f["nombre"], monto, f["categoria"], metodo or f["metodo"] or None, tipo, notas=f["inmueble"] or None)
    notion_fijo_marcar_pagado(f["id"], mes_actual())
    pp = f.get("monto_pronto_pago") or 0
    ahorro = (f.get("monto") or 0) - monto
    extra = f"\n🎉 Pronto pago: ahorraste {fmt(ahorro)}." if (pp and monto == pp and ahorro > 0) else ""
    finalizar(chat_id, f"🟢 Pagado: <b>{f['nombre']}</b> — {fmt(monto)}{extra}\nRegistrado en Movimientos. 📌\n\n¿Algo más? 👇")


def pagar_fijo(chat_id, page_id, mid=None):
    f = next((x for x in notion_fijos_listar() if x["id"] == page_id), None)
    if not f:
        _out(chat_id, mid, "No encontré ese pago fijo."); return
    PENDIENTE[chat_id] = {"pagar_fijo": page_id}
    ef, desc = monto_efectivo(f)
    if f["monto"] and f["monto"] > 0:
        nota_desc = (f"\n🎉 <b>Pronto pago</b>: hoy pagas {fmt(ef)} (antes del día {int(f['dia_limite_descuento'])}), "
                     f"en vez de {fmt(f['monto'])}.") if desc else ""
        _out(chat_id, mid, f"Pagar <b>{f['nombre']}</b> ({fmt(ef)}).{nota_desc}\n¿Con qué medio?\n"
                           f"(efectivo, nequi, bancolombia, daviplata…)\n"
                           f"<i>Si el monto fue otro, escribe: monto medio</i>")
    else:
        _out(chat_id, mid, f"¿Cuánto pagaste de <b>{f['nombre']}</b> y con qué medio?\n"
                           f"Ej: <code>82000 bancolombia</code>")


# ---------- Callbacks ----------
def handle_callback(chat_id, data, mid):
    ed = lambda txt, mk=None: editar(chat_id, mid, txt, mk)   # edita en el sitio (fluido)
    if data == "T|inicio":
        ed("¿Qué vas a registrar? 👇", kb_tipo()); return
    if data in ("T|ingreso", "T|gasto"):
        modo = data.split("|")[1]; MODO[chat_id] = modo
        t = "💰 <b>Ingresos</b> — elige grupo:" if modo == "ingreso" else "🧾 <b>Pagos</b> — elige grupo:"
        ed(t, kb_grupos(modo)); return
    if data == "T|otro":
        MODO.pop(chat_id, None); ed("➕ <b>Otro</b>", kb_otro()); return
    if data == "T|resumen":
        ed("📅 <b>Resumen</b> — ¿de qué periodo?", kb_resumen()); return
    if data == "RSM|mes":
        try: ed(resumen_mes_texto(), kb_resumen())
        except Exception as e: ed(f"No pude armar el resumen: {e}", kb_resumen())
        return
    if data == "RSM|semana":
        try: ed(resumen_semana_texto(), kb_resumen())
        except Exception as e: ed(f"No pude armar el resumen: {e}", kb_resumen())
        return
    if data == "O|km":
        PENDIENTE[chat_id] = {"km": True}
        ed("🚗 Escribe: <b>odómetro combustible [costo]</b>\nEj: <code>45200 gas 30000</code>"); return
    if data == "O|didi":
        ed("🚕 ¿Cuál?", _kb([[{"text": "DiDi", "callback_data": "DD|DiDi"},
                             {"text": "Uber", "callback_data": "DD|Uber"}]])); return
    if data.startswith("DD|"):
        origen = data.split("|")[1]
        PENDIENTE[chat_id] = {"esperar_total": origen}
        ed(f"🚕 <b>{origen}</b>: escribe el <b>total del día</b>. Ej: <code>200000</code>"); return
    if data == "O|retiromenu":
        ed(f"🏦 Saldo DiDi: <b>{fmt(notion_saldo_didi())}</b>", kb_retiro()); return
    if data == "R|todo":
        acum = notion_saldo_didi()
        if acum <= 0:
            ed("No hay saldo para retirar.", kb_fin())
        else:
            notion_crear("Retiro DiDi → Bancolombia", acum, "Uber", "Bancolombia", "Transferencia",
                         didi=-acum, notas="Retiro de saldo DiDi a Bancolombia")
            ed(f"✅ Retirado <b>{fmt(acum)}</b> a Bancolombia.\n🏦 Saldo DiDi: <b>{fmt(notion_saldo_didi())}</b>\n\n¿Algo más? 👇", kb_fin())
        return
    if data == "R|parcial":
        PENDIENTE[chat_id] = {"retiro": True}
        ed("¿Cuánto retiras? Escribe el monto. Ej: <code>100000</code>"); return
    if data == "F|nuevo":
        PENDIENTE[chat_id] = {"fijo": True}
        ed("➕ Nuevo pago fijo. Escribe:\n"
           "<b>nombre ; inmueble ; monto ; día ; frecuencia</b>\n"
           "Ej: <code>Internet Casa ; Apto 1305 ; 80000 ; 10 ; mensual</code>\n"
           "<i>Frecuencia: mensual/bimestral/trimestral/semestral/anual. Variable = 0.\n"
           "El medio lo eliges al pagarlo.</i>"); return
    if data == "P|ver":
        mostrar_pendientes(chat_id, mid); return
    if data.startswith("PAY|"):
        pagar_fijo(chat_id, data.split("|", 1)[1], mid); return
    if data.startswith("N|"):
        PENDIENTE[chat_id] = {"nota_para": data.split("|", 1)[1]}
        ed("🗒️ Escribe la nota:"); return
    if data.startswith("B|"):
        ed("Elige grupo:", kb_grupos(data.split("|")[1])); return
    if data.startswith("G|"):
        _, modo, gi = data.split("|"); gi = int(gi)
        nombre, cats = GRUPOS[modo][gi]
        if cats == ["__didi__"]:
            ed("🚕 ¿Cuál?", _kb([[{"text": "DiDi", "callback_data": "DD|DiDi"},
                                 {"text": "Uber", "callback_data": "DD|Uber"}],
                                [{"text": "⬅️ Atrás", "callback_data": f"B|{modo}"}]]))
            return
        reales = [c for c in cats if c != "__didi__"]
        if len(reales) == 1:
            handle_callback(chat_id, f"C|{modo}|{reales[0]}", mid); return
        ed(f"{nombre} — elige categoría:", kb_categorias(modo, gi)); return
    if data.startswith("C|"):
        _, modo, cat = data.split("|", 2)
        PENDIENTE[chat_id] = {"categoria": cat, "modo": modo}
        ed(f"Elegiste <b>{cat}</b>. Escribe: <b>monto [medio] [nota]</b>\nEj: <code>20000 efectivo papa</code>"); return


# ---------- Mensajes ----------
def manejar(chat_id, texto):
    t = texto.strip(); low = t.lower()
    if low in ("/start", "/menu", "menu", "hola", "inicio"):
        menu(chat_id); return
    if low in ("/mes", "mes", "resumen", "/resumen"):
        try:
            responder(chat_id, resumen_mes_texto(), kb_resumen())
        except Exception as e:
            responder(chat_id, f"No pude armar el resumen: {e}")
        return
    if low in ("/semana", "semana"):
        try:
            responder(chat_id, resumen_semana_texto(), kb_resumen())
        except Exception as e:
            responder(chat_id, f"No pude armar el resumen: {e}")
        return
    if low in ("/pendientes", "pendientes"):
        mostrar_pendientes(chat_id); return

    if chat_id in PENDIENTE:
        p = PENDIENTE[chat_id]
        if "esperar_total" in p:
            total, _ = parsear_monto(t)
            if total is None:
                responder(chat_id, "Dime el total del día. Ej: <code>200000</code>"); return
            origen = p["esperar_total"]
            PENDIENTE[chat_id] = {"origen": origen, "total": total}
            responder(chat_id, f"{origen}: total <b>{fmt(total)}</b>.\n"
                               f"¿Cuánto muestra tu <b>saldo {origen}</b> ahora? (el total de la app)\n"
                               f"O escribe <b>igual</b> si no cambió."); return
        if "origen" in p:
            PENDIENTE.pop(chat_id)
            origen = p["origen"]; actual = notion_saldo_didi()
            if low in ("no", "igual", "mismo", "nada"):
                reportado = actual
            else:
                reportado, _ = parsear_monto(t)
                if reportado is None:
                    reportado = actual
            notion_crear(f"{origen} del día", p["total"], "Uber", None, "Ingreso",
                         didi=reportado - actual, notas=f"Ingreso {origen}. Saldo app: {fmt(reportado)}")
            finalizar(chat_id, f"✅ Ingreso {origen}: <b>{fmt(p['total'])}</b>\n🏦 Saldo DiDi ahora: <b>{fmt(reportado)}</b>\n\n¿Algo más? 👇")
            return
        if "categoria" in p:
            if registrar_con_categoria(chat_id, t, p["categoria"], p["modo"]):
                PENDIENTE.pop(chat_id)
            return
        if "km" in p:
            if registrar_km(chat_id, t):
                PENDIENTE.pop(chat_id)
            return
        if "fijo" in p:
            if registrar_fijo(chat_id, t):
                PENDIENTE.pop(chat_id)
            return
        if "retiro" in p:
            PENDIENTE.pop(chat_id)
            monto, _ = parsear_monto(t)
            acum = notion_saldo_didi()
            if monto is None or monto <= 0:
                responder(chat_id, "Monto inválido."); return
            monto = min(monto, acum)
            notion_crear("Retiro DiDi → Bancolombia", monto, "Uber", "Bancolombia", "Transferencia",
                         didi=-monto, notas="Retiro parcial de saldo DiDi")
            finalizar(chat_id, f"✅ Retirado <b>{fmt(monto)}</b>.\n🏦 Saldo DiDi: <b>{fmt(notion_saldo_didi())}</b>\n\n¿Algo más? 👇")
            return
        if "pagar_fijo" in p:
            PENDIENTE.pop(chat_id)
            f = next((x for x in notion_fijos_listar() if x["id"] == p["pagar_fijo"]), None)
            if not f:
                responder(chat_id, "No encontré ese pago."); return
            monto, resto = parsear_monto(t)
            if monto is None:            # no puso monto: usa el fijo (con descuento si aplica)
                monto, _desc = monto_efectivo(f)
                metodo, _n = metodo_y_nota(t.split())
            else:
                metodo, _n = metodo_y_nota(resto.split())
            if not monto or monto <= 0:
                responder(chat_id, "Dime el monto. Ej: <code>82000 bancolombia</code>"); return
            _pagar(chat_id, f, monto, metodo)
            return
        if "nota_para" in p:
            PENDIENTE.pop(chat_id)
            notion_agregar_nota(p["nota_para"], t)
            finalizar(chat_id, "🗒️ Nota agregada.\n\n¿Algo más? 👇"); return

    if low.startswith("didi") or low.startswith("uber"):
        origen = "DiDi" if low.startswith("didi") else "Uber"
        resto = t[4:].strip(); rl = resto.lower()
        if rl.startswith("saldo"):
            responder(chat_id, f"🏦 Saldo DiDi: <b>{fmt(notion_saldo_didi())}</b>", kb_retiro()); return
        if rl.startswith("retirar") or rl.startswith("retiro"):
            monto, _ = parsear_monto(rl); acum = notion_saldo_didi()
            retiro = min(monto, acum) if monto else acum
            if retiro <= 0:
                responder(chat_id, "No hay saldo para retirar."); return
            notion_crear("Retiro DiDi → Bancolombia", retiro, "Uber", "Bancolombia", "Transferencia",
                         didi=-retiro, notas="Retiro de saldo DiDi a Bancolombia")
            finalizar(chat_id, f"✅ Retirado <b>{fmt(retiro)}</b>.\n🏦 Saldo DiDi: <b>{fmt(notion_saldo_didi())}</b>\n\n¿Algo más? 👇"); return
        total, _ = parsear_monto(resto)
        if total is None:
            responder(chat_id, "Dime el total. Ej: <code>didi 200000</code>"); return
        PENDIENTE[chat_id] = {"origen": origen, "total": total}
        responder(chat_id, f"{origen}: total del día <b>{fmt(total)}</b>.\n"
                           f"¿Cuánto muestra tu <b>saldo {origen}</b> ahora? (el total de la app)\n"
                           f"O escribe <b>igual</b> si no cambió."); return

    modo = MODO.get(chat_id)
    if modo:
        registrar_rapido(chat_id, t, modo); return
    responder(chat_id, "Elige con /menu 👇", kb_tipo())


# ---------- Recordatorios ----------
def guardar_chat(chat_id):
    try:
        with open(CHAT_FILE, "w") as fh:
            fh.write(str(chat_id))
    except OSError:
        pass


def cargar_chat():
    if SOLO_CHAT:
        return SOLO_CHAT
    try:
        with open(CHAT_FILE) as fh:
            return fh.read().strip()
    except OSError:
        return None


def revisar_recordatorios(chat_id):
    if not chat_id:
        return
    hoy = dt.datetime.now().day
    try:
        for f in notion_fijos_listar():
            if not esta_pendiente(f) or not f.get("notificar", True):
                continue
            faltan = int(f["dia"]) - hoy
            if faltan in (1, 2):
                responder(chat_id,
                    f"🔔 <b>{f['nombre']}</b>" + (f" ({f['inmueble']})" if f['inmueble'] else "") +
                    f" vence en {faltan} día(s) (el {int(f['dia'])}).\n"
                    f"💵 {fmt(f['monto']) if f['monto'] else 'variable'} · págalo en 📄 Pagos fijos.",
                    track=False)
    except Exception as e:
        print("recordatorio err:", e)


# ---------- Main ----------
def main():
    faltan = [k for k, v in {"TELEGRAM_TOKEN": TG_TOKEN, "NOTION_TOKEN": NOTION_TOKEN,
                             "NOTION_DB_ID": NOTION_DB}.items() if not v]
    if faltan:
        print("Falta en el .env:", ", ".join(faltan)); return
    print("Bot corriendo. Escríbele /start. (Ctrl+C para parar)")
    offset = None
    ult_check = None
    while True:
        try:
            # Recordatorios: una vez al día
            hoy = dt.date.today().isoformat()
            if hoy != ult_check:
                revisar_recordatorios(cargar_chat())
                ult_check = hoy

            r = requests.get(f"{TG_API}/getUpdates", params={"timeout": 30, "offset": offset}, timeout=40)
            for upd in r.json().get("result", []):
                offset = upd["update_id"] + 1
                cb = upd.get("callback_query")
                if cb:
                    chat_id = str(cb["message"]["chat"]["id"])
                    if SOLO_CHAT and chat_id != SOLO_CHAT:
                        continue
                    requests.post(f"{TG_API}/answerCallbackQuery", json={"callback_query_id": cb["id"]}, timeout=20)
                    try:
                        handle_callback(chat_id, cb.get("data", ""), cb["message"]["message_id"])
                    except Exception as e:
                        responder(chat_id, f"⚠️ Error: {e}"); print("ERROR cb:", e)
                    continue
                msg = upd.get("message") or upd.get("edited_message")
                if not msg or "text" not in msg:
                    continue
                chat_id = str(msg["chat"]["id"])
                if SOLO_CHAT and chat_id != SOLO_CHAT:
                    continue
                guardar_chat(chat_id)
                RASTRO.setdefault(chat_id, []).append(msg["message_id"])
                try:
                    manejar(chat_id, msg["text"])
                except Exception as e:
                    responder(chat_id, f"⚠️ Error: {e}"); print("ERROR:", e)
        except requests.RequestException as e:
            print("Red:", e); time.sleep(3)
        except KeyboardInterrupt:
            print("\nAdiós."); break


if __name__ == "__main__":
    main()
