#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #09: omega_phantom_v7_main.py
SISTEMA: OMEGA-PHANTOM V7.0 (APEX-CHRONOS SINGULARITY)
==============================================================================
Kernel Orquestador Asincrono sobre uvloop (Linux) / asyncio (Windows):
  1. Cerrojo Fisico de Instancia Unica (.omega_phantom_v7.lock) con verificacion
     de PID vivo en el kernel.
  2. Reconciliacion Inteligente de Arranque en Bybit UTA: adopta posiciones
     abiertas sin warnings de array en V5, cancela ordenes huerfanas y
     sincroniza Paridad Exacta 1:1 (SCAR-LOCK-04).
  3. Auditoria de Lotes Minimos Indivisibles por simbolo.
  4. Bucle de Ingesta Hibrida a 50 Hz (20 ms) L2 + publicTrade, Vigilancia
     Multi-Slot de Posiciones, Enjambre Tri-Cortex LPU y Hot-Reload OOS.
==============================================================================
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import signal
import sys
import time
from typing import Any, Dict, List, Optional

import omega_phantom_v7_config as cfg
from omega_phantom_v7_gestor import GESTOR_POSICIONES
from omega_phantom_v7_radar import RADAR, calcular_percentil_intradia_utc
from omega_phantom_v7_ram import ESTADO_RAM, PosicionActiva, log_sniper
from omega_phantom_v7_sniper import EJECUTOR_SNIPER
from omega_phantom_v7_stats import CAJA_NEGRA
from omega_phantom_v7_tricortex import ESCUDO_TRICORTEX

if sys.platform != "win32":
    try:
        import uvloop
        uvloop.install()
    except Exception:
        pass


class CerrojoInstanciaUnica:
    """Garantiza que solo un proceso de OMEGA-PHANTOM V7.0 opere sobre la cuenta."""

    def __init__(self, ruta_lock: Optional[pathlib.Path] = None) -> None:
        nombre = cfg.ARCHIVO_LOCK_TEST if cfg.es_modo_test() else cfg.ARCHIVO_LOCK_PRODUCCION
        self.ruta_lock: pathlib.Path = ruta_lock or (cfg.ROOT_DIR / nombre)
        self.adquirido: bool = False

    @staticmethod
    def _pid_esta_vivo(pid: int) -> bool:
        if pid <= 0:
            return False
        if pid == os.getpid():
            return True
        try:
            os.kill(pid, 0)
            return True
        except PermissionError:
            return True
        except OSError:
            return False

    def adquirir(self) -> bool:
        if self.ruta_lock.exists():
            try:
                lineas = self.ruta_lock.read_text(encoding="utf-8").splitlines()
                primera = lineas[0].strip() if lineas else ""
                pid_antiguo = int(primera) if primera else -1
                if self._pid_esta_vivo(pid_antiguo) and pid_antiguo != os.getpid():
                    log_sniper(
                        f"[LOCK ERROR] Instancia activa detectada con PID {pid_antiguo} en {self.ruta_lock.name}."
                    )
                    return False
            except Exception:
                pass

        try:
            self.ruta_lock.write_text(f"{os.getpid()}\n", encoding="utf-8")
            self.adquirido = True
            return True
        except Exception as exc:
            log_sniper(f"[LOCK ERROR] No se pudo escribir {self.ruta_lock.name}: {exc}")
            return False

    def liberar(self) -> None:
        if not self.adquirido:
            return
        try:
            if self.ruta_lock.exists():
                lineas = self.ruta_lock.read_text(encoding="utf-8").splitlines()
                primera = lineas[0].strip() if lineas else ""
                if primera == str(os.getpid()):
                    self.ruta_lock.unlink(missing_ok=True)
        except Exception:
            pass
        self.adquirido = False


