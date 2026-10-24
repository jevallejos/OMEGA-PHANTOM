#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #07: omega_phantom_v7_sniper.py
SISTEMA: OMEGA-PHANTOM V7.0 (APEX-CHRONOS SINGULARITY)
==============================================================================
Motor de Disparo Zero-REST con:
  1. Cotizacion Top-of-Book Exacta (prioridad FIFO #1 cuando spread == 1 tick).
  2. Recuperacion Instantanea ante Cancelacion Asincrona PostOnly de Bybit V5
     (cuando el libro se mueve 1 tick durante los ~120ms de RTT y Bybit marca
     status='canceled' a los 0.34s): re-cotiza en el nuevo Top-of-Book o
     captura con Limit IOC si la ruptura a favor ya esta confirmada.
  3. Captura Hibrida de Ruptura Confirmada a 1.20s y reserva de margen 5x.
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
    """
    Si el spread es >= 2 ticks y |OFI| >= PENNY_JUMP_OFI_UMBRAL, adelanta 1 tick
    adentro del spread. Si el spread es de 1 tick, se posiciona exactamente en
    best_bid (Long) o best_ask (Short) para garantizar prioridad #1 de llenado.
    """
    t_size = max(1e-8, float(tick_size))
    spread = float(best_ask) - float(best_bid)
    side_norm = str(side).lower()

    if side_norm == "long":
        if spread >= (1.95 * t_size) and abs(float(ofi)) >= cfg.PENNY_JUMP_OFI_UMBRAL:
            candidato = float(best_bid) + t_size
        else:
            candidato = float(best_bid)
        precio_seguro = min(candidato, float(best_ask) - t_size)
        return max(t_size, precio_seguro)

    if spread >= (1.95 * t_size) and abs(float(ofi)) >= cfg.PENNY_JUMP_OFI_UMBRAL:
        candidato = float(best_ask) - t_size
    else:
        candidato = float(best_ask)
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
            "ARB/USDT:USDT": {"tick_size": 0.00001, "step_size": 0.1, "min_qty": 1.0},
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

    async def _ejecutar_cruce_ioc_controlado(
        self,
        symbol: str,
        side: str,
        side_orden: str,
        qty: float,
        precio_base: float,
        tick_sym: float,
    ) -> Tuple[float, float]:
        if self.exchange is None or cfg.es_modo_test():
            return 0.0, precio_base
        tk_now = ESTADO_RAM.ticks_ram.get(symbol)
        if tk_now is None or tk_now.bid <= 0.0 or tk_now.ask <= tk_now.bid:
            return 0.0, precio_base

        # Limita el deslizamiento maximo a 2 ticks respecto al precio_base original
        if side == "short":
            px_ioc = self.redondear_precio(symbol, max(tk_now.bid, precio_base - (2.0 * tick_sym)))
        else:
            px_ioc = self.redondear_precio(symbol, min(tk_now.ask, precio_base + (2.0 * tick_sym)))

        try:
            ord_ioc = await self.exchange.create_order(
                symbol=symbol,
                type="limit",
                side=side_orden,
                amount=qty,
                price=px_ioc,
                params={"timeInForce": "IOC", "reduceOnly": False},
            )
            oid_ioc = str(ord_ioc.get("id", "")) if isinstance(ord_ioc, dict) else ""
            await asyncio.sleep(0.12)
            q_p, px_p = await self._verificar_posicion_abierta_bybit(symbol, px_ioc)
            if q_p > 0.0:
                return q_p, px_p
            if oid_ioc:
                est_ioc = await self._consultar_orden_segura(oid_ioc, symbol)
                f_ioc = float(est_ioc.get("filled", 0.0) or 0.0)
                if f_ioc > 0.0:
                    return f_ioc, float(est_ioc.get("average", 0.0) or px_ioc)
        except Exception:
            pass
        return 0.0, precio_base

    async def _colocar_stop_loss_servidor_bybit(
        self,
        symbol: str,
        side_posicion: str,
        sl_price: float,
    ) -> bool:
        if self.exchange is None:
            return True
        raw_sym = symbol.split("/")[0] + "USDT"
        tk = ESTADO_RAM.ticks_ram.get(symbol)
        sl_seguro = float(sl_price)
        if tk is not None and tk.bid > 0.0 and tk.ask > 0.0 and not cfg.es_modo_test():
            if str(side_posicion).lower() == "long" and sl_seguro >= tk.bid:
                sl_seguro = self.redondear_precio(symbol, tk.bid * (1.0 - cfg.SL_BYBIT_SERVIDOR_PCT))
            elif str(side_posicion).lower() == "short" and sl_seguro <= tk.ask:
                sl_seguro = self.redondear_precio(symbol, tk.ask * (1.0 + cfg.SL_BYBIT_SERVIDOR_PCT))

        try:
            if hasattr(self.exchange, "private_post_v5_position_trading_stop"):
                await self.exchange.private_post_v5_position_trading_stop(
                    {
                        "category": "linear",
                        "symbol": raw_sym,
                        "stopLoss": str(sl_seguro),
                        "slTriggerBy": "MarkPrice",
                        "positionIdx": 0,
                    }
                )
                return True
            if hasattr(self.exchange, "set_trading_stop"):
                await self.exchange.set_trading_stop(
                    symbol=symbol,
                    stopLoss=sl_seguro,
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
        palanca_margen = float(cfg.APALANCAMIENTO_BASE) if cfg.es_modo_test() else 5.0
        margen_real = round(nocional_real / palanca_margen, 4)
        if not cfg.es_modo_test() and margen_real > ESTADO_RAM.margen_libre_usdt * 0.92:
            margen_real = round(max(cfg.MARGEN_MINIMO_OPERACION_USDT, ESTADO_RAM.margen_libre_usdt * 0.88), 4)

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

            nocional_l1 = round(qty_l1 * precio_quote, 2)
            log_sniper(
                f"[FRANCOTIRADOR ORDEN] {order_id_l1} en {symbol} [{side.upper()}]: "
                f"{qty_l1} @ {precio_quote} (nocional ~{nocional_l1:.2f} USDT, {int(palanca_margen)}x, "
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
                qty=qty_l1,
                entry_price=precio_quote,
                nocional_usdt=nocional_l1,
                apalancamiento=int(palanca_margen),
                fraccion_kelly=fraccion_kelly,
                z_score=z_score,
                ofi=ofi,
                hurst=hurst,
                rtt_ms=rtt_ms,
                grado_senal=grado_senal,
                slot_modo=slot_modo,
            )

            ttl_max = float(cfg.TTL_ORDEN_ENTRADA_SEG)
            paso_poll = 0.10 if cfg.es_modo_test() else 0.15
            t_inicio_cola = time.time()
            qty_llenada = 0.0
            precio_llenado = precio_quote
            precio_quote_inicial = precio_quote
            repegs_realizados = 0
            tick_sym = float(self.obtener_precision(symbol)["tick_size"])

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

                tk_now = ESTADO_RAM.ticks_ram.get(symbol)
                edad_cola = time.time() - t_inicio_cola

                if status in ("canceled", "cancelled", "rejected", "expired"):
                    qty_llenada = filled
                    ya_cancelada_l1 = True
                    if filled > 0.0 and avg_px > 0.0:
                        precio_llenado = avg_px
                        break

                    # Si Bybit cancelo asincronamente el PostOnly (ej. a los 0.34s en ARB) porque el
                    # libro se movio 1 tick durante el RTT, recuperamos la orden de inmediato:
                    if (
                        not cfg.es_modo_test()
                        and repegs_realizados < 2
                        and tk_now is not None
                        and tk_now.bid > 0.0
                        and tk_now.ask > tk_now.bid
                        and tk_now.hurst <= 0.485
                    ):
                        repegs_realizados += 1
                        sigue_fuerte = (
                            (side == "short" and tk_now.ofi_l1_l5 <= -0.32)
                            or (side == "long" and tk_now.ofi_l1_l5 >= 0.32)
                        )
                        if sigue_fuerte:
                            nuevo_px = self.calcular_cotizacion_penny_jump(
                                symbol=symbol,
                                side=side,
                                best_bid=tk_now.bid,
                                best_ask=tk_now.ask,
                                ofi=tk_now.ofi_l1_l5,
                                sigma_bv=tk_now.volatilidad_local,
                                hawkes_i=tk_now.hawkes_intensidad,
                            )
                            if abs(nuevo_px - precio_quote_inicial) <= (tick_sym * 3.0):
                                nuevo_id, _ = await self._colocar_orden_limit_postonly(
                                    symbol=symbol,
                                    side_orden=side_orden,
                                    qty=qty_l1,
                                    precio=nuevo_px,
                                )
                                if nuevo_id:
                                    order_id_l1 = nuevo_id
                                    precio_quote = nuevo_px
                                    ya_cancelada_l1 = False
                                    continue
                            q_ioc, px_ioc = await self._ejecutar_cruce_ioc_controlado(
                                symbol, side, side_orden, qty_l1, precio_quote_inicial, tick_sym
                            )
                            if q_ioc > 0.0:
                                qty_llenada = q_ioc
                                precio_llenado = px_ioc
                    break

                if tk_now is not None:
                    umbral_abort = (
                        abs(cfg.OFI_ABORTAR_COLA_UMBRAL)
                        if (cfg.es_modo_test() or edad_cola >= 0.90)
                        else 0.55
                    )
                    if side == "long" and tk_now.ofi_l1_l5 <= -umbral_abort:
                        try:
                            await self.exchange.cancel_order(order_id_l1, symbol)
                        except Exception:
                            pass
                        ya_cancelada_l1 = True
                        break
                    if side == "short" and tk_now.ofi_l1_l5 >= umbral_abort:
                        try:
                            await self.exchange.cancel_order(order_id_l1, symbol)
                        except Exception:
                            pass
                        ya_cancelada_l1 = True
                        break

                    if not cfg.es_modo_test() and edad_cola >= 0.80 and tk_now.hurst > 0.498:
                        try:
                            await self.exchange.cancel_order(order_id_l1, symbol)
                        except Exception:
                            pass
                        ya_cancelada_l1 = True
                        break

                    # Captura Hibrida de Ruptura Confirmada a 1.20s
                    if (
                        not cfg.es_modo_test()
                        and repegs_realizados == 0
                        and filled <= 0.0
                        and edad_cola >= 1.20
                        and tk_now.bid > 0.0
                        and tk_now.ask > tk_now.bid
                        and tk_now.hurst <= 0.482
                    ):
                        repegs_realizados += 1
                        rompio_short_a_favor = (
                            side == "short"
                            and (precio_quote_inicial - tk_now.bid) >= (tick_sym * 0.90)
                            and (precio_quote_inicial - tk_now.bid) <= (tick_sym * 3.00)
                            and tk_now.ofi_l1_l5 <= -0.34
                        )
                        rompio_long_a_favor = (
                            side == "long"
                            and (tk_now.ask - precio_quote_inicial) >= (tick_sym * 0.90)
                            and (tk_now.ask - precio_quote_inicial) <= (tick_sym * 3.00)
                            and tk_now.ofi_l1_l5 >= 0.34
                        )
                        if rompio_short_a_favor or rompio_long_a_favor:
                            try:
                                await self.exchange.cancel_order(order_id_l1, symbol)
                            except Exception:
                                pass
                            ya_cancelada_l1 = True
                            q_ioc, px_ioc = await self._ejecutar_cruce_ioc_controlado(
                                symbol, side, side_orden, qty_l1, precio_quote_inicial, tick_sym
                            )
                            if q_ioc > 0.0:
                                qty_llenada = q_ioc
                                precio_llenado = px_ioc
                            break

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

                q_pos, px_pos = await self._verificar_posicion_abierta_bybit(symbol, precio_quote)
                if q_pos > 0.0:
                    qty_llenada = q_pos
                    precio_llenado = px_pos
                else:
                    TELEMETRIA_TG.descartar_apertura_no_llenada(symbol)
                    edad_real = time.time() - t_inicio_cola
                    log_sniper(
                        f"[COLA MOALLEMI-YUAN] Orden en {symbol} no llenada en {edad_real:.1f}s (Cero Re-Quote): margen liberado."
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