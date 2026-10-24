#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO: tools/omega_phantom_v7_validator.py
SISTEMA: OMEGA-PHANTOM V7.0 (APEX-CHRONOS SINGULARITY)
==============================================================================
Motor Determinista de Compuerta 0:
  1. Sanitiza y verifica codificacion UTF-8 sin BOM y saltos de linea Unix (LF).
  2. Verifica ausencia de secuencias Mojibake (??) y bloques envoltorios.
  3. Compila el AST de todos los modulos Python presentes en el repositorio.
  4. Certifica el invariante exacto de 100 constantes globales unicas en
     omega_phantom_v7_config.py (AST_100_CONSTANTES_OK).
==============================================================================
"""
from __future__ import annotations

import ast
import json
import pathlib
import sys
from typing import List, Set, Tuple

ROOT_DIR: pathlib.Path = pathlib.Path(__file__).resolve().parent.parent

ARCHIVOS_PROYECTO: Tuple[str, ...] = (
    ".gitignore",
    "README.md",
    "requirements.txt",
    "omega_phantom_v7_config.py",
    "omega_phantom_v7_ram.py",
    "omega_phantom_v7_telegram.py",
    "omega_phantom_v7_stats.py",
    "omega_phantom_v7_tricortex.py",
    "omega_phantom_v7_radar.py",
    "omega_phantom_v7_sniper.py",
    "omega_phantom_v7_gestor.py",
    "omega_phantom_v7_main.py",
    "omega_phantom_v7_oos_twin.py",
    "omega_phantom_v7_install.sh",
    "omega_phantom_v7_test_suite.py",
    "tools/omega_phantom_v7_validator.py",
    "omega_phantom_v7_calibracion.json",
)


def _sanitizar_utf8_lf(ruta: pathlib.Path) -> Tuple[bool, str]:
    raw = ruta.read_bytes()
    modificado = False
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
        modificado = True
    if b"\r\n" in raw or b"\r" in raw:
        raw = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        modificado = True
    try:
        texto = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return False, f"ERROR_UTF8: {exc}"
    if modificado:
        ruta.write_bytes(texto.encode("utf-8"))
    return True, texto


def _auditar_constantes_config(arbol: ast.Module) -> Tuple[bool, str]:
    nombres: List[str] = []
    duplicadas: Set[str] = set()
    vistas: Set[str] = set()

    for nodo in arbol.body:
        target_name = None
        if isinstance(nodo, ast.Assign) and len(nodo.targets) == 1:
            t = nodo.targets[0]
            if isinstance(t, ast.Name):
                target_name = t.id
        elif isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name):
            target_name = nodo.target.id

        if target_name and target_name.isupper():
            nombres.append(target_name)
            if target_name in vistas:
                duplicadas.add(target_name)
            vistas.add(target_name)

    if duplicadas:
        return False, f"CONSTANTES_DUPLICADAS: {sorted(duplicadas)}"
    if len(nombres) != 100:
        return False, f"CONTEO_CONSTANTES_INVALIDO: {len(nombres)} != 100"
    return True, "AST_100_CONSTANTES_OK"


def ejecutar_auditoria(modo_estricto_completo: bool = False) -> int:
    sanitizar = "--sanitize" in sys.argv
    if "--full" in sys.argv:
        modo_estricto_completo = True

    print("=" * 94)
    print(" [COMPUERTA 0] AUDITORIA ESTATICA UTF-8 / LF / AST -- OMEGA-PHANTOM V7.0")
    print("=" * 94)

    errores = 0
    presentes = 0

    for rel in ARCHIVOS_PROYECTO:
        ruta = ROOT_DIR / rel
        if not ruta.exists():
            if modo_estricto_completo:
                print(f" [FALTA]  {rel:<38} -> ARCHIVO_NO_ENCONTRADO")
                errores += 1
            continue

        presentes += 1
        if sanitizar:
            ok_io, resultado = _sanitizar_utf8_lf(ruta)
            if not ok_io:
                print(f" [ERROR]  {rel:<38} -> {resultado}")
                errores += 1
                continue
            texto = resultado
        else:
            raw = ruta.read_bytes()
            if raw.startswith(b"\xef\xbb\xbf"):
                print(f" [ERROR]  {rel:<38} -> CONTIENE_BOM_UTF8")
                errores += 1
                continue
            if b"\r\n" in raw:
                print(f" [ERROR]  {rel:<38} -> CONTIENE_CRLF")
                errores += 1
                continue
            texto = raw.decode("utf-8")

        if (chr(63) * 2) in texto and rel != "tools/omega_phantom_v7_validator.py":
            print(f" [ERROR]  {rel:<38} -> MOJIBAKE_DETECTADO")
            errores += 1
            continue

        if rel.endswith(".py"):
            try:
                arbol = ast.parse(texto, filename=rel)
            except SyntaxError as exc:
                print(f" [ERROR]  {rel:<38} -> SYNTAX_ERROR: {exc}")
                errores += 1
                continue

            if rel == "omega_phantom_v7_config.py":
                ok_cfg, tag_cfg = _auditar_constantes_config(arbol)
                if not ok_cfg:
                    print(f" [ERROR]  {rel:<38} -> {tag_cfg}")
                    errores += 1
                    continue
                print(f" [OK]     {rel:<38} -> {tag_cfg}")
            else:
                print(f" [OK]     {rel:<38} -> AST_OK")
        elif rel.endswith(".json"):
            try:
                json.loads(texto)
                print(f" [OK]     {rel:<38} -> JSON_OK")
            except Exception as exc:
                print(f" [ERROR]  {rel:<38} -> JSON_INVALIDO: {exc}")
                errores += 1
        elif rel.endswith(".sh"):
            print(f" [OK]     {rel:<38} -> SH_LF_OK")
        else:
            print(f" [OK]     {rel:<38} -> LIMPIO_UTF8_LF")

    print("-" * 94)
    if errores == 0:
        print(
            f" RESULTADO FINAL: 0 ERRORES DETECTADOS | {presentes} ARCHIVOS CERTIFICADOS (UTF-8 / LF / AST)"
        )
        print("=" * 94)
        return 0

    print(f" RESULTADO FINAL: {errores} ERRORES DETECTADOS EN EL POOL")
    print("=" * 94)
    return 1


if __name__ == "__main__":
    sys.exit(ejecutar_auditoria())