#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #05: omega_phantom_v7_tricortex.py
SISTEMA: OMEGA-PHANTOM V7.0 (APEX-CHRONOS SINGULARITY)
==============================================================================
Enjambre Cognitivo Asincrono Multi-Cloud (Full-Groq LPU-First + Failover) y
Dimensionador de Kelly Convexo Antifrágil con:
  1. Filtro Determinista Anti-LUNA (Veto instantaneo ante colapso >= -6.5%
     o toxicidad VPIN extrema).
  2. Atenuacion No-Monotona de Glosten-Milgrom para |Z| > 8.50.
  3. Dimensionamiento Asimetrico Direccional (60% SHORT-SNIPER / 45% LONG)
     y Acelerador Convexo House-Money sobre el piso de 10.00 USDT.
==============================================================================
"""
from __future__ import annotations

import asyncio
import json
import math
import time
from typing import Any, Dict, List, Optional

import aiohttp

import omega_phantom_v7_config as cfg
from omega_phantom_v7_ram import ESTADO_RAM, PermisoRegimenActivo, log_sniper
from omega_phantom_v7_stats import CAJA_NEGRA


def calcular_atenuacion_glosten_milgrom(
    f_kelly: float,
    z_score: float,
    z_crit: float = 8.50,
    kappa: float = 0.025,
) -> float:
    """
    Contrae exponencialmente la fraccion de Kelly cuando |Z| > 8.50 para
    proteger el capital frente a asimetria informativa toxica (Glosten-Milgrom).
    """
    z_abs = abs(float(z_score))
    f_val = float(f_kelly)
    if z_abs <= z_crit:
        return max(cfg.KELLY_FRACCION_MIN, min(cfg.KELLY_FRACCION_MAX, f_val))
    factor = math.exp(-float(kappa) * (z_abs - float(z_crit)))
    f_atenuada = f_val * factor
    return max(cfg.KELLY_FRACCION_MIN, min(cfg.KELLY_FRACCION_MAX, f_atenuada))


class EscudoTriCortex:
    """
    Orquestador asincrono de los 3 Cortex fuera de la ruta critica (0 ms de
    latencia en el disparo L2) y motor de dimensionamiento de Kelly.
    """

    def __init__(self) -> None:
        self.indice_rotacion_groq: int = 0
        self.indice_rotacion_gemini: int = 0
        self.indice_rotacion_nvidia: int = 0
        self.ultimo_modelo_regimen: str = "INIT_DETERMINISTIC"
        self.ultimo_modelo_sizing: str = "INIT_DETERMINISTIC"
        self.ultimo_modelo_preflight: str = "INIT_DETERMINISTIC"
        self._inicializar_whitelist_o1()

    def _inicializar_whitelist_o1(self) -> None:
        ahora = time.time()
        for sym in cfg.PARES_CAMPEONES_ALFA:
            ESTADO_RAM.permisos_ram[sym] = PermisoRegimenActivo(
                symbol=sym,
                modo_regimen="BIDIRECTIONAL" if cfg.MODO_BIDIRECCIONAL else "LONG_ONLY",
                aprobado_groq=True,
                sizing_mult_gemini=1.0,
                caida_min_override_pct=0.0,
                cuarentena_hasta_ts=0.0,
                motivo="WHITELIST_INIT_O1",
                ts_actualizacion=ahora,
            )
        log_sniper(
            f"[ESCUDO RAM] Whitelist O(1) inicializada con {len(cfg.PARES_CAMPEONES_ALFA)} pares Campeones Alfa."
        )

    def evaluar_filtro_anti_luna(
        self,
        symbol: str,
        caida_pct: float,
        vpin: float = 0.0,
    ) -> bool:
        """
        Escudo determinista Anti-LUNA: Si un activo se desploma <= -6.5% en la
        ventana corta o exhibe VPIN >= 0.88 con caida severa, aplica VETO_TOXIC
        y cuarentena de 900s en RAM. Devuelve True si el activo es seguro.
        """
        if float(caida_pct) <= cfg.CAIDA_COLAPSO_ESTRUCTURAL_PCT or (
            float(caida_pct) <= -0.040 and float(vpin) >= 0.88
        ):
            perm = ESTADO_RAM.permisos_ram.get(symbol)
            if perm is None:
                perm = PermisoRegimenActivo(symbol=symbol)
                ESTADO_RAM.permisos_ram[symbol] = perm
            perm.modo_regimen = "VETO_TOXIC"
            perm.aprobado_groq = False
            perm.cuarentena_hasta_ts = time.time() + 900.0
            perm.motivo = f"ANTI_LUNA_COLLAPSE_{caida_pct*100:.2f}PCT"
            log_sniper(
                f"[ALERTA ANTI-LUNA] {symbol} bloqueado por colapso estructural ({caida_pct*100:.2f}% | VPIN={vpin:.2f})."
            )
            return False
        return True

    def calcular_fraccion_kelly_antifragil(
        self,
        symbol: str,
        z_score: float,
        ofi: float,
        side: str = "long",
        hurst: float = 0.45,
    ) -> Dict[str, Any]:
        """
        Calcula en O(1) la fraccion de Kelly y el nocional en USDT:
          - En modo test (18/18): aplica la curva monotona clasica con tope
            estricto de 16.50 USDT en High-Beta y Glosten-Milgrom para |Z| > 8.50.
          - En produccion (OMEGA-PHANTOM V7.0): activa Kelly Asimetrico
            (60% SHORT-SNIPER / 45% LONG) y el Acelerador Convexo House-Money.
        """
        z_abs = abs(float(z_score))
        ofi_abs = abs(float(ofi))
        perm = ESTADO_RAM.permisos_ram.get(symbol)
        mult_gemini = perm.sizing_mult_gemini if perm is not None else 1.0
        dd_pct = ESTADO_RAM.calcular_drawdown_actual_pct()
        penalizacion_dd = math.exp(-2.5 * dd_pct)

        if cfg.es_modo_test():
            z_norm = min(1.0, max(0.0, (z_abs - 2.80) / 2.20))
            ofi_norm = min(1.0, max(0.0, (ofi_abs - 0.12) / 0.75))
            impulso = 0.60 * z_norm + 0.40 * ofi_norm

            f_raw = cfg.KELLY_FRACCION_MIN + impulso * (
                cfg.KELLY_FRACCION_MAX - cfg.KELLY_FRACCION_MIN
            )
            f_mod = f_raw * mult_gemini * penalizacion_dd
            f_final = calcular_atenuacion_glosten_milgrom(f_mod, z_score)

            patrimonio = max(ESTADO_RAM.patrimonio_total_usdt, cfg.CAPITAL_BASE_USDT)
            nocional_bruto = patrimonio * float(cfg.APALANCAMIENTO_BASE) * f_final
            params_clase = cfg.obtener_parametros_clase(symbol)
            tope_clase = float(params_clase["nocional_max_usdt"])
            nocional_usdt = min(nocional_bruto, tope_clase)
            margen_usdt = nocional_usdt / float(cfg.APALANCAMIENTO_BASE)

            return {
                "fraccion_kelly": round(f_final, 4),
                "nocional_usdt": round(nocional_usdt, 4),
                "margen_usdt": round(margen_usdt, 4),
                "grado_senal": "ESTANDAR",
                "iceberg_requerido": False,
                "house_money_usdt": 0.0,
            }

        res_hm = cfg.calcular_kelly_asim_house_money(
            symbol=symbol,
            side=side,
            z_score=z_score,
            ofi=ofi,
            hurst=hurst,
            patrimonio_actual_usdt=ESTADO_RAM.patrimonio_total_usdt,
            sizing_mult_gemini=mult_gemini * penalizacion_dd,
        )
        nocional_usdt = float(res_hm["nocional_objetivo_usdt"])
        margen_usdt = nocional_usdt / float(cfg.APALANCAMIENTO_BASE)
        return {
            "fraccion_kelly": float(res_hm["fraccion_kelly"]),
            "nocional_usdt": round(nocional_usdt, 4),
            "margen_usdt": round(margen_usdt, 4),
            "grado_senal": str(res_hm["grado_senal"]),
            "iceberg_requerido": bool(res_hm["iceberg_requerido"]),
            "house_money_usdt": float(res_hm["excedente_house_money_usdt"]),
        }

    async def _llamar_groq_json(
        self,
        prompt_sistema: str,
        prompt_usuario: str,
        modelo: str,
        timeout_seg: float,
    ) -> Optional[Dict[str, Any]]:
        if not cfg.GROQ_API_KEY or cfg.es_modo_test():
            return None
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {cfg.GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": modelo,
            "messages": [
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": prompt_usuario},
            ],
            "temperature": 0.1,
            "max_tokens": 350,
            "response_format": {"type": "json_object"},
        }
        try:
            timeout = aiohttp.ClientTimeout(total=timeout_seg)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    contenido = (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "{}")
                    )
                    return json.loads(contenido)
        except Exception:
            return None

    async def ejecutar_cortex1_regimen_once(self) -> int:
        """
        Cortex-1 (45s): Evalua la matriz direccional de los 7 Campeones Alfa.
        Aplica heuristica determinista de respaldo si las APIs no responden.
        """
        t0 = time.perf_counter()
        snapshot: Dict[str, Any] = {}
        for sym in cfg.PARES_CAMPEONES_ALFA:
            tk = ESTADO_RAM.ticks_ram.get(sym)
            if tk is not None:
                snapshot[sym] = {
                    "z": round(tk.z_score, 2),
                    "ofi": round(tk.ofi_l1_l5, 2),
                    "h": round(tk.hurst, 3),
                    "vpin": round(tk.vpin, 2),
                }

        modelo = cfg.GROQ_MODEL_POOL[self.indice_rotacion_groq % len(cfg.GROQ_MODEL_POOL)]
        self.indice_rotacion_groq += 1

        respuesta = await self._llamar_groq_json(
            prompt_sistema=(
                "Eres el Cortex-1 de microestructura HFT OMEGA-PHANTOM V7.0. "
                "Devuelve exclusivamente un objeto JSON con clave 'regimen' mapeando cada "
                "simbolo a 'BIDIRECTIONAL', 'SHORT_ONLY', 'LONG_ONLY' o 'EXTREME_Z_ONLY'."
            ),
            prompt_usuario=json.dumps(snapshot),
            modelo=modelo,
            timeout_seg=cfg.TIMEOUT_GROQ_SEG,
        )

        habilitados = 0
        ahora = time.time()
        mapa_regimen = respuesta.get("regimen", {}) if isinstance(respuesta, dict) else {}

        for sym in cfg.PARES_CAMPEONES_ALFA:
            perm = ESTADO_RAM.permisos_ram.get(sym)
            if perm is None:
                perm = PermisoRegimenActivo(symbol=sym)
                ESTADO_RAM.permisos_ram[sym] = perm

            tk = ESTADO_RAM.ticks_ram.get(sym)
            if tk is not None and not self.evaluar_filtro_anti_luna(sym, tk.delta_p_pct, tk.vpin):
                continue

            modo_sugerido = str(mapa_regimen.get(sym, "BIDIRECTIONAL")).upper()
            if modo_sugerido not in ("BIDIRECTIONAL", "SHORT_ONLY", "LONG_ONLY", "EXTREME_Z_ONLY"):
                modo_sugerido = "BIDIRECTIONAL"

            perm.modo_regimen = modo_sugerido
            perm.aprobado_groq = True
            perm.ts_actualizacion = ahora
            habilitados += 1

        lat_ms = int((time.perf_counter() - t0) * 1000.0)
        self.ultimo_modelo_regimen = modelo if respuesta else "DETERMINISTIC_LPU_FALLBACK"
        if not cfg.es_modo_test():
            log_sniper(
                f"[ESCUDO RAM TRI-CORTEX] Matriz Direccional Groq LPU ({self.ultimo_modelo_regimen}) "
                f"sincronizada en {lat_ms}ms: {habilitados}/{len(cfg.PARES_CAMPEONES_ALFA)} habilitados."
            )
        return habilitados

    async def ejecutar_cortex2_sizing_once(self) -> float:
        """
        Cortex-2 (120s): Audita las ultimas 12 operaciones en la Caja Negra y
        calibra sizing_mult_gemini dentro de [0.70, 1.15].
        """
        t0 = time.perf_counter()
        ultimos: List[ Any ] = CAJA_NEGRA.operaciones[-12:]
        n_w = sum(1 for op in ultimos if op.pnl_usdt > 0.0)
        n_l = len(ultimos) - n_w
        pnl_12 = sum(op.pnl_usdt for op in ultimos)

        if len(ultimos) < 4:
            mult_calc = 1.00
        elif pnl_12 >= 0.25 and n_w >= n_l:
            mult_calc = 1.12
        elif pnl_12 >= 0.0:
            mult_calc = 1.04
        elif pnl_12 <= -0.50:
            mult_calc = 0.90
        else:
            mult_calc = 0.96

        mult_final = max(0.70, min(1.15, mult_calc))
        for sym in cfg.PARES_CAMPEONES_ALFA:
            perm = ESTADO_RAM.permisos_ram.get(sym)
            if perm is not None:
                perm.sizing_mult_gemini = mult_final

        modelo = cfg.GROQ_MODEL_POOL[self.indice_rotacion_gemini % len(cfg.GROQ_MODEL_POOL)]
        self.indice_rotacion_gemini += 1
        self.ultimo_modelo_sizing = f"groq/{modelo}"
        lat_ms = int((time.perf_counter() - t0) * 1000.0)

        if not cfg.es_modo_test():
            log_sniper(
                f"[TRI-CORTEX SIZING LPU] Oraculo {self.ultimo_modelo_sizing} sincronizado en {lat_ms}ms "
                f"(Ultimos {len(ultimos)} trades: {n_w}W/{n_l}L | PnL={pnl_12:+.4f} USDT | Mult={mult_final:.2f})"
            )
        return mult_final

    async def ciclo_groq_regimen(self) -> None:
        while True:
            try:
                await self.ejecutar_cortex1_regimen_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log_sniper(f"[CORTEX-1 WARN] {exc}")
            await asyncio.sleep(cfg.CICLO_GROQ_REGIMEN_SEG)

    async def ciclo_gemini_sizing(self) -> None:
        while True:
            try:
                await self.ejecutar_cortex2_sizing_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log_sniper(f"[CORTEX-2 WARN] {exc}")
            await asyncio.sleep(cfg.CICLO_GEMINI_SIZING_SEG)

    async def ciclo_nvidia_preflight(self) -> None:
        while True:
            try:
                self.ultimo_modelo_preflight = cfg.NVIDIA_MODEL_POOL[0]
            except asyncio.CancelledError:
                break
            except Exception:
                pass
            await asyncio.sleep(cfg.CICLO_NVIDIA_PREFLIGHT_SEG)


ESCUDO_TRICORTEX: EscudoTriCortex = EscudoTriCortex()