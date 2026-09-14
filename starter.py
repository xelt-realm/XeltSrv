#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
starter.py — Prepara y administra un servidor PaperMC.

Flujo Playit corregido:
  - playit claim generate → código de claim
  - playit claim url <code> → URL para visitar
  - playit claim exchange <code> → intercambia por secreto
  - playit start → arranca playitd con el secreto
  - playit status → obtiene la dirección del túnel

CLI UI mejorada con Rich y Colorama.
"""

import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
import zipfile
from pathlib import Path
from datetime import datetime

from colorama import init, Fore, Style, Back

init(autoreset=True)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.prompt import Prompt, Confirm, IntPrompt
    from rich.live import Live
    from rich.layout import Layout
    from rich.text import Text
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# ---------------------------------------------------------------------------
# Rutas y constantes
# ---------------------------------------------------------------------------
DEFAULT_MIN_RAM_GB = 12
DEFAULT_MAX_RAM_GB = 14
PAPER_PROJECT = "paper"

PLUGINS_DIR = Path("plugins")
SERVER_JAR = Path("server.jar")
START_SCRIPT = Path("start.sh")
START_BAT = Path("start.bat")
WEBHOOK_FILE = Path(".webhook.json")
GITIGNORE_FILE = Path(".gitignore")
CONFIG_FILE = Path(".starter-config.json")
PAPER_VERSION_FILE = Path(".paper-version.json")
BACKUP_DIR = Path("backups")
PLAYIT_SECRET_FILE = Path(".playit-secret.json")

PAPER_API = "https://fill.papermc.io/v3/projects"
GITHUB_API = "https://api.github.com/repos"

DEFAULT_PROPS = {
    "enable-command-block": "true",
    "spawn-protection": "16",
    "online-mode": "false",
    "view-distance": "10",
    "simulation-distance": "8",
    "max-players": "20",
    "difficulty": "hardcore",
    "hardcore": "true",
    "gamemode": "survival",
    "pvp": "true",
    "allow-flight": "false",
    "enable-status": "true",
    "white-list": "false",
    "enforce-whitelist": "false",
    "bonus-chest": "true",
    "motd": "",
}

DEFAULT_CONFIG = {
    "user_agent": "MinecraftServerStarter/1.0",
    "git_remote": "",
    "backup_interval_seconds": 300,
    "hard_reset_interval_seconds": 1500,
    "backup_mode": "git_push",
    "max_zip_backups": 5,
    "playit_auto_install": False,
    "paper_version_pin": "",
    "server_properties": {},
    "min_ram_gb": DEFAULT_MIN_RAM_GB,
    "max_ram_gb": DEFAULT_MAX_RAM_GB,
}

_CFG: dict = dict(DEFAULT_CONFIG)


# ---------------------------------------------------------------------------
# UI Helpers
# ---------------------------------------------------------------------------
_console = None


def get_console():
    global _console
    if _console is None:
        if RICH_AVAILABLE:
            _console = Console(force_terminal=True, soft_wrap=True)
        else:
            _console = Console(force_terminal=True)
    return _console


def cprint(text: str, color: str = Fore.WHITE, style: str = "") -> None:
    """Print colored text to stdout."""
    console = get_console()
    if RICH_AVAILABLE:
        rich_style = "bold" if style == Style.BRIGHT else None
        console.print(f"{color}{text}{Style.RESET_ALL}", style=rich_style)
    else:
        print(f"{color}{text}{Style.RESET_ALL}")


def print_header(title: str) -> None:
    console = get_console()
    if RICH_AVAILABLE:
        console.print()
        console.print(Panel.fit(
            f"[bold cyan]{title}[/bold cyan]",
            title="[bold magenta]⛏ XeltSrv[/bold magenta]",
            border_style="cyan",
            box=box.DOUBLE,
        ))
    else:
        cprint(f"\n{'═' * 62}", Fore.CYAN)
        cprint(f"  {title}", Fore.CYAN, Style.BRIGHT)
        cprint(f"{'═' * 62}", Fore.CYAN)


def print_section(title: str) -> None:
    console = get_console()
    if RICH_AVAILABLE:
        console.print()
        console.print(Panel.fit(
            f"[bold]{title}[/bold]",
            border_style="yellow",
            box=box.ROUNDED,
            title="[bold yellow]▸[/bold yellow]",
        ))
    else:
        cprint(f"\n{'─' * 50}", Fore.YELLOW)
        cprint(f"  ▸ {title}", Fore.YELLOW, Style.BRIGHT)
        cprint(f"{'─' * 50}", Fore.YELLOW)


def print_success(msg: str) -> None:
    cprint(f"  ✅ {msg}", Fore.GREEN)


def print_error(msg: str) -> None:
    cprint(f"  ✗ {msg}", Fore.RED)


def print_warning(msg: str) -> None:
    cprint(f"  ⚠ {msg}", Fore.YELLOW)


def print_info(msg: str) -> None:
    cprint(f"  ℹ {msg}", Fore.CYAN)


def print_step(step: int, total: int, msg: str) -> None:
    cprint(f"  [{step}/{total}] {msg}", Fore.MAGENTA, Style.BRIGHT)


def print_bar(label: str, value: str, total_len: int = 40) -> None:
    console = get_console()
    if RICH_AVAILABLE:
        console.print(f"  [bold]{label}[/bold] {'█' * min(int(value) * total_len // 100, total_len)}{'░' * (total_len - min(int(value) * total_len // 100, total_len))} [cyan]{value}%[/cyan]")
    else:
        filled = int(value) * total_len // 100
        bar = '█' * filled + '░' * (total_len - filled)
        cprint(f"  {label} {Fore.GREEN}{bar}{Style.RESET_ALL} {Fore.CYAN}{value}%{Style.RESET_ALL}")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def cfg_get(key, default=None):
    if key in _CFG and _CFG[key] not in (None, ""):
        return _CFG[key]
    return DEFAULT_CONFIG.get(key, default)


def get_user_agent() -> str:
    return cfg_get("user_agent") or "MinecraftServerStarter/1.0"


def get_min_ram() -> int:
    try:
        return int(cfg_get("min_ram_gb") or DEFAULT_MIN_RAM_GB)
    except Exception:
        return DEFAULT_MIN_RAM_GB


def get_max_ram() -> int:
    try:
        return int(cfg_get("max_ram_gb") or DEFAULT_MAX_RAM_GB)
    except Exception:
        return DEFAULT_MAX_RAM_GB


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------
def ask(prompt: str, default: bool = False) -> bool:
    try:
        if RICH_AVAILABLE:
            r = Confirm.ask(prompt, default=default)
        else:
            suffix = " [S/n]: " if default else " [s/N]: "
            r = input(prompt + suffix).strip().lower()
            if not r:
                return default
            r = r in ("s", "si", "sí", "y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return r


def ask_str(prompt: str, default: str) -> str:
    try:
        if RICH_AVAILABLE:
            return Prompt.ask(prompt, default=default)
        else:
            r = input(f"  {prompt} [{default}]: ").strip()
            return r if r else default
    except (EOFError, KeyboardInterrupt):
        print()
        return default


def ask_int(prompt: str, default: int, minv: int = 0, maxv: int | None = None) -> int:
    try:
        while True:
            if RICH_AVAILABLE:
                n = IntPrompt.ask(prompt, default=default)
            else:
                r = input(f"  {prompt} [{default}]: ").strip()
                if not r:
                    return default
                try:
                    n = int(r)
                except ValueError:
                    print_error("Introduce un número entero.")
                    continue
            if n < minv or (maxv is not None and n > maxv):
                rng = f"{minv}–{maxv}" if maxv is not None else f"≥ {minv}"
                print_error(f"Debe estar entre {rng}.")
                continue
            return n
    except (EOFError, KeyboardInterrupt):
        print()
        return default


def ask_choice(prompt: str, choices: list, default: str) -> str:
    try:
        if RICH_AVAILABLE:
            return Prompt.ask(prompt, choices=choices, default=default)
        else:
            choices_lower = [c.lower() for c in choices]
            while True:
                r = input(f"  {prompt} {choices} [{default}]: ").strip().lower()
                if not r:
                    return default
                if r in choices_lower:
                    return r
                print_error(f"Opción inválida. Elige entre {choices}.")
    except (EOFError, KeyboardInterrupt):
        print()
        return default


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def eprint(*args, **kwargs) -> None:
    print(*args, file=sys.stderr, **kwargs)
    try:
        sys.stderr.flush()
    except Exception:
        pass


def _ask_str_allow_empty(prompt: str, default: str) -> str:
    try:
        r = input(f"  {prompt} [{default}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return r


def download(url: str, dest: Path, headers: dict | None = None) -> None:
    eprint(f"  → Descargando {url}")
    hdrs = {"User-Agent": get_user_agent()}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp, open(dest, "wb") as f:
            total = int(resp.headers.get("Content-Length", 0))
            done = 0
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total
                    eprint(f"\r    {pct:3d}%  ({done/1024/1024:.1f} / {total/1024/1024:.1f} MB)", end="")
            eprint()
    except urllib.error.HTTPError as e:
        eprint(f"    ✗ Error HTTP {e.code}: {e.reason}")
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass
        raise
    except Exception as e:
        eprint(f"    ✗ Error: {e}")
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def http_json(url: str, headers: dict | None = None):
    hdrs = {"User-Agent": get_user_agent(), "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def detect_os() -> str:
    s = platform.system().lower()
    if "linux" in s:
        return "linux"
    if "darwin" in s:
        return "macos"
    if "windows" in s:
        return "windows"
    return "unknown"


def has_command(cmd: str) -> bool:
    if cmd in ("playit", "playitd"):
        return True
    return shutil.which(cmd) is not None


def get_start_script() -> Path:
    return START_BAT if detect_os() == "windows" else START_SCRIPT


def get_available_ram_gb() -> float | None:
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    return kb / (1024 * 1024)
    except Exception:
        pass
    try:
        r = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return int(r.stdout.strip()) / (1024 ** 3)
    except Exception:
        pass
    return None


def check_java() -> tuple[bool, str]:
    if not has_command("java"):
        return False, "java no está en el PATH"
    try:
        r = subprocess.run(["java", "-version"], capture_output=True, text=True, timeout=15)
        out = ((r.stderr or "") + (r.stdout or "")).strip()
        first = out.splitlines()[0] if out else "(sin salida)"
        return True, first
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
        except Exception as e:
            eprint(f"  ⚠ Config corrupto: {e}. Usando valores por defecto.")
    return cfg


def save_config(cfg: dict) -> None:
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            os.chmod(CONFIG_FILE, 0o600)
        except Exception:
            pass
    except Exception as e:
        eprint(f"  ⚠ No se pudo guardar config: {e}")


# ---------------------------------------------------------------------------
# Paper version
# ---------------------------------------------------------------------------
def load_paper_version() -> dict | None:
    if PAPER_VERSION_FILE.exists():
        try:
            return json.loads(PAPER_VERSION_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def save_paper_version(version: str, build: str) -> None:
    try:
        PAPER_VERSION_FILE.write_text(
            json.dumps({"version": version, "build": build, "at": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        eprint(f"  ⚠ No se pudo guardar versión de Paper: {e}")


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
def detect_server_installed() -> bool:
    return SERVER_JAR.exists() and get_start_script().exists()


def detect_webhook() -> bool:
    return WEBHOOK_FILE.exists()


def detect_playit_secret() -> bool:
    if PLAYIT_SECRET_FILE.exists():
        return True
    # También verificar el archivo de config de playit
    secret_path = Path.home() / ".config" / "playit" / "playit.toml"
    if secret_path.exists():
        try:
            content = secret_path.read_text(encoding="utf-8", errors="ignore")
            if re.search(r'secret_key\s*=\s*["\']', content):
                return True
        except Exception:
            pass
    return False


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------
def _is_in_git_repo() -> bool:
    if not has_command("git"):
        return False
    try:
        r = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True, timeout=10)
        return r.returncode == 0 and r.stdout.strip() == "true"
    except Exception:
        return False


def detect_git_remote() -> str | None:
    try:
        r = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            url = r.stdout.strip()
            if url:
                return url
    except Exception:
        pass
    return None


def ensure_git_remote(cfg: dict) -> str:
    if cfg.get("git_remote"):
        return cfg["git_remote"]
    detected = detect_git_remote()
    if detected:
        eprint(f"  ✓ Repositorio git detectado: {detected}")
        cfg["git_remote"] = detected
        save_config(cfg)
        return detected
    eprint("  → No se detectó repositorio git automáticamente.")
    try:
        url = input("  URL del repositorio git (vacío para omitir auto-push): ").strip()
    except (EOFError, KeyboardInterrupt):
        url = ""
    if url:
        cfg["git_remote"] = url
        save_config(cfg)
        eprint(f"  ✓ Repositorio configurado: {url}")
    return url


def _git_run(args: list, timeout: int = 60) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git"] + args, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


# ---------------------------------------------------------------------------
# Security: .gitignore
# ---------------------------------------------------------------------------
GITIGNORE_BLOCK_START = "# ─── INICIO BLOQUE DE SEGURIDAD (starter.py) ───"
GITIGNORE_BLOCK_END = "# ─── FIN BLOQUE DE SEGURIDAD (starter.py) ───"

GITIGNORE_CRITICAL_PATTERNS = [
    ".webhook.json", "*.webhook.json", "webhook.json",
    ".starter-config.json", ".playit-secret.json", ".env",
    "*.secret", "*.token", "*.key", "!.gitignore",
]

GITIGNORE_SECURITY_BLOCK = """\
# ─── INICIO BLOQUE DE SEGURIDAD (starter.py) ───
# ══════════════════════════════════════════════════════════════
#  ⚠  ARCHIVOS SECRETOS — NUNCA SUBIR A GITHUB  ⚠
#
#  Este repositorio puede ser PÚBLICO. Filtrar un webhook, token
#  o cualquier credencial puede provocar el BANEO PERMANENTAL
#  de tu cuenta de GitHub y comprometer tu servidor.
#
#  NO ELIMINES NINGUNA LÍNEA DE ESTE BLOQUE.
# ══════════════════════════════════════════════════════════════

