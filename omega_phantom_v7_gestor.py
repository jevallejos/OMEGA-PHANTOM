#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #08: omega_phantom_v7_gestor.py
SISTEMA: OMEGA-PHANTOM V7.0 (APEX-CHRONOS SINGULARITY)
==============================================================================
Guardian de Custodia Multi-Slot, Geometria Campeona (+0.44% / 45s / -0.30%),
Protocolo Chain-Jail (6 Eslabones hasta +8.00%), Paridad Taker/UTA 1:1
(SCAR-LOCK-04), Captura de retCode: 110017 y Consola Forense CLI `veromega`.
==============================================================================
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import omega_phantom_v7_config as cfg
from omega_phantom_v7_ram import ESTADO_RAM, PosicionActiva, log_sniper
from omega_phantom_v7_sniper import EJECUTOR_SNIPER
from omega_phantom_v7_stats import CAJA_NEGRA
from omega_phantom_v7_telegram import TELEMETRIA_TG

_ESLABONES_CHAIN_JAIL: Tuple[Tuple[int, float, float], ...] = (
    (1, 0.0055, 0.0032),
    (2, 0.0095, 0.0065),
    (3, 0.0150, 0.0110),
    (4, 0.0240, 0.0185),
    (5, 0.0420, 0.0330),
    (6, 0.0800, 0.0650),
)


def calcular_eslabon_chain_jail(pnl_pct: float) -> Tuple[int, float, float]:
    """Devuelve (eslabon, activacion_pct, piso_asegurado_pct) segun el PnL bruto."""
    eslabon_actual = 0
    act_actual = 0.0
    piso_actual = 0.0
    for idx, act, piso in _ESLABONES_CHAIN_JAIL:
        if float(pnl_pct) >= act:
            eslabon_actual = idx
            act_actual = act
            piso_actual = piso
    return eslabon_actual, act_actual, piso_actual


def evaluar_reloj_actividad_maker_scratch(
    edad_seg: float,
    pnl_bruto_pct: float,
    max_pnl_pct: float,
    ofi_5s: float,
    side: str,
    ticks_activos: int = 0,
) -> bool:
    """
    Ley 2 (Test Secuencial de Wald a los 18s):
    Determina si la posicion carece de traccion y debe evacuarse en Limit PostOnly.
    """
    if float(edad_seg) < cfg.MAKER_SCRATCH_TIEMPO_SEG:
        return False
    if float(pnl_bruto_pct) > cfg.MAKER_SCRATCH_PNL_MAX_PCT:
        return False
    if float(max_pnl_pct) >= cfg.COSECHA_TRIZ_ACTIVACION_PCT:
        return False

    side_norm = str(side).lower()
    if side_norm == "long":
        flujo_adverso = float(ofi_5s) <= cfg.MAKER_SCRATCH_OFI_UMBRAL
    else:
        flujo_adverso = float(ofi_5s) >= abs(cfg.MAKER_SCRATCH_OFI_UMBRAL)

    return flujo_adverso or (float(pnl_bruto_pct) <= -0.0005 and ticks_activos >= 0)


