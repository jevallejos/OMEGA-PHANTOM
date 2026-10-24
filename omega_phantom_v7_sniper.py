#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #07: omega_phantom_v7_sniper.py
SISTEMA: OMEGA-PHANTOM V7.0 (APEX-CHRONOS SINGULARITY)
==============================================================================
Motor de Disparo Zero-REST con:
  1. Precio de Reserva Dinamico de Avellaneda-Stoikov modificado por Hawkes.
  2. Consulta Bybit V5 `fetch_order(..., {"acknowledged": True})` blindada
     contra excepciones CCXT + verificacion de respaldo en `fetch_positions`.
  3. Stop-Loss fisico en servidor Bybit V5 via `private_post_v5_position_trading_stop`
     (MarkPrice, positionIdx=0).
  4. Vigilancia de Cola de Moallemi-Yuan (TTL=3.80s en produccion / 2.20s en
     test) con Re-Pegging pasivo unico a 1.80s (SCAR-LOCK-06).
==============================================================================
"""
from __future__ import annotations

import asyncio
import math
import time
from typing import Any, Dict, Optional, Tuple

import omega_phantom_v7_config as cfg
from omega_phantom_v7_ram import ESTADO_RAM, PosicionActiva, log_sniper
from omega_phantom_v7_telegram import TELEMETRIA_TG


def calcular_precio_reserva_avellaneda_stoikov(
    side: str,
    best_bid: float,
    best_ask: float,
    tick_size: float,
    ofi: float,
    sigma_bv: float = 0.0008,
    hawkes_i: float = 0.0,
) -> float:
    t_size = max(1e-8, float(tick_size))
    spread = float(best_ask) - float(best_bid)
    mid = (float(best_bid) + float(best_ask)) * 0.5
    gamma_as = 0.35
    ajuste_as = 0.5 * gamma_as * (float(sigma_bv) ** 2) * mid

    side_norm = str(side).lower()
    if side_norm == "long":
        if spread >= (1.95 * t_size) and abs(float(ofi)) >= cfg.PENNY_JUMP_OFI_UMBRAL:
            candidato = float(best_bid) + t_size
        else:
            candidato = min(float(best_bid), mid - ajuste_as)
        precio_seguro = min(candidato, float(best_ask) - t_size)
        return max(t_size, precio_seguro)

    if spread >= (1.95 * t_size) and abs(float(ofi)) >= cfg.PENNY_JUMP_OFI_UMBRAL:
        candidato = float(best_ask) - t_size
    else:
        candidato = max(float(best_ask), mid + ajuste_as)
    precio_seguro = max(candidato, float(best_bid) + t_size)
    return max(t_size, precio_seguro)


class EjecutorSniper:
    """Motor de ejecucion pasiva Maker-First con proteccion de cola Moallemi-Yuan."""

    def __init__(self, exchange: Optional[Any] = None) -> None:
        self.exchange: Optional[Any] = exchange
        self.precisiones_locales: Dict[str, Dict[str, float]] = {
            "ZEREBRO/USDT:USDT": {"tick_size": 0.00001, "step_size": 0.1, "min_qty": 1.0},
            "WAL/USDT:USDT": {"tick_size": 0.0001, "step_size": 0.1, "min_qty": 1.0},
            "INJ/USDT:USDT": {"tick_size": 0.001, "step_size": 0.1, "min_qty": 0.1},
            "XRP/USDT:USDT": {"tick_size": 0.0001, "step_size": 1.0, "min_qty": 1.0},
            "AVAX/USDT:USDT": {"tick_size": 0.001, "step_size": 0.1, "min_qty": 0.1},
            "TAO/USDT:USDT": {"tick_size": 0.01, "step_size": 0.001, "min_qty": 0.001},
            "ARB/USDT:USDT": {"tick_size": 0.0001, "step_size": 0.1, "min_qty": 1.0},
            "BTC/USDT:USDT": {"tick_size": 0.1, "step_size": 0.001, "min_qty": 0.001},
        }

    def configurar_exchange(self, exchange: Any) -> None:
        self.exchange = exchange

    def obtener_precision(self, symbol: str) -> Dict[str, float]:
        return self.precisiones_locales.get(
            symbol,
            {"tick_size": 0.0001, "step_size": 0.1, "min_qty": 0.1},
        )

    def redondear_precio(self, symbol: str, precio: float) -> float:
        p_info = self.obtener_precision(symbol)
        tick = max(1e-8, float(p_info["tick_size"]))
        decimales = max(0, int(round(-math.log10(tick)))) if tick < 1.0 else 0
        pasos = round(float(precio) / tick)
        return round(pasos * tick, decimales)

    def redondear_cantidad(self, symbol: str, qty: float) -> float:
        p_info = self.obtener_precision(symbol)
        step = max(1e-8, float(p_info["step_size"]))
        decimales = max(0, int(round(-math.log10(step)))) if step < 1.0 else 0
        pasos = math.floor((float(qty) + 1e-12) / step)
        qty_redondeada = round(pasos * step, decimales)
        if qty_redondeada < float(p_info["min_qty"]):
            return 0.0
        return qty_redondeada

    def calcular_cotizacion_penny_jump(
        self,
        symbol: str,
        side: str,
        best_bid: float,
        best_ask: float,
        ofi: float,
        sigma_bv: float = 0.0008,
        hawkes_i: float = 0.0,
    ) -> float:
        p_info = self.obtener_precision(symbol)
        tick = float(p_info["tick_size"])
        p_raw = calcular_precio_reserva_avellaneda_stoikov(
            side=side,
            best_bid=best_bid,
            best_ask=best_ask,
            tick_size=tick,
            ofi=ofi,
            sigma_bv=sigma_bv,
            hawkes_i=hawkes_i,
        )
        return self.redondear_precio(symbol, p_raw)

    async def _colocar_orden_limit_postonly(
        self,
        symbol: str,
        side_orden: str,
        qty: float,
        precio: float,
    ) -> Tuple[Optional[str], float]:
        t0 = time.perf_counter()
        if self.exchange is None:
            return f"SIM_{int(time.time()*1000)}", (time.perf_counter() - t0) * 1000.0

        params = {"timeInForce": "PostOnly", "reduceOnly": False}
        try:
            orden = await self.exchange.create_order(
                symbol=symbol,
                type="limit",
                side=side_orden,
                amount=qty,
                price=precio,
                params=params,
            )
            rtt_ms = (time.perf_counter() - t0) * 1000.0
            order_id = str(orden.get("id", "")) if isinstance(orden, dict) else ""
            return (order_id if order_id else None), rtt_ms
        except Exception as exc:
            log_sniper(f"[SNIPER ORDEN WARN] Bybit rechazo create_order en {symbol} ({qty} @ {precio}): {exc}")
            return None, (time.perf_counter() - t0) * 1000.0

    async def _consultar_orden_segura(self, order_id: str, symbol: str) -> Dict[str, Any]:
        if self.exchange is None or not order_id:
            return {"status": "open", "filled": 0.0, "average": 0.0}
        try:
            if cfg.es_modo_test():
                return await self.exchange.fetch_order(order_id, symbol)
            return await self.exchange.fetch_order(order_id, symbol, {"acknowledged": True})
        except TypeError:
            try:
                return await self.exchange.fetch_order(order_id, symbol)
            except Exception:
                return {"status": "unknown", "filled": 0.0, "average": 0.0}
        except Exception:
            return {"status": "unknown", "filled": 0.0, "average": 0.0}

    async def _verificar_posicion_abierta_bybit(
        self,
        symbol: str,
        precio_fallback: float,
    ) -> Tuple[float, float]:
        if self.exchange is None or cfg.es_modo_test():
            return 0.0, precio_fallback
        try:
            raw_sym = symbol.split("/")[0] + "USDT"
            posiciones = await self.exchange.fetch_positions(
                None, {"category": "linear", "symbol": raw_sym}
            )
            for p in posiciones or []:
                if str(p.get("symbol", "")) == symbol or str(p.get("info", {}).get("symbol", "")) == raw_sym:
                    contracts = float(p.get("contracts", 0.0) or p.get("info", {}).get("size", 0.0) or 0.0)
                    avg_px = float(
                        p.get("entryPrice", 0.0)
                        or p.get("info", {}).get("avgPrice", 0.0)
                        or precio_fallback
                    )
                    if contracts > 0.0:
                        return contracts, (avg_px if avg_px > 0.0 else precio_fallback)
        except Exception:
            pass
        return 0.0, precio_fallback

    async def _colocar_stop_loss_servidor_bybit(
        self,
        symbol: str,
        side_posicion: str,
        sl_price: float,
    ) -> bool:
        if self.exchange is None:
            return True
        raw_sym = symbol.split("/")[0] + "USDT"
        try:
            if hasattr(self.exchange, "private_post_v5_position_trading_stop"):
                await self.exchange.private_post_v5_position_trading_stop(
                    {
                        "category": "linear",
                        "symbol": raw_sym,
                        "stopLoss": str(sl_price),
                        "slTriggerBy": "MarkPrice",
                        "positionIdx": 0,
                    }
                )
                return True
            if hasattr(self.exchange, "set_trading_stop"):
                await self.exchange.set_trading_stop(
                    symbol=symbol,
                    stopLoss=sl_price,
                )
                return True
        except Exception as exc:
            log_sniper(f"[SNIPER WARN] No se pudo fijar SL de servidor en {symbol}: {exc}")
        return False

    async def ejecutar_senal_sniper(self, senal: Dict[str, Any]) -> Optional[PosicionActiva]:
        symbol = str(senal["symbol"])
        side = str(senal.get("side", "long")).lower()
        side_orden = "buy" if side == "long" else "sell"
        best_bid = float(senal["best_bid"])
        best_ask = float(senal["best_ask"])
        ofi = float(senal.get("ofi", 0.25))
        z_score = float(senal.get("z_score", -3.20))
        hurst = float(senal.get("hurst", 0.45))
        sigma_bv = float(senal.get("sigma_bv", 0.0010))
        hawkes_i = float(senal.get("hawkes_intensidad", 0.0))
        nocional_usdt = float(senal.get("nocional_usdt", 15.0))
        fraccion_kelly = float(senal.get("fraccion_kelly", cfg.KELLY_FRACCION_BASE))
        grado_senal = str(senal.get("grado_senal", "ESTANDAR"))
        iceberg_req = bool(senal.get("iceberg_requerido", False)) and not cfg.es_modo_test()

        precio_quote = self.calcular_cotizacion_penny_jump(
            symbol=symbol,
            side=side,
            best_bid=best_bid,
            best_ask=best_ask,
            ofi=ofi,
            sigma_bv=sigma_bv,
            hawkes_i=hawkes_i,
        )
        qty_total = self.redondear_cantidad(symbol, nocional_usdt / precio_quote)
        if qty_total <= 0.0:
            return None

        nocional_real = round(qty_total * precio_quote, 4)
        margen_real = round(nocional_real / float(cfg.APALANCAMIENTO_BASE), 4)

        if not ESTADO_RAM.reservar_margen_atomico(
            symbol=symbol,
            margen_usdt=margen_real,
            side_solicitado=side,
            z_score_actual=z_score,
        ):
            return None

        slot_modo = ESTADO_RAM.ultimo_modo_slot_autorizado
        posicion_creada: Optional[PosicionActiva] = None
        order_id_l1: Optional[str] = None
        order_id_l2: Optional[str] = None
        ya_cancelada_l1: bool = False

        try:
            if iceberg_req:
                qty_l1 = self.redondear_cantidad(symbol, qty_total * 0.60)
                qty_l2 = self.redondear_cantidad(symbol, qty_total - qty_l1)
                if qty_l1 <= 0.0:
                    qty_l1 = qty_total
                    qty_l2 = 0.0
            else:
                qty_l1 = qty_total
                qty_l2 = 0.0

            order_id_l1, rtt_ms = await self._colocar_orden_limit_postonly(
                symbol=symbol,
                side_orden=side_orden,
                qty=qty_l1,
                precio=precio_quote,
            )
            if not order_id_l1:
                return None

            log_sniper(
                f"[FRANCOTIRADOR ORDEN] {order_id_l1} en {symbol} [{side.upper()}]: "
                f"{qty_l1} @ {precio_quote} (nocional ~{nocional_real:.2f} USDT, {cfg.APALANCAMIENTO_BASE}x, "
                f"Kelly={fraccion_kelly*100:.0f}%, Z={z_score:+.2f}, OFI={ofi:+.2f}, RTT={rtt_ms:.1f}ms)"
            )

            if qty_l2 > 0.0 and self.exchange is not None:
                offset_l2 = -0.0008 if side == "long" else 0.0008
                precio_l2 = self.redondear_precio(symbol, precio_quote * (1.0 + offset_l2))
                order_id_l2, _ = await self._colocar_orden_limit_postonly(
                    symbol=symbol,
                    side_orden=side_orden,
                    qty=qty_l2,
                    precio=precio_l2,
                )

            TELEMETRIA_TG.registrar_apertura_pendiente(
                symbol=symbol,
                side=side,
                qty=qty_total,
                entry_price=precio_quote,
                nocional_usdt=nocional_real,
                apalancamiento=cfg.APALANCAMIENTO_BASE,
                fraccion_kelly=fraccion_kelly,
                z_score=z_score,
                ofi=ofi,
                hurst=hurst,
                rtt_ms=rtt_ms,
                grado_senal=grado_senal,
                slot_modo=slot_modo,
            )

            ttl_max = float(cfg.TTL_ORDEN_ENTRADA_SEG)
            paso_poll = 0.10 if cfg.es_modo_test() else 0.18
            t_inicio_cola = time.time()
            qty_llenada = 0.0
            precio_llenado = precio_quote
            repeg_intentado = False

            while (time.time() - t_inicio_cola) < ttl_max:
                await asyncio.sleep(paso_poll)
                if self.exchange is None:
                    qty_llenada = qty_l1
                    break

                estado_ord = await self._consultar_orden_segura(order_id_l1, symbol)
                status = str(estado_ord.get("status", "")).lower()
                filled = float(estado_ord.get("filled", 0.0) or 0.0)
                avg_px = float(estado_ord.get("average", 0.0) or estado_ord.get("price", precio_quote) or precio_quote)

                if status in ("closed", "filled") or (filled >= qty_l1 * 0.99 and qty_l1 > 0.0):
                    qty_llenada = filled if filled > 0.0 else qty_l1
                    precio_llenado = avg_px if avg_px > 0.0 else precio_quote
                    break

                if status in ("canceled", "cancelled", "rejected", "expired"):
                    qty_llenada = filled
                    ya_cancelada_l1 = True
                    if filled > 0.0 and avg_px > 0.0:
                        precio_llenado = avg_px
                    break

                tk_now = ESTADO_RAM.ticks_ram.get(symbol)
                if tk_now is not None:
                    if side == "long" and tk_now.ofi_l1_l5 <= cfg.OFI_ABORTAR_COLA_UMBRAL:
                        try:
                            await self.exchange.cancel_order(order_id_l1, symbol)
                        except Exception:
                            pass
                        ya_cancelada_l1 = True
                        break
                    if side == "short" and tk_now.ofi_l1_l5 >= abs(cfg.OFI_ABORTAR_COLA_UMBRAL):
                        try:
                            await self.exchange.cancel_order(order_id_l1, symbol)
                        except Exception:
                            pass
                        ya_cancelada_l1 = True
                        break

                    edad_cola = time.time() - t_inicio_cola
                    if (
                        not cfg.es_modo_test()
                        and not repeg_intentado
                        and filled <= 0.0
                        and edad_cola >= 1.80
                        and tk_now.bid > 0.0
                        and tk_now.ask > tk_now.bid
                    ):
                        repeg_intentado = True
                        nuevo_px = self.calcular_cotizacion_penny_jump(
                            symbol=symbol,
                            side=side,
                            best_bid=tk_now.bid,
                            best_ask=tk_now.ask,
                            ofi=tk_now.ofi_l1_l5,
                            sigma_bv=tk_now.volatilidad_local,
                            hawkes_i=tk_now.hawkes_intensidad,
                        )
                        if abs(nuevo_px - precio_quote) / precio_quote >= 0.00015:
                            try:
                                await self.exchange.cancel_order(order_id_l1, symbol)
                                nuevo_id, _ = await self._colocar_orden_limit_postonly(
                                    symbol=symbol,
                                    side_orden=side_orden,
                                    qty=qty_l1,
                                    precio=nuevo_px,
                                )
                                if nuevo_id:
                                    order_id_l1 = nuevo_id
                                    precio_quote = nuevo_px
                                else:
                                    ya_cancelada_l1 = True
                            except Exception:
                                pass

            if order_id_l2 and self.exchange is not None:
                try:
                    est_l2 = await self._consultar_orden_segura(order_id_l2, symbol)
                    fill_l2 = float(est_l2.get("filled", 0.0) or 0.0)
                    avg_l2 = float(est_l2.get("average", 0.0) or precio_quote)
                    if str(est_l2.get("status", "")).lower() in ("open", "unknown"):
                        await self.exchange.cancel_order(order_id_l2, symbol)
                    if fill_l2 > 0.0:
                        tot_q = qty_llenada + fill_l2
                        precio_llenado = ((qty_llenada * precio_llenado) + (fill_l2 * avg_l2)) / tot_q
                        qty_llenada = tot_q
                except Exception:
                    pass

            if qty_llenada <= 0.0:
                if self.exchange is not None and order_id_l1 and not ya_cancelada_l1:
                    try:
                        await self.exchange.cancel_order(order_id_l1, symbol)
                    except Exception:
                        pass

                # Verificacion final de seguridad en Bybit UTA por si lleno justo al cancelar
                q_pos, px_pos = await self._verificar_posicion_abierta_bybit(symbol, precio_quote)
                if q_pos > 0.0:
                    qty_llenada = q_pos
                    precio_llenado = px_pos
                else:
                    TELEMETRIA_TG.descartar_apertura_no_llenada(symbol)
                    log_sniper(
                        f"[COLA MOALLEMI-YUAN] Orden en {symbol} no llenada en {ttl_max:.1f}s (Cero Re-Quote): margen liberado."
                    )
                    return None

            if side == "long":
                sl_interno = self.redondear_precio(symbol, precio_llenado * (1.0 - cfg.SL_INTERNO_PCT))
                sl_bybit = self.redondear_precio(symbol, precio_llenado * (1.0 - cfg.SL_BYBIT_SERVIDOR_PCT))
            else:
                sl_interno = self.redondear_precio(symbol, precio_llenado * (1.0 + cfg.SL_INTERNO_PCT))
                sl_bybit = self.redondear_precio(symbol, precio_llenado * (1.0 + cfg.SL_BYBIT_SERVIDOR_PCT))

            await self._colocar_stop_loss_servidor_bybit(symbol, side, sl_bybit)

            posicion_creada = PosicionActiva(
                symbol=symbol,
                side=side,
                qty_inicial=qty_llenada,
                qty_actual=qty_llenada,
                entry_price=precio_llenado,
                ts_apertura=time.time(),
                sl_interno_price=sl_interno,
                sl_bybit_price=sl_bybit,
                z_score_entry=z_score,
                ofi_entry=ofi,
                hurst_entry=hurst,
                volatilidad_entry=sigma_bv,
                p_dia_entry=float(senal.get("p_dia", 0.25)),
                tag_percentil_entry=str(senal.get("tag_percentil", "P25_ELASTICO")),
                ema900_dist_entry=float(senal.get("ema900_dist_pct", 0.0)),
                ema900_slope_entry=float(senal.get("ema900_slope_pct", 0.0)),
                delta_p_entry=float(senal.get("delta_p_pct", 0.0)),
                lyapunov_entry=float(senal.get("lyapunov_acel_pct", 0.0)),
                hawkes_entry=hawkes_i,
                vpin_entry=float(senal.get("vpin", 0.0)),
                z_btc_entry=float(senal.get("z_btc", 0.0)),
                ofi_btc_entry=float(senal.get("ofi_btc", 0.0)),
                kelly_fraccion_entry=fraccion_kelly,
                grado_senal_entry=grado_senal,
                slot_modo_apertura=slot_modo,
                iceberg_activo=iceberg_req and (qty_llenada > qty_l1),
                house_money_usdt_entry=float(senal.get("house_money_usdt", 0.0)),
                margen_reservado_usdt=margen_real,
            )

            ESTADO_RAM.orden_en_vuelo_symbol = None
            ESTADO_RAM.posiciones_activas[symbol] = posicion_creada
            await TELEMETRIA_TG.confirmar_y_despachar_apertura(
                symbol=symbol,
                qty_llenada=qty_llenada,
                precio_llenado=precio_llenado,
            )
            log_sniper(
                f"[FRANCOTIRADOR OPEN] {symbol} [{side.upper()} | {grado_senal} | {slot_modo}] "
                f"{qty_llenada} @ {precio_llenado} (SL Int: {sl_interno} | SL Bybit: {sl_bybit})"
            )
            return posicion_creada
        except Exception as exc:
            log_sniper(f"[SNIPER ERROR] Excepcion en ejecutar_senal_sniper ({symbol}): {exc}")
            return None
        finally:
            if posicion_creada is None:
                ESTADO_RAM.liberar_margen_atomico(symbol, margen_real)


EJECUTOR_SNIPER: EjecutorSniper = EjecutorSniper()