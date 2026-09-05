#!/usr/bin/env python3
"""CLI de administración para Cazador API.

Uso:
    python admin.py list                    # listar usuarios
    python admin.py add <github_id> <login> # añadir usuario autorizado
    python admin.py delete <github_id>      # eliminar usuario
    python admin.py limit <github_id> <N>   # max busquedas/dia
    python admin.py stats                   # estadisticas de uso
    python admin.py jobs                    # resumen de ofertas

Requiere: D1 local (default) o --remote para D1 remoto.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

DB = "cazador"
WRANGLER = ["npx.cmd", "wrangler", "d1", "execute", DB]
CHUNKS_DIR = Path(__file__).parent / "seed"


def run_sql(sql: str, remote: bool = False) -> dict:
    cmd = WRANGLER.copy()
    if remote:
        cmd.append("--remote")
    else:
        cmd.append("--local")
    cmd.extend(["--command", sql])
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=Path(__file__).parent)
    if result.returncode != 0:
        print(f"ERROR: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    # Parse the JSON output from wrangler
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("[") or line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    # Try to find JSON in the output
    output = result.stdout
    start = output.find("[")
    if start == -1:
        start = output.find("{")
    if start >= 0:
        try:
            return json.loads(output[start:])
        except json.JSONDecodeError:
            pass
    return {"results": []}


def cmd_list(args):
    data = run_sql(
        "SELECT u.id, u.github_id, u.login, u.name, u.created_at, "
        "(SELECT count(*) FROM profiles WHERE user_id=u.id) as profiles, "
        "(SELECT count(*) FROM search_log WHERE user_id=u.id) as searches "
        "FROM users u ORDER BY u.id",
        remote=args.remote,
    )
    rows = data.get("results", [data]) if isinstance(data, dict) else data
    if not rows:
        print("No hay usuarios registrados.")
        return
    print(f"{'ID':>4} {'GitHub ID':>14} {'Login':<20} {'Nombre':<20} {'Perfiles':>8} {'Busquedas':>10}")
    print("-" * 85)
    for r in rows:
        print(f"{r.get('id', ''):>4} {r.get('github_id', ''):>14} {r.get('login', ''):<20} {r.get('name', ''):<20} {r.get('profiles', 0):>8} {r.get('searches', 0):>10}")


def cmd_add(args):
    # Check if user exists
    existing = run_sql(
        f"SELECT id FROM users WHERE github_id = {args.github_id}",
        remote=args.remote,
    )
    rows = existing.get("results", [existing]) if isinstance(existing, dict) else existing
    if rows and any(r.get("id") for r in rows if isinstance(r, dict)):
        print(f"Usuario github_id={args.github_id} ya existe.")
        return

    run_sql(
        f"INSERT INTO users (github_id, login) VALUES ({args.github_id}, '{args.login}')",
        remote=args.remote,
    )
    # Get the new user ID
    data = run_sql(
        f"SELECT id FROM users WHERE github_id = {args.github_id}",
        remote=args.remote,
    )
    rows = data.get("results", [data]) if isinstance(data, dict) else data
    user_id = None
    for r in rows:
        if isinstance(r, dict) and r.get("id"):
            user_id = r["id"]
            break

    if user_id:
        # Create default profile
        profile_sql = (
            "INSERT INTO profiles (user_id, name, is_default) VALUES "
            f"({user_id}, 'default', 1)"
        )
        run_sql(profile_sql, remote=args.remote)
        print(f"Usuario creado: id={user_id}, github_id={args.github_id}, login={args.login}")
    else:
        print(f"Usuario creado pero no se pudo obtener el ID.")


def cmd_delete(args):
    data = run_sql(
        f"SELECT id FROM users WHERE github_id = {args.github_id}",
        remote=args.remote,
    )
    rows = data.get("results", [data]) if isinstance(data, dict) else data
    user_id = None
    for r in rows:
        if isinstance(r, dict) and r.get("id"):
            user_id = r["id"]
            break

    if not user_id:
        print(f"No se encontro usuario con github_id={args.github_id}")
        return

    run_sql(f"DELETE FROM profiles WHERE user_id = {user_id}", remote=args.remote)
    run_sql(f"DELETE FROM search_log WHERE user_id = {user_id}", remote=args.remote)
    run_sql(f"DELETE FROM users WHERE id = {user_id}", remote=args.remote)
    print(f"Usuario eliminado: github_id={args.github_id}, login (id={user_id})")


def cmd_stats(args):
    data = run_sql(
        "SELECT "
        "(SELECT count(*) FROM users) as total_users, "
        "(SELECT count(*) FROM profiles) as total_profiles, "
        "(SELECT count(*) FROM jobs) as total_jobs, "
        "(SELECT count(*) FROM jobs WHERE match >= 40) as jobs_over40, "
        "(SELECT max(match) FROM jobs) as max_match",
        remote=args.remote,
    )
    rows = data.get("results", [data]) if isinstance(data, dict) else data
    if rows:
        r = rows[0] if isinstance(rows, list) else rows
        if isinstance(r, dict):
            print(f"Usuarios:      {r.get('total_users', 0)}")
            print(f"Perfiles:      {r.get('total_profiles', 0)}")
            print(f"Ofertas:       {r.get('total_jobs', 0)}")
            print(f"Ofertas >=40:  {r.get('jobs_over40', 0)}")
            print(f"Match max:     {r.get('max_match', 0)}")
            return
    print("No se pudieron obtener estadisticas.")


def cmd_jobs(args):
    data = run_sql(
        "SELECT source, count(*) as c FROM jobs GROUP BY source ORDER BY c DESC",
        remote=args.remote,
    )
    rows = data.get("results", [data]) if isinstance(data, dict) else data
    if not rows:
        print("No hay ofertas.")
        return
    print(f"{'Fuente':<30} {'Cantidad':>10}")
    print("-" * 42)
    total = 0
    for r in rows:
        if isinstance(r, dict):
            print(f"{r.get('source', '?'):<30} {r.get('c', 0):>10}")
            total += r.get("c", 0)
    print("-" * 42)
    print(f"{'TOTAL':<30} {total:>10}")


def main():
    parser = argparse.ArgumentParser(description="Admin CLI para Cazador API")
    parser.add_argument("--remote", action="store_true", help="Usar D1 remoto en vez de local")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="Listar usuarios")
    sub.add_parser("stats", help="Estadisticas generales")
    sub.add_parser("jobs", help="Resumen de ofertas por fuente")

    add_p = sub.add_parser("add", help="Anadir usuario autorizado")
    add_p.add_argument("github_id", type=int, help="GitHub user ID numerico")
    add_p.add_argument("login", help="GitHub login (nombre de usuario)")

    del_p = sub.add_parser("delete", help="Eliminar usuario")
    del_p.add_argument("github_id", type=int, help="GitHub user ID numerico")

    args = parser.parse_args()
    if args.command == "list":
        cmd_list(args)
    elif args.command == "add":
        cmd_add(args)
    elif args.command == "delete":
        cmd_delete(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "jobs":
        cmd_jobs(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
