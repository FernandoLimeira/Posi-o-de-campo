import argparse
import getpass

from .database import create_or_update_admin, init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Cria ou redefine a conta Administrador da Posição de Campo")
    parser.add_argument("--name", help="Nome do Administrador")
    args = parser.parse_args()

    init_db()
    name = (args.name or input("Nome do Administrador [admin]: ").strip() or "admin").strip()
    password = getpass.getpass("Senha: ")
    if not password:
        raise SystemExit("A senha não pode ficar vazia.")
    confirmation = getpass.getpass("Confirme a senha: ")
    if password != confirmation:
        raise SystemExit("As senhas não conferem.")

    admin = create_or_update_admin(name, password)
    print()
    print(f"Administrador configurado: {admin['name']}")
    print("A conta está ativa e qualquer sessão anterior desse usuário foi encerrada.")


if __name__ == "__main__":
    main()
