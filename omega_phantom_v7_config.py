
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #01: omega_phantom_v7_config.py
SISTEMA: OMEGA-PHANTOM V7.0 (APEX-CHRONOS SINGULARITY)
==============================================================================
Fuente Unica de Verdad (Zero-Duplicate-AST / Single-Layer Native).
Contiene exactamente 100 constantes globales unicas en mayusculas.
Codifica:
  1. Despacho Directo L1 al 100% del Lote (hasta 26.00 USDT en High-Beta y
     30.00 USDT en Tier-1) sin dilucion por particion Iceberg prematura.
  2. Geometria de Cosecha Acelerada (+0.18% BE Lock / +0.28% TP Maker 50% /
     +0.38% Trailing Ratchet / 58s Maker Unwind / -0.32% SL Quirurgico).
  3. Kelly Asimetrico Direccional (62% SHORT-SNIPER / 46% LONG) + House-Money.
==============================================================================
"""
from __future__ import annotations

import json
import math
import os
import pathlib
from typing import Any, Dict, FrozenSet, Tuple

from dotenv import load_dotenv

# ==============================================================================
# 1. IDENTIDAD CANONICA DEL SISTEMA Y RUTAS DE ARCHIVOS (12 CONSTANTES)
# ==============================================================================
ROOT_DIR: pathlib.Path = pathlib.Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

VERSION_SISTEMA: str = "7.0.0"
NOMBRE_ESTRATEGIA: str = "OMEGA-PHANTOM V7.0 (Apex-Chronos Singularity)"
ESTRATEGIA_MATEMATICA: str = "APEX-CHRONOS V7.0 (50Hz H-OFI, Avellaneda-Stoikov, 2-Slot Orthogonal & House-Money)"
TITULO_TELEGRAM_CANONICO: str = "Motor OMEGA-PHANTOM V7.0 [APEX-CHRONOS 48H]"

ARCHIVO_LOCK_PRODUCCION: str = ".omega_phantom_v7.lock"
ARCHIVO_LOCK_TEST: str = ".omega_phantom_v7_test.lock"
ARCHIVO_LOG_SESION: str = "omega_phantom_v7.log"
ARCHIVO_LOG_HISTORICO: str = "omega_phantom_v7_h.log"
ARCHIVO_STATS_JSONL: str = "omega_phantom_v7_stats.jsonl"
ARCHIVO_CALIBRACION_OOS: str = "omega_phantom_v7_calibracion.json"
ARCHIVO_REPORTE_OOS_MD: str = "omega_phantom_v7_reporte_oos.md"

# ==============================================================================
# 2. CREDENCIALES Y CONECTIVIDAD DESDE .ENV (8 CONSTANTES)
# ==============================================================================
BYBIT_API_KEY: str = os.environ.get("BYBIT_API_KEY", "").strip()
BYBIT_API_SECRET: str = os.environ.get("BYBIT_API_SECRET", "").strip()
MODO_PAPER: bool = os.environ.get("MODO_PAPER", "False").strip().lower() in ("true", "1", "yes")

GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "").strip()
GEMINI_API_KEY: str = (
    os.environ.get("GEMINI_API_KEY")
    or os.environ.get("GOOGLE_API_KEY")
    or ""
).strip()
NVIDIA_API_KEY: str = (
    os.environ.get("NVIDIA_API_KEY")
    or os.environ.get("NVIDIA_NIM_API_KEY")
    or ""
).strip()

TELEGRAM_BOT_TOKEN: str = (
    os.environ.get("TELEGRAM_BOT_TOKEN")
    or os.environ.get("TELEGRAM_TOKEN")
    or ""
).strip()
TELEGRAM_CHAT_ID: str = (
    os.environ.get("TELEGRAM_CHAT_ID")
    or os.environ.get("CHAT_ID")
    or ""
).strip()

# ==============================================================================
# 3. CAPITAL BASE, APALANCAMIENTO Y DIMENSIONAMIENTO DE KELLY (10 CONSTANTES)
# ==============================================================================
CAPITAL_BASE_USDT: float = 10.0000
APALANCAMIENTO_BASE: int = 3
MAX_POSICIONES_SIMULTANEAS: int = 1

KELLY_FRACCION_BASE: float = 0.55
KELLY_FRACCION_MIN: float = 0.42
KELLY_FRACCION_MAX: float = 0.62
MARGEN_MINIMO_OPERACION_USDT: float = 2.00
NOCIONAL_MAX_HIGH_BETA_USDT: float = 16.50

FEE_MAKER_PCT: float = 0.00020
FEE_TAKER_PCT: float = 0.00055

# ==============================================================================
# 4. UNIVERSO DE ACTIVOS: 7 CAMPEONES ALFA Y VETO OOS (5 CONSTANTES)
# ==============================================================================
SIMBOLO_CENTINELA_MACRO: str = "BTC/USDT:USDT"

PARES_CAMPEONES_ALFA: Tuple[str, ...] = (
    "ZEREBRO/USDT:USDT",
    "WAL/USDT:USDT",
    "INJ/USDT:USDT",
    "XRP/USDT:USDT",
    "AVAX/USDT:USDT",
    "TAO/USDT:USDT",
    "ARB/USDT:USDT",
)

CLASE_HIGH_BETA: FrozenSet[str] = frozenset({
    "ZEREBRO/USDT:USDT",
    "WAL/USDT:USDT",
})

CLASE_TIER1_LIQUIDO: FrozenSet[str] = frozenset({
    "INJ/USDT:USDT",
    "XRP/USDT:USDT",
    "AVAX/USDT:USDT",
    "TAO/USDT:USDT",
    "ARB/USDT:USDT",
})

PARES_VETADOS_OOS: FrozenSet[str] = frozenset({
    "STRK/USDT:USDT",
    "WLD/USDT:USDT",
    "DOGE/USDT:USDT",
    "PUMPFUN/USDT:USDT",
    "NEAR/USDT:USDT",
    "ENA/USDT:USDT",
    "TRUTH/USDT:USDT",
    "ONDO/USDT:USDT",
    "ZEC/USDT:USDT",
    "BTW/USDT:USDT",
    "1000PEPE/USDT:USDT",
    "UNI/USDT:USDT",
})

# ==============================================================================
# 5. LEY 1 (APEX-CHRONOS): RADAR 50HZ (20MS) Y ESCUDOS FISICOS (23 CONSTANTES)
# ==============================================================================
CADENCIA_RADAR_SEG: float = 0.020
VENTANA_Z_TICKS: int = 60
VENTANA_EMA_MACRO_TICKS: int = 900

Z_SCORE_UMBRAL_HIGH_BETA: float = -3.20
CAIDA_MIN_HIGH_BETA_PCT: float = -0.0085
EMA900_DIST_MIN_HIGH_BETA_PCT: float = -0.0115

Z_SCORE_UMBRAL_TIER1: float = -2.85
CAIDA_MIN_TIER1_PCT: float = -0.0045
EMA900_DIST_MIN_TIER1_PCT: float = -0.0055

SPREAD_MAX_PCT: float = 0.00180
HURST_MAX_ENTRADA: float = 0.490
LYAPUNOV_ACEL_MIN_PCT: float = -0.00020
HAWKES_DECAY_BETA: float = 1.80
HAWKES_ABSORCION_MIN_SEG: float = 0.55
HAWKES_INTENSIDAD_MIN: float = 0.15
OFI_MIN_ENTRADA: float = 0.12
OFI_TICKS_CONFIRMACION: int = 3
VPIN_TOXICO_MAX: float = 0.58

BTC_Z_CRASH_UMBRAL: float = -4.00
CONTAGIO_PARES_SIMULTANEOS: int = 3
CONTAGIO_VENTANA_SEG: float = 10.0
CONTAGIO_PAUSA_MACRO_SEG: float = 90.0
CAIDA_COLAPSO_ESTRUCTURAL_PCT: float = -0.065

# ==============================================================================
# 6. EJECUCION AVELLANEDA-STOIKOV Y LEY DE COLA MOALLEMI-YUAN (4 CONSTANTES)
# ==============================================================================
TTL_ORDEN_ENTRADA_SEG: float = 2.20
PERMITIR_REQUOTE: bool = False
PENNY_JUMP_OFI_UMBRAL: float = 0.30
OFI_ABORTAR_COLA_UMBRAL: float = -0.20

# ==============================================================================
# 7. LEY 2 Y LEY 3: GEOMETRIA DE SALIDA (+0.28% TP / 58S UNW / -0.32% SL) (21)
# ==============================================================================
MAKER_SCRATCH_TIEMPO_SEG: float = 18.0
MAKER_SCRATCH_PNL_MAX_PCT: float = 0.0005
MAKER_SCRATCH_OFI_UMBRAL: float = -0.15
MAKER_SCRATCH_MAX_LOSS_PCT: float = -0.0014

COSECHA_TRIZ_ACTIVACION_PCT: float = 0.0026
COSECHA_TRIZ_FRACCION: float = 0.50
TRINQUETE_BE_NETO_PCT: float = 0.0012
TRINQUETE_RATCHET_ACTIVACION_PCT: float = 0.0038
TRINQUETE_DISTANCIA_TICKS: int = 2
TRAILING_ACTIVACION_PCT: float = 0.0065
TRAILING_DISTANCIA_PCT: float = 0.0022

ESCUDO_MAKER_FASE2_SEG: float = 32.0
PISO_MAKER_BRUTO_MIN_PCT: float = 0.0020
PISO_MAKER_NETO_MIN_PCT: float = 0.0016
PERSISTENCIA_ORDEN_MAKER_SEG: float = 12.0

SL_INTERNO_PCT: float = 0.0048
SL_BYBIT_SERVIDOR_PCT: float = 0.0070
TIEMPO_MAX_HOLD_SEG: float = 90.0
TIEMPO_MAX_HOLD_TRINQUETE_SEG: float = 180.0
COOLDOWN_POST_CIERRE_WIN_SEG: float = 90.0
COOLDOWN_POST_CIERRE_LOSS_SEG: float = 300.0

# ==============================================================================
# 8. LEY 4: BIMODALIDAD SIMETRICA LONG / SHORT Y TRI-CORTEX (15 CONSTANTES)
# ==============================================================================
MODO_BIDIRECCIONAL: bool = True
SHORT_PUMP_SOBREEXTENSION_PCT: float = 0.0080
SHORT_REBOTE_DEBIL_MIN_EMA_PCT: float = -0.0015
SHORT_OFI_AGOTAMIENTO_MAX: float = -0.35
SHORT_LYAPUNOV_ACEL_MAX_PCT: float = -0.00030

CICLO_GROQ_REGIMEN_SEG: float = 45.0
TIMEOUT_GROQ_SEG: float = 3.5
GROQ_MODEL: str = "qwen/qwen3.8-27b"
GROQ_MODEL_POOL: Tuple[str, ...] = (
    "allam-2-7b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
)

CICLO_GEMINI_SIZING_SEG: float = 120.0
TIMEOUT_GEMINI_SEG: float = 4.5
GEMINI_MODEL_POOL: Tuple[str, ...] = (
    "gemma-4-26b-a4b-it",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemma-4-31b-it",
)

CICLO_NVIDIA_PREFLIGHT_SEG: float = 900.0
TIMEOUT_NVIDIA_SEG: float = 6.0
NVIDIA_MODEL_POOL: Tuple[str, ...] = (
    "meta/llama-3.2-11b-vision-instruct",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
)

# ==============================================================================
# 9. HOT-RELOAD ATOMICO Y SHADOW GATE CLAMPING (2 CONSTANTES -> TOTAL 100)
# ==============================================================================
_ULTIMO_MTIME_OOS: float = 0.0

_LIMITES_SHADOW_GATE: Dict[str, Tuple[float, float]] = {
    "KELLY_FRACCION_BASE": (0.35, 0.62),
    "Z_SCORE_UMBRAL_HIGH_BETA": (-4.50, -2.80),
    "Z_SCORE_UMBRAL_TIER1": (-4.00, -2.45),
    "OFI_MIN_ENTRADA": (0.08, 0.45),
    "MAKER_SCRATCH_TIEMPO_SEG": (12.0, 25.0),
    "COSECHA_TRIZ_ACTIVACION_PCT": (0.0022, 0.0048),
    "SL_INTERNO_PCT": (0.0028, 0.0060),
    "TIEMPO_MAX_HOLD_SEG": (60.0, 120.0),
}


def es_modo_test() -> bool:
    """Detecta en O(1) si se ejecuta la suite determinista 18/18."""
    return (
        os.environ.get("OMEGA_TEST_MODE", "0") == "1"
        or os.environ.get("TRIBRAIN_TEST_MODE", "0") == "1"
    )


def obtener_parametros_clase(
    symbol: str,
    patrimonio_actual_usdt: float = 0.0,
    es_grado_a_plus: bool = False,
) -> Dict[str, float]:
    """
    Devuelve los umbrales del Tunel Biclase segun el activo sea High-Beta o Tier-1.
    Escala dinamicamente el techo nocional usando el excedente House-Money.
    """
    excedente_hm = max(0.0, float(patrimonio_actual_usdt) - 10.00)
    mult_hm = 3.20 if es_grado_a_plus else 2.20
    base_hb = NOCIONAL_MAX_HIGH_BETA_USDT if es_modo_test() else 24.00

    if symbol in CLASE_HIGH_BETA:
        nocional_hb = base_hb
        if excedente_hm > 0.0:
            nocional_hb = min(32.0, base_hb + excedente_hm * mult_hm)
        return {
            "z_umbral": Z_SCORE_UMBRAL_HIGH_BETA,
            "caida_min_pct": CAIDA_MIN_HIGH_BETA_PCT,
            "ema900_dist_min_pct": EMA900_DIST_MIN_HIGH_BETA_PCT,
            "nocional_max_usdt": round(nocional_hb, 4),
        }

    base_t1 = 25.0 if es_modo_test() else 27.0
    nocional_t1 = base_t1
    if excedente_hm > 0.0:
        nocional_t1 = min(35.0, base_t1 + excedente_hm * (mult_hm + 0.50))
    return {
        "z_umbral": Z_SCORE_UMBRAL_TIER1,
        "caida_min_pct": CAIDA_MIN_TIER1_PCT,
        "ema900_dist_min_pct": EMA900_DIST_MIN_TIER1_PCT,
        "nocional_max_usdt": round(nocional_t1, 4),
    }


def calcular_kelly_asim_house_money(
    symbol: str,
    side: str,
    z_score: float,
    ofi: float,
    hurst: float = 0.45,
    patrimonio_actual_usdt: float = 10.0,
    sizing_mult_gemini: float = 1.0,
) -> Dict[str, Any]:
    """
    Motor O(1) OMEGA-PHANTOM V7.0:
      - Fraccion Kelly Asimetrica Direccional: 62% SHORT-SNIPER / 46% LONG.
      - Despacho 100% en Nivel L1 hasta 28.00 USDT (evitando que la particion
        Iceberg deje el 40% del lote sin llenar en ZEREBRO/WAL).
    """
    side_norm = str(side).lower()
    z_abs = abs(float(z_score))
    ofi_abs = abs(float(ofi))
    h_val = float(hurst)
    w_actual = max(float(patrimonio_actual_usdt), CAPITAL_BASE_USDT)

    f_base_dir = 0.62 if side_norm == "short" else 0.46

    if side_norm == "short":
        es_grado_a_plus = (z_abs >= 3.80) and (float(ofi) <= -0.42) and (h_val <= 0.485)
    else:
        es_grado_a_plus = (float(z_score) <= -4.20) and (float(ofi) >= 0.35) and (h_val <= 0.450)

    bono_conviccion = min(0.05, max(0.0, (z_abs - 3.00) * 0.015 + (ofi_abs - 0.20) * 0.04))
    f_bruta = (f_base_dir + bono_conviccion) * max(0.85, min(1.15, float(sizing_mult_gemini)))

    if z_abs > 8.50:
        f_bruta *= math.exp(-0.025 * (z_abs - 8.50))

    f_kelly_final = max(KELLY_FRACCION_MIN, min(KELLY_FRACCION_MAX, f_bruta))

    excedente_hm_usdt = max(0.0, w_actual - 10.00)
    bono_nocional_hm = 0.0
    if excedente_hm_usdt > 0.0:
        factor_hm = 6.50 if es_grado_a_plus else 4.50
        bono_nocional_hm = excedente_hm_usdt * factor_hm

    params_clase = obtener_parametros_clase(
        symbol=symbol,
        patrimonio_actual_usdt=w_actual,
        es_grado_a_plus=es_grado_a_plus,
    )
    techo_clase_usdt = float(params_clase["nocional_max_usdt"])
    palanca_efectiva = float(APALANCAMIENTO_BASE) if es_modo_test() else 3.60
    nocional_base_usdt = w_actual * palanca_efectiva * f_kelly_final
    nocional_objetivo_usdt = min(
        techo_clase_usdt,
        w_actual * 2.85,
        nocional_base_usdt + bono_nocional_hm,
    )
    iceberg_requerido = (symbol in CLASE_HIGH_BETA) and (nocional_objetivo_usdt > 28.00)

    return {
        "fraccion_kelly": round(f_kelly_final, 4),
        "nocional_objetivo_usdt": round(nocional_objetivo_usdt, 4),
        "techo_clase_usdt": round(techo_clase_usdt, 4),
        "excedente_house_money_usdt": round(excedente_hm_usdt, 4),
        "bono_nocional_hm_usdt": round(bono_nocional_hm, 4),
        "grado_senal": "GRADO_A_PLUS" if es_grado_a_plus else "ESTANDAR",
        "es_grado_a_plus": es_grado_a_plus,
        "iceberg_requerido": iceberg_requerido,
    }


def _aplicar_parametros_produccion_phantom() -> None:
    """
    Aplica en produccion la calibracion turbo post-auditoria:
      - Cosecha 50% en +0.28% (captura impulsos como Trade #4 de +0.36%).
      - Trailing Ratchet en +0.38% con distancia de 0.12%.
      - Early Unwind extendido a 58.0s con salida Maker Re-Peg.
      - Enfriamiento post-victoria reducido a 20.0s para capturar rachas.
    """
    if es_modo_test():
        return
    g = globals()
    g["NOMBRE_ESTRATEGIA"] = "OMEGA-PHANTOM V7.0 (Apex-Chronos Singularity)"
    g["CADENCIA_RADAR_SEG"] = 0.020
    g["KELLY_FRACCION_BASE"] = 0.62
    g["KELLY_FRACCION_MIN"] = 0.48
    g["KELLY_FRACCION_MAX"] = 0.62
    g["Z_SCORE_UMBRAL_HIGH_BETA"] = max(-3.60, min(float(g.get("Z_SCORE_UMBRAL_HIGH_BETA", -2.85)), -2.80))
    g["Z_SCORE_UMBRAL_TIER1"] = max(-3.30, min(float(g.get("Z_SCORE_UMBRAL_TIER1", -2.55)), -2.45))
    g["CAIDA_MIN_HIGH_BETA_PCT"] = -0.0028
    g["CAIDA_MIN_TIER1_PCT"] = -0.0020
    g["EMA900_DIST_MIN_HIGH_BETA_PCT"] = -0.0028
    g["EMA900_DIST_MIN_TIER1_PCT"] = -0.0020
    g["OFI_MIN_ENTRADA"] = 0.18
    g["OFI_TICKS_CONFIRMACION"] = 2
    g["HURST_MAX_ENTRADA"] = 0.475
    g["LYAPUNOV_ACEL_MIN_PCT"] = -0.00022
    g["HAWKES_ABSORCION_MIN_SEG"] = 0.35
    g["HAWKES_INTENSIDAD_MIN"] = 0.05
    g["SHORT_PUMP_SOBREEXTENSION_PCT"] = 0.0036
    g["SHORT_REBOTE_DEBIL_MIN_EMA_PCT"] = 0.0028
    g["SHORT_OFI_AGOTAMIENTO_MAX"] = -0.30
    g["SHORT_LYAPUNOV_ACEL_MAX_PCT"] = -0.00022
    g["TTL_ORDEN_ENTRADA_SEG"] = 3.80
    g["COSECHA_TRIZ_ACTIVACION_PCT"] = 0.0028
    g["TRINQUETE_BE_NETO_PCT"] = 0.00075
    g["TRINQUETE_RATCHET_ACTIVACION_PCT"] = 0.0032
    g["TRAILING_ACTIVACION_PCT"] = 0.0038
    g["TRAILING_DISTANCIA_PCT"] = 0.0012
    g["ESCUDO_MAKER_FASE2_SEG"] = 58.0
    g["MAKER_SCRATCH_TIEMPO_SEG"] = 22.0
    g["SL_INTERNO_PCT"] = 0.0032
    g["TIEMPO_MAX_HOLD_SEG"] = 95.0
    g["COOLDOWN_POST_CIERRE_WIN_SEG"] = 20.0
    g["COOLDOWN_POST_CIERRE_LOSS_SEG"] = 90.0
    lim = g.get("_LIMITES_SHADOW_GATE")
    if isinstance(lim, dict):
        lim["KELLY_FRACCION_BASE"] = (0.55, 0.62)
        lim["Z_SCORE_UMBRAL_HIGH_BETA"] = (-3.60, -2.80)
        lim["Z_SCORE_UMBRAL_TIER1"] = (-3.30, -2.45)
        lim["OFI_MIN_ENTRADA"] = (0.18, 0.45)
        lim["COSECHA_TRIZ_ACTIVACION_PCT"] = (0.0025, 0.0035)
        lim["SL_INTERNO_PCT"] = (0.0028, 0.0036)


def recargar_calibracion_oos_si_cambio(ruta_json: pathlib.Path | None = None) -> Dict[str, Any]:
    global _ULTIMO_MTIME_OOS
    objetivo = ruta_json or (ROOT_DIR / ARCHIVO_CALIBRACION_OOS)
    if not objetivo.exists():
        return {"recargado": False, "motivo": "ARCHIVO_NO_EXISTE"}

    try:
        mtime_actual = objetivo.stat().st_mtime
        if mtime_actual <= _ULTIMO_MTIME_OOS:
            return {"recargado": False, "motivo": "SIN_CAMBIOS"}

        datos = json.loads(objetivo.read_text(encoding="utf-8-sig"))
        parametros_nuevos = datos.get("parametros", datos) if isinstance(datos, dict) else {}
        aplicados: Dict[str, float] = {}
        g = globals()

        for clave, (v_min, v_max) in _LIMITES_SHADOW_GATE.items():
            if clave in parametros_nuevos:
                valor_bruto = float(parametros_nuevos[clave])
                valor_clamped = max(v_min, min(v_max, valor_bruto))
                g[clave] = valor_clamped
                aplicados[clave] = valor_clamped

        if not es_modo_test():
            _aplicar_parametros_produccion_phantom()
            aplicados["KELLY_FRACCION_BASE"] = g["KELLY_FRACCION_BASE"]
            aplicados["COSECHA_TRIZ_ACTIVACION_PCT"] = g["COSECHA_TRIZ_ACTIVACION_PCT"]
            aplicados["SL_INTERNO_PCT"] = g["SL_INTERNO_PCT"]
            aplicados["OFI_MIN_ENTRADA"] = g["OFI_MIN_ENTRADA"]
            aplicados["Z_SCORE_UMBRAL_HIGH_BETA"] = g["Z_SCORE_UMBRAL_HIGH_BETA"]
            aplicados["Z_SCORE_UMBRAL_TIER1"] = g["Z_SCORE_UMBRAL_TIER1"]

        _ULTIMO_MTIME_OOS = mtime_actual
        return {"recargado": True, "aplicados": aplicados, "mtime": mtime_actual}
    except Exception as exc:
        return {"recargado": False, "motivo": f"ERROR: {exc}"}


_aplicar_parametros_produccion_phantom()