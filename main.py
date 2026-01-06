"""
================================================================================
TTS_CLIPBOARD_MP3 v0.6.6
================================================================================
Arquivo:        main.py
Projeto:        Texto colado → (1) Ler em voz alta (sem MP3) OU (2) Gerar MP3 (pt)
Autor:          Fábio Bettio
Licença:        Uso educacional / experimental
Data:           05/01/2026

DESCRIÇÃO
    - Cole o texto (Ctrl+V) no editor.
    - "LER AGORA" fala o texto sem gerar MP3 (offline via Windows SAPI / pyttsx3).
    - "GERAR MP3" cria MP3 (online). Agora com Edge TTS (voz/rate/pitch reais).
    - Nome do MP3 = 1ª linha do texto (sanitizado).

CONTROLE DE EXECUÇÃO
    - PAUSAR/CONTINUAR: pausa cooperativa entre blocos (chunks).
    - PARAR: cancela o job atual e REINICIA O MOTOR ao final do cancelamento.
    - Ao finalizar GERAR MP3 com sucesso: REINICIA O MOTOR automaticamente.

PROGRESSO
    - Barra determinística + percentual na área de status (abaixo do texto).
    - Leitura e geração mostram % de conclusão por blocos.

PERFORMANCE (textos grandes)
    - Divide o texto em blocos e gera vários MP3s pequenos, depois concatena.
    - Concat rápida usa FFmpeg (-c copy). Sem FFmpeg usa fallback (menos confiável).

CONFIG (robusta)
    - Existe "CONFIG RASCUNHO" (UI) e "CONFIG APLICADA" (cfg).
    - Executar LER/MP3 usa SOMENTE a config aplicada.
    - Só muda de fato quando clicar "SALVAR CONFIG".
    - Botão "REINICIAR MOTOR" recupera o TTS offline.

REQUISITOS
    pip install pyttsx3 gtts edge-tts
    (Recomendado) FFmpeg no PATH:
        winget install Gyan.FFmpeg

================================================================================
CHANGELOG
    v0.6.6 (05/01/2026) [ESTÁVEL] (~930 linhas)
        - Status (barra + % + texto) movido para dentro da aba Editor (não corta).
        - Ao concluir GERAR MP3: reinicia motor automaticamente.
        - MP3 com Edge TTS: voz/rate/pitch passam a ter efeito real no MP3.
        - Fallback para gTTS se edge-tts não estiver instalado (com aviso).
    v0.6.5 (05/01/2026) (~790 linhas)
        - Barra de progresso determinística + % no status (abaixo do texto).
        - Progresso atualizado em LER e GERAR por bloco, com etapa de concatenação.
    v0.6.4 (05/01/2026) (~740 linhas)
        - Ao clicar PARAR, agenda REINICIAR MOTOR automaticamente ao final do job.
        - Melhora a recuperação após cancelamento (pyttsx3 travado).
    v0.6.3 (05/01/2026) (~720 linhas)
        - Adicionado PAUSAR/CONTINUAR e PARAR para LER AGORA e GERAR MP3.
        - Pausa cooperativa por blocos (não no meio do áudio).
        - PARAR cancela geração e interrompe leitura (engine.stop()).
    v0.6.2 (05/01/2026) [ESTÁVEL] (~640 linhas)
        - Correção definitiva: mudanças na UI não afetam execução (staged config).
        - Novo botão "SALVAR CONFIG" (aplica + persiste + reinicia TTS offline).
        - Novo botão "REINICIAR MOTOR" (recuperação imediata).
        - Execução (LER/MP3) usa apenas config aplicada, nunca valores “ao vivo”.
    v0.6.1 (05/01/2026) (~575 linhas)
        - Config só aplica/salva ao clicar "SALVAR CONFIG".
        - pyttsx3 reinicia com segurança ao aplicar config.
        - Config bloqueada durante execução.
        - Detecção de FFmpeg mais robusta.
    v0.6.0 (05/01/2026) (~520 linhas)
        - Chunking + concat via FFmpeg.
        - Config persistente em JSON.
    v0.5.0 (05/01/2026) (~390 linhas)
        - Aba de configurações (voz/rate/chunk) + botão LER (sem MP3).
        - Interface melhorada.
    v0.4.0 (05/01/2026) [ESTÁVEL] (~310 linhas)
        - Primeira versão utilizável (Ctrl+V → gerar MP3).
================================================================================
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Tuple

import tkinter as tk
from tkinter import messagebox
from tkinter import ttk

from gtts import gTTS

try:
    import pyttsx3
except Exception:
    pyttsx3 = None

try:
    import edge_tts
except Exception:
    edge_tts = None

APP_VERSION = "0.6.6"
CONFIG_PATH = Path.cwd() / "config_tts_clipboard_mp3.json"


# =========================
# CONFIG MODEL
# =========================
@dataclass
class AppConfig:
    exclude_first_line: bool = False

    # MP3 (Edge TTS / gTTS fallback)
    mp3_backend: str = "edge"  # edge|gtts
    mp3_voice: str = "pt-BR-FranciscaNeural"
    mp3_rate: str = "+0%"      # edge: "-50%".."+100%"
    mp3_pitch: str = "+0Hz"    # edge: "-20Hz".."+20Hz"
    gt_tld_label: str = "pt-BR (padrão)"
    gt_speed: str = "Normal"  # Normal|Lenta

    # LER (pyttsx3)
    read_voice_name: str = ""
    read_rate: int = 175

    # Performance
    chunk_max_chars: int = 1100


def load_config() -> AppConfig:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            allowed = {k: data[k] for k in data if k in AppConfig.__annotations__}
            return AppConfig(**allowed)
        except Exception:
            pass
    return AppConfig()


def save_config(cfg: AppConfig) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# =========================
# UTILS
# =========================
def sanitize_filename(name: str, max_len: int = 120) -> str:
    name = (name or "").strip()
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    name = re.sub(r"\s+", " ", name)
    name = name.strip(" .")
    if not name:
        name = "audio"
    return name[:max_len]


def pick_first_nonempty_line(text: str) -> str:
    for ln in text.splitlines():
        if ln.strip():
            return ln.strip()
    return "audio"


def unique_path(folder: Path, filename: str) -> Path:
    base = sanitize_filename(filename)
    candidate = folder / f"{base}.mp3"
    if not candidate.exists():
        return candidate
    i = 2
    while True:
        candidate = folder / f"{base} ({i}).mp3"
        if not candidate.exists():
            return candidate
        i += 1


def open_folder(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception:
        pass


def ffmpeg_status() -> Tuple[bool, str]:
    try:
        exe = shutil.which("ffmpeg")
        if exe:
            return True, exe
        res = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if res.returncode == 0:
            return True, "(ffmpeg executável, mas não localizado via which)"
        return False, "ffmpeg não encontrado no PATH"
    except Exception as e:
        return False, f"erro ao testar ffmpeg: {e}"


def smart_split_text(text: str, max_chars: int) -> List[str]:
    s = re.sub(r"\r\n", "\n", text).strip()
    if not s:
        return []
    chunks: List[str] = []
    i = 0
    n = len(s)
    sentence_breaks = set(".!?;:")
    max_chars = max(300, int(max_chars))

    while i < n:
        end = min(i + max_chars, n)
        if end == n:
            chunk = s[i:end].strip()
            if chunk:
                chunks.append(chunk)
            break

        window = s[i:end]
        cut = -1

        nl = window.rfind("\n")
        if nl >= int(max_chars * 0.60):
            cut = nl + 1

        if cut == -1:
            for k in range(len(window) - 1, int(max_chars * 0.55), -1):
                if window[k] in sentence_breaks:
                    cut = k + 1
                    break

        if cut == -1:
            sp = window.rfind(" ")
            if sp >= int(max_chars * 0.55):
                cut = sp + 1

        if cut == -1:
            cut = len(window)

        chunk = s[i:i + cut].strip()
        if chunk:
            chunks.append(chunk)
        i = i + cut

    return chunks


def concat_mp3_ffmpeg(parts: List[Path], output: Path) -> None:
    if not parts:
        raise RuntimeError("Nenhuma parte para concatenar.")
    with tempfile.TemporaryDirectory() as td:
        list_path = Path(td) / "list.txt"
        lines = []
        for p in parts:
            path_str = str(p).replace("'", "'\\''")
            lines.append(f"file '{path_str}'")
        list_path.write_text("\n".join(lines), encoding="utf-8")

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_path),
            "-c", "copy",
            str(output),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            msg = (res.stderr or res.stdout or "").strip()
            raise RuntimeError(f"FFmpeg falhou ao concatenar: {msg}")


def concat_mp3_naive(parts: List[Path], output: Path) -> None:
    with open(output, "wb") as out:
        for p in parts:
            out.write(p.read_bytes())


async def edge_tts_save_mp3(text: str, out_path: Path, voice: str, rate: str, pitch: str) -> None:
    comm = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    await comm.save(str(out_path))


# =========================
# UI DIALOGS
# =========================
class DoneDialog(tk.Toplevel):
    def __init__(self, master: tk.Tk, out_dir: Path, extra: str = ""):
        super().__init__(master)
        self.title("Concluído")
        self.resizable(False, False)
        self.out_dir = out_dir
        self.var_open = tk.BooleanVar(value=True)
        self.configure(padx=14, pady=12)

        msg = f"Finalizado.\nPasta de destino:\n{out_dir}"
        if extra:
            msg += f"\n\n{extra}"

        ttk.Label(self, text=msg, justify="left").pack(fill="x")
        ttk.Checkbutton(self, text="Abrir pasta de destino", variable=self.var_open).pack(anchor="w", pady=(10, 10))
        ttk.Button(self, text="OK", width=12, command=self._on_ok).pack(anchor="e")

        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_ok)
        self.after(50, self._center_on_master)

    def _center_on_master(self):
        self.update_idletasks()
        mw = self.master.winfo_width()
        mh = self.master.winfo_height()
        mx = self.master.winfo_rootx()
        my = self.master.winfo_rooty()
        w = self.winfo_width()
        h = self.winfo_height()
        x = mx + (mw // 2) - (w // 2)
        y = my + (mh // 2) - (h // 2)
        self.geometry(f"+{x}+{y}")

    def _on_ok(self):
        if self.var_open.get():
            open_folder(self.out_dir)
        self.destroy()


# =========================
# MAIN APP
# =========================
class App(tk.Tk):
    TLD_OPTIONS = {
        "pt-BR (padrão)": "com.br",
        "pt (alternativo)": "pt",
        "com (alternativo)": "com",
    }

    def __init__(self):
        super().__init__()
        self.title(f"TTS → Ler / MP3 (pt) v{APP_VERSION}")
        self.geometry("1100x780")
        self.minsize(980, 720)

        self.out_dir = Path.cwd() / "saida_mp3"
        self.out_dir.mkdir(parents=True, exist_ok=True)

        self.cfg = load_config()

        self._py_engine = None
        self._py_voices = []
        self._is_busy = False

        self._pause_event = threading.Event()
        self._pause_event.set()
        self._stop_event = threading.Event()
        self._current_job = "idle"

        self._restart_after_stop = False

        self._setup_style()
        self._build_ui()
        self._bind_shortcuts()

        self.after(100, self._init_pyttsx3)
        self.after(180, self._load_cfg_into_ui_staged)
        self.after(240, self._refresh_summary)

    def _setup_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("Hint.TLabel", foreground="#444")
        style.configure("Danger.TLabel", foreground="#8a2b2b")
        style.configure("Toolbar.TFrame", padding=8)
        style.configure("Card.TLabelframe", padding=10)
        style.configure("Primary.TButton", padding=(14, 8))
        style.configure("Secondary.TButton", padding=(12, 8))

    def _build_ui(self):
        header = ttk.Frame(self, padding=(14, 12))
        header.pack(fill="x")
        ttk.Label(header, text="Texto → Ler em voz alta / Gerar MP3", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Cole (Ctrl+V). F5 = LER | Ctrl+Enter = MP3 | Ctrl+L = LIMPAR | F6 = PAUSAR | ESC = PARAR",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(6, 0))

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=10)

        self.tab_main = ttk.Frame(nb)
        self.tab_cfg = ttk.Frame(nb)
        nb.add(self.tab_main, text="Editor")
        nb.add(self.tab_cfg, text="Configurações")

        toolbar = ttk.Frame(self.tab_main, style="Toolbar.TFrame")
        toolbar.pack(fill="x")

        self.btn_read = ttk.Button(toolbar, text="LER AGORA (sem MP3)", style="Primary.TButton", command=self.read_now)
        self.btn_read.pack(side="left")

        self.btn_gen = ttk.Button(toolbar, text="GERAR MP3", style="Primary.TButton", command=self.generate_mp3)
        self.btn_gen.pack(side="left", padx=(10, 0))

        self.btn_pause = ttk.Button(toolbar, text="PAUSAR", style="Secondary.TButton", command=self.pause_job)
        self.btn_pause.pack(side="left", padx=(10, 0))

        self.btn_stop = ttk.Button(toolbar, text="PARAR", style="Secondary.TButton", command=self.stop_job)
        self.btn_stop.pack(side="left", padx=(10, 0))

        ttk.Button(toolbar, text="LIMPAR", style="Secondary.TButton", command=self.clear_text).pack(side="left", padx=(10, 0))

        self.var_exclude_first_staged = tk.BooleanVar(value=self.cfg.exclude_first_line)
        ttk.Checkbutton(
            toolbar,
            text="Não narrar a 1ª linha (usar só como nome)",
            variable=self.var_exclude_first_staged,
        ).pack(side="right")

        pane = ttk.Panedwindow(self.tab_main, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        left = ttk.Labelframe(pane, text="Texto (Ctrl+V aqui)", style="Card.TLabelframe")
        pane.add(left, weight=3)

        self.txt = tk.Text(left, wrap="word", font=("Segoe UI", 11), undo=True)
        self.txt.pack(fill="both", expand=True, side="left")

        sb = ttk.Scrollbar(left, command=self.txt.yview)
        sb.pack(fill="y", side="right")
        self.txt.configure(yscrollcommand=sb.set)
        self.txt.bind("<<Modified>>", self._on_text_modified)

        right = ttk.Labelframe(pane, text="Resumo", style="Card.TLabelframe")
        pane.add(right, weight=1)

        self.lbl_name = ttk.Label(right, text="Nome do MP3: (vazio)")
        self.lbl_name.pack(anchor="w")
        self.lbl_len = ttk.Label(right, text="Caracteres: 0")
        self.lbl_len.pack(anchor="w", pady=(6, 0))
        self.lbl_chunks = ttk.Label(right, text="Blocos estimados: 0")
        self.lbl_chunks.pack(anchor="w", pady=(6, 0))

        ttk.Label(right, text="Saída:", style="Hint.TLabel").pack(anchor="w", pady=(14, 0))
        ttk.Label(right, text=str(self.out_dir), wraplength=320).pack(anchor="w")

        self.lbl_engine = ttk.Label(right, text="Leitura: carregando...", style="Hint.TLabel", wraplength=320)
        self.lbl_engine.pack(anchor="w", pady=(14, 0))

        ok_ff, ff_info = ffmpeg_status()
        ff_txt = "FFmpeg: OK" if ok_ff else "FFmpeg: AUSENTE"
        self.lbl_ffmpeg = ttk.Label(
            right,
            text=f"{ff_txt}\n{ff_info}",
            style=("Hint.TLabel" if ok_ff else "Danger.TLabel"),
            wraplength=320,
        )
        self.lbl_ffmpeg.pack(anchor="w", pady=(6, 0))

        # STATUS + PROGRESSO (DENTRO DA ABA EDITOR, abaixo do texto)
        status = ttk.Frame(self.tab_main, padding=(12, 8))
        status.pack(fill="x", padx=12, pady=(0, 10))

        self.var_status = tk.StringVar(value=f"Pronto. Saída: {self.out_dir}")
        ttk.Label(status, textvariable=self.var_status, anchor="w").pack(side="left", fill="x", expand=True)

        self.var_progress = tk.IntVar(value=0)
        self.lbl_pct = ttk.Label(status, text="0%", width=5, anchor="e")
        self.lbl_pct.pack(side="right", padx=(8, 0))

        self.pb = ttk.Progressbar(status, mode="determinate", maximum=100, variable=self.var_progress, length=260)
        self.pb.pack(side="right")

        # ---------------- Config tab ----------------
        cfg = ttk.Frame(self.tab_cfg, padding=14)
        cfg.pack(fill="both", expand=True)

        g1 = ttk.Labelframe(cfg, text="LER AGORA (offline - pyttsx3 / SAPI)", style="Card.TLabelframe")
        g1.pack(fill="x", padx=4, pady=(0, 12))

        row = ttk.Frame(g1)
        row.pack(fill="x")

        ttk.Label(row, text="Voz:").pack(side="left")
        self.var_read_voice_staged = tk.StringVar(value=self.cfg.read_voice_name or "(carregando...)")
        self.cmb_voice = ttk.Combobox(row, textvariable=self.var_read_voice_staged, state="readonly", width=52)
        self.cmb_voice.pack(side="left", padx=(8, 18))

        ttk.Label(row, text="Velocidade:").pack(side="left")
        self.var_read_rate_staged = tk.IntVar(value=int(self.cfg.read_rate))
        self.sld_rate = ttk.Scale(row, from_=120, to=240, orient="horizontal", length=240)
        self.sld_rate.set(self.var_read_rate_staged.get())
        self.sld_rate.pack(side="left", padx=(8, 8))
        ttk.Label(row, textvariable=self.var_read_rate_staged, width=4).pack(side="left")
        self.sld_rate.configure(command=lambda v: self.var_read_rate_staged.set(int(float(v))))

        self.lbl_read_warn = ttk.Label(g1, text="", style="Danger.TLabel")
        self.lbl_read_warn.pack(anchor="w", pady=(8, 0))

        g2 = ttk.Labelframe(cfg, text="GERAR MP3 (Edge TTS recomendado)", style="Card.TLabelframe")
        g2.pack(fill="x", padx=4)

        row2 = ttk.Frame(g2)
        row2.pack(fill="x")

        ttk.Label(row2, text="Backend:").pack(side="left")
        self.var_mp3_backend_staged = tk.StringVar(value=self.cfg.mp3_backend)
        self.cmb_backend = ttk.Combobox(row2, textvariable=self.var_mp3_backend_staged, values=["edge", "gtts"], state="readonly", width=8)
        self.cmb_backend.pack(side="left", padx=(8, 18))

        ttk.Label(row2, text="Voz (Edge):").pack(side="left")
        self.var_mp3_voice_staged = tk.StringVar(value=self.cfg.mp3_voice)
        self.ent_mp3_voice = ttk.Entry(row2, textvariable=self.var_mp3_voice_staged, width=34)
        self.ent_mp3_voice.pack(side="left", padx=(8, 18))

        ttk.Label(row2, text="Rate:").pack(side="left")
        self.var_mp3_rate_staged = tk.StringVar(value=self.cfg.mp3_rate)
        self.ent_mp3_rate = ttk.Entry(row2, textvariable=self.var_mp3_rate_staged, width=7)
        self.ent_mp3_rate.pack(side="left", padx=(8, 10))

        ttk.Label(row2, text="Pitch:").pack(side="left")
        self.var_mp3_pitch_staged = tk.StringVar(value=self.cfg.mp3_pitch)
        self.ent_mp3_pitch = ttk.Entry(row2, textvariable=self.var_mp3_pitch_staged, width=7)
        self.ent_mp3_pitch.pack(side="left", padx=(8, 0))

        row2b = ttk.Frame(g2)
        row2b.pack(fill="x", pady=(10, 0))

        ttk.Label(row2b, text="gTTS (fallback): endpoint:", style="Hint.TLabel").pack(side="left")
        self.var_gt_tld_staged = tk.StringVar(value=self.cfg.gt_tld_label)
        self.cmb_tld = ttk.Combobox(row2b, textvariable=self.var_gt_tld_staged, values=list(self.TLD_OPTIONS.keys()), state="readonly", width=18)
        self.cmb_tld.pack(side="left", padx=(8, 18))

        ttk.Label(row2b, text="Velocidade:", style="Hint.TLabel").pack(side="left")
        self.var_gt_speed_staged = tk.StringVar(value=self.cfg.gt_speed)
        self.cmb_spd = ttk.Combobox(row2b, textvariable=self.var_gt_speed_staged, values=["Normal", "Lenta"], state="readonly", width=10)
        self.cmb_spd.pack(side="left", padx=(8, 0))

        info = "Edge TTS: voz/rate/pitch têm efeito no MP3.\n" \
               "gTTS: só endpoint e slow; não existe pitch/voz real."
        ttk.Label(g2, text=info, style="Hint.TLabel").pack(anchor="w", pady=(10, 0))

        g3 = ttk.Labelframe(cfg, text="Performance (textos grandes)", style="Card.TLabelframe")
        g3.pack(fill="x", padx=4, pady=(12, 0))

        row3 = ttk.Frame(g3)
        row3.pack(fill="x")

        ttk.Label(row3, text="Tamanho do bloco (chars):").pack(side="left")
        self.var_chunk_staged = tk.IntVar(value=int(self.cfg.chunk_max_chars))
        self.sld_chunk = ttk.Scale(row3, from_=500, to=2500, orient="horizontal", length=340)
        self.sld_chunk.set(self.var_chunk_staged.get())
        self.sld_chunk.pack(side="left", padx=(8, 8))
        ttk.Label(row3, textvariable=self.var_chunk_staged, width=5).pack(side="left")
        self.sld_chunk.configure(command=lambda v: self._on_chunk_slide(v))

        actions = ttk.Frame(cfg)
        actions.pack(fill="x", pady=(14, 0))

        self.btn_restart = ttk.Button(actions, text="REINICIAR MOTOR", style="Secondary.TButton", command=self.restart_engine)
        self.btn_restart.pack(side="right")

        self.btn_save = ttk.Button(actions, text="SALVAR CONFIG", style="Primary.TButton", command=self.save_and_apply_config)
        self.btn_save.pack(side="right", padx=(10, 0))

        ttk.Label(actions, text="Você pode mexer. Só vale depois de SALVAR.", style="Hint.TLabel").pack(side="left")

        self.after(50, lambda: self.txt.focus_set())

        self.btn_pause.config(state="disabled")
        self.btn_stop.config(state="disabled")

    def _bind_shortcuts(self):
        self.bind("<F5>", lambda e: self.read_now())
        self.bind("<Control-Return>", lambda e: self.generate_mp3())
        self.bind("<Control-l>", lambda e: self.clear_text())
        self.bind("<Escape>", lambda e: self.stop_job())
        self.bind("<F6>", lambda e: self.pause_job())

    def _on_chunk_slide(self, v):
        self.var_chunk_staged.set(int(float(v)))
        self._refresh_summary()

    # --------- PROGRESSO ----------
    def _set_progress(self, pct: int):
        pct = max(0, min(100, int(pct)))
        self.var_progress.set(pct)
        self.lbl_pct.config(text=f"{pct}%")

    def _reset_progress(self):
        self._set_progress(0)

    # --------- staged <-> applied cfg ----------
    def _load_cfg_into_ui_staged(self):
        self.var_exclude_first_staged.set(bool(self.cfg.exclude_first_line))

        self.var_mp3_backend_staged.set(self.cfg.mp3_backend)
        self.var_mp3_voice_staged.set(self.cfg.mp3_voice)
        self.var_mp3_rate_staged.set(self.cfg.mp3_rate)
        self.var_mp3_pitch_staged.set(self.cfg.mp3_pitch)

        self.var_gt_tld_staged.set(self.cfg.gt_tld_label)
        self.var_gt_speed_staged.set(self.cfg.gt_speed)

        self.var_read_rate_staged.set(int(self.cfg.read_rate))
        self.sld_rate.set(self.var_read_rate_staged.get())

        self.var_chunk_staged.set(int(self.cfg.chunk_max_chars))
        self.sld_chunk.set(self.var_chunk_staged.get())

        if self.cfg.read_voice_name:
            self.var_read_voice_staged.set(self.cfg.read_voice_name)

    def save_and_apply_config(self):
        if self._is_busy:
            return

        self.cfg.exclude_first_line = bool(self.var_exclude_first_staged.get())

        self.cfg.mp3_backend = self.var_mp3_backend_staged.get().strip() or "edge"
        self.cfg.mp3_voice = self.var_mp3_voice_staged.get().strip() or "pt-BR-FranciscaNeural"
        self.cfg.mp3_rate = self.var_mp3_rate_staged.get().strip() or "+0%"
        self.cfg.mp3_pitch = self.var_mp3_pitch_staged.get().strip() or "+0Hz"

        self.cfg.gt_tld_label = self.var_gt_tld_staged.get()
        self.cfg.gt_speed = self.var_gt_speed_staged.get()

        self.cfg.read_rate = int(self.var_read_rate_staged.get())
        self.cfg.read_voice_name = self.var_read_voice_staged.get()
        self.cfg.chunk_max_chars = int(self.var_chunk_staged.get())

        save_config(self.cfg)
        self._reinit_pyttsx3()
        self.var_status.set("Config salva e aplicada.")
        self._refresh_summary()

    def restart_engine(self):
        if self._is_busy:
            return
        self._reinit_pyttsx3()
        self.var_status.set("Motor reiniciado.")

    # --------- pause/stop ----------
    def pause_job(self):
        if not self._is_busy:
            return
        if self._pause_event.is_set():
            self._pause_event.clear()
            self.btn_pause.config(text="CONTINUAR")
            self.var_status.set("Pausado.")
        else:
            self._pause_event.set()
            self.btn_pause.config(text="PAUSAR")
            self.var_status.set("Continuando...")

    def stop_job(self):
        if not self._is_busy:
            return
        self._restart_after_stop = True
        self._stop_event.set()
        self._pause_event.set()
        try:
            if self._current_job == "read" and self._py_engine is not None:
                self._py_engine.stop()
        except Exception:
            pass
        self.var_status.set("Parando... (vai reiniciar o motor)")

    def _reset_job_flags(self):
        self._stop_event.clear()
        self._pause_event.set()
        self.btn_pause.config(text="PAUSAR")

    def _end_job_cleanup(self):
        self._current_job = "idle"
        self._reset_job_flags()
        self.after(0, lambda: self.btn_pause.config(text="PAUSAR"))
        if self._restart_after_stop:
            self._restart_after_stop = False
            self.after(50, self._reinit_pyttsx3)

    # --------- Text handling ----------
    def _on_text_modified(self, _evt=None):
        if self.txt.edit_modified():
            self._refresh_summary()
            self.txt.edit_modified(False)

    def _refresh_summary(self):
        text = self.txt.get("1.0", "end-1c")
        self.lbl_len.config(text=f"Caracteres: {len(text)}")

        title = pick_first_nonempty_line(text) if text.strip() else "(vazio)"
        title = sanitize_filename(title)
        self.lbl_name.config(text=f"Nome do MP3: {title if title else '(vazio)'}")

        body = self._get_text_to_speak(use_applied_cfg=True)
        est = len(smart_split_text(body, max_chars=int(self.cfg.chunk_max_chars))) if body else 0
        self.lbl_chunks.config(text=f"Blocos estimados: {est}")

    def clear_text(self):
        if self._is_busy:
            return
        self.txt.delete("1.0", "end")
        self.var_status.set("Texto limpo.")
        self._refresh_summary()
        self._reset_progress()

    def _get_text_to_speak(self, use_applied_cfg: bool) -> str:
        raw = self.txt.get("1.0", "end-1c").strip()
        if not raw:
            return ""
        exclude = self.cfg.exclude_first_line if use_applied_cfg else bool(self.var_exclude_first_staged.get())
        if exclude:
            lines = raw.splitlines()
            body = "\n".join(lines[1:]).strip()
            return body if body else raw
        return raw

    # --------- Busy lock ----------
    def _set_busy(self, busy: bool, msg: str = ""):
        self._is_busy = busy

        self.btn_gen.config(state="disabled" if busy else "normal")
        self.btn_save.config(state="disabled" if busy else "normal")
        self.btn_restart.config(state="disabled" if busy else "normal")

        read_enabled = (pyttsx3 is not None and self._py_engine is not None and not busy)
        self.btn_read.config(state="normal" if read_enabled else "disabled")

        self.btn_pause.config(state="normal" if busy else "disabled")
        self.btn_stop.config(state="normal" if busy else "disabled")

        cfg_state = "disabled" if busy else "readonly"
        try:
            self.cmb_voice.configure(state=cfg_state)
            self.cmb_backend.configure(state=cfg_state)
            self.cmb_tld.configure(state=cfg_state)
            self.cmb_spd.configure(state=cfg_state)
        except Exception:
            pass

        try:
            self.sld_rate.configure(state="disabled" if busy else "normal")
            self.sld_chunk.configure(state="disabled" if busy else "normal")
        except Exception:
            pass

        try:
            self.ent_mp3_voice.configure(state="disabled" if busy else "normal")
            self.ent_mp3_rate.configure(state="disabled" if busy else "normal")
            self.ent_mp3_pitch.configure(state="disabled" if busy else "normal")
        except Exception:
            pass

        if msg:
            self.var_status.set(msg)

    # --------- pyttsx3 ----------
    def _init_pyttsx3(self):
        if pyttsx3 is None:
            self.lbl_engine.config(text="Leitura: indisponível (instale pyttsx3).")
            self.btn_read.config(state="disabled")
            self.lbl_read_warn.config(text="Instale: pip install pyttsx3")
            return
        self._reinit_pyttsx3()

    def _reinit_pyttsx3(self):
        if pyttsx3 is None:
            return
        try:
            if self._py_engine:
                try:
                    self._py_engine.stop()
                except Exception:
                    pass
                self._py_engine = None

            self._py_engine = pyttsx3.init()
            self._load_voices_into_ui()
            self._apply_pyttsx3_settings_from_cfg()

            self.lbl_engine.config(text="Leitura: OK (offline).")
            self.lbl_read_warn.config(text="")
            self._set_busy(False)
        except Exception as e:
            self._py_engine = None
            self.lbl_engine.config(text="Leitura: falhou ao inicializar/reiniciar.")
            self.btn_read.config(state="disabled")
            self.lbl_read_warn.config(text=f"Erro TTS: {e}")

    def _load_voices_into_ui(self):
        if self._py_engine is None:
            return
        voices = self._py_engine.getProperty("voices") or []
        self._py_voices = []
        names = []
        for v in voices:
            vid = getattr(v, "id", "")
            vname = getattr(v, "name", "") or str(vid)
            names.append(vname)
            self._py_voices.append({"id": vid, "name": vname})

        if names:
            self.cmb_voice["values"] = names
            if self.var_read_voice_staged.get() not in names:
                if self.cfg.read_voice_name in names:
                    self.var_read_voice_staged.set(self.cfg.read_voice_name)
                else:
                    self.var_read_voice_staged.set(names[0])
        else:
            self.var_read_voice_staged.set("(nenhuma voz encontrada)")

    def _apply_pyttsx3_settings_from_cfg(self):
        if self._py_engine is None:
            return
        self._py_engine.setProperty("rate", int(self.cfg.read_rate))
        sel_name = self.cfg.read_voice_name
        voice_id = None
        for v in self._py_voices:
            if v["name"] == sel_name:
                voice_id = v["id"]
                break
        if voice_id:
            self._py_engine.setProperty("voice", voice_id)

    # --------- READ ----------
    def read_now(self):
        if self._is_busy:
            return

        text_to_speak = self._get_text_to_speak(use_applied_cfg=True)
        if not text_to_speak:
            messagebox.showerror("Erro", "Cole um texto na caixa (Ctrl+V).")
            return
        if pyttsx3 is None or self._py_engine is None:
            messagebox.showerror("Indisponível", "Leitura offline não está ativa. Instale: pip install pyttsx3")
            return

        self._reset_job_flags()
        self._current_job = "read"
        self.after(0, self._reset_progress)

        chunks = smart_split_text(text_to_speak, max_chars=max(800, int(self.cfg.chunk_max_chars)))
        total = max(1, len(chunks))

        def worker():
            self.after(0, lambda: self._set_busy(True, f"Lendo... (0/{total})"))
            try:
                self._apply_pyttsx3_settings_from_cfg()
                for idx, chunk in enumerate(chunks, start=1):
                    if self._stop_event.is_set():
                        break
                    self._pause_event.wait()
                    if self._stop_event.is_set():
                        break

                    pct = int((idx / total) * 100)
                    self.after(0, lambda i=idx, p=pct: (self.var_status.set(f"Lendo... ({i}/{total})"), self._set_progress(p)))

                    self._py_engine.say(chunk)
                    self._py_engine.runAndWait()

                if self._stop_event.is_set():
                    self.after(0, lambda: self._set_busy(False, "Leitura cancelada."))
                else:
                    self.after(0, lambda: (self._set_progress(100), self._set_busy(False, "Leitura concluída.")))
            except Exception as e:
                self._py_engine = None
                self.after(0, lambda: self._set_busy(False, f"Falhou: {e}"))
                self.after(0, lambda: messagebox.showerror("Erro ao ler", str(e)))
            finally:
                self._end_job_cleanup()

        threading.Thread(target=worker, daemon=True).start()

    # --------- MP3 ----------
    def generate_mp3(self):
        if self._is_busy:
            return

        raw = self.txt.get("1.0", "end-1c").strip()
        if not raw:
            messagebox.showerror("Erro", "Cole um texto na caixa (Ctrl+V).")
            return

        first_line = pick_first_nonempty_line(raw)
        mp3_path = unique_path(self.out_dir, first_line)

        text_to_speak = self._get_text_to_speak(use_applied_cfg=True)
        if not text_to_speak:
            messagebox.showerror("Erro", "Nada para narrar.")
            return

        self._reset_job_flags()
        self._current_job = "gen"
        self.after(0, self._reset_progress)

        chunks = smart_split_text(text_to_speak, max_chars=int(self.cfg.chunk_max_chars))
        total = max(1, len(chunks))
        ok_ff, _ = ffmpeg_status()

        # snapshot da config aplicada (garante efeito no GERAR)
        backend = (self.cfg.mp3_backend or "edge").strip().lower()
        voice = (self.cfg.mp3_voice or "pt-BR-FranciscaNeural").strip()
        rate = (self.cfg.mp3_rate or "+0%").strip()
        pitch = (self.cfg.mp3_pitch or "+0Hz").strip()

        tld = self.TLD_OPTIONS.get(self.cfg.gt_tld_label, "com.br")
        slow = True if self.cfg.gt_speed == "Lenta" else False

        def worker():
            self.after(0, lambda: self._set_busy(True, f"Gerando MP3... (0/{total})"))
            try:
                with tempfile.TemporaryDirectory() as td:
                    td_path = Path(td)
                    parts: List[Path] = []

                    for idx, chunk in enumerate(chunks, start=1):
                        if self._stop_event.is_set():
                            raise RuntimeError("Operação cancelada pelo usuário.")
                        self._pause_event.wait()
                        if self._stop_event.is_set():
                            raise RuntimeError("Operação cancelada pelo usuário.")

                        gen_pct = int((idx / total) * 95)
                        self.after(0, lambda i=idx, p=gen_pct: (self.var_status.set(f"Gerando... ({i}/{total})"), self._set_progress(p)))

                        part = td_path / f"part_{idx:04d}.mp3"

                        if backend == "edge" and edge_tts is not None:
                            asyncio.run(edge_tts_save_mp3(chunk, part, voice=voice, rate=rate, pitch=pitch))
                        else:
                            # fallback gTTS (não tem pitch/voz real)
                            gTTS(text=chunk, lang="pt", tld=tld, slow=slow).save(str(part))

                        parts.append(part)

                    self.after(0, lambda: (self.var_status.set("Concatenando MP3..."), self._set_progress(95)))
                    if ok_ff:
                        concat_mp3_ffmpeg(parts, mp3_path)
                    else:
                        concat_mp3_naive(parts, mp3_path)

                self.after(0, lambda: self._set_progress(100))
                self.after(0, lambda: self._set_busy(False, f"OK: {mp3_path.name}"))

                extra = f"Arquivo: {mp3_path.name}"
                if backend == "edge" and edge_tts is None:
                    extra += "\nAviso: edge-tts não instalado. Usado gTTS (sem voz/pitch)."
                if not ok_ff:
                    extra += "\nAviso: FFmpeg não encontrado. Concat fallback pode falhar em alguns casos."

                # ao terminar, reinicia motor (como você pediu)
                self.after(0, self._reinit_pyttsx3)
                self.after(0, lambda: DoneDialog(self, self.out_dir, extra=extra))

            except Exception as e:
                self.after(0, lambda: self._set_busy(False, f"Falhou/cancelado: {e}"))
                if "cancelada" not in str(e).lower():
                    self.after(0, lambda: messagebox.showerror("Erro ao gerar MP3", str(e)))
            finally:
                self._end_job_cleanup()

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    App().mainloop()