class GestorPosiciones:
    """Guardian de custodia de posiciones activas y salidas Maker-First."""

    def __init__(self, exchange: Optional[Any] = None) -> None:
        self.exchange: Optional[Any] = exchange

    def configurar_exchange(self, exchange: Any) -> None:
        self.exchange = exchange

    def _calcular_precio_piso_be(self, pos: PosicionActiva) -> float:
        piso_pct = max(cfg.TRINQUETE_BE_NETO_PCT, 2.0 * cfg.FEE_MAKER_PCT + 0.00045)
        if pos.side == "long":
            p_raw = pos.entry_price * (1.0 + piso_pct)
        else:
            p_raw = pos.entry_price * (1.0 - piso_pct)
        return EJECUTOR_SNIPER.redondear_precio(pos.symbol, p_raw)

    async def _obtener_precio_real_orden_market(
        self,
        symbol: str,
        order_id: str,
        precio_fallback: float,
    ) -> float:
        """
        SCAR-LOCK-04: Espera 120ms y consulta fetch_order para obtener el
        average fill price exacto de una orden Market en Bybit UTA.
        """
        if self.exchange is None or not order_id:
            return precio_fallback
        try:
            if not cfg.es_modo_test():
                await asyncio.sleep(0.120)
            ord_info = await self.exchange.fetch_order(order_id, symbol)
            if isinstance(ord_info, dict):
                avg = float(ord_info.get("average", 0.0) or ord_info.get("price", 0.0) or 0.0)
                if avg > 0.0:
                    return avg
        except Exception:
            pass
        return precio_fallback

    async def _ejecutar_cierre_posicion(
        self,
        pos: PosicionActiva,
        precio_salida: float,
        motivo: str,
        es_maker: bool = True,
    ) -> None:
        if pos.cerrada:
            return

        side_cierre = "sell" if pos.side == "long" else "buy"
        px_final = EJECUTOR_SNIPER.redondear_precio(pos.symbol, precio_salida)

        if self.exchange is not None:
            try:
                if es_maker:
                    await self.exchange.create_order(
                        symbol=pos.symbol,
                        type="limit",
                        side=side_cierre,
                        amount=pos.qty_actual,
                        price=px_final,
                        params={"timeInForce": "PostOnly", "reduceOnly": True},
                    )
                else:
                    orden_mkt = await self.exchange.create_order(
                        symbol=pos.symbol,
                        type="market",
                        side=side_cierre,
                        amount=pos.qty_actual,
                        params={"reduceOnly": True},
                    )
                    ord_id = str(orden_mkt.get("id", "")) if isinstance(orden_mkt, dict) else ""
                    px_final = await self._obtener_precio_real_orden_market(
                        pos.symbol, ord_id, px_final
                    )
            except Exception as exc:
                msg_err = str(exc)
                if "110017" in msg_err or "position is zero" in msg_err.lower() or "ordernotfound" in msg_err.lower():
                    motivo = "SL_EXCHANGE"
                    es_maker = False
                    px_final = pos.sl_bybit_price if pos.sl_bybit_price > 0.0 else px_final
                else:
                    log_sniper(f"[GESTOR WARN] Error cerrando {pos.symbol}: {exc}")

        registro = CAJA_NEGRA.registrar_cierre(
            pos=pos,
            exit_price=px_final,
            motivo=motivo,
            es_maker_salida=es_maker,
        )
        if registro is not None:
            if pos.side == "short" and registro.pnl_usdt < 0.0:
                ESTADO_RAM.ultimo_sl_short_precio[pos.symbol] = (px_final, time.time())

            duracion_cd = (
                cfg.COOLDOWN_POST_CIERRE_WIN_SEG
                if registro.pnl_usdt >= 0.0
                else cfg.COOLDOWN_POST_CIERRE_LOSS_SEG
            )
            ESTADO_RAM.aplicar_cuarentena(pos.symbol, duracion_cd, f"POST_{motivo}")
            ESTADO_RAM.liberar_margen_atomico(pos.symbol, pos.margen_reservado_usdt)

            m_res = CAJA_NEGRA.obtener_resumen_metricas()
            await TELEMETRIA_TG.notificar_cierre_definitivo(
                registro=registro,
                patrimonio_actual_usdt=m_res["balance_contable_usdt"],
                win_rate_efectivo_pct=m_res["wr_efectivo_pct"],
            )

            tag_log = "[WIN]" if registro.pnl_usdt > 0.0 else ("[SCRATCH]" if "SCRATCH" in motivo else "[LOSS]")
            log_sniper(
                f"[FRANCOTIRADOR] {tag_log} CIERRE {pos.symbol} [{motivo}] "
                f"{pos.entry_price} -> {px_final} | {registro.pnl_percentage:+.2f} % "
                f"({registro.pnl_usdt:+.4f} USDT) en {int(registro.hold_seg)}s"
            )

    async def evaluar_posicion_activa(
        self,
        pos: PosicionActiva,
        precio_actual: float,
        ofi_5s: float = 0.0,
        ahora: Optional[float] = None,
    ) -> None:
        if pos.cerrada or precio_actual <= 0.0:
            return

        t_now = float(ahora) if ahora is not None else time.time()
        edad_seg = pos.edad_segundos(t_now)
        pnl_pct = pos.calcular_pnl_bruto_pct(precio_actual)
        pos.actualizar_anatomia_intratrade(pnl_pct, edad_seg)

        # 1. Stop-Loss Quirurgico Interno (-0.30% en produccion / -0.48% en test)
        if not pos.trinquete_be_armado and pnl_pct <= -cfg.SL_INTERNO_PCT:
            await self._ejecutar_cierre_posicion(
                pos=pos,
                precio_salida=precio_actual,
                motivo="SL_INTERNO_CHRONOS",
                es_maker=False,
            )
            return

        # 2. Si el Trinquete Break-Even o Ratchet esta armado y el precio retrocede al piso
        if pos.trinquete_be_armado:
            toco_piso_be = (
                (pos.side == "long" and precio_actual <= pos.sl_interno_price)
                or (pos.side == "short" and precio_actual >= pos.sl_interno_price)
            )
            if toco_piso_be:
                motivo_be = "TRAILING_RATCHET_MAKER" if pos.trailing_activo else "TRINQUETE_BE_MAKER"
                await self._ejecutar_cierre_posicion(
                    pos=pos,
                    precio_salida=pos.sl_interno_price,
                    motivo=motivo_be,
                    es_maker=True,
                )
                return

        # 3. Cosecha 50% TRIZ PostOnly (+0.44% en produccion / +0.26% en test) y armado de BE+
        if not pos.cosecha_50_ejecutada and pnl_pct >= cfg.COSECHA_TRIZ_ACTIVACION_PCT:
            piso_be = self._calcular_precio_piso_be(pos)
            pos.sl_interno_price = piso_be
            pos.trinquete_be_armado = True
            log_sniper(
                f"[FRANCOTIRADOR] [SHIELD] {pos.symbol} Trinquete Break-Even armado: SL {piso_be} (PnL {pnl_pct*100:+.2f}%)"
            )

            qty_mitad = EJECUTOR_SNIPER.redondear_cantidad(
                pos.symbol, pos.qty_actual * cfg.COSECHA_TRIZ_FRACCION
            )
            if 0.0 < qty_mitad < pos.qty_actual:
                px_cosecha = EJECUTOR_SNIPER.redondear_precio(pos.symbol, precio_actual)
                nocional_mitad = qty_mitad * pos.entry_price
                fee_mitad = nocional_mitad * (2.0 * cfg.FEE_MAKER_PCT)
                pnl_mitad_usdt = round((nocional_mitad * pnl_pct) - fee_mitad, 4)

                pos.qty_actual = round(pos.qty_actual - qty_mitad, 6)
                pos.cosecha_50_ejecutada = True
                pos.ts_cosecha_50 = t_now
                pos.modo_cosecha_ejecutado = "ESCALERA_50_25_25"
                CAJA_NEGRA.registrar_cosecha_parcial_en_vivo(pos, pnl_mitad_usdt, fee_mitad)

                await TELEMETRIA_TG.notificar_cosecha_parcial(
                    symbol=pos.symbol,
                    side=pos.side,
                    qty_cosechada=qty_mitad,
                    precio_cosecha=px_cosecha,
                    pnl_pct=pnl_pct,
                    pnl_usdt=pnl_mitad_usdt,
                )
                log_sniper(
                    f"[FRANCOTIRADOR] [DIAMOND] {pos.symbol} Cosecha 50% TRIZ PostOnly ejecutada: "
                    f"{qty_mitad} @ {px_cosecha} ({pnl_pct*100:+.2f}% | {pnl_mitad_usdt:+.4f} USDT). "
                    f"Restan {pos.qty_actual} contratos en Escalera 50/25/25."
                )

        # 4. Escalera Chain-Jail (6 Eslabones) y Trailing Ratchet (+0.65%)
        eslabon, _, piso_cj_pct = calcular_eslabon_chain_jail(pnl_pct)
        if eslabon > pos.eslabon_chain_jail:
            pos.eslabon_chain_jail = eslabon
            pos.chain_jail_activo = True
            if pos.side == "long":
                nuevo_sl = pos.entry_price * (1.0 + piso_cj_pct)
                if nuevo_sl > pos.sl_interno_price:
                    pos.sl_interno_price = EJECUTOR_SNIPER.redondear_precio(pos.symbol, nuevo_sl)
            else:
                nuevo_sl = pos.entry_price * (1.0 - piso_cj_pct)
                if pos.sl_interno_price <= 0.0 or nuevo_sl < pos.sl_interno_price:
                    pos.sl_interno_price = EJECUTOR_SNIPER.redondear_precio(pos.symbol, nuevo_sl)
            pos.trinquete_be_armado = True

        if pnl_pct >= cfg.TRAILING_ACTIVACION_PCT:
            if not pos.trailing_activo:
                pos.trailing_activo = True
                log_sniper(f"[FRANCOTIRADOR] {pos.symbol} Trailing Stop activado (PnL {pnl_pct*100:+.2f}%)")
            dist = cfg.TRAILING_DISTANCIA_PCT
            if pos.side == "long":
                cand_sl = EJECUTOR_SNIPER.redondear_precio(pos.symbol, precio_actual * (1.0 - dist))
                if cand_sl > pos.sl_interno_price:
                    pos.sl_interno_price = cand_sl
            else:
                cand_sl = EJECUTOR_SNIPER.redondear_precio(pos.symbol, precio_actual * (1.0 + dist))
                if pos.sl_interno_price <= 0.0 or cand_sl < pos.sl_interno_price:
                    pos.sl_interno_price = cand_sl
            pos.trinquete_be_armado = True

        # 5. Ley 2: Maker-Scratch Pasivo a los 18s (Continuous Wald Scratch)
        if not pos.cosecha_50_ejecutada and evaluar_reloj_actividad_maker_scratch(
            edad_seg=edad_seg,
            pnl_bruto_pct=pnl_pct,
            max_pnl_pct=pos.max_pnl_pct_alcanzado,
            ofi_5s=ofi_5s,
            side=pos.side,
        ):
            pos.scratch_18s_evaluado = True
            pos.scratch_18s_activo = True
            px_scratch = EJECUTOR_SNIPER.redondear_precio(pos.symbol, precio_actual)
            log_sniper(
                f"[MAKER-SCRATCH 18s] {pos.symbol} sin rebote tras {edad_seg:.1f}s "
                f"(PnL {pnl_pct*100:+.2f}%, OFI5s {ofi_5s:+.2f}): evacuando en Limit PostOnly @ {px_scratch}."
            )
            await self._ejecutar_cierre_posicion(
                pos=pos,
                precio_salida=px_scratch,
                motivo="MAKER_SCRATCH_18S",
                es_maker=True,
            )
            return

        # 6. Early Stagnation Maker Unwind a los 45.0s (SCAR-LOCK-12b) y limite de Hold (84s)
        if not cfg.es_modo_test() and not pos.cosecha_50_ejecutada and edad_seg >= cfg.ESCUDO_MAKER_FASE2_SEG:
            if -0.0012 <= pnl_pct <= 0.0018:
                await self._ejecutar_cierre_posicion(
                    pos=pos,
                    precio_salida=precio_actual,
                    motivo="MAKER_UNWIND",
                    es_maker=True,
                )
                return

        max_hold = cfg.TIEMPO_MAX_HOLD_TRINQUETE_SEG if pos.trinquete_be_armado else cfg.TIEMPO_MAX_HOLD_SEG
        if edad_seg >= max_hold:
            await self._ejecutar_cierre_posicion(
                pos=pos,
                precio_salida=precio_actual,
                motivo="MAKER_HOLD_EXPIRED",
                es_maker=True,
            )

    async def ciclo_vigilancia_posiciones(self) -> None:
        while True:
            try:
                for sym, pos in list(ESTADO_RAM.posiciones_activas.items()):
                    tk = ESTADO_RAM.ticks_ram.get(sym)
                    if tk is not None and tk.last > 0.0:
                        await self.evaluar_posicion_activa(
                            pos=pos,
                            precio_actual=tk.last,
                            ofi_5s=tk.ofi_5s,
                        )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log_sniper(f"[GESTOR WARN] {exc}")
            await asyncio.sleep(0.025)