async def reconciliar_posiciones_arranque(exchange: Any) -> Dict[str, Any]:
    """
    Sincroniza el estado real de Bybit UTA al iniciar el demonio:
      - Lee el patrimonio USDT total y libre (Paridad 1:1 SCAR-LOCK-04).
      - Adopta cualquier posicion abierta en ESTADO_RAM.posiciones_activas.
      - Cancela ordenes limite huerfanas en simbolos sin posicion abierta.
    """
    resultado = {"balance_uta_usdt": 0.0, "adoptadas": 0, "ordenes_canceladas": 0}
    if exchange is None:
        return resultado

    try:
        bal = await exchange.fetch_balance()
        usdt_info = bal.get("USDT", {}) if isinstance(bal, dict) else {}
        total_usdt = float(
            usdt_info.get("total", 0.0)
            or bal.get("total", {}).get("USDT", 0.0)
            or 0.0
        )
        free_usdt = float(
            usdt_info.get("free", 0.0)
            or bal.get("free", {}).get("USDT", 0.0)
            or total_usdt
        )
        if total_usdt > 0.0:
            CAJA_NEGRA.sincronizar_paridad_uta(total_usdt)
            ESTADO_RAM.sincronizar_balance_uta(total_usdt, free_usdt)
            resultado["balance_uta_usdt"] = round(total_usdt, 4)
    except Exception as exc:
        log_sniper(f"[RECONCILIACION WARN] Fallo leyendo balance UTA: {exc}")

    simbolos_con_posicion: set[str] = set()
    try:
        try:
            posiciones = await exchange.fetch_positions(
                None, {"category": "linear", "settleCoin": "USDT"}
            )
        except TypeError:
            posiciones = await exchange.fetch_positions(list(cfg.PARES_CAMPEONES_ALFA))

        for p in posiciones or []:
            contracts = float(p.get("contracts", 0.0) or p.get("info", {}).get("size", 0.0) or 0.0)
            if contracts <= 0.0:
                continue
            sym = str(p.get("symbol", ""))
            if not sym or sym not in cfg.PARES_CAMPEONES_ALFA:
                continue
            side = str(p.get("side", "long")).lower()
            entry_px = float(p.get("entryPrice", 0.0) or p.get("info", {}).get("avgPrice", 0.0) or 0.0)
            if entry_px <= 0.0:
                continue

            if side == "long":
                sl_int = EJECUTOR_SNIPER.redondear_precio(sym, entry_px * (1.0 - cfg.SL_INTERNO_PCT))
                sl_byb = EJECUTOR_SNIPER.redondear_precio(sym, entry_px * (1.0 - cfg.SL_BYBIT_SERVIDOR_PCT))
            else:
                sl_int = EJECUTOR_SNIPER.redondear_precio(sym, entry_px * (1.0 + cfg.SL_INTERNO_PCT))
                sl_byb = EJECUTOR_SNIPER.redondear_precio(sym, entry_px * (1.0 + cfg.SL_BYBIT_SERVIDOR_PCT))

            nocional = contracts * entry_px
            margen_est = round(nocional / float(cfg.APALANCAMIENTO_BASE), 4)
            pos_adoptada = PosicionActiva(
                symbol=sym,
                side=side,
                qty_inicial=contracts,
                qty_actual=contracts,
                entry_price=entry_px,
                ts_apertura=time.time(),
                sl_interno_price=sl_int,
                sl_bybit_price=sl_byb,
                margen_reservado_usdt=margen_est,
            )
            ESTADO_RAM.posiciones_activas[sym] = pos_adoptada
            ESTADO_RAM.slot_ocupado = True
            simbolos_con_posicion.add(sym)
            resultado["adoptadas"] += 1
            log_sniper(
                f"[RECONCILIACION UTA] Posicion adoptada en {sym} [{side.upper()}]: {contracts} @ {entry_px}"
            )
    except Exception as exc:
        log_sniper(f"[RECONCILIACION WARN] Fallo leyendo posiciones: {exc}")

    for sym in cfg.PARES_CAMPEONES_ALFA:
        if sym in simbolos_con_posicion:
            continue
        try:
            ordenes = await exchange.fetch_open_orders(sym)
            for o in ordenes or []:
                oid = str(o.get("id", ""))
                if oid:
                    await exchange.cancel_order(oid, sym)
                    resultado["ordenes_canceladas"] += 1
        except Exception:
            pass

    return resultado


