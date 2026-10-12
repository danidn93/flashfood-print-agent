import json
import plistlib
import webbrowser
import os
import platform
import subprocess
import sys
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from queue import Queue, Empty
from typing import Any, Dict, List, Optional, Tuple

import requests
import customtkinter as ctk
from PIL import Image
from tkinter import messagebox

from build_config import (
    SUPABASE_URL as BUILD_SUPABASE_URL,
    SUPABASE_ANON_KEY as BUILD_SUPABASE_ANON_KEY,
)

APP_NAME = "FlashFood Print Agent"
APP_VERSION = "1.5.0"
POLL_SECONDS = 3
REQUEST_TIMEOUT = 20

def app_dir() -> Path:
    system = platform.system().lower()
    if system == "windows":
        base = Path(os.getenv("APPDATA") or Path.home())
    elif system == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.getenv("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    path = base / "FlashFoodPrintAgent"
    path.mkdir(parents=True, exist_ok=True)
    return path

CONFIG_FILE = app_dir() / "config.json"
LOG_FILE = app_dir() / "agent.log"

def log(msg: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line)
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

@dataclass
class AgentConfig:
    supabase_url: str = ""
    anon_key: str = ""
    agent_token: str = ""
    agent_id: str = ""
    local_name: str = ""
    sucursal_name: str = ""
    printer_kitchen: str = ""
    printer_invoice: str = ""
    kitchen_enabled: bool = True
    invoice_enabled: bool = True
    paper_kitchen_mm: int = 80
    paper_invoice_mm: int = 80
    kitchen_copies: int = 1
    invoice_copies: int = 1
    kitchen_cut: bool = True
    invoice_cut: bool = True
    auto_start_worker: bool = True
    device_name: str = ""
    terminal_id: str = ""

def load_config() -> AgentConfig:
    defaults = AgentConfig(
        supabase_url=str(BUILD_SUPABASE_URL or os.environ.get("FF_SUPABASE_URL") or os.environ.get("PALACIO_SUPABASE_URL") or ""),
        anon_key=str(BUILD_SUPABASE_ANON_KEY or os.environ.get("FF_SUPABASE_ANON_KEY") or os.environ.get("PALACIO_SUPABASE_ANON_KEY") or ""),
        device_name=platform.node() or "Esta computadora",
        terminal_id=__import__("uuid").uuid4().hex[:8],
    )
    if not CONFIG_FILE.exists():
        return defaults
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return AgentConfig(
            supabase_url=defaults.supabase_url or str(data.get("supabase_url") or ""),
            anon_key=defaults.anon_key or str(data.get("anon_key") or ""),
            agent_token=str(data.get("agent_token") or ""),
            agent_id=str(data.get("agent_id") or ""),
            local_name=str(data.get("local_name") or ""),
            sucursal_name=str(data.get("sucursal_name") or ""),
            printer_kitchen=str(data.get("printer_kitchen") or ""),
            printer_invoice=str(data.get("printer_invoice") or ""),
            kitchen_enabled=bool(data.get("kitchen_enabled", True)),
            invoice_enabled=bool(data.get("invoice_enabled", True)),
            paper_kitchen_mm=int(data.get("paper_kitchen_mm") or 80),
            paper_invoice_mm=int(data.get("paper_invoice_mm") or 80),
            kitchen_copies=max(1, int(data.get("kitchen_copies") or 1)),
            invoice_copies=max(1, int(data.get("invoice_copies") or 1)),
            kitchen_cut=bool(data.get("kitchen_cut", True)),
            invoice_cut=bool(data.get("invoice_cut", True)),
            auto_start_worker=bool(data.get("auto_start_worker", True)),
            device_name=str(data.get("device_name") or defaults.device_name),
            terminal_id=str(data.get("terminal_id") or defaults.terminal_id),
        )
    except Exception as e:
        log(f"Error leyendo configuración: {e}")
        return defaults

def save_config(cfg: AgentConfig) -> None:
    CONFIG_FILE.write_text(
        json.dumps(asdict(cfg), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

def headers(cfg: AgentConfig) -> Dict[str, str]:
    return {
        "apikey": cfg.anon_key,
        "Authorization": f"Bearer {cfg.anon_key}",
        "Content-Type": "application/json",
    }

def rpc(cfg: AgentConfig, name: str, payload: Dict[str, Any]) -> Any:
    base = cfg.supabase_url.rstrip("/")
    url = f"{base}/rest/v1/rpc/{name}"
    r = requests.post(
        url,
        headers=headers(cfg),
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    if not r.ok:
        raise RuntimeError(f"{name}: HTTP {r.status_code}: {r.text}")
    if not r.text:
        return None
    try:
        return r.json()
    except Exception:
        return r.text

PDF_TEST_PRINTER = "FlashFood - Guardar ticket en PDF (prueba)"

UPDATE_FEED_URL = "https://api.github.com/repos/danidn93/flashfood-print-agent/releases/latest"
LOGIN_AGENT_LABEL = "com.flashfood.printagent.login"


def macos_login_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LOGIN_AGENT_LABEL}.plist"


def macos_login_enabled() -> bool:
    return platform.system() == "Darwin" and macos_login_agent_path().exists()


def set_macos_login_enabled(enabled: bool) -> None:
    if platform.system() != "Darwin":
        raise RuntimeError("Esta opción está disponible en macOS.")
    path = macos_login_agent_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    executable = Path(sys.executable).resolve()
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Instala la aplicación compilada en Aplicaciones antes de activar el inicio automático.")
    if ".app/Contents/MacOS/" not in str(executable):
        raise RuntimeError("Abre el agente desde la aplicación .app instalada en Aplicaciones.")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LOGIN_AGENT_LABEL,
        "ProgramArguments": [str(executable)],
        "RunAtLoad": True,
        "KeepAlive": False,
        "ProcessType": "Interactive",
    }
    with path.open("wb") as file:
        plistlib.dump(payload, file)


def release_version_info() -> tuple[str, str]:
    """Return the latest published release; never auto-execute downloaded code."""
    response = requests.get(UPDATE_FEED_URL, timeout=15, headers={"Accept": "application/vnd.github+json"})
    if response.status_code == 404:
        raise RuntimeError("Todavía no hay una versión pública disponible para actualizar.")
    response.raise_for_status()
    data = response.json()
    return str(data.get("tag_name", "")).lstrip("v"), str(data.get("html_url", ""))


def version_parts(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return (0,)


def list_printers() -> List[str]:
    system = platform.system().lower()
    result: List[str] = []
    try:
        if system == "windows":
            p = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-Printer | Select-Object -ExpandProperty Name"],
                capture_output=True, text=True, timeout=15,
            )
            if p.returncode == 0:
                result = [x.strip() for x in p.stdout.splitlines() if x.strip()]
        else:
            # lpstat -e returns queue names independent of the OS language.
            p = subprocess.run(["lpstat", "-e"], capture_output=True, text=True, timeout=15)
            if p.returncode == 0:
                result = [x.strip() for x in p.stdout.splitlines() if x.strip()]
            if not result:
                p = subprocess.run(["lpstat", "-v"], capture_output=True, text=True, timeout=15)
                if p.returncode == 0:
                    result = [
                        line.split(":", 1)[0].rsplit(" ", 1)[-1]
                        for line in p.stdout.splitlines() if ":" in line
                    ]
    except Exception as e:
        log(f"No se pudieron listar impresoras: {e}")
    return sorted(set(result), key=str.lower)


def save_ticket_as_pdf(text: str) -> Path:
    """Generate a local test ticket; no CUPS queue or physical printer required."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    directory = Path.home() / "Documents" / "FlashFood Print Agent" / "Tickets PDF"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"ticket-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.pdf"
    lines = text.expandtabs(4).splitlines() or [""]
    width = 80 * mm
    margin = 4 * mm
    font_name = "Courier"
    font_path = Path("/System/Library/Fonts/Supplemental/Courier New.ttf")
    if font_path.exists():
        try:
            pdfmetrics.registerFont(TTFont("FlashFoodCourier", str(font_path)))
            font_name = "FlashFoodCourier"
        except Exception:
            pass
    font_size = 8
    leading = 10
    height = max(60 * mm, (len(lines) * leading + 2 * margin))
    pdf = canvas.Canvas(str(path), pagesize=(width, height))
    pdf.setTitle("FlashFood - Ticket de prueba")
    pdf.setFont(font_name, font_size)
    y = height - margin - leading
    for line in lines:
        pdf.drawString(margin, y, line[:50])
        y -= leading
    pdf.save()
    log(f"Ticket de prueba PDF: {path}")
    return path

def print_text_windows(printer_name: str, text: str) -> None:
    try:
        import win32print
    except Exception as e:
        raise RuntimeError(
            "Falta pywin32 en Windows. Reinstala el agente desde el instalador."
        ) from e

    hprinter = win32print.OpenPrinter(printer_name)
    try:
        job = win32print.StartDocPrinter(
            hprinter,
            1,
            (APP_NAME, None, "RAW"),
        )
        try:
            win32print.StartPagePrinter(hprinter)
            # ESC/POS init + CP850 where supported.
            data = b"\x1b@" + text.encode("cp850", errors="replace") + b"\n\n\n"
            win32print.WritePrinter(hprinter, data)
            win32print.EndPagePrinter(hprinter)
        finally:
            win32print.EndDocPrinter(hprinter)
    finally:
        win32print.ClosePrinter(hprinter)

def print_text_unix(printer_name: str, text: str) -> None:
    p = subprocess.run(
        ["lp", "-d", printer_name, "-o", "raw"],
        input=text.encode("utf-8", errors="replace"),
        capture_output=True,
        timeout=30,
    )
    if p.returncode != 0:
        raise RuntimeError(
            (p.stderr or p.stdout or b"Error enviando a impresora")
            .decode("utf-8", errors="replace")
        )

def print_text(printer_name: str, text: str) -> None:
    if printer_name == PDF_TEST_PRINTER:
        save_ticket_as_pdf(text)
        return
    if not printer_name:
        raise RuntimeError("No hay impresora configurada para este tipo de trabajo.")
    if platform.system().lower() == "windows":
        print_text_windows(printer_name, text)
    else:
        print_text_unix(printer_name, text)

def money(value: Any) -> str:
    try:
        return f"{float(value or 0):.2f}"
    except Exception:
        return "0.00"

def clean(value: Any) -> str:
    return str(value or "").strip()

def wrap_text(text: str, width: int = 42) -> List[str]:
    words = clean(text).split()
    if not words:
        return []
    lines: List[str] = []
    cur = ""
    for word in words:
        nxt = word if not cur else f"{cur} {word}"
        if len(nxt) <= width:
            cur = nxt
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines

def center(text: str, width: int = 42) -> str:
    text = clean(text)
    if len(text) >= width:
        return text
    left = max(0, (width - len(text)) // 2)
    return (" " * left) + text

def line(width: int = 42, ch: str = "-") -> str:
    return ch * width

def extract_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = [
        payload.get("items"),
        payload.get("pedido_items"),
        payload.get("detalle"),
        payload.get("productos"),
    ]
    for c in candidates:
        if isinstance(c, list):
            return [x for x in c if isinstance(x, dict)]
    return []

def item_name(item: Dict[str, Any]) -> str:
    p = item.get("productos_local")
    if isinstance(p, dict):
        return clean(p.get("nombre") or p.get("descripcion") or "Producto")
    return clean(
        item.get("nombre_producto")
        or item.get("nombre")
        or item.get("descripcion")
        or "Producto"
    )

def item_qty(item: Dict[str, Any]) -> Any:
    return item.get("cantidad", item.get("qty", 1))

def item_note(item: Dict[str, Any]) -> str:
    return clean(item.get("nota") or item.get("observacion") or item.get("comentario"))

def format_kitchen(payload: Dict[str, Any]) -> str:
    width = 42
    lines: List[str] = []

    source = clean(payload.get("origen") or payload.get("source")).upper()
    order_number = payload.get("ticket_number") or payload.get("numero_pedido") or payload.get("pedido_numero") or ""
    delivery_type = clean(payload.get("tipo_entrega")).lower()
    priority = bool(payload.get("prioritario") or payload.get("pedido_prioritario"))
    pickup_time = clean(payload.get("retiro_estimado_at") or payload.get("hora_retiro"))
    client = clean(payload.get("cliente_nombre") or payload.get("cliente"))
    order_note = clean(payload.get("observacion") or payload.get("observacion_cliente") or payload.get("observacion_pedido") or payload.get("nota_pedido"))

    lines.append(center("*** PEDIDO COCINA ***", width))
    if source:
        lines.append(center(f"ORIGEN: {source}", width))
    if order_number:
        lines.append(center(f"PEDIDO #{order_number}", width))
    if priority:
        lines.append(center("!!! PRIORITARIO !!!", width))
    lines.append(line(width))

    mesa_nombre = clean(payload.get("mesa_nombre") or payload.get("mesa"))
    if mesa_nombre:
        lines.append(f"MESA: {mesa_nombre}")
    if delivery_type:
        label = "DELIVERY" if delivery_type == "delivery" else ("SERVIR EN LOCAL" if delivery_type in ("local", "consumo_local", "mesa") else "RETIRO EN LOCAL")
        lines.append(f"ENTREGA: {label}")
    if pickup_time and delivery_type != "delivery":
        lines.append(f"RETIRO: {pickup_time}")
    if client:
        lines.append(f"CLIENTE: {client}")

    if delivery_type or pickup_time or client:
        lines.append(line(width))

    items = extract_items(payload)
    for item in items:
        qty = item_qty(item)
        name = item_name(item)
        for idx, wrapped in enumerate(wrap_text(f"{qty} x {name}", width)):
            lines.append(wrapped if idx else wrapped.upper())
        note = item_note(item)
        if note:
            for w in wrap_text(f"OBS: {note}", width):
                lines.append("  " + w)
        lines.append("")

    if order_note:
        lines.append(line(width))
        lines.append("OBSERVACION DEL PEDIDO:")
        for w in wrap_text(order_note, width):
            lines.append(w)

    lines.append(line(width))
    lines.append(center("GRACIAS", width))
    return "\n".join(lines) + "\n"

def format_invoice(payload: Dict[str, Any]) -> str:
    width = 42
    lines: List[str] = []

    local_name = clean(
        payload.get("nombre_comercial")
        or payload.get("local_nombre")
        or payload.get("negocio")
        or "RESTAURANTE"
    )
    invoice_number = clean(payload.get("numero_factura") or payload.get("factura_numero"))
    client = clean(payload.get("cliente_nombre") or payload.get("cliente"))
    ident = clean(payload.get("cliente_identificacion") or payload.get("identificacion"))
    payment = clean(payload.get("metodo_pago") or payload.get("metodo"))
    source = clean(payload.get("origen") or "APP").upper()
    delivery_type = clean(payload.get("tipo_entrega")).lower()

    lines.append(center(local_name.upper(), width))
    lines.append(center("FACTURA / COMPROBANTE", width))
    if invoice_number:
        lines.append(center(invoice_number, width))
    lines.append(line(width))

    if client:
        lines.append(f"CLIENTE: {client}")
    if ident:
        lines.append(f"ID: {ident}")
    if payment:
        lines.append(f"PAGO: {payment.upper()}")
    lines.append(f"ORIGEN: {source}")
    if delivery_type:
        lines.append(
            f"ENTREGA: {'DELIVERY' if delivery_type == 'delivery' else 'RETIRO EN LOCAL'}"
        )

    items = extract_items(payload)
    if items:
        lines.append(line(width))
        for item in items:
            qty = item_qty(item)
            name = item_name(item)
            subtotal = item.get("subtotal")
            text = f"{qty} x {name}"
            for w in wrap_text(text, width):
                lines.append(w)
            if subtotal is not None:
                lines.append(f"{'':24}{money(subtotal):>18}")

    lines.append(line(width))
    if payload.get("subtotal") is not None:
        lines.append(f"{'SUBTOTAL':<24}{money(payload.get('subtotal')):>18}")
    if payload.get("impuestos") is not None:
        lines.append(f"{'IVA':<24}{money(payload.get('impuestos')):>18}")
    if payload.get("total") is not None:
        lines.append(f"{'TOTAL FACTURA':<24}{money(payload.get('total')):>18}")

    extras = [
        ("DELIVERY", payload.get("app_costo_delivery") or payload.get("costo_delivery")),
        ("SERVICIO APP", payload.get("app_tarifa_servicio") or payload.get("tarifa_servicio")),
        ("PRIORIDAD", payload.get("app_tarifa_prioridad") or payload.get("tarifa_prioridad")),
        ("PROPINA", payload.get("app_propina_delivery") or payload.get("propina_delivery")),
    ]
    shown = False
    for label, value in extras:
        try:
            if float(value or 0) > 0:
                if not shown:
                    lines.append(line(width))
                    lines.append(center("CARGOS NO INCLUIDOS EN SRI", width))
                    shown = True
                lines.append(f"{label:<24}{money(value):>18}")
        except Exception:
            pass

    total_paid = payload.get("app_total_pagado") or payload.get("total_pagado")
    if total_paid is not None:
        lines.append(f"{'TOTAL PAGADO':<24}{money(total_paid):>18}")

    lines.append(line(width))
    lines.append(center("¡GRACIAS POR TU VISITA!", width))
    lines.append(center(local_name, width))
    return "\n".join(lines) + "\n"

def choose_printer_and_text(cfg: AgentConfig, job: Dict[str, Any]) -> Tuple[str, str]:
    tipo = clean(job.get("tipo")).lower()
    payload = job.get("payload")
    if not isinstance(payload, dict):
        payload = {}

    destination = clean(
        payload.get("destino_impresion")
        or payload.get("printer_role")
        or payload.get("destino")
    ).lower()

    invoice_types = {
        "factura",
        "factura_app",
        "invoice",
        "invoice_reprint",
        "factura_reprint",
        "reimpresion_factura",
    }

    is_invoice = (
        destination in {"factura", "facturas", "mostrador", "invoice"}
        or tipo in invoice_types
        or "factura" in tipo
        or "invoice" in tipo
    )

    if is_invoice:
        if not cfg.invoice_enabled:
            raise RuntimeError("La impresión de facturas está deshabilitada en este equipo.")
        return cfg.printer_invoice, format_invoice(payload)

    if not cfg.kitchen_enabled:
        raise RuntimeError("La impresión de cocina está deshabilitada en este equipo.")
    return cfg.printer_kitchen, format_kitchen(payload)

class Worker(threading.Thread):
    def __init__(self, cfg_getter, events: Queue):
        super().__init__(daemon=True)
        self.cfg_getter = cfg_getter
        self.events = events
        self.stop_event = threading.Event()

    def emit(self, event: str, message: str = ""):
        self.events.put((event, message))

    def stop(self):
        self.stop_event.set()

    def run(self):
        self.emit("status", "Conectando…")
        while not self.stop_event.is_set():
            cfg = self.cfg_getter()

            if not cfg.supabase_url or not cfg.anon_key or not cfg.agent_token:
                self.emit("status", "Falta configurar conexión o token")
                time.sleep(2)
                continue

            try:
                try:
                    rpc(cfg, "print_agent_ping", {"p_token": cfg.agent_token})
                except Exception as e:
                    log(f"Ping: {e}")

                job = rpc(
                    cfg,
                    "print_agent_claim_job",
                    {"p_token": cfg.agent_token},
                )

                if not job or (isinstance(job, dict) and not job.get("id")):
                    self.emit("status", "Conectado · esperando trabajos")
                    time.sleep(POLL_SECONDS)
                    continue

                job_id = clean(job.get("id"))
                self.emit("status", f"Imprimiendo {job_id[:8]}…")
                log(f"Trabajo recibido {job_id}: tipo={job.get('tipo')}")

                try:
                    printer, text = choose_printer_and_text(cfg, job)
                    if not printer:
                        raise RuntimeError("No hay impresora configurada para este trabajo.")
                    print_text(printer, text)
                    rpc(
                        cfg,
                        "print_agent_finish_job",
                        {
                            "p_token": cfg.agent_token,
                            "p_job_id": job_id,
                            "p_ok": True,
                            "p_error": None,
                        },
                    )
                    self.emit("printed", job_id)
                    self.emit("status", "Conectado · impresión completada")
                    log(f"Trabajo impreso {job_id} en {printer}")
                except Exception as e:
                    err = str(e)
                    log(f"Error imprimiendo {job_id}: {err}")
                    try:
                        rpc(
                            cfg,
                            "print_agent_finish_job",
                            {
                                "p_token": cfg.agent_token,
                                "p_job_id": job_id,
                                "p_ok": False,
                                "p_error": err[:1000],
                            },
                        )
                    except Exception as rpc_error:
                        log(f"No se pudo marcar error de job: {rpc_error}")
                    self.emit("error", err)
                    self.emit("status", "Error de impresión")
                    time.sleep(2)

            except Exception as e:
                log(f"Worker: {e}")
                self.emit("error", str(e))
                self.emit("status", "Sin conexión")
                time.sleep(5)


ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

class App(ctk.CTk):
    PAGE = "#EEF3F8"
    CARD = "#FFFFFF"
    DARK = "#121212"
    DARK2 = "#1C1C1C"
    TEXT = "#0F172A"
    MUTED = "#64748B"
    BORDER = "#DDE5EF"
    ORANGE = "#FF7100"
    ORANGE_DARK = "#E85E00"
    ORANGE_SOFT = "#FFF1E7"
    BLUE = "#1677F2"
    BLUE_SOFT = "#EAF3FF"
    GREEN = "#16A34A"
    GREEN_SOFT = "#ECFDF3"
    GREEN_BORDER = "#B7E7C6"

    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1460x900")
        self.minsize(1180, 760)
        self.configure(fg_color=self.PAGE)

        self.cfg = load_config()
        self.events: Queue = Queue()
        self.worker: Optional[Worker] = None
        self.activities: List[Tuple[str, str, str, str]] = []
        self._logo = None

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after(250, self.process_events)
        self.render()

        if self.cfg.agent_token and self.cfg.auto_start_worker:
            self.after(800, self.start_worker)

    def _asset(self, name: str) -> Path:
        if hasattr(sys, "_MEIPASS"):
            return Path(getattr(sys, "_MEIPASS")) / "assets" / name
        return Path(__file__).resolve().parent / "assets" / name

    def card(self, parent, fg=None, border=None, radius=24):
        return ctk.CTkFrame(
            parent,
            fg_color=fg or self.CARD,
            border_width=1,
            border_color=border or self.BORDER,
            corner_radius=radius,
        )

    def label(self, parent, text, size=13, weight="normal", color=None, **kwargs):
        return ctk.CTkLabel(
            parent,
            text=text,
            text_color=color or self.TEXT,
            font=ctk.CTkFont(size=size, weight=weight),
            **kwargs,
        )

    def button(self, parent, text, command, primary=False, color=None, width=140):
        if primary:
            fg=color or self.ORANGE
            return ctk.CTkButton(
                parent, text=text, command=command, width=width, height=42,
                corner_radius=13, fg_color=fg,
                hover_color=self.ORANGE_DARK if not color else fg,
                text_color="#FFFFFF",
                font=ctk.CTkFont(size=13, weight="bold"),
            )
        return ctk.CTkButton(
            parent, text=text, command=command, width=width, height=42,
            corner_radius=13, fg_color="#FFFFFF", hover_color="#F1F5F9",
            text_color=self.TEXT, border_width=1, border_color=self.BORDER,
            font=ctk.CTkFont(size=13, weight="bold"),
        )

    def clear(self):
        for child in self.winfo_children():
            child.destroy()

    def load_logo(self):
        try:
            img = Image.open(self._asset("logo.png"))
            return ctk.CTkImage(light_image=img, dark_image=img, size=(148, 112))
        except Exception as e:
            log(f"Logo: {e}")
            return None

    def render(self):
        self.clear()
        shell = ctk.CTkScrollableFrame(self, fg_color=self.PAGE, corner_radius=0)
        shell.pack(fill="both", expand=True)
        shell.grid_columnconfigure(0, weight=1)

        self.render_hero(shell)

        if not self.cfg.agent_token:
            self.render_pairing(shell)
        else:
            self.render_dashboard(shell)

    def render_hero(self, shell):
        hero = ctk.CTkFrame(shell, fg_color=self.DARK, corner_radius=28, height=170)
        hero.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))
        hero.grid_propagate(False)
        hero.grid_columnconfigure(1, weight=1)

        logo = self.load_logo()
        if logo:
            self._logo = logo
            ctk.CTkLabel(hero, image=logo, text="").grid(
                row=0, column=0, rowspan=3, padx=(28,18), pady=22
            )

        titles = ctk.CTkFrame(hero, fg_color="transparent")
        titles.grid(row=0, column=1, rowspan=3, sticky="w", pady=30)
        self.label(titles, "FLASHFOOD", 13, "bold", self.ORANGE).pack(anchor="w")
        self.label(titles, "Print Agent", 34, "bold", "#FFFFFF").pack(anchor="w", pady=(3,2))
        self.label(
            titles, "Impresión automática para restaurantes", 15, "normal", "#D1D5DB"
        ).pack(anchor="w")

        badge = ctk.CTkFrame(
            hero, fg_color="#2A2119", border_width=1, border_color="#725030", corner_radius=22
        )
        badge.grid(row=1, column=2, padx=28, pady=35)
        self.status_dot = self.label(badge, "●", 19, "bold", self.ORANGE)
        self.status_dot.pack(side="left", padx=(18,8), pady=12)
        btxt = ctk.CTkFrame(badge, fg_color="transparent")
        btxt.pack(side="left", padx=(0,18), pady=9)
        self.status_title = self.label(btxt, "Agente detenido", 13, "bold", "#FFFFFF")
        self.status_title.pack(anchor="w")
        self.status_sub = self.label(
            btxt,
            "Vincula el equipo para comenzar" if not self.cfg.agent_token else "Conectando…",
            11, "normal", "#D1D5DB"
        )
        self.status_sub.pack(anchor="w")

    def render_pairing(self, shell):
        banner = self.card(shell, fg="#FFF8EF", border="#FFD5B2", radius=22)
        banner.grid(row=1, column=0, sticky="ew", padx=18, pady=(0,12))
        banner.grid_columnconfigure(1, weight=1)
        self.label(banner, "●", 21, "bold", self.ORANGE).grid(
            row=0, column=0, padx=(20,12), pady=18
        )
        txt = ctk.CTkFrame(banner, fg_color="transparent")
        txt.grid(row=0, column=1, sticky="w", pady=14)
        self.label(txt, "Equipo pendiente de vinculación", 16, "bold").pack(anchor="w")
        self.label(
            txt,
            "Genera un código de 6 dígitos desde Configuración → Agente de impresión.",
            12, "normal", self.MUTED
        ).pack(anchor="w", pady=(2,0))

        body = ctk.CTkFrame(shell, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0,18))
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)

        left = self.card(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0,7))
        right = self.card(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(7,0))

        self.label(left, "VINCULACIÓN", 11, "bold", self.ORANGE).pack(
            anchor="w", padx=28, pady=(28,4)
        )
        self.label(left, "Conectar esta computadora", 25, "bold").pack(anchor="w", padx=28)
        self.label(
            left, "Escribe el código temporal generado desde tu panel web.",
            13, "normal", self.MUTED
        ).pack(anchor="w", padx=28, pady=(5,24))

        self.pair_code_var = ctk.StringVar()
        entry = ctk.CTkEntry(
            left, textvariable=self.pair_code_var, placeholder_text="000000",
            height=76, corner_radius=18, border_width=2, border_color="#FFD0AC",
            fg_color="#FFF9F4", justify="center",
            font=ctk.CTkFont(size=34, weight="bold")
        )
        entry.pack(fill="x", padx=28, pady=(0,18))
        entry.bind("<Return>", lambda _e: self.pair_device())

        self.button(left, "Vincular equipo", self.pair_device, True, width=190).pack(
            anchor="e", padx=28, pady=(0,28)
        )

        self.label(right, "CÓMO FUNCIONA", 11, "bold", self.ORANGE).pack(
            anchor="w", padx=28, pady=(28,12)
        )
        for step in [
            "1. Instala FlashFood Print Agent.",
            "2. En la web pulsa “Generar código”.",
            "3. Escribe los 6 dígitos aquí.",
            "4. El equipo queda ligado al local y sucursal.",
            "5. Selecciona Cocina y Facturas.",
        ]:
            row = ctk.CTkFrame(right, fg_color="#F8FAFC", corner_radius=14)
            row.pack(fill="x", padx=28, pady=5)
            self.label(row, step, 13).pack(anchor="w", padx=14, pady=12)

        self.label(
            right,
            "No necesitas copiar URL, Anon key ni tokens.",
            12, "bold", self.GREEN
        ).pack(anchor="w", padx=28, pady=(15,28))

    def render_dashboard(self, shell):
        banner = self.card(shell, fg=self.GREEN_SOFT, border=self.GREEN_BORDER, radius=22)
        banner.grid(row=1, column=0, sticky="ew", padx=18, pady=(0,12))
        banner.grid_columnconfigure(1, weight=1)

        circle = ctk.CTkFrame(banner, width=48, height=48, corner_radius=24, fg_color=self.GREEN)
        circle.grid(row=0, column=0, padx=(20,12), pady=14)
        circle.grid_propagate(False)
        self.label(circle, "✓", 24, "bold", "#FFFFFF").place(relx=.5, rely=.5, anchor="center")

        txt = ctk.CTkFrame(banner, fg_color="transparent")
        txt.grid(row=0, column=1, sticky="w", pady=14)
        self.banner_title = self.label(
            txt, "Listo para recibir pedidos y facturas", 16, "bold", "#14532D"
        )
        self.banner_title.pack(anchor="w")
        self.banner_sub = self.label(
            txt,
            "El agente está vinculado. Selecciona las impresoras y prueba la conexión.",
            12, "normal", "#287443"
        )
        self.banner_sub.pack(anchor="w", pady=(2,0))
        self.button(banner, "Probar conexión", self.test_connection, width=165).grid(
            row=0, column=2, padx=20, pady=14
        )

        grid = ctk.CTkFrame(shell, fg_color="transparent")
        grid.grid(row=2, column=0, sticky="nsew", padx=18)
        for col in range(3):
            grid.grid_columnconfigure(col, weight=1)

        self.render_printer_card(grid, 0, "kitchen", "PEDIDOS / COCINA", "Impresora de cocina",
                                 "Recibe e imprime pedidos automáticamente.", self.ORANGE, self.ORANGE_SOFT)
        self.render_printer_card(grid, 1, "invoice", "FACTURAS / MOSTRADOR", "Impresora de facturas",
                                 "Reimpresiones y comprobantes de pago.", self.BLUE, self.BLUE_SOFT)
        self.render_terminal_card(grid, 2)
        self.render_activity(shell, 3)
        self.refresh_printers()

    def render_printer_card(self, parent, col, role, kicker, title, desc, accent, soft):
        card = self.card(parent)
        card.grid(row=0, column=col, sticky="nsew", padx=(0 if col==0 else 7, 7), pady=(0,12))

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=24, pady=(24,12))
        icon = ctk.CTkFrame(head, width=54, height=54, corner_radius=16, fg_color=soft)
        icon.pack(side="left", padx=(0,12)); icon.pack_propagate(False)
        self.label(icon, "♨" if role=="kitchen" else "▤", 24, "bold", accent).place(
            relx=.5, rely=.5, anchor="center"
        )
        titles=ctk.CTkFrame(head,fg_color="transparent"); titles.pack(side="left",fill="x",expand=True)
        self.label(titles,kicker,11,"bold",accent).pack(anchor="w")
        self.label(titles,title,17,"bold").pack(anchor="w")
        self.label(titles,desc,11,"normal",self.MUTED).pack(anchor="w")

        enabled_var=ctk.BooleanVar(value=self.cfg.kitchen_enabled if role=="kitchen" else self.cfg.invoice_enabled)
        ctk.CTkSwitch(head,text="",variable=enabled_var,progress_color=accent,command=self.save_settings).pack(side="right")

        self.label(card,"Impresora instalada",12,"bold").pack(anchor="w",padx=24,pady=(10,6))
        pvar=ctk.StringVar(value=self.cfg.printer_kitchen if role=="kitchen" else self.cfg.printer_invoice)
        combo=ctk.CTkComboBox(card,variable=pvar,values=[""],height=44,corner_radius=12,
                              border_color=self.BORDER,fg_color="#FFFFFF",button_color=soft,
                              dropdown_fg_color="#FFFFFF",text_color=self.TEXT)
        combo.pack(fill="x",padx=24)

        fields=ctk.CTkFrame(card,fg_color="transparent")
        fields.pack(fill="x",padx=24,pady=18); fields.grid_columnconfigure((0,1),weight=1)
        self.label(fields,"Ancho de papel",11,"bold").grid(row=0,column=0,sticky="w")
        self.label(fields,"Copias",11,"bold").grid(row=0,column=1,sticky="w",padx=(12,0))
        paper_var=ctk.StringVar(value=str(self.cfg.paper_kitchen_mm if role=="kitchen" else self.cfg.paper_invoice_mm))
        copies_var=ctk.StringVar(value=str(self.cfg.kitchen_copies if role=="kitchen" else self.cfg.invoice_copies))
        ctk.CTkComboBox(fields,variable=paper_var,values=["58","80"],height=42,corner_radius=12).grid(
            row=1,column=0,sticky="ew",pady=(6,0)
        )
        ctk.CTkEntry(fields,textvariable=copies_var,height=42,corner_radius=12).grid(
            row=1,column=1,sticky="ew",padx=(12,0),pady=(6,0)
        )

        cut_box=ctk.CTkFrame(card,fg_color=soft,corner_radius=16)
        cut_box.pack(fill="x",padx=24,pady=(0,16))
        t=ctk.CTkFrame(cut_box,fg_color="transparent"); t.pack(side="left",fill="x",expand=True,padx=14,pady=12)
        self.label(t,"Corte automático",13,"bold").pack(anchor="w")
        self.label(t,"Corta al finalizar el comprobante.",11,"normal",self.MUTED).pack(anchor="w")
        cut_var=ctk.BooleanVar(value=self.cfg.kitchen_cut if role=="kitchen" else self.cfg.invoice_cut)
        ctk.CTkSwitch(cut_box,text="",variable=cut_var,progress_color=accent,command=self.save_settings).pack(
            side="right",padx=14
        )

        actions=ctk.CTkFrame(card,fg_color="transparent"); actions.pack(fill="x",padx=24,pady=(0,24))
        self.button(actions,"Imprimir prueba",self.test_kitchen if role=="kitchen" else self.test_invoice).pack(
            side="left",fill="x",expand=True
        )
        self.button(actions,"Guardar",self.save_settings,True,accent).pack(
            side="left",fill="x",expand=True,padx=(10,0)
        )

        if role=="kitchen":
            self.kitchen_var=pvar; self.kitchen_combo=combo; self.kitchen_enabled_var=enabled_var
            self.kitchen_paper_var=paper_var; self.kitchen_copies_var=copies_var; self.kitchen_cut_var=cut_var
        else:
            self.invoice_var=pvar; self.invoice_combo=combo; self.invoice_enabled_var=enabled_var
            self.invoice_paper_var=paper_var; self.invoice_copies_var=copies_var; self.invoice_cut_var=cut_var

    def render_terminal_card(self,parent,col):
        card=self.card(parent); card.grid(row=0,column=col,sticky="nsew",padx=(7,0),pady=(0,12))
        self.label(card,"ESTA COMPUTADORA",11,"bold",self.ORANGE).pack(anchor="w",padx=24,pady=(24,3))
        self.label(card,"Terminal de impresión",20,"bold").pack(anchor="w",padx=24)
        self.label(card,"Nombre de la terminal",11,"bold").pack(anchor="w",padx=24,pady=(18,6))
        self.device_var=ctk.StringVar(value=self.cfg.device_name or platform.node())
        ctk.CTkEntry(card,textvariable=self.device_var,height=42,corner_radius=12).pack(fill="x",padx=24)

        info=ctk.CTkFrame(card,fg_color="transparent"); info.pack(fill="x",padx=24,pady=16)
        self.label(info,"ID de terminal",11,"bold",self.MUTED).pack(side="left")
        self.label(info,self.cfg.terminal_id,12,"bold").pack(side="right")

        if self.cfg.sucursal_name:
            box=ctk.CTkFrame(card,fg_color="#F8FAFC",corner_radius=14); box.pack(fill="x",padx=24,pady=(0,15))
            self.label(box,"Vinculado a",10,"bold",self.MUTED).pack(anchor="w",padx=14,pady=(10,0))
            self.label(box,f"{self.cfg.local_name or 'Local'} · {self.cfg.sucursal_name}",12,"bold").pack(
                anchor="w",padx=14,pady=(1,10)
            )

        if platform.system() == "Darwin":
            self.login_var = ctk.BooleanVar(value=macos_login_enabled())
            self.automation_row(card, "Abrir al iniciar sesión en macOS",
                                "Inicia el agente automáticamente.", self.login_var)
            self.button(card, "Buscar actualizaciones", self.check_updates).pack(
                fill="x", padx=24, pady=(8, 10)
            )

        self.label(card,"AUTOMATIZACIÓN",11,"bold",self.ORANGE).pack(anchor="w",padx=24,pady=(8,5))
        self.auto_var=ctk.BooleanVar(value=self.cfg.auto_start_worker)
        self.automation_row(card,"Impresión automática","Recibe trabajos sin confirmación.",self.auto_var)

        footer=ctk.CTkFrame(card,fg_color="#F8FAFC",corner_radius=12); footer.pack(fill="x",padx=24,pady=(15,10))
        self.label(footer,platform.system(),11,"bold").pack(side="left",padx=12,pady=10)
        self.label(footer,f"v{APP_VERSION}",11,"normal",self.MUTED).pack(side="right",padx=12,pady=10)

        acts=ctk.CTkFrame(card,fg_color="transparent"); acts.pack(fill="x",padx=24,pady=(0,24))
        self.button(acts,"Guardar",self.save_settings,True).pack(side="left",fill="x",expand=True)
        self.button(acts,"Desvincular",self.unpair).pack(side="left",fill="x",expand=True,padx=(10,0))

    def automation_row(self,parent,title,desc,var):
        row=ctk.CTkFrame(parent,fg_color="transparent"); row.pack(fill="x",padx=24,pady=6)
        t=ctk.CTkFrame(row,fg_color="transparent"); t.pack(side="left",fill="x",expand=True)
        self.label(t,title,13,"bold").pack(anchor="w")
        self.label(t,desc,10,"normal",self.MUTED).pack(anchor="w")
        ctk.CTkSwitch(row,text="",variable=var,progress_color=self.ORANGE,command=self.save_settings).pack(side="right")

    def render_activity(self,shell,row):
        card=self.card(shell); card.grid(row=row,column=0,sticky="ew",padx=18,pady=(0,18))
        head=ctk.CTkFrame(card,fg_color="transparent"); head.pack(fill="x",padx=24,pady=(18,8))
        t=ctk.CTkFrame(head,fg_color="transparent"); t.pack(side="left")
        self.label(t,"ACTIVIDAD RECIENTE",11,"bold",self.ORANGE).pack(anchor="w")
        self.label(t,"Últimos eventos del agente",12,"normal",self.MUTED).pack(anchor="w")
        self.button(head,"Limpiar",self.clear_activity,width=95).pack(side="right")
        self.activity_box=ctk.CTkFrame(card,fg_color="transparent"); self.activity_box.pack(fill="x",padx=24,pady=(0,18))
        self.refresh_activity()

    def refresh_activity(self):
        if not hasattr(self,"activity_box"): return
        for c in self.activity_box.winfo_children(): c.destroy()
        if not self.activities:
            r=ctk.CTkFrame(self.activity_box,fg_color="#F8FAFC",corner_radius=14); r.pack(fill="x")
            self.label(r,"Sin actividad todavía. Las impresiones aparecerán aquí.",12,"normal",self.MUTED).pack(
                anchor="w",padx=14,pady=14
            ); return
        for stamp,msg,dest,status in self.activities:
            r=ctk.CTkFrame(self.activity_box,fg_color="#F8FAFC",corner_radius=12); r.pack(fill="x",pady=3)
            dot=self.GREEN if status in ("Impreso","Conectado") else "#DC2626"
            self.label(r,"●",13,"bold",dot).pack(side="left",padx=(12,8),pady=10)
            self.label(r,stamp,11,"normal",self.MUTED).pack(side="left",padx=(0,16))
            self.label(r,msg,12).pack(side="left",fill="x",expand=True)
            self.label(r,dest,10,"bold",self.ORANGE if dest=="Cocina" else self.BLUE if dest=="Mostrador" else self.MUTED).pack(
                side="left",padx=12
            )
            self.label(r,status,10,"bold",dot).pack(side="right",padx=14)

    def add_activity(self,msg,dest="Sistema",status="Conectado"):
        self.activities.insert(0,(time.strftime("%H:%M"),msg,dest,status))
        self.activities=self.activities[:8]
        self.refresh_activity()

    def clear_activity(self):
        self.activities=[]; self.refresh_activity()

    def refresh_printers(self):
        printers=list_printers(); values=[PDF_TEST_PRINTER] + printers
        if hasattr(self,"kitchen_combo"): self.kitchen_combo.configure(values=values)
        if hasattr(self,"invoice_combo"): self.invoice_combo.configure(values=values)
        self.add_activity(
            f"{len(printers)} impresora(s) del sistema y modo PDF de prueba disponible",
            "Sistema","Conectado" if printers else "Revisar"
        )

    def check_updates(self):
        def worker():
            try:
                latest, url = release_version_info()
                if not latest:
                    raise RuntimeError("La versión publicada no contiene número de versión.")
                def show():
                    if version_parts(latest) > version_parts(APP_VERSION):
                        if messagebox.askyesno(APP_NAME,
                            f"Disponible v{latest}. Se abrirá la página oficial para descargarla. "
                            "La instalación no es automática todavía. ¿Abrir ahora?"):
                            webbrowser.open(url)
                    else:
                        messagebox.showinfo(APP_NAME, f"Ya tienes la última versión publicada (v{APP_VERSION}).")
                self.after(0, show)
            except Exception as error:
                self.after(0, lambda msg=str(error): messagebox.showwarning(APP_NAME, msg))
        threading.Thread(target=worker, daemon=True).start()

    def _read_settings(self):
        if not self.cfg.agent_token: return
        self.cfg.device_name=self.device_var.get().strip() or platform.node()
        self.cfg.printer_kitchen=self.kitchen_var.get().strip()
        self.cfg.printer_invoice=self.invoice_var.get().strip()
        self.cfg.kitchen_enabled=bool(self.kitchen_enabled_var.get())
        self.cfg.invoice_enabled=bool(self.invoice_enabled_var.get())
        self.cfg.paper_kitchen_mm=int(self.kitchen_paper_var.get() or 80)
        self.cfg.paper_invoice_mm=int(self.invoice_paper_var.get() or 80)
        try: self.cfg.kitchen_copies=max(1,int(self.kitchen_copies_var.get() or 1))
        except Exception: self.cfg.kitchen_copies=1
        try: self.cfg.invoice_copies=max(1,int(self.invoice_copies_var.get() or 1))
        except Exception: self.cfg.invoice_copies=1
        self.cfg.kitchen_cut=bool(self.kitchen_cut_var.get())
        self.cfg.invoice_cut=bool(self.invoice_cut_var.get())
        self.cfg.auto_start_worker=bool(self.auto_var.get())

    def save_settings(self, show=False):
        if not self.cfg.agent_token: return
        self._read_settings(); save_config(self.cfg)
        if platform.system() == 'Darwin' and hasattr(self, 'login_var'):
            try:
                set_macos_login_enabled(bool(self.login_var.get()))
            except Exception as error:
                messagebox.showwarning(APP_NAME, f'No se pudo configurar el inicio automático: {error}')
        try:
            rpc(self.cfg,"print_agent_update_config",{
                "p_token":self.cfg.agent_token,
                "p_device_name":self.cfg.device_name,
                "p_os":platform.system(),
                "p_version":APP_VERSION,
                "p_printer_kitchen_name":self.cfg.printer_kitchen or None,
                "p_printer_invoice_name":self.cfg.printer_invoice or None,
                "p_paper_kitchen_mm":self.cfg.paper_kitchen_mm,
                "p_paper_invoice_mm":self.cfg.paper_invoice_mm,
                "p_kitchen_enabled":self.cfg.kitchen_enabled,
                "p_invoice_enabled":self.cfg.invoice_enabled,
            })
        except Exception as e: log(f"Sync config: {e}")
        if self.cfg.auto_start_worker: self.start_worker()
        else: self.stop_worker()
        if show: messagebox.showinfo(APP_NAME,"Configuración guardada.")

    def pair_device(self):
        code="".join(c for c in self.pair_code_var.get() if c.isdigit())
        if len(code)!=6:
            messagebox.showwarning(APP_NAME,"Ingresa un código de 6 dígitos."); return
        if not self.cfg.supabase_url or not self.cfg.anon_key:
            messagebox.showerror(
                APP_NAME,
                "Este instalador no contiene la configuración del servidor. Regénéralo desde GitHub Actions con los Secrets."
            ); return
        try:
            data=rpc(self.cfg,"pair_print_agent_by_code",{
                "p_code":code,
                "p_device_name":platform.node() or "Esta computadora",
                "p_os":platform.system(),
                "p_version":APP_VERSION,
                "p_terminal_id":self.cfg.terminal_id,
            })
            if not isinstance(data,dict) or not data.get("token"):
                raise RuntimeError("Respuesta de vinculación inválida.")
            self.cfg.agent_token=str(data.get("token") or "")
            self.cfg.agent_id=str(data.get("agent_id") or "")
            self.cfg.local_name=str(data.get("local_name") or "")
            self.cfg.sucursal_name=str(data.get("sucursal_name") or "")
            save_config(self.cfg)
            messagebox.showinfo(APP_NAME,"Equipo vinculado correctamente.")
            self.render()
            if self.cfg.auto_start_worker: self.start_worker()
        except Exception as e:
            messagebox.showerror(APP_NAME,str(e))

    def unpair(self):
        if not messagebox.askyesno(APP_NAME,"¿Desvincular esta computadora?"): return
        self.stop_worker()
        try:
            if self.cfg.agent_token:
                rpc(self.cfg,"print_agent_unpair",{"p_token":self.cfg.agent_token})
        except Exception as e: log(f"Unpair: {e}")
        keep_url,keep_key,tid=self.cfg.supabase_url,self.cfg.anon_key,self.cfg.terminal_id
        self.cfg=AgentConfig(
            supabase_url=keep_url,anon_key=keep_key,
            device_name=platform.node() or "Esta computadora",terminal_id=tid
        )
        save_config(self.cfg); self.render()

    def test_connection(self):
        try:
            rpc(self.cfg,"print_agent_ping",{"p_token":self.cfg.agent_token})
            self.set_online(True); self.add_activity("Conexión establecida con el servidor","Sistema","Conectado")
            messagebox.showinfo(APP_NAME,"Conexión correcta con FlashFood.")
        except Exception as e:
            self.set_online(False); messagebox.showerror(APP_NAME,str(e))

    def test_kitchen(self):
        self.save_settings()
        try:
            print_text(
                self.cfg.printer_kitchen,
                format_kitchen({
                    "origen":"APP","numero_pedido":"PRUEBA","tipo_entrega":"retiro",
                    "prioritario":True,"cliente_nombre":"Cliente de prueba",
                    "items":[{"cantidad":2,"nombre_producto":"Producto de prueba","nota":"Sin cebolla"}],
                    "observacion_cliente":"Prueba de cocina"
                })
            )
            self.add_activity("Prueba de cocina impresa correctamente","Cocina","Impreso")
        except Exception as e: messagebox.showerror(APP_NAME,str(e))

    def test_invoice(self):
        self.save_settings()
        try:
            print_text(
                self.cfg.printer_invoice,
                format_invoice({
                    "nombre_comercial":"RESTAURANTE DE PRUEBA","numero_factura":"001-001-PRUEBA",
                    "cliente_nombre":"Cliente de prueba","cliente_identificacion":"9999999999999",
                    "metodo_pago":"transferencia","subtotal":10,"impuestos":1.5,"total":11.5,
                    "app_total_pagado":14,"app_costo_delivery":2,"app_tarifa_servicio":0.5
                })
            )
            self.add_activity("Prueba de factura impresa correctamente","Mostrador","Impreso")
        except Exception as e: messagebox.showerror(APP_NAME,str(e))

    def start_worker(self):
        if not self.cfg.agent_token: return
        if self.worker and self.worker.is_alive(): return
        self.worker=Worker(lambda:self.cfg,self.events); self.worker.start()
        self.status_title.configure(text="Conectando…")
        self.status_sub.configure(text="Estableciendo conexión con el servidor")

    def stop_worker(self):
        if self.worker: self.worker.stop(); self.worker=None

    def set_online(self,online):
        if not hasattr(self,"status_title"): return
        if online:
            self.status_title.configure(text="Agente activo")
            self.status_sub.configure(text="Conectado y listo")
            self.status_dot.configure(text_color=self.GREEN)
            if hasattr(self,"banner_sub"):
                self.banner_sub.configure(text="El agente está conectado correctamente. Recibe pedidos y reimpresiones de facturas.")
        else:
            self.status_title.configure(text="Sin conexión")
            self.status_sub.configure(text="Revisa la conexión o la vinculación")
            self.status_dot.configure(text_color=self.ORANGE)

    def process_events(self):
        try:
            while True:
                event,msg=self.events.get_nowait()
                if event=="status" and hasattr(self,"banner_sub"):
                    self.banner_sub.configure(text=str(msg))
                elif event=="printed":
                    self.add_activity(f"Trabajo {str(msg)[:8]} impreso correctamente","Sistema","Impreso")
                elif event=="error":
                    self.add_activity(str(msg),"Sistema","Error")
                if event=="status" and ("Conectado" in str(msg) or "completada" in str(msg)):
                    self.set_online(True)
        except Empty: pass
        self.after(250,self.process_events)

    def destroy(self):
        self.stop_worker()
        super().destroy()


def packaged_self_test():
    try:
        import uuid as _uuid
        import tkinter as _tkinter
        import customtkinter as _customtkinter
        import requests as _requests
        from PIL import Image as _Image
        import build_config as _build_config

        _uuid.uuid4()
        _ = _tkinter.TclVersion
        _ = _customtkinter.__name__
        _ = _requests.__version__
        _ = _Image.__name__

        build_url = str(
            getattr(
                _build_config,
                "SUPABASE_URL",
                "",
            )
            or ""
        ).strip()

        build_key = str(
            getattr(
                _build_config,
                "SUPABASE_ANON_KEY",
                "",
            )
            or ""
        ).strip()

        if not build_url:
            raise RuntimeError(
                "SUPABASE_URL no quedó empaquetada en el instalador."
            )

        if not build_key:
            raise RuntimeError(
                "SUPABASE_ANON_KEY no quedó empaquetada en el instalador."
            )

        if not build_url.startswith("https://"):
            raise RuntimeError(
                "SUPABASE_URL empaquetada no es válida."
            )

        return 0

    except Exception as error:
        log(
            f"SELF-TEST ERROR: {error}"
        )
        return 91

def main():
    try:
        app=App(); app.mainloop()
    except Exception as e:
        log(traceback.format_exc())
        try: messagebox.showerror(APP_NAME,str(e))
        except Exception: pass
        raise

if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(packaged_self_test())
    main()