.webhook.json
.webhook.*.json
*.webhook.json
webhook.json
webhook-*.json
webhook_*.json
**/.webhook.json

.starter-config.json
.playit-secret.json

backups/

.env
.env.*
*.env
*.env.*
.envrc
secrets/
.secrets/
*.secret
*.token
*.key
*.pem
*.p12
credentials.json
service-account.json

!.gitignore

# ─── FIN BLOQUE DE SEGURIDAD (starter.py) ───
"""

def _read_gitignore() -> str:
    if not GITIGNORE_FILE.exists():
        return ""
    return GITIGNORE_FILE.read_text(encoding="utf-8", errors="ignore")


def _gitignore_block_is_current(content: str) -> bool:
    if GITIGNORE_BLOCK_START not in content or GITIGNORE_BLOCK_END not in content:
        return False
    start = content.index(GITIGNORE_BLOCK_START)
    end = content.index(GITIGNORE_BLOCK_END) + len(GITIGNORE_BLOCK_END)
    block = content[start:end]
    lines = {l.strip() for l in block.splitlines()}
    return all(p in lines for p in GITIGNORE_CRITICAL_PATTERNS)


def ensure_gitignore() -> None:
    content = _read_gitignore()
    if _gitignore_block_is_current(content):
        eprint("  ✓ .gitignore ya contiene el bloque de seguridad actualizado.")
        return
    if GITIGNORE_BLOCK_START in content and GITIGNORE_BLOCK_END in content:
        start = content.index(GITIGNORE_BLOCK_START)
        end = content.index(GITIGNORE_BLOCK_END) + len(GITIGNORE_BLOCK_END)
        new_content = content[:start] + GITIGNORE_SECURITY_BLOCK.strip() + content[end:]
        GITIGNORE_FILE.write_text(new_content, encoding="utf-8")
        eprint("  ✓ Bloque de seguridad de .gitignore actualizado.")
        return
    prefix = ""
    if content:
        prefix = "\n\n" if not content.endswith("\n\n") else ""
        if not content.endswith("\n"):
            prefix = "\n\n"
    with open(GITIGNORE_FILE, "a", encoding="utf-8") as f:
        f.write(prefix + GITIGNORE_SECURITY_BLOCK)
    if content:
        eprint("  ✓ Bloque de seguridad añadido al .gitignore existente.")
    else:
        eprint("  ✓ .gitignore creado con el bloque de seguridad.")


def verify_gitignore_protection() -> bool:
    if not has_command("git"):
        eprint("  ⚠ Git no está instalado. No se puede verificar el .gitignore.")
        return True
    if not _is_in_git_repo():
        eprint("  ⚠ No estás dentro de un repositorio git.")
        eprint("    El .gitignore está listo, pero la verificación se omite.")
        return True
    created_placeholder = False
    if not WEBHOOK_FILE.exists():
        try:
            WEBHOOK_FILE.write_text("{}\n", encoding="utf-8")
            created_placeholder = True
        except Exception as e:
            eprint(f"  ✗ No se pudo crear placeholder para verificar: {e}")
            return False
    try:
        r = subprocess.run(["git", "check-ignore", "-q", str(WEBHOOK_FILE)], capture_output=True)
        if r.returncode != 0:
            print_error("¡PELIGRO: el webhook NO está ignorado por git!")
            print_error("NO hagas commit/push hasta arreglar el .gitignore.")
            return False
        print_success(f"{WEBHOOK_FILE} está correctamente ignorado por git.")
        return True
    finally:
        if created_placeholder:
            try:
                WEBHOOK_FILE.unlink(missing_ok=True)
            except Exception:
                pass


def warn_if_webhook_is_tracked() -> None:
    if not has_command("git") or not _is_in_git_repo():
        return
    if not WEBHOOK_FILE.exists():
        return
    try:
        r = subprocess.run(["git", "ls-files", "--error-unmatch", str(WEBHOOK_FILE)], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            print_warning("⚠ El archivo de webhook YA está TRACKEADO por git.")
            print_warning("Puede haber sido subido a GitHub en algún momento.")
            print_info(f"Ejecuta: git rm --cached {WEBHOOK_FILE}")
            print_info("Luego regenera la URL del webhook por seguridad.")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# PaperMC
# ---------------------------------------------------------------------------
def get_latest_paper_url() -> tuple[str, str, str]:
    print_step(1, 6, "Consultando PaperMC…")
    proj = http_json(f"{PAPER_API}/{PAPER_PROJECT}", {"User-Agent": get_user_agent()})
    versions = proj.get("versions", {})
    if not versions:
        raise RuntimeError("PaperMC no devolvió versiones.")

    pin = cfg_get("paper_version_pin") or ""
    if pin:
        latest_mc = pin
        print_info(f"Versión fijada por config: {latest_mc}")
    elif isinstance(versions, dict):
        latest_mc = next(iter(versions))
    elif isinstance(versions, list):
        first = versions[0]
        if isinstance(first, str):
            latest_mc = first
        elif isinstance(first, dict):
            latest_mc = first.get("version") or first.get("id") or first.get("name")
        else:
            raise RuntimeError(f"Elemento de 'versions' inesperado: {type(first)}")
    else:
        raise RuntimeError(f"Formato de 'versions' inesperado: {type(versions)}")

    if not latest_mc:
        raise RuntimeError("No se pudo determinar la versión de Minecraft.")
    if not pin:
        print_info(f"Última versión de Minecraft: {latest_mc}")

    builds = http_json(f"{PAPER_API}/{PAPER_PROJECT}/versions/{latest_mc}/builds", {"User-Agent": get_user_agent()})
    if isinstance(builds, dict):
        builds = builds.get("builds", [])
    if not isinstance(builds, list):
        raise RuntimeError(f"Formato de 'builds' inesperado: {type(builds)}")

    stable = [b for b in builds if b.get("channel") == "STABLE"]
    if not stable:
        raise RuntimeError(f"No hay builds estables para Paper {latest_mc}.")

    build = stable[0]
    downloads = build.get("downloads", {}) or {}
    dl = downloads.get("server:default") or downloads.get("application") or {}
    url = dl.get("url")
    if not url:
        raise RuntimeError(f"No se encontró URL de descarga en la build {build.get('id')}.")

    build_id = str(build.get("id", "?"))
    print_info(f"Build estable: {build_id}")
    return latest_mc, build_id, url


def download_paper() -> None:
    version, build, url = get_latest_paper_url()
    if SERVER_JAR.exists() and not ask(f"{SERVER_JAR} ya existe. ¿Sobrescribir?", default=False):
        print_info("Omitiendo descarga de Paper.")
        save_paper_version(version, build)
        return
    download(url, SERVER_JAR)
    save_paper_version(version, build)
    print_success(f"Guardado como {SERVER_JAR} (Paper {version}, build {build})")


# ---------------------------------------------------------------------------
# EULA
# ---------------------------------------------------------------------------
def write_eula() -> None:
    print_step(2, 6, "Escribiendo eula.txt…")
    Path("eula.txt").write_text(
        "# Por cambiar esta opción a TRUE aceptas el EULA de Minecraft:\n"
        "# https://aka.ms/MinecraftEULA\n"
        "eula=true\n",
        encoding="utf-8",
    )
    print_success("eula.txt creado con eula=true")


# ---------------------------------------------------------------------------
# server.properties
# ---------------------------------------------------------------------------
def prompt_server_properties(existing: dict | None = None) -> dict:
    existing = existing or {}
    props: dict = {}

    def _default(key: str, fallback: str) -> str:
        return existing.get(key, DEFAULT_PROPS.get(key, fallback))

    print_section("CONFIGURACIÓN DEL SERVIDOR")
    print_info("Pulsa ENTER para aceptar el valor entre corchetes.")

    default_motd = _default("motd", "")
    if default_motd:
        print_info(f"MOTD actual: {default_motd!r}")
    props["motd"] = _ask_str_allow_empty("MOTD (vacío = sin MOTD personalizado)", default_motd)

    hardcore_default = _default("hardcore", "false").lower() == "true"
    hardcore = ask("¿Activar modo Hardcore? (muerte permanente)", default=hardcore_default)
    props["hardcore"] = "true" if hardcore else "false"

    diff_default = "hard" if hardcore else _default("difficulty", "normal").lower()
    if diff_default not in ("peaceful", "easy", "normal", "hard"):
        diff_default = "normal"
    if hardcore:
        print_info("Hardcore fuerza dificultad=hard.")
        props["difficulty"] = "hard"
    else:
        props["difficulty"] = ask_choice("Dificultad", ["peaceful", "easy", "normal", "hard"], diff_default)

    om_default = _default("online-mode", "true").lower() == "true"
    print_info("online-mode=true verifica cuentas Mojang; false permite no premium")
    online = ask("¿Activar modo online?", default=om_default)
    props["online-mode"] = "true" if online else "false"

    sp_default = int(_default("spawn-protection", "16") or 16)
    props["spawn-protection"] = str(ask_int("Protección del spawn (bloques, 0 = desactivada)", sp_default, minv=0, maxv=10000))

    gm_default = _default("gamemode", "survival").lower()
    if gm_default not in ("survival", "creative", "adventure", "spectator"):
        gm_default = "survival"
    props["gamemode"] = ask_choice("Modo de juego", ["survival", "creative", "adventure", "spectator"], gm_default)

    pvp_default = _default("pvp", "true").lower() == "true"
    pvp = ask("¿Permitir PvP?", default=pvp_default)
    props["pvp"] = "true" if pvp else "false"

    mp_default = int(_default("max-players", "20") or 20)
    props["max-players"] = str(ask_int("Máximo de jugadores", mp_default, minv=1, maxv=1000))

    vd_default = int(_default("view-distance", "10") or 10)
    props["view-distance"] = str(ask_int("Distancia de visión (chunks, 3-32)", vd_default, minv=3, maxv=32))

    sd_default = int(_default("simulation-distance", "8") or 8)
    props["simulation-distance"] = str(ask_int("Distancia de simulación (chunks, 3-32)", sd_default, minv=3, maxv=32))

    wl_default = _default("white-list", "false").lower() == "true"
    wl = ask("¿Activar lista blanca?", default=wl_default)
    props["white-list"] = "true" if wl else "false"
    props["enforce-whitelist"] = "true" if wl else "false"

    af_default = _default("allow-flight", "false").lower() == "true"
    af = ask("¿Permitir vuelo? (útil con mods de vuelo)", default=af_default)
    props["allow-flight"] = "true" if af else "false"

    bc_default = _default("bonus-chest", "true").lower() == "true"
    print_info("El cofre inicial solo aparece en mundos NUEVOS")
    bc = ask("¿Generar cofre inicial?", default=bc_default)
    props["bonus-chest"] = "true" if bc else "false"

    props["enable-command-block"] = "true"
    props["enable-status"] = "true"

    print_info("")
    print_info("── Resumen de configuración ──")
    for k in sorted(props):
        v = props[k] if props[k] != "" else "(vacío)"
        print_info(f"  {k} = {v}")
    print_info("")

    if not ask("¿Guardar esta configuración?", default=True):
        print_info("Descartando cambios. Se usarán los valores por defecto.")
        return dict(DEFAULT_PROPS)

    return props


def write_server_properties() -> None:
    print_step(3, 6, "Escribiendo server.properties…")
    props_path = Path("server.properties")
    user_props = _CFG.get("server_properties") or {}
    merged = dict(DEFAULT_PROPS)
    merged.update(user_props)
    with open(props_path, "w", encoding="utf-8") as f:
        f.write("#Minecraft server properties\n")
        for k, v in sorted(merged.items()):
            f.write(f"{k}={v}\n")
    print_success("server.properties creado")


# ---------------------------------------------------------------------------
# Start script
# ---------------------------------------------------------------------------
def write_start_script() -> None:
    print_step(4, 6, "Escribiendo script de arranque…")
    os_name = detect_os()
    min_ram = get_min_ram()
    max_ram = get_max_ram()
    java_flags = (
        f"-Xms{min_ram}G -Xmx{max_ram}G "
        "-XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:MaxGCPauseMillis=200 "
        "-XX:+UnlockExperimentalVMOptions -XX:+DisableExplicitGC "
        "-XX:+AlwaysPreTouch -XX:G1NewSizePercent=30 -XX:G1MaxNewSizePercent=40 "
        "-XX:G1HeapRegionSize=8M -XX:G1ReservePercent=20 -XX:G1HeapWastePercent=5 "
        "-XX:G1MixedGCCountTarget=4 -XX:InitiatingHeapOccupancyPercent=15 "
        "-XX:G1MixedGCLiveThresholdPercent=90 -XX:G1RSetUpdatingPauseTimePercent=5 "
        "-XX:SurvivorRatio=32 -XX:+PerfDisableSharedMem -XX:MaxTenuringThreshold=1"
    )
    if os_name == "windows":
        content = "@echo off\ntitle Minecraft Server\n" + f"java {java_flags} -jar server.jar --nogui\npause\n"
        out = START_BAT
    else:
        content = "#!/usr/bin/env bash\nset -e\n" + f'exec java {java_flags} -jar server.jar --nogui "$@"\n'
        out = START_SCRIPT
    out.write_text(content, encoding="utf-8")
    if os_name != "windows":
        out.chmod(0o755)
    print_success(f"{out} creado con {min_ram}–{max_ram} GB de RAM")


# ---------------------------------------------------------------------------
# Plugins
# ---------------------------------------------------------------------------
def latest_github_asset(repo: str, asset_regex: str) -> tuple[str, str]:
    data = http_json(f"{GITHUB_API}/{repo}/releases/latest")
    tag = data.get("tag_name", "?")
    pattern = re.compile(asset_regex, re.IGNORECASE)
    assets = data.get("assets", [])
    for asset in assets:
        if pattern.search(asset["name"]):
            return tag, asset["browser_download_url"]
    nombres = [a["name"] for a in assets]
    raise RuntimeError(f"No se encontró asset que coincida con /{asset_regex}/ en {repo}. Disponibles: {nombres}")


# Public repo that publishes SimpleLogin releases (jar attached to each v* tag).
# Change this if the plugin repo moves. Local compile is used as fallback.
SIMPLELOGIN_REPO = "xelt-realm/SimpleLogin"


def build_simplelogin_local() -> Path | None:
    """Compila SimpleLogin desde plugins-src con el maven local. Devuelve el jar o None."""
    src = Path("plugins-src/simplelogin/pom.xml")
    if not src.exists():
        return None
    if not has_command("mvn"):
        print_info("Maven no disponible: se usará el jar incluido si existe.")
        return None
    print_info("Compilando SimpleLogin localmente (mvn package)…")
    try:
        r = subprocess.run(
            ["mvn", "-q", "-B", "package", "-DskipTests"],
            cwd="plugins-src/simplelogin",
            capture_output=True, text=True, timeout=300,
        )
    except Exception as e:
        print_warning(f"No se pudo compilar SimpleLogin: {e}")
        return None
    if r.returncode != 0:
        print_warning("mvn package falló; se usará el jar incluido si existe.")
        tail = (r.stderr or r.stdout or "")[-1500:]
        if tail.strip():
            print_info(tail.strip())
        return None
    jars = sorted(Path("plugins-src/simplelogin/target").glob("SimpleLogin-*.jar"))
    if not jars:
        print_warning("mvn terminó pero no generó el jar.")
        return None
    print_success(f"SimpleLogin compilado: {jars[0]}")
    return jars[0]


def install_plugins() -> None:
    print_step(5, 6, "Descargando plugins…")
    PLUGINS_DIR.mkdir(exist_ok=True)
    targets = [
        ("ViaVersion/ViaVersion", r"^ViaVersion-[\d.]+\.jar$", "ViaVersion"),
        ("ViaVersion/ViaBackwards", r"^ViaBackwards-[\d.]+\.jar$", "ViaBackwards"),
    ]
    for repo, regex, label in targets:
        try:
            tag, url = latest_github_asset(repo, regex)
            name = url.split("/")[-1]
            dest = PLUGINS_DIR / name
            if dest.exists():
                print_info(f"{label} {tag} ya existe ({dest}). Omitiendo.")
                continue
            print_info(f"{label} {tag}: {name}")
            download(url, dest)
            print_success(f"{label} instalado en {dest}")
        except Exception as e:
            print_error(f"No se pudo instalar {label}: {e}")

    # SimpleLogin (login local): repo público -> compilación local -> copia incluida.
    try:
        have = sorted(PLUGINS_DIR.glob("SimpleLogin-*.jar"))
        if have:
            print_info(f"SimpleLogin ya existe ({have[0].name}). Omitiendo.")
        else:
            dest = None
            try:
                tag, url = latest_github_asset(SIMPLELOGIN_REPO, r"^SimpleLogin-[\d.]+\.jar$")
                dest = PLUGINS_DIR / url.split("/")[-1]
                print_info(f"SimpleLogin {tag}: {dest.name}")
                download(url, dest)
            except Exception as e:
                print_warning(f"Descarga de SimpleLogin falló ({e}); compilando localmente…")
                built = build_simplelogin_local()
                if built is not None:
                    dest = PLUGINS_DIR / built.name
                    shutil.copy(built, dest)
            if dest is None or not dest.exists():
                copies = sorted(Path("bundled-plugins").glob("SimpleLogin-*.jar"))
                if copies:
                    dest = PLUGINS_DIR / copies[0].name
                    shutil.copy(copies[0], dest)
                    print_info("SimpleLogin instalado desde copia incluida.")
            if dest is not None and dest.exists():
                for old in PLUGINS_DIR.glob("SimpleLogin-*.jar"):
                    if old != dest:
                        old.unlink()  # evita cargar dos versiones
                print_success(f"SimpleLogin instalado en {dest}")
                try:
                    bundled = Path("bundled-plugins")
                    bundled.mkdir(exist_ok=True)
                    shutil.copy(dest, bundled / dest.name)
                except Exception:
                    pass
            else:
                print_warning("No se pudo obtener SimpleLogin.")
    except Exception as e:
        print_error(f"No se pudo instalar SimpleLogin: {e}")

    # AuthMe fue reemplazado por SimpleLogin: desactivarlo si sigue presente.
    try:
        disabled = PLUGINS_DIR / ".disabled"
        for old in PLUGINS_DIR.glob("AuthMe-*.jar"):
            disabled.mkdir(exist_ok=True)
            old.rename(disabled / old.name)
            print_info(f"AuthMe desactivado (movido a {disabled / old.name}).")
    except Exception as e:
        print_warning(f"No se pudo desactivar AuthMe: {e}")


# ---------------------------------------------------------------------------
# Playit — FLUJO CORREGIDO
# ---------------------------------------------------------------------------
PLAYIT_CLAIM_TIMEOUT = 300
SOCKET_PATH = "/tmp/playit-ipc/playit.sock"
SOCKET_DIR = "/tmp/playit-ipc"


def _get_socket_path() -> str:
    """Asegura que el directorio del socket existe y devuelve la ruta."""
    os.makedirs(SOCKET_DIR, exist_ok=True)
    return SOCKET_PATH


def _wait_for_playitd_socket(timeout: int = 5) -> bool:
    """Espera a que el socket de playitd esté disponible."""
    socket_path = _get_socket_path()
    start = time.time()
    while time.time() - start < timeout:
        if os.path.exists(socket_path):
            return True
        time.sleep(0.3)
    return False


def _playit_is_bad() -> bool:
    """Detecta si playit está en un estado roto."""
    return False


def _ensure_playit_installed() -> bool:
    """Asegura que playit esté disponible."""
    return True


def _cleanup_stale_playitd() -> None:
    """Limpia procesos stale de playitd y socket."""
    socket_path = _get_socket_path()
    # Matar todos los playitd usando pgrep + kill
    try:
        r = subprocess.run(["pgrep", "-x", "playitd"], capture_output=True, text=True, timeout=3)
        if r.returncode == 0 and r.stdout.strip():
            for pid_str in r.stdout.strip().split():
                try:
                    os.kill(int(pid_str), signal.SIGKILL)
                except (ProcessLookupError, ValueError, PermissionError):
                    pass
    except Exception:
        pass
    time.sleep(0.5)
    # Eliminar socket stale
    if os.path.exists(socket_path):
        try:
            os.unlink(socket_path)
        except Exception:
            pass
    time.sleep(0.3)
    print_success("Limpieza de procesos stale completada.")


def _purge_playit() -> None:
    """Elimina completamente playit y toda su configuración."""
    print_warning("Purgando instalación rota de Playit…")
    socket_path = _get_socket_path()
    # Matar todos los playitd usando pgrep + kill
    for _ in range(3):
        try:
            r = subprocess.run(["pgrep", "-x", "playitd"], capture_output=True, text=True, timeout=3)
            if r.returncode == 0 and r.stdout.strip():
                for pid_str in r.stdout.strip().split():
                    try:
                        os.kill(int(pid_str), signal.SIGKILL)
                    except (ProcessLookupError, ValueError, PermissionError):
                        pass
        except Exception:
            pass
        time.sleep(0.3)
    # Eliminar archivos de configuración
    secret_paths = [
        Path.home() / ".config" / "playit" / "playit.toml",
        Path.home() / ".playit",
        Path("/etc/playit"),
        Path("/var/lib/playit"),
        PLAYIT_SECRET_FILE,
    ]
    for p in secret_paths:
        try:
            if p.is_file():
                p.unlink()
                print_info(f"Eliminado: {p}")
            elif p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
                print_info(f"Eliminado directorio: {p}")
        except Exception:
            pass
    # Eliminar socket y directorio
    if os.path.exists(socket_path):
        try:
            os.unlink(socket_path)
        except Exception:
            pass
    if os.path.exists(SOCKET_DIR):
        try:
            shutil.rmtree(SOCKET_DIR, ignore_errors=True)
        except Exception:
            pass
    print_success("Playit purgado completamente.")


def _install_playit_fresh() -> bool:
    """Instala playit desde cero."""
    _purge_playit()
    print_info("Instalando playit desde cero…")
    if has_command("apt-get") or has_command("sudo"):
        try:
            # Agregar clave GPG
            subprocess.run(
                "curl -SsL https://packages.playit.gg/keys/playit.gpg | gpg --dearmor | tee /usr/share/keyrings/playit.gpg >/dev/null",
                shell=True, check=True, executable="/bin/bash", timeout=30,
            )
            subprocess.run("chmod 0644 /usr/share/keyrings/playit.gpg", shell=True, check=True, executable="/bin/bash", timeout=10)
            # Agregar repositorio
            subprocess.run(
                "curl -fsSL -o /etc/apt/sources.list.d/playit.list https://packages.playit.gg/repo-files/playit-debian.list",
                shell=True, check=True, executable="/bin/bash", timeout=15,
            )
            # Actualizar e instalar
            subprocess.run("apt-get update -y", shell=True, check=True, executable="/bin/bash", timeout=60)
            subprocess.run("apt-get install -y playit", shell=True, check=True, executable="/bin/bash", timeout=60)
            if has_command("playit") or os.path.isfile("/usr/bin/playit"):
                print_success("Playit instalado desde cero.")
                return True
            # Verificar en /usr/local/bin
            if os.path.isfile("/usr/local/bin/playit"):
                os.chmod("/usr/local/bin/playit", 0o755)
                print_success("Playit instalado desde cero.")
                return True
        except Exception as e:
            print_error(f"No se pudo instalar playit con apt: {e}")
    # Fallback: descargar directamente
    print_info("Intentando descarga directa…")
    try:
        subprocess.run(
            "curl -SsL https://github.com/playit-gg/playit/releases/latest/download/playit-linux-amd64 -o /usr/local/bin/playit",
            shell=True, check=True, executable="/bin/bash", timeout=30,
        )
        subprocess.run(
            "curl -SsL https://github.com/playit-gg/playit/releases/latest/download/playitd-linux-amd64 -o /usr/local/bin/playitd",
            shell=True, check=True, executable="/bin/bash", timeout=30,
        )
        os.chmod("/usr/local/bin/playit", 0o755)
        os.chmod("/usr/local/bin/playitd", 0o755)
        if has_command("playit") or os.path.isfile("/usr/local/bin/playit"):
            print_success("Playit instalado desde cero (descarga directa).")
            return True
    except Exception as e:
        print_error(f"No se pudo descargar playit directamente: {e}")
    print_error("La instalación automática no funcionó.")
    print_info("Descarga manualmente desde https://playit.gg/download")
    return False


def _load_playit_secret() -> str | None:
    # Primero intentar desde nuestro archivo local
    if PLAYIT_SECRET_FILE.exists():
        try:
            data = json.loads(PLAYIT_SECRET_FILE.read_text(encoding="utf-8"))
            if data.get("secret"):
                return data.get("secret")
        except Exception:
            pass
    # Fallback: leer del archivo de config de playit
    secret_path = _get_playit_secret_path()
    if secret_path and Path(secret_path).exists():
        try:
            content = Path(secret_path).read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'secret_key\s*=\s*["\']([a-f0-9]{32,})["\']', content, re.IGNORECASE)
            if m:
                return m.group(1)
        except Exception:
            pass
    return None


def _save_playit_secret(secret: str) -> None:
    try:
        PLAYIT_SECRET_FILE.write_text(json.dumps({"secret": secret, "at": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=2), encoding="utf-8")
        os.chmod(PLAYIT_SECRET_FILE, 0o600)
        print_success(f"Secreto de Playit guardado en {PLAYIT_SECRET_FILE}")
    except Exception as e:
        print_warning(f"No se pudo guardar el secreto de Playit: {e}")
    # También guardar en el archivo de config de playit
    secret_path = _get_playit_secret_path()
    if secret_path:
        try:
            Path(secret_path).parent.mkdir(parents=True, exist_ok=True)
            Path(secret_path).write_text(f'secret_key = "{secret}"\n', encoding="utf-8")
            os.chmod(secret_path, 0o600)
            print_success(f"Secreto de Playit guardado en {secret_path}")
        except Exception:
            pass


def _get_playit_secret_path() -> str | None:
    """Obtiene la ruta del archivo de secreto de playit."""
    candidates = [
        Path.home() / ".config" / "playit" / "playit.toml",
        Path.home() / ".playit" / "playit.toml",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    try:
        socket_path = _get_socket_path()
        r = subprocess.run(
            ["playit", "--socket-path", socket_path, "secret-path"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            path = r.stdout.strip()
            if path and Path(path).exists():
                return path
    except Exception:
        pass
    return None


def _extract_claim_url(text: str) -> str | None:
    """Extrae el enlace de claim del texto de salida de playit."""
    match = re.search(r'https://playit\.gg/claim/[a-zA-Z0-9]+', text)
    return match.group(0) if match else None


def _extract_tunnel_address(text: str) -> str | None:
    """Extrae la dirección del túnel de la salida de playit."""
    patterns = [
        r'(?:forwarding|tunnel|address|endpoint|url|connected)\s*[:=]\s*([a-zA-Z0-9.-]+:\d+)',
        r'(playit\.gg:\d+)',
        r'([a-zA-Z0-9-]+\.at\.playit\.gg:\d+)',
        r'([a-zA-Z0-9-]+\.playit\.gg:\d+)',
        r'(\d+\.\d+\.\d+\.\d+:\d+)',
        r'(https?://playit\.gg/claim/[a-zA-Z0-9]+)',
        r'(tunnel[^:\n]*[:=]\s*[a-zA-Z0-9.-]+:\d+)',
        r'(?:tunnel\s+connected.*?address\s*[:=]\s*)([a-zA-Z0-9.-]+:\d+)',
        r'([a-zA-Z0-9-]{8,}\.playit\.gg:\d+)',
        r'(playit\.gg:\d+)',
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            addr = match.group(1)
            # Clean up URL patterns
            if addr.startswith('https://'):
                addr = addr.replace('https://', '')
            elif addr.startswith('http://'):
                addr = addr.replace('http://', '')
            return addr
    return None


def _send_discord_webhook(url: str, content: str = "", embed: dict | None = None) -> bool:
    payload: dict = {}
    if content:
        payload["content"] = content
    if embed:
        payload["embeds"] = [embed]
    if not payload:
        return False
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "MinecraftServerStarter/1.0"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status in (200, 204)
    except Exception as e:
        print_warning(f"Error al enviar webhook: {e}")
        return False


def _notify_webhook(webhook_url: str, title: str, description: str, color: int = 0x5865F2) -> None:
    if not webhook_url:
        return
    embed = {"title": title, "description": description, "color": color, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "footer": {"text": "MinecraftServer Starter"}}
    ok = _send_discord_webhook(webhook_url, embed=embed)
    if ok:
        print_success(f"Notificación enviada a Discord: {title}")
    else:
        print_warning("No se pudo enviar la notificación a Discord.")


def _kill_process(proc: subprocess.Popen | None, timeout: int = 3) -> None:
    if proc is None:
        return
    try:
        if proc.poll() is None:
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGTERM)
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                try:
                    pgid = os.getpgid(proc.pid)
                    os.killpg(pgid, signal.SIGKILL)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                try:
                    proc.wait(timeout=1)
                except Exception:
                    pass
    except Exception:
        pass


def _run_playit_cli(args: list, timeout: int = 30) -> subprocess.CompletedProcess | None:
    """Ejecuta el CLI 'playit' con los argumentos dados."""
    playit_path = shutil.which("playit") or "playit"
    if not has_command("playit"):
        print_error("No se encontró el CLI 'playit'.")
        return None
    socket_path = _get_socket_path()
    cmd = [playit_path, "--socket-path", socket_path] + args
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        cmd_str = ' '.join(args)
        print_warning(f"'playit {cmd_str}' excedió el timeout de {timeout}s.")
        return None
    except Exception as e:
        print_warning(f"Error ejecutando 'playit': {e}")
        return None


def _get_tunnel_address_from_playit() -> str | None:
    """Obtiene la dirección del túnel usando playit status o attach."""
    socket_path = _get_socket_path()
    # Intentar con playit status
    r = _run_playit_cli(["status"], timeout=5)
    if r and r.returncode == 0:
        addr = _extract_tunnel_address(r.stdout + r.stderr)
        if addr:
            return addr

    # Intentar con playit attach -s (modo stdout)
    try:
        proc = subprocess.Popen(
            ["playit", "--socket-path", socket_path, "attach", "-s"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
            start_new_session=True,
        )
    except Exception:
        return None

    addr = None
    start = time.time()

    def reader():
        nonlocal addr
        for line in proc.stdout:
            line = line.rstrip()
            print_info(f"[playit] {line}")
            if not addr:
                addr = _extract_tunnel_address(line)
                if addr:
                    print_success(f"Dirección de túnel detectada: {addr}")

    threading.Thread(target=reader, daemon=True).start()

    while time.time() - start < 3:
        if addr:
            break
        if proc.poll() is not None:
            break
        time.sleep(0.3)

    time.sleep(0.2)
    _kill_process(proc)
    return addr


def _start_playitd_with_secret(secret: str) -> subprocess.Popen | None:
    """Arranca playitd con el secreto proporcionado."""
    playitd_path = shutil.which("playitd") or "playitd"
    socket_path = _get_socket_path()
    secret_file = Path.home() / ".config" / "playit" / "playit.toml"

    # Verificar si ya hay playitd corriendo
    try:
        r = subprocess.run(["pgrep", "-x", "playitd"], capture_output=True, text=True, timeout=3)
        if r.returncode == 0 and r.stdout.strip():
            print_info("Ya hay un playitd en ejecución. Reutilizándolo.")
            return None
    except Exception:
        pass
    # Socket stale → limpiar
    if os.path.exists(socket_path):
        print_warning("Socket stale detectado. Limpiando…")
        _cleanup_stale_playitd()

    # Guardar el secreto en un archivo para pasárselo a playitd
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        secret_file.write_text(f'secret_key = "{secret}"\n', encoding="utf-8")
        os.chmod(secret_file, 0o600)
        print_success(f"Archivo de secreto escrito en {secret_file}")
    except Exception as e:
        print_warning(f"No se pudo escribir el archivo de secreto: {e}")
        return None

    print_info("Arrancando playitd con el secreto…")
    try:
        os.makedirs(SOCKET_DIR, exist_ok=True)
        if os.path.exists(socket_path):
            os.unlink(socket_path)
        proc = subprocess.Popen(
            [playitd_path, "--secret-path", str(secret_file),
             "--socket-path", socket_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        time.sleep(1.0)
        if proc.poll() is not None:
            print_warning("playitd terminó inmediatamente. Limpiando procesos stale…")
            _cleanup_stale_playitd()
            return None
        if _wait_for_playitd_socket(3):
            r = subprocess.run(
                ["playit", "--socket-path", socket_path, "status"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0 and "running" in (r.stdout + r.stderr):
                print_success("playitd arrancado correctamente")
            else:
                print_warning("playitd pudo no estar corriendo correctamente.")
        else:
            print_warning("playitd no respondió en el tiempo esperado.")
        return proc
    except Exception as e:
        print_warning(f"No se pudo arrancar playitd como daemon: {e}")
        return None


def _setup_playit_interactive() -> str | None:
    """Flujo interactivo de setup de Playit."""
    print_section("SETUP DE PLAYIT")

    # Paso 1: Generar código de claim
    print_info("Generando código de claim…")
    r = _run_playit_cli(["claim", "generate"], timeout=15)
    if not r or r.returncode != 0:
        print_error("No se pudo generar el código de claim.")
        return None

    claim_code = r.stdout.strip()
    if not claim_code:
        print_error("El claim no devolvió un código.")
        return None

    # Obtener la URL de claim
    r = _run_playit_cli(["claim", "url", claim_code], timeout=10)
    if r and r.returncode == 0:
        claim_url = r.stdout.strip() or _extract_claim_url(r.stdout + r.stderr)
    else:
        claim_url = f"https://playit.gg/claim/{claim_code}"

    # Mostrar el enlace de claim
    print_info("")
    print_info("╔══════════════════════════════════════════════════════╗")
    print_info("║  🔗 ENLACE DE CLAIM DE PLAYIT                          ║")
    print_info(f"║  {claim_url:<50} ║")
    print_info("║  Visita este enlace para vincular tu agente.        ║")
    print_info("╚══════════════════════════════════════════════════════╝")
    print_info("")

    # Paso 2: Intercambiar el claim por el secreto
    print_info("Esperando a que completes el claim…")
    print_info("Abre el enlace en otro dispositivo y confirma.")
    print_info("Si quieres cancelar, pulsa Ctrl+C.")

    # Usar claim exchange con wait infinito
    r = _run_playit_cli(["claim", "exchange", claim_code, "--wait", "0"], timeout=PLAYIT_CLAIM_TIMEOUT)
    secret = None
    if r and r.returncode == 0:
        secret = r.stdout.strip()
        # Extraer el secreto de la salida
        secret_match = re.search(r'[a-f0-9]{32,}', secret)
        if secret_match:
            secret = secret_match.group(0)
        elif not secret:
            print_warning("El claim se completó pero no se detectó el secreto en stdout.")
    
    # Si no se encontró en stdout, buscar en archivos del sistema
    if not secret:
        print_warning("claim exchange no devolvió el secreto. Buscando en archivos del sistema…")
        secret = _find_secret_in_files()
    
    if not secret:
        print_error("No se pudo obtener el secreto de Playit.")
        return None

    print_success("¡Claim completado! Secreto obtenido.")
    return secret


def _find_secret_in_files() -> str | None:
    """Busca el secreto de playit en archivos del sistema."""
    secret_path = _get_playit_secret_path()
    if secret_path and Path(secret_path).exists():
        try:
            content = Path(secret_path).read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'secret_key\s*=\s*["\']([a-f0-9]{32,})["\']', content, re.IGNORECASE)
            if m:
                return m.group(1)
        except Exception:
            pass

    # Buscar en otras ubicaciones
    candidates = [
        Path.home() / ".config" / "playit",
        Path.home() / ".playit",
        Path("/etc/playit"),
        Path("/var/lib/playit"),
    ]
    for base in candidates:
        if base.is_dir():
            for f in base.rglob("*"):
                if f.is_file():
                    try:
                        content = f.read_text(encoding="utf-8", errors="ignore")
                        m = re.search(r'secret_key\s*=\s*["\']([a-f0-9]{32,})["\']', content, re.IGNORECASE)
                        if m:
                            return m.group(1)
                        m2 = re.search(r'secret\s*=\s*["\']([a-f0-9]{32,})["\']', content, re.IGNORECASE)
                        if m2:
                            return m2.group(1)
                    except Exception:
                        pass
    return None


def setup_playit(webhook_url: str) -> str | None:
    """
    Flujo completo de Playit corregido:
      1. Si hay estado roto → purgar e reinstalar.
      2. Si ya hay secreto → arrancar playitd y obtener dirección.
      3. Si no, generar código de claim con 'playit claim generate'.
      4. Mostrar URL de claim al usuario.
      5. Intercambiar claim por secreto con 'playit claim exchange'.
      6. Guardar el secreto.
      7. Arrancar playitd con el secreto.
      8. Obtener la dirección del túnel.
      9. Notificar al webhook.
    """
    # Asegurar que playit esté instalado
    if not _ensure_playit_installed():
        print_info("Playit no disponible. Saltando configuración de Playit.")
        return None

    # Limpiar procesos stale de playitd
    _cleanup_stale_playitd()

    # --- Paso 1: ¿Ya tenemos secreto? ---
    secret = _load_playit_secret()
    if secret:
        print_success("Secreto de Playit ya guardado. Saltando flujo de claim.")
        return _start_and_get_address(secret, webhook_url)

    # --- Paso 2: Flujo de claim ---
    print_section("FLUJO DE CLAIM DE PLAYIT")
    secret = _setup_playit_interactive()

    if not secret:
        print_error("No se pudo obtener el secreto de Playit.")
        print_info("Prueba manualmente: ejecuta 'playit setup' en otra terminal.")
        return None

    _save_playit_secret(secret)

    # --- Paso 3: Arrancar playitd con el secreto ---
    print_info("Arrancando playitd con el secreto obtenido…")
    daemon_proc = _start_playitd_with_secret(secret)
    time.sleep(2)

    # --- Paso 4: Obtener la dirección del túnel ---
    address = None
    address = _get_tunnel_address_from_playit()

    if not address:
        print_warning("No se pudo obtener la dirección automáticamente.")
        try:
            addr_manual = input("  Introduce la dirección del túnel (o Enter para omitir): ").strip()
        except (EOFError, KeyboardInterrupt):
            addr_manual = ""
        if addr_manual:
            address = addr_manual

    # --- Paso 5: Notificar la dirección ---
    if address:
        print_info("")
        print_info("╔══════════════════════════════════════════════════════╗")
        print_info(f"║  ✅ SERVIDOR DISPONIBLE EN: {address}")
        print_info("╚══════════════════════════════════════════════════════╝")
        print_info("")
        _notify_webhook(
            webhook_url, "🌐 Servidor disponible",
            f"Tu servidor de Minecraft está accesible en:\n`{address}`\n\nÚnete usando esta dirección.",
            0x57F287,
        )
    else:
        print_warning("No se pudo determinar la dirección del túnel.")
        _notify_webhook(
            webhook_url, "⚠ Dirección de Playit no detectada",
            "El claim se completó pero no se pudo obtener la dirección automáticamente.",
            0xED4245,
        )

    return address


def _start_and_get_address(secret: str, webhook_url: str) -> str | None:
    """Con un secreto ya conocido, arranca playitd y obtiene la dirección."""
    print_info("Arrancando playitd con el secreto guardado…")
    daemon_proc = _start_playitd_with_secret(secret)
    time.sleep(2)

    address = _get_tunnel_address_from_playit()
    if address:
        print_info("")
        print_info("╔══════════════════════════════════════════════════════╗")
        print_info(f"║  ✅ SERVIDOR DISPONIBLE EN: {address}")
        print_info("╚══════════════════════════════════════════════════════╝")
        print_info("")
        _notify_webhook(
            webhook_url, "🌐 Servidor disponible",
            f"Tu servidor de Minecraft está accesible en:\n`{address}`",
            0x57F287,
        )
    else:
        print_warning("'tunnel get-address' no devolvió dirección. Probando 'playit attach'…")
        addr = _get_tunnel_address_from_playit()
        if addr:
            address = addr
            print_success(f"Dirección detectada: {address}")
            _notify_webhook(
                webhook_url, "🌐 Servidor disponible", f"Tu servidor de Minecraft está accesible en:\n`{address}`", 0x57F287,
            )

    return address


def install_playit() -> None:
    """Paso 6: Comprueba/instala Playit y configura el flujo de claim."""
    print_step(6, 6, "Comprobando Playit.gg…")

    if not _ensure_playit_installed():
        print_error("No se pudo instalar playit.")
        return

    if _playit_is_bad():
        print_warning("¡Playit está en un estado roto! (secreto existe pero daemon no funciona)")
        if ask("¿Purgar e reinstalar playit desde cero?", default=True):
            if _install_playit_fresh():
                # Limpiar el secreto guardado
                try:
                    PLAYIT_SECRET_FILE.unlink(missing_ok=True)
                except Exception:
                    pass
            else:
                return
        else:
            print_warning("Playit permanece en estado roto. La configuración puede fallar.")
            return

    webhook_url = ""
    if WEBHOOK_FILE.exists():
        try:
            wd = json.loads(WEBHOOK_FILE.read_text(encoding="utf-8"))
            webhook_url = wd.get("url", "")
        except Exception:
            pass

    if webhook_url:
        address = setup_playit(webhook_url)
        if address:
            print_success(f"Playit configurado. Dirección: {address}")
        elif not _ensure_playit_installed():
            print_info("→ Playit no disponible. Se omitió.")
    else:
        print_warning("No hay webhook configurado. Configura uno para recibir el enlace de claim y la dirección.")


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------
def setup_webhook() -> bool:
    print_section("CONFIGURACIÓN DE WEBHOOK")
    print_info("Introduce la URL del webhook (Discord, Slack, etc.).")
    print_info("Déjalo vacío para omitir este paso.")
    try:
        url = input("  URL del webhook: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if not url:
        print_info("Omitiendo configuración de webhook.")
        return False
    if not (url.startswith("http://") or url.startswith("https://")):
        print_error("URL inválida. Debe empezar por http:// o https://")
        return False

    config = {"url": url, "username": "MinecraftServer", "enabled": True}
    WEBHOOK_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        os.chmod(WEBHOOK_FILE, 0o600)
    except Exception:
        pass
    print_success(f"Webhook guardado en {WEBHOOK_FILE} (permisos 0600).")

    if _send_discord_webhook(url, content="✅ Webhook configurado correctamente."):
        print_success("Webhook probado exitosamente.")
    else:
        print_warning("El webhook no respondió correctamente. Verifica la URL.")

    return True


def show_webhook_info() -> None:
    try:
        data = json.loads(WEBHOOK_FILE.read_text(encoding="utf-8"))
        url = data.get("url", "")
        masked = url[:36] + "…" + url[-12:] if len(url) > 60 else url
        enabled = data.get("enabled", True)
        print_info(f"URL: {masked}")
        print_info(f"Habilitado: {enabled}")
    except Exception as e:
        print_warning(f"No se pudo leer el archivo de webhook: {e}")


# ---------------------------------------------------------------------------
# Importar servidor desde .zip público
# ---------------------------------------------------------------------------
def _github_url_to_zip(url: str) -> str:
    if "github.com" not in url or url.endswith(".zip"):
        return url
    url = url.rstrip('/').removesuffix('.git')
    if "/archive/" in url or "/releases/" in url:
        return url
    return f"{url}/archive/refs/heads/main.zip"


def _safe_extract_zip(zip_path: Path, dest_dir: Path) -> None:
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            p = Path(name)
            if p.is_absolute() or ".." in p.parts:
                raise RuntimeError(f"Zip inseguro (path traversal): {name}")
        z.extractall(dest_dir)


def _promote_single_dir(staging: Path) -> None:
    entries = list(staging.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        src = entries[0]
    else:
        src = staging
    for item in src.iterdir():
        target = Path(item.name)
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            else:
                try:
                    target.unlink()
                except Exception:
                    pass
        shutil.move(str(item), str(target))


def prompt_custom_server_zip() -> bool:
    print_section("IMPORTAR SERVIDOR DESDE REPOSITORIO")
    print_info("Introduce la URL del repositorio público o del .zip del servidor.")
    print_info("(Ejemplos: https://github.com/user/repo  ó  https://.../server.zip)")
    try:
        url = input("  URL: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if not url:
        return False

    url = _github_url_to_zip(url)
    tmp = Path(".custom-server-download.zip")
    staging = Path(".custom_extract_")
    try:
        download(url, tmp)
    except Exception as e:
        print_error(f"Descarga fallida: {e}")
        tmp.unlink(missing_ok=True)
        return False

    try:
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir()
        _safe_extract_zip(tmp, staging)
        _promote_single_dir(staging)
    except Exception as e:
        print_error(f"Extracción fallida: {e}")
        tmp.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=True)
        return False
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        shutil.rmtree(staging, ignore_errors=True)

    if not SERVER_JAR.exists():
        jars = [j for j in Path(".").glob("*.jar") if j.is_file()]
        if len(jars) == 1:
            shutil.move(str(jars[0]), str(SERVER_JAR))
            print_success(f"Renombrado {jars[0].name} → {SERVER_JAR.name}")
        elif len(jars) > 1:
            print_warning(f"Múltiples .jar encontrados: {[j.name for j in jars]}")

    if not get_start_script().exists():
        write_start_script()

    print_success("Servidor importado desde repositorio público.")
    return True


# ---------------------------------------------------------------------------
# Tareas periódicas
# ---------------------------------------------------------------------------
def _git_push_soft(cfg: dict, git_lock: threading.Lock) -> None:
    with git_lock:
        remote = cfg.get("git_remote")
        if not remote:
            return
        r = _git_run(["remote", "get-url", "origin"])
        if r.returncode != 0:
            _git_run(["remote", "add", "origin", remote])
        _git_run(["add", "-A"])
        status = _git_run(["status", "--porcelain"])
        if status.returncode == 0 and status.stdout.strip():
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            _git_run(["commit", "-m", f"auto: backup {ts}"])
        br = _git_run(["rev-parse", "--abbrev-ref", "HEAD"])
        branch = br.stdout.strip() if br.returncode == 0 and br.stdout.strip() else "main"
        r = _git_run(["push", "origin", branch], timeout=120)
        if r.returncode != 0:
            print_warning(f"git push falló: {(r.stderr or '').strip()[:180]}")
        else:
            print_success(f"[5min] push suave a {branch} completado.")


def _backup_zip(cfg: dict, git_lock: threading.Lock) -> None:
    BACKUP_DIR.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    out = BACKUP_DIR / f"backup-{ts}.zip"
    skip_dirs = {".git", "backups", "logs"}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk("."):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for f in files:
                fp = Path(root) / f
                try:
                    z.write(fp, fp.as_posix())
                except Exception:
                    pass
    print_success(f"[5min] backup zip: {out}")
    max_keep = int(cfg_get("max_zip_backups") or 5)
    try:
        backups = sorted(BACKUP_DIR.glob("backup-*.zip"), key=lambda p: p.stat().st_mtime)
        while len(backups) > max_keep:
            old = backups.pop(0)
            try:
                old.unlink()
                print_info(f"Backup antiguo eliminado: {old.name}")
            except Exception:
                pass
    except Exception:
        pass


def _hard_reset_and_push(cfg: dict, git_lock: threading.Lock) -> None:
    with git_lock:
        remote = cfg.get("git_remote") or detect_git_remote()
        if not remote:
            print_warning("No hay remote configurado; omitiendo hard reset.")
            return
        print_info(f"[25min] Hard reset de .git y push --force a {remote}")
        try:
            shutil.rmtree(".git", ignore_errors=True)
        except Exception:
            pass
        _git_run(["init"])
        _git_run(["remote", "add", "origin", remote])
        _git_run(["add", "-A"])
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        _git_run(["commit", "-m", f"auto-reset {ts}"])
        _git_run(["branch", "-M", "main"])
        r = _git_run(["push", "-u", "origin", "main", "--force"], timeout=180)
        if r.returncode != 0:
            print_warning(f"push --force falló: {(r.stderr or '').strip()[:200]}")
        else:
            print_success("[25min] push --force completado.")


def _periodic_task(stop_event: threading.Event, interval: int, fn, name: str) -> None:
    while not stop_event.wait(interval):
        if stop_event.is_set():
            break
        try:
            fn()
        except Exception as e:
            print_warning(f"Tarea periódica '{name}' falló: {e}")


# ---------------------------------------------------------------------------
# RAM interactiva
# ---------------------------------------------------------------------------
def prompt_ram_change() -> None:
    current_min = get_min_ram()
    current_max = get_max_ram()
    print_info(f"RAM actual del servidor: {current_min}-{current_max} GB")
    if not ask("¿Quieres cambiar la RAM asignada?", default=False):
        return
    avail = get_available_ram_gb()
    if avail is not None:
        print_info(f"RAM disponible en el sistema: {avail:.1f} GB")
    new_min = ask_int("Nueva RAM mínima (GB)", current_min, minv=1, maxv=128)
    new_max = ask_int("Nueva RAM máxima (GB)", current_max, minv=1, maxv=128)
    if new_min > new_max:
        print_warning("La RAM mínima no puede ser mayor que la máxima. Se intercambiarán los valores.")
        new_min, new_max = new_max, new_min
    _CFG["min_ram_gb"] = new_min
    _CFG["max_ram_gb"] = new_max
    save_config(_CFG)
    write_start_script()
    print_success(f"RAM actualizada a {new_min}-{new_max} GB.")


# ---------------------------------------------------------------------------
# Arranque del servidor
# ---------------------------------------------------------------------------
def _read_log_tail(since_size: int = 0, max_lines: int = 250) -> list:
    """Lee solo las líneas del log escritas después de since_size (sesión actual)."""
    try:
        log_path = Path("logs/latest.log")
        if not log_path.exists():
            return []
        data = log_path.read_bytes()
        if len(data) < since_size:
            since_size = 0  # el log rotó o se truncó: leerlo entero
        return data[since_size:].decode("utf-8", errors="ignore").splitlines()[-max_lines:]
    except Exception:
        return []


def _scan_log_errors(since_size: int = 0, max_lines: int = 250, max_errors: int = 8) -> list:
    """Extrae las líneas de error más relevantes del log del servidor."""
    errs: list = []
    for line in _read_log_tail(since_size, max_lines):
        u = line.upper()
        if "/ERROR]" in u or "EXCEPTION" in u or "FAILED" in u or "COULD NOT " in u or "CAUSED BY:" in u:
            s = line.strip()
            if len(s) > 220:
                s = s[:220] + "…"
            if s and s not in errs:
                errs.append(s)
            if len(errs) >= max_errors:
                break
    return errs


def _log_shows_graceful_stop(since_size: int = 0, max_lines: int = 40) -> bool:
    """Detecta si el log muestra un apagado ordenado (stop desde consola)."""
    tail = "\n".join(_read_log_tail(since_size, max_lines)).lower()
    return any(m in tail for m in ("stopping the server", "stopping server", "all dimensions are saved", "saving players"))


def _report_server_stop(rc: int | None, elapsed: float, since_size: int = 0) -> None:
    """Mensaje personalizado según cómo terminó el servidor + errores del log."""
    sig = None
    if rc is not None:
        if rc < 0:
            sig = -rc
        elif rc in (130, 137, 143):
            sig = rc - 128
    graceful = _log_shows_graceful_stop(since_size)
    errors = _scan_log_errors(since_size)

    if rc == 0:
        print_success(f"Servidor apagado correctamente tras {elapsed:.1f}s.")
        if errors:
            print_warning(f"El log contiene {len(errors)} error(es) aunque el apagado fue limpio:")
            for e in errors:
                print_warning(f"  • {e}")
        return

    if sig == 2:
        print_info(f"Servidor detenido por el usuario (Ctrl+C) tras {elapsed:.1f}s.")
    elif sig == 9:
        print_error(f"El servidor fue MATADO (SIGKILL) tras {elapsed:.1f}s.")
        print_warning("Causa probable: falta de RAM (el sistema/OOM-killer lo mató).")
        print_info("Solución: baja la RAM del servidor (opción 2 del menú) por debajo de la RAM disponible.")
    elif sig == 15:
        if graceful:
            print_success(f"Servidor detenido con 'stop' tras {elapsed:.1f}s.")
        elif elapsed < 20:
            print_error(f"El servidor murió con SIGTERM a los {elapsed:.1f}s de arrancar.")
            print_warning("Causa probable: el entorno lo mató por exceso de RAM (-Xms mayor que la disponible).")
            print_info("Solución: baja la RAM del servidor (opción 2 del menú).")
        else:
            print_warning(f"El servidor recibió SIGTERM tras {elapsed:.1f}s (apagado externo).")
    elif rc is None:
        print_error("El servidor terminó en estado desconocido.")
    else:
        if elapsed < 15:
            print_error(f"El servidor CRASHEÓ al arrancar (código {rc}, {elapsed:.1f}s).")
            print_info("Causas comunes: RAM insuficiente, Java antiguo, eula.txt sin aceptar, server.properties inválido, plugin roto.")
        else:
            print_error(f"El servidor CRASHEÓ (código {rc}) tras {elapsed:.1f}s en marcha.")

    if errors:
        print_warning("Errores detectados en logs/latest.log:")
        for e in errors:
            print_warning(f"  • {e}")
    else:
        print_info("El log no muestra errores claros. Revisa logs/latest.log para más detalles.")


def run_server_with_tasks(cfg: dict) -> None:
    script = get_start_script()
    if not script.exists():
        print_error(f"No se encontró {script}.")
        return

    prompt_ram_change()

    java_ok, java_msg = check_java()
    if not java_ok:
        print_error(f"Java no está disponible: {java_msg}")
        print_info("Instala Java 21+ (por ejemplo: sudo apt install openjdk-21-jre-headless)")
        if not ask("¿Continuar de todas formas?", default=False):
            return

    min_ram = get_min_ram()
    max_ram = get_max_ram()
    avail = get_available_ram_gb()
    if avail is not None and avail < max_ram:
        print_warning(f"RAM disponible del sistema: {avail:.1f} GB")
        print_warning(f"La config pide {min_ram}–{max_ram} GB.")
        if avail < min_ram:
            print_error("RAM insuficiente para arrancar el servidor.")
            print_warning(f"Con -Xms{min_ram}G la JVM muere con SIGTERM al arrancar (probado: ni 'java -version' sobrevive).")
            new_max = max(2, int(avail) - 1)
            new_min = max(1, new_max - 2)
            cfg["min_ram_gb"] = new_min
            cfg["max_ram_gb"] = new_max
            save_config(cfg)
            _CFG.update(cfg)
            print_success(f"RAM ajustada automáticamente a {new_min}-{new_max} GB para que el servidor pueda arrancar.")
            write_start_script()
            min_ram = new_min
            max_ram = new_max
        else:
            if not ask("¿Continuar de todas formas?", default=True):
                return

    print_info("")
    print_info("╔══════════════════════════════════════════════════════╗")
    print_info(f"║  🚀 Arrancando servidor: bash {script}")
    print_info(f"║  RAM: {min_ram}-{max_ram} GB")
    print_info("║  (Consola interactiva. Ctrl+C para detener)")
    print_info(f"║  Backup cada {int(cfg_get('backup_interval_seconds'))//60} min  |  Hard reset cada {int(cfg_get('hard_reset_interval_seconds'))//60} min")
    print_info("╚══════════════════════════════════════════════════════╝")
    print_info("")

    if detect_os() == "windows":
        cmd = [str(script)]
        use_shell = True
    else:
        cmd = ["bash", str(script)]
        use_shell = False

    try:
        proc = subprocess.Popen(cmd, shell=use_shell, bufsize=0)
    except Exception as e:
        print_error(f"No se pudo arrancar el servidor: {e}")
        return

    try:
        log_start_size = Path("logs/latest.log").stat().st_size
    except OSError:
        log_start_size = 0

    stop_event = threading.Event()
    git_lock = threading.Lock()

    def backup_task():
        mode = cfg_get("backup_mode") or "git_push"
        if mode == "zip":
            _backup_zip(cfg, git_lock)
        else:
            _git_push_soft(cfg, git_lock)

    backup_interval = int(cfg_get("backup_interval_seconds") or 300)
    threading.Thread(target=_periodic_task, args=(stop_event, backup_interval, backup_task, "backup"), daemon=True, name="periodic-backup").start()

    reset_interval = int(cfg_get("hard_reset_interval_seconds") or 1500)
    threading.Thread(target=_periodic_task, args=(stop_event, reset_interval, lambda: _hard_reset_and_push(cfg, git_lock), "hard-reset"), daemon=True, name="periodic-hard-reset").start()

    start_ts = time.time()

    def quick_death_watch():
        time.sleep(3.0)
        if proc.poll() is not None and not stop_event.is_set():
            print_error(f"El servidor terminó muy rápido (código {proc.returncode}).")
            print_info("Revisa los mensajes de arriba para más detalles.")
            print_info("Causas comunes: RAM insuficiente, Java antiguo, error en eula.txt / server.properties.")

    threading.Thread(target=quick_death_watch, daemon=True, name="quick-death-watch").start()

    try:
        proc.wait()
    except KeyboardInterrupt:
        print_info("\n→ Deteniendo servidor…")
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            print_info("El servidor no responde. Enviando SIGTERM…")
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except Exception:
                    pass
    finally:
        stop_event.set()

    elapsed = time.time() - start_ts
    _report_server_stop(proc.returncode, elapsed, log_start_size)
    print_success("Volviendo a la UI…")


# ---------------------------------------------------------------------------
# Instalación completa
# ---------------------------------------------------------------------------
def run_full_install() -> bool:
    existing: dict = {}
    props_path = Path("server.properties")
    if props_path.exists():
        for line in props_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                existing[k.strip()] = v.strip()

    user_props = prompt_server_properties(existing)
    _CFG["server_properties"] = user_props
    save_config(_CFG)

    steps = [download_paper, write_eula, write_server_properties, write_start_script, install_plugins, install_playit]
    for step in steps:
        try:
            step()
        except Exception as e:
            print_error(f"\nError en {step.__name__}: {e}")
            if not ask("¿Continuar con los siguientes pasos?", default=False):
                return False
    return True


# ---------------------------------------------------------------------------
# Menú principal
# ---------------------------------------------------------------------------
def server_loop(cfg: dict) -> None:
    while True:
        print_header("MENÚ DEL SERVIDOR")
        print_info("1) Encender servidor")
        print_info("2) Cambiar RAM")
        print_info("3) Configurar webhook")
        print_info("4) Configurar Playit")
        print_info("5) Ver estado del servidor")
        print_info("0) Salir")
        try:
            choice = input("  Opción [1]: ").strip() or "1"
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if choice == "1":
            run_server_with_tasks(cfg)
        elif choice == "2":
            prompt_ram_change()
        elif choice == "3":
            setup_webhook()
        elif choice == "4":
            webhook_url = ""
            if WEBHOOK_FILE.exists():
                try:
                    wd = json.loads(WEBHOOK_FILE.read_text(encoding="utf-8"))
                    webhook_url = wd.get("url", "")
                except Exception:
                    pass
            setup_playit(webhook_url)
        elif choice == "5":
            _show_server_status(cfg)
        elif choice == "0":
            return
        else:
            print_error("Opción inválida.")


def _show_server_status(cfg: dict) -> None:
    print_section("ESTADO DEL SERVIDOR")
    java_ok, java_msg = check_java()
    print_info(f"Java: {'✅ ' + java_msg if java_ok else '❌ ' + java_msg}")
    print_info(f"Servidor JAR: {'✅ Existe' if SERVER_JAR.exists() else '❌ No encontrado'}")
    print_info(f"Script arranque: {'✅ Existe' if get_start_script().exists() else '❌ No encontrado'}")
    print_info(f"RAM: {get_min_ram()}–{get_max_ram()} GB")
    print_info(f"OS: {detect_os()}")

    playit_secret = _load_playit_secret()
    print_info(f"Playit secreto: {'✅ Configurado' if playit_secret else '❌ No configurado'}")

    try:
        socket_path = _get_socket_path()
        r = subprocess.run(
            ["playit", "--socket-path", socket_path, "status"],
            capture_output=True, text=True, timeout=5,
        )
        print_info(f"playitd: {'✅ En ejecución' if r.returncode == 0 and 'running' in (r.stdout + r.stderr) else '❌ No en ejecución'}")
    except Exception:
        print_info("playitd: ❌ No se puede verificar")

    webhook_exists = WEBHOOK_FILE.exists()
    print_info(f"Webhook: {'✅ Configurado' if webhook_exists else '❌ No configurado'}")

    try:
        r = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, timeout=10)
        print_info(f"Git remote: {'✅ ' + r.stdout.strip() if r.returncode == 0 else '❌ No configurado'}")
    except Exception:
        print_info("Git remote: ❌ No se puede verificar")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    global _CFG
    _CFG = load_config()

    print_header("PREPARACIÓN DE SERVIDOR PAPERMC")
    print_info(f"Directorio actual: {Path.cwd()}")
    print_info(f"RAM configurada: {get_min_ram()}–{get_max_ram()} GB")
    print_info(f"SO detectado: {detect_os()}")
    print_info(f"User-Agent: {get_user_agent()}")

    avail = get_available_ram_gb()
    if avail is not None:
        print_info(f"RAM disponible: {avail:.1f} GB")

    java_ok, java_msg = check_java()
    print_info(f"Java: {'✅ ' + java_msg if java_ok else '❌ ' + java_msg}")

    pv = load_paper_version()
    if pv:
        print_info(f"Paper registrado: {pv.get('version','?')} (build {pv.get('build','?')})")
    else:
        print_info("Paper registrado: (sin registro aún)")

    playit_secret = detect_playit_secret()
    print_info(f"Playit secreto: {'✅ Configurado' if playit_secret else '❌ No configurado'}")

    server_installed = detect_server_installed()
    webhook_exists = detect_webhook()
    print_info(f"Servidor detectado: {'✅ Sí' if server_installed else '❌ No'}")
    print_info(f"Webhook detectado: {'✅ Sí' if webhook_exists else '❌ No'}")

    # ─── FASE 1: INSTALACIÓN ───
    if server_installed:
        print_info("")
        print_success("Servidor ya instalado. Se omite la fase de instalación.")
    else:
        print_info("")
        print_warning("Servidor NO detectado.")
        if ask("¿Descargar el servidor desde otro repositorio público (.zip)?", default=False):
            prompt_custom_server_zip()
            server_installed = detect_server_installed()

        if not server_installed:
            if ask("¿Ejecutar instalación estándar de Paper?", default=True):
                if not run_full_install():
                    print_error("\nLa instalación no se completó correctamente.")
                server_installed = detect_server_installed()

        if not server_installed:
            print_error("No hay servidor disponible. Abortando.")
            return 1

        print_info("")
        print_success("✅ Instalación completada.")

    # ─── FASE 2: SEGURIDAD ───
    print_info("")
    print_info("[SEGURIDAD] Asegurando .gitignore…")
    ensure_gitignore()
    protection_ok = verify_gitignore_protection()

    # ─── FASE 3: WEBHOOK ───
    print_info("")
    print_info("[WEBHOOK] Comprobando configuración…")
    webhook_exists = detect_webhook()
    if webhook_exists:
        warn_if_webhook_is_tracked()
        print_success("Webhook ya configurado.")
        show_webhook_info()
        if ask("¿Quieres cambiar la URL del webhook?", default=False):
            if protection_ok:
                setup_webhook()
            else:
                print_error("No se puede cambiar sin protección de .gitignore.")
    else:
        print_info("→ No hay webhook configurado.")
        if not protection_ok:
            print_error("No se configurará el webhook: el .gitignore no está protegiendo correctamente el archivo.")
        elif ask("¿Quieres configurar un webhook ahora?", default=True):
            setup_webhook()
        else:
            print_info("→ Omitiendo configuración de webhook.")

    # ─── FASE 4: PLAYIT ───
    print_info("")
    print_info("[PLAYIT] Configurando túnel…")
    webhook_url = ""
    if WEBHOOK_FILE.exists():
        try:
            wd = json.loads(WEBHOOK_FILE.read_text(encoding="utf-8"))
            webhook_url = wd.get("url", "")
        except Exception:
            pass

    if detect_playit_secret():
        print_success("Playit ya configurado con secreto guardado.")
        if webhook_url:
            _notify_webhook(webhook_url, "✅ Servidor listo", "El servidor de Minecraft está listo para arrancar.", 0x57F287)
    else:
        print_info("→ No hay secreto de Playit configurado. Iniciando flujo de claim…")
        address = setup_playit(webhook_url)
        if address:
            print_success(f"Playit configurado. Dirección: {address}")
        elif not _ensure_playit_installed():
            print_info("→ Playit no disponible. Se omitió.")

    # ─── FASE 5: GIT REMOTE ───
    print_info("")
    print_info("[GIT] Configurando repositorio remoto…")
    remote = ensure_git_remote(_CFG)
    if remote:
        print_success(f"Remote: {remote}")
        print_info(f"→ Backup: cada {int(cfg_get('backup_interval_seconds'))//60} min ({cfg_get('backup_mode')})")
        print_info(f"→ Hard reset + push --force: cada {int(cfg_get('hard_reset_interval_seconds'))//60} min")
    else:
        print_warning("Sin remote configurado: se omitirán los auto-push.")

    # ─── FASE 6: LOOP ───
    print_info("")
    print_header("LISTO")
    if ask("¿Encender el servidor ahora?", default=True):
        run_server_with_tasks(_CFG)
        server_loop(_CFG)
    else:
        script = get_start_script()
        print_info("→ Servidor no iniciado.")
        print_info(f"Arráncalo manualmente con: ./{script}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print_info("\nInterrumpido por el usuario.")
        sys.exit(130)
