"""Comando `fatura`: sobe o servidor local e abre o navegador."""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import webbrowser

HOST = "127.0.0.1"


def free_port(preferred: int) -> int:
    for port in (preferred, 0):
        with socket.socket() as s:
            if sys.platform.startswith("linux"):
                # reabrir logo depois de fechar não cai numa porta aleatória. Só no Linux: lá a opção
                # ainda recusa uma porta em uso; no Windows e no macOS ela pode deixar dividir a porta.
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((HOST, port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise SystemExit("Não foi possível abrir uma porta local.")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="fatura", description="Fatura OCR: capturas da fatura -> CSV (local).")
    ap.add_argument("--port", type=int, default=8765, help="porta local (padrão 8765; se ocupada, escolhe outra)")
    ap.add_argument("--no-browser", action="store_true", help="não abrir o navegador automaticamente")
    args = ap.parse_args(argv)

    import uvicorn
    from .server import create_app

    port = free_port(args.port)
    url = f"http://{HOST}:{port}/"
    print(f"  Endereço do Fatura OCR: {url}  (se o navegador não abrir, copie e cole)")
    print("  Para encerrar: feche esta janela ou aperte Ctrl+C.\n")
    if not args.no_browser:
        threading.Timer(1.2, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(), host=HOST, port=port, log_level="warning")


if __name__ == "__main__":
    main()