GESTOR_POSICIONES: GestorPosiciones = GestorPosiciones()


# ==============================================================================
# CONSOLA FORENSE INTERACTIVA CLI `veromega` (-s, -x, -t, -h, -b)
# ==============================================================================
def imprimir_baul_ia_cli_veromega() -> None:
    ruta_baul = cfg.ROOT_DIR / "omega_phantom_v7_baul_ia.jsonl"
    print("-" * 102)
    print(" BAUL FORENSE IA (omega_phantom_v7_baul_ia.jsonl) -- ORACULO CONTRAFACTUAL +15S & ANATOMIA MFE/MAE")
    print("-" * 102)
    if not ruta_baul.exists():
        print(" [INFO] Baul Forense IA inicializado y en espera del primer evento (+15s / cierre).")
        return

    eventos: List[Dict[str, Any]] = []
    try:
        for ln in ruta_baul.read_text(encoding="utf-8-sig").splitlines():
            if ln.strip():
                eventos.append(json.loads(ln))
    except Exception:
        pass

    auditorias = [e for e in eventos if e.get("tipo_evento") == "AUDITORIA_ESCUDO_15S"]
    true_shields = [e for e in auditorias if e.get("veredicto_ia") == "CAPITAL_SALVADO_TRUE_SHIELD"]
    false_rej = [e for e in auditorias if e.get("veredicto_ia") == "OPORTUNIDAD_PERDIDA_FALSE_REJECTION"]
    usdt_salvados = sum(float(e.get("impacto_estimado_usdt", 0.0)) for e in true_shields)

    print(
        f" Eventos Auditados (+15s): {len(auditorias)} | True Shields: {len(true_shields)} "
        f"(+{usdt_salvados:.4f} USDT salvados) | False Rejections: {len(false_rej)}"
    )
    for ev in auditorias[-5:]:
        print(
            f"   -> {ev.get('ts_utc', '')[-8:]} | {ev.get('veredicto_ia', '')[:14]:<14} | "
            f"{ev.get('symbol', '').split('/')[0]:<7} | {ev.get('scar_id', '')[:24]:<24} | "
            f"15s: {float(ev.get('excursion_15s_pct', 0.0)):+6.2f}% ({float(ev.get('impacto_estimado_usdt', 0.0)):+.4f} USDT)"
        )