async def auditar_y_filtrar_lotes_minimos(exchange: Any) -> List[str]:
    """
    Audita los mercados de Bybit al arrancar y excluye en ESTADO_RAM cualquier
    par cuyo lote minimo supere el nocional maximo permitido para su clase.
    """
    excluidos: List[str] = []
    if exchange is None:
        return excluidos

    try:
        mercados = await exchange.load_markets()
        for sym in cfg.PARES_CAMPEONES_ALFA:
            m = mercados.get(sym)
            if not isinstance(m, dict):
                continue

            limits = m.get("limits", {})
            prec = m.get("precision", {})
            min_qty = float(limits.get("amount", {}).get("min", 0.0) or 0.0)
            tick_size = float(prec.get("price", 0.0001) or 0.0001)
            step_size = float(prec.get("amount", 0.1) or 0.1)

            if tick_size > 0.0 and step_size > 0.0:
                EJECUTOR_SNIPER.precisiones_locales[sym] = {
                    "tick_size": tick_size,
                    "step_size": step_size,
                    "min_qty": max(min_qty, step_size),
                }

            precio_ref = float(m.get("info", {}).get("lastPrice", 0.0) or 0.0)
            if precio_ref <= 0.0:
                tk = ESTADO_RAM.ticks_ram.get(sym)
                precio_ref = tk.last if (tk and tk.last > 0.0) else 1.0

            nocional_minimo = max(min_qty, step_size) * precio_ref
            params_clase = cfg.obtener_parametros_clase(
                sym, patrimonio_actual_usdt=ESTADO_RAM.patrimonio_total_usdt
            )
            tope_clase = float(params_clase["nocional_max_usdt"])

            if nocional_minimo > tope_clase:
                ESTADO_RAM.pares_excluidos_lote.add(sym)
                excluidos.append(sym)
                log_sniper(
                    f"[FILTRO LOTE] {sym} excluido: nocional minimo {nocional_minimo:.2f} USDT > tope {tope_clase:.2f} USDT."
                )
    except Exception as exc:
        log_sniper(f"[FILTRO LOTE WARN] {exc}")

    return excluidos


