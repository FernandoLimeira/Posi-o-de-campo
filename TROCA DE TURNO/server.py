import argparse
from socketserver import ThreadingMixIn
from wsgiref.simple_server import ServerHandler, WSGIServer, make_server

from backend.app import application
from backend.database import has_admin

ServerHandler.server_software = "PosicaoCampo"


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    parser = argparse.ArgumentParser(description="Servidor da aplicação Posição de Campo")
    parser.add_argument("--host", default="0.0.0.0", help="Endereço do servidor")
    parser.add_argument("--port", type=int, default=8000, help="Porta do servidor")
    args = parser.parse_args()

    display_host = "localhost" if args.host in {"0.0.0.0", "127.0.0.1"} else args.host
    print("=" * 52)
    print(" POSIÇÃO DE CAMPO - SERVIDOR")
    print("=" * 52)
    print(f"Acesso local: http://{display_host}:{args.port}")
    if args.host == "0.0.0.0":
        print("Rede local: use http://IP-DESTE-COMPUTADOR:%d" % args.port)
    print("Backups automáticos: data/backups/")
    if not has_admin():
        print()
        print("ATENÇÃO: nenhum Administrador está configurado.")
        print("Execute criar-admin.bat neste computador antes do primeiro login.")
    print("Pressione Ctrl+C para encerrar.")
    print()

    with make_server(
        args.host,
        args.port,
        application,
        server_class=ThreadingWSGIServer,
    ) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor encerrado.")


if __name__ == "__main__":
    main()