def imprimir_status_cli_veromega() -> None:
    CAJA_NEGRA.cargar_y_auditar_historial()
    m = CAJA_NEGRA.obtener_resumen_metricas()

    pid_str = "OFFLINE"
    lock_file = cfg.ROOT_DIR / cfg.ARCHIVO_LOCK_PRODUCCION
    if lock_file.exists():
        pid_str = lock_file.read_text(encoding="utf-8").strip()

    print("=" * 102)
    print(f" OMEGA-PHANTOM V7.0 -- PANEL FORENSE EN TIEMPO REAL [DESAFIO 48H: 10.00 -> 14.00 USDT]")
    print("=" * 102)
    print(
        f" MOTOR EN VIVO -> PID: {pid_str} | Estrategia: {cfg.ESTRATEGIA_MATEMATICA}"
    )
    print(
        f" CAJA NEGRA    -> Trades: {m['n_trades']} (W: {m['n_wins']} | L: {m['n_losses']} | "
        f"Scratch 18s: {m['n_scratches']} | Cosechas 50%: {m['cosechas_parciales']})"
    )
    print(
        f" RENDIMIENTO   -> WR Efectivo: {m['wr_efectivo_pct']:.1f}% | PnL Neto: {m['pnl_neto_usdt']:+.4f} USDT | "
        f"Ahorro Scratch: +{m['ahorro_scratch_usdt']:.4f} USDT"
    )
    print(
        f" META 48 HORAS -> Balance Contable: {m['balance_contable_usdt']:.4f} USDT | "
        f"Progreso Meta 14.00 USDT: {m['progreso_meta_48h_pct']:.1f}%"
    )
    print("-" * 102)
    print(" ULTIMAS 10 OPERACIONES REGISTRADAS EN OMEGA-PHANTOM V7.0:")
    ultimas = CAJA_NEGRA.operaciones[-10:]
    if not ultimas:
        print("   [0 operaciones registradas aun en omega_phantom_v7_stats.jsonl]")
    for idx, op in enumerate(ultimas, start=max(1, len(CAJA_NEGRA.operaciones) - len(ultimas) + 1)):
        tag = "SCR" if "SCRATCH" in op.motivo.upper() else ("WIN" if op.pnl_usdt > 0 else "LOSS")
        sym_corto = op.symbol.split("/")[0]
        print(
            f"  {idx:3d}. {tag:<5} {op.timestamp} | {sym_corto:<8} [{op.side.upper():<5}] | "
            f"{op.pnl_percentage:+6.2f}% ({op.pnl_usdt:+.4f} USDT) | {int(op.hold_seg):3d}s | {op.motivo}"
        )
    imprimir_baul_ia_cli_veromega()
    print("=" * 102)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "-s"
    if arg in ("-b", "--baul"):
        imprimir_baul_ia_cli_veromega()
    else:
        imprimir_status_cli_veromega()