class MotorOmegaPhantomV7:
    """Kernel central de ejecucion continua 24/7 para el desafio de 48 horas."""

    def __init__(self) -> None:
        self.cerrojo: CerrojoInstanciaUnica = CerrojoInstanciaUnica()
        self.exchange: Optional[Any] = None
        self.detener_evento: asyncio.Event = asyncio.Event()

    async def _inicializar_exchange_bybit(self) -> Any:
        import ccxt.async_support as ccxt_async

        opciones = {
            "apiKey": cfg.BYBIT_API_KEY,
            "secret": cfg.BYBIT_API_SECRET,
            "enableRateLimit": False,
            "options": {"defaultType": "swap", "adjustForTimeDifference": True},
        }
        ex = ccxt_async.bybit(opciones)
        if cfg.MODO_PAPER:
            ex.set_sandbox_mode(True)
        return ex

    async def _ingerir_simbolo_50hz(self, symbol: str) -> None:
        if self.exchange is None or symbol in ESTADO_RAM.pares_excluidos_lote:
            return
        if symbol == "INJ/USDT:USDT" and not cfg.es_modo_test():
            return
        try:
            ob = await self.exchange.fetch_order_book(symbol, limit=10)
            bids = ob.get("bids", [])
            asks = ob.get("asks", [])
            if not bids or not asks:
                return
            mid = (float(bids[0][0]) + float(asks[0][0])) * 0.5
            senal = RADAR.procesar_libro_l2(
                symbol=symbol,
                bids=bids,
                asks=asks,
                last_price=mid,
            )
            if senal is not None:
                log_sniper(
                    f"[RADAR 50HZ] {symbol} [{senal['side'].upper()} | {senal['grado_senal']} | {senal['slot_modo']}] "
                    f"Z={senal['z_score']:+.2f} | dp={senal['delta_p_pct']*100:+.2f}% | EMA900={senal['ema900_dist_pct']*100:+.2f}% | "
                    f"OFI={senal['ofi']:+.2f} | H={senal['hurst']:.3f} -> DISPARO APROBADO"
                )
                await EJECUTOR_SNIPER.ejecutar_senal_sniper(senal)
        except Exception:
            pass

    async def _bucle_radar_50hz(self) -> None:
        todos_simbolos = (cfg.SIMBOLO_CENTINELA_MACRO,) + tuple(cfg.PARES_CAMPEONES_ALFA)
        while not self.detener_evento.is_set():
            t0 = time.perf_counter()
            try:
                await asyncio.gather(*(self._ingerir_simbolo_50hz(sym) for sym in todos_simbolos))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log_sniper(f"[RADAR LOOP WARN] {exc}")

            transcurrido = time.perf_counter() - t0
            pausa = max(0.020, cfg.CADENCIA_RADAR_SEG - transcurrido)
            await asyncio.sleep(pausa)

    async def _bucle_paridad_y_hot_reload(self) -> None:
        ciclo = 0
        while not self.detener_evento.is_set():
            try:
                res_oos = cfg.recargar_calibracion_oos_si_cambio()
                if res_oos.get("recargado"):
                    log_sniper(
                        f"[HOT-RELOAD OOS] Parametros actualizados en caliente: {res_oos.get('aplicados')}"
                    )

                if self.exchange is not None and not ESTADO_RAM.posiciones_activas:
                    bal = await self.exchange.fetch_balance()
                    usdt_info = bal.get("USDT", {}) if isinstance(bal, dict) else {}
                    tot = float(
                        usdt_info.get("total", 0.0)
                        or bal.get("total", {}).get("USDT", 0.0)
                        or 0.0
                    )
                    if tot > 0.0:
                        CAJA_NEGRA.sincronizar_paridad_uta(tot)

                ciclo += 1
                if ciclo % 2 == 0:
                    tk_z = ESTADO_RAM.ticks_ram.get("ZEREBRO/USDT:USDT")
                    tk_w = ESTADO_RAM.ticks_ram.get("WAL/USDT:USDT")
                    tk_a = ESTADO_RAM.ticks_ram.get("ARB/USDT:USDT")
                    p_dia, tag_p, _ = calcular_percentil_intradia_utc(
                        sigma_bv=tk_z.volatilidad_local if tk_z else 0.0006
                    )
                    if tk_z and tk_w and tk_a:
                        log_sniper(
                            f"[PULSO 50HZ {tag_p} ({p_dia:.2f})] "
                            f"ZEREBRO(Z={tk_z.z_score:+.2f}, dp={tk_z.delta_p_pct*100:+.2f}%, EMA={tk_z.ema900_dist_pct*100:+.2f}%, OFI={tk_z.ofi_l1_l5:+.2f}, H={tk_z.hurst:.2f}) | "
                            f"WAL(Z={tk_w.z_score:+.2f}, OFI={tk_w.ofi_l1_l5:+.2f}) | "
                            f"ARB(Z={tk_a.z_score:+.2f}, OFI={tk_a.ofi_l1_l5:+.2f})"
                        )
                if ciclo % 10 == 0:
                    CAJA_NEGRA.imprimir_hud_caja_negra()
            except asyncio.CancelledError:
                break
            except Exception:
                pass
            await asyncio.sleep(30.0)

    async def ejecutar(self) -> int:
        if not self.cerrojo.adquirir():
            return 1

        log_sniper("=" * 78)
        log_sniper(f" INICIANDO KERNEL {cfg.NOMBRE_ESTRATEGIA} -- PID: {os.getpid()}")
        log_sniper(f" ARQUITECTURA: {cfg.ESTRATEGIA_MATEMATICA}")
        log_sniper("=" * 78)

        try:
            self.exchange = await self._inicializar_exchange_bybit()
            EJECUTOR_SNIPER.configurar_exchange(self.exchange)
            GESTOR_POSICIONES.configurar_exchange(self.exchange)

            await auditar_y_filtrar_lotes_minimos(self.exchange)
            rec = await reconciliar_posiciones_arranque(self.exchange)
            log_sniper(
                f"[ARRANQUE UTA 1:1] Balance Real Bybit: {rec['balance_uta_usdt']:.4f} USDT | "
                f"Posiciones Adoptadas: {rec['adoptadas']} | Ordenes Limpiadas: {rec['ordenes_canceladas']}"
            )
            CAJA_NEGRA.imprimir_hud_caja_negra()

            tareas = [
                asyncio.create_task(self._bucle_radar_50hz(), name="radar_50hz"),
                asyncio.create_task(GESTOR_POSICIONES.ciclo_vigilancia_posiciones(), name="gestor_pos"),
                asyncio.create_task(ESCUDO_TRICORTEX.ciclo_groq_regimen(), name="cortex_1_groq"),
                asyncio.create_task(ESCUDO_TRICORTEX.ciclo_gemini_sizing(), name="cortex_2_sizing"),
                asyncio.create_task(ESCUDO_TRICORTEX.ciclo_nvidia_preflight(), name="cortex_3_nvidia"),
                asyncio.create_task(self._bucle_paridad_y_hot_reload(), name="paridad_hot_reload"),
            ]

            await self.detener_evento.wait()
            for t in tareas:
                t.cancel()
            await asyncio.gather(*tareas, return_exceptions=True)
            return 0
        finally:
            if self.exchange is not None:
                try:
                    await self.exchange.close()
                except Exception:
                    pass
            self.cerrojo.liberar()
            log_sniper("[SHUTDOWN] Kernel OMEGA-PHANTOM V7.0 detenido limpiamente.")


def main() -> int:
    motor = MotorOmegaPhantomV7()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, motor.detener_evento.set)
        except NotImplementedError:
            pass

    try:
        return loop.run_until_complete(motor.ejecutar())
    except KeyboardInterrupt:
        motor.detener_evento.set()
        return 0
    finally:
        loop.close()


if __name__ == "__main__":
    sys.exit(main